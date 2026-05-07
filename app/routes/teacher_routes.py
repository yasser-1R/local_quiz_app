"""
Teacher pages + teacher session-control API.
URLs are now codeless — the current session is resolved on the server.
"""
import io
import csv
import re
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from ..config import TEACHER_PASSWORD, TEMPLATES_DIR, APP_TITLE
from ..services import (
    analytics_service,
    quiz_service,
    session_service,
    player_service,
    scoring_service,
)


router = APIRouter(prefix="/teacher", tags=["teacher"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def require_teacher(teacher_auth: str | None = Cookie(default=None)):
    if teacher_auth != TEACHER_PASSWORD:
        raise HTTPException(status_code=401, detail="teacher login required")
    return True


# ---------- login ----------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "teacher/login.html",
        {"app_title": APP_TITLE, "error": None},
    )


@router.post("/login")
async def do_login(password: str = Form(...)):
    if password != TEACHER_PASSWORD:
        return RedirectResponse(url="/teacher/login?bad=1", status_code=303)
    resp = RedirectResponse(url="/teacher", status_code=303)
    resp.set_cookie("teacher_auth", TEACHER_PASSWORD, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/teacher/login", status_code=303)
    resp.delete_cookie("teacher_auth")
    return resp


# ---------- dashboard ----------
@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, teacher_auth: str | None = Cookie(default=None)):
    if teacher_auth != TEACHER_PASSWORD:
        return RedirectResponse(url="/teacher/login", status_code=303)
    quizzes = quiz_service.list_quizzes()
    current = session_service.get_current_session()
    waiting_count = len(player_service.list_players(current["id"])) if current else 0
    return templates.TemplateResponse(
        request,
        "teacher/dashboard.html",
        {
            "app_title": APP_TITLE,
            "quizzes": quizzes,
            "current": current,
            "waiting_count": waiting_count,
        },
    )


# ---------- teacher reports ----------
@router.get("/reports", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def reports_index(request: Request):
    sessions = analytics_service.list_finished_sessions()
    return templates.TemplateResponse(
        request,
        "teacher/reports.html",
        {
            "app_title": APP_TITLE,
            "sessions": sessions,
        },
    )


@router.get("/reports/{session_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_teacher)])
async def report_detail(request: Request, session_id: int):
    report = analytics_service.build_session_report(session_id)
    if report is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "teacher/report_detail.html",
        {
            "app_title": APP_TITLE,
            "report": report,
        },
    )


@router.get("/reports/{session_id}/export.csv", dependencies=[Depends(require_teacher)])
async def report_export_csv(session_id: int):
    report = analytics_service.build_session_report(session_id)
    if report is None:
        raise HTTPException(status_code=404)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Rapport de quiz"])
    writer.writerow(["Quiz", report["quiz"]["title"]])
    writer.writerow(["Session", report["session"]["session_code"]])
    writer.writerow(["Debut", report["session"].get("started_at") or ""])
    writer.writerow(["Fin", report["session"].get("ended_at") or ""])
    writer.writerow([])

    writer.writerow(["Vue d'ensemble"])
    writer.writerow(["Eleves", report["overview"]["player_count"]])
    writer.writerow(["Questions", report["overview"]["question_count"]])
    writer.writerow(["Taux de reussite moyen", f"{report['overview']['average_success_rate']}%"])
    writer.writerow(["Score moyen", report["overview"]["average_score"]])
    writer.writerow(["Score minimum", report["overview"]["min_score"]])
    writer.writerow(["Score maximum", report["overview"]["max_score"]])
    writer.writerow([])

    writer.writerow(["Vue par question"])
    writer.writerow([
        "Question", "Texte", "Taux de reussite", "Bonnes reponses",
        "Reponses", "Sans reponse", "Temps moyen (s)",
    ])
    for q in report["questions"]:
        writer.writerow([
            q["number"], q["text"], f"{q['success_rate']}%",
            q["correct_count"], q["answer_count"], q["unanswered_count"],
            q["avg_response_seconds"] if q["avg_response_seconds"] is not None else "",
        ])
    writer.writerow([])

    writer.writerow(["Repartition des reponses"])
    writer.writerow(["Question", "Choix", "Nombre", "Pourcentage", "Correct"])
    for q in report["questions"]:
        for choice in q["distribution"]:
            writer.writerow([
                q["number"], choice["choice_text"],
                choice["count"], f"{choice['percent']}%",
                "oui" if choice["is_correct"] else "non",
            ])
    writer.writerow([])

    writer.writerow(["Vue par eleve"])
    writer.writerow([
        "Eleve", "Score total", "Taux de reussite", "Bonnes reponses", "Temps moyen (s)",
    ])
    for student in report["students"]:
        writer.writerow([
            student["nickname"], student["total_score"],
            f"{student['success_rate']}%", student["correct_answers"],
            student["avg_response_seconds"] if student["avg_response_seconds"] is not None else "",
        ])
    writer.writerow([])

    writer.writerow(["Details par eleve"])
    writer.writerow(["Eleve", "Question", "Resultat", "Reponse", "Temps (s)", "Points"])
    for student in report["students"]:
        for row in student["questions"]:
            writer.writerow([
                student["nickname"], row["number"],
                "reussie" if row["is_correct"] else "ratee",
                row["selected_choice"],
                row["response_seconds"] if row["response_seconds"] is not None else "",
                row["points"],
            ])

    quiz_slug = _filename_slug(report["quiz"]["title"])
    timestamp = _filename_slug(report["session"].get("ended_at") or "session")
    filename = f"rapport_{quiz_slug}_{timestamp}.csv"
    return StreamingResponse(
        iter(["﻿" + output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _filename_slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "quiz"


# ---------- quiz create / edit ----------
@router.get("/quiz/new", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def new_quiz_page(request: Request):
    return templates.TemplateResponse(
        request,
        "teacher/create_quiz.html",
        {"app_title": APP_TITLE, "quiz": None},
    )


@router.get("/quiz/{quiz_id}/edit", response_class=HTMLResponse,
            dependencies=[Depends(require_teacher)])
async def edit_quiz_page(request: Request, quiz_id: int):
    quiz = quiz_service.get_quiz(quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "teacher/edit_quiz.html",
        {"app_title": APP_TITLE, "quiz": quiz},
    )


# ---------- single-room session pages ----------
@router.get("/lobby", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def lobby(request: Request):
    session = session_service.ensure_current_session()
    quiz = (
        quiz_service.get_quiz(session["quiz_id"])
        if session.get("quiz_id") is not None
        else None
    )
    players = player_service.list_players(session["id"])

    return templates.TemplateResponse(
        request,
        "teacher/lobby.html",
        {
            "app_title": APP_TITLE,
            "session": session,
            "quiz": quiz,
            "players": players,
        },
    )


@router.get("/control", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def control(request: Request):
    session = session_service.get_current_session()
    if session is None or session.get("quiz_id") is None:
        return RedirectResponse(url="/teacher", status_code=303)
    quiz = quiz_service.get_quiz(session["quiz_id"])
    players = player_service.list_players(session["id"])
    return templates.TemplateResponse(
        request,
        "teacher/control.html",
        {
            "app_title": APP_TITLE,
            "session": session,
            "quiz": quiz,
            "players": players,
        },
    )


@router.get("/results", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def results(request: Request):
    session = session_service.latest_finished_session()
    if session is None:
        return RedirectResponse(url="/teacher", status_code=303)
    board = scoring_service.leaderboard(session["id"])
    quiz = quiz_service.get_quiz(session["quiz_id"]) if session.get("quiz_id") else None
    return templates.TemplateResponse(
        request,
        "teacher/results.html",
        {
            "app_title": APP_TITLE,
            "session": session,
            "quiz": quiz,
            "leaderboard": board,
        },
    )
