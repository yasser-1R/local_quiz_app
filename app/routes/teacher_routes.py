"""
Teacher pages + teacher session-control API.
URLs are now codeless — the current session is resolved on the server.
"""
import io
import csv
import re
try:
    import xlsxwriter
    _HAS_XLSX = True
except ImportError:
    _HAS_XLSX = False
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from ..config import TEACHER_PASSWORD, TEMPLATES_DIR, APP_TITLE, LEADERBOARD_TOP_N
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


# ══════════════════════════════════════════════════════════════════
#  REPORTS  (session / quiz / student)
# ══════════════════════════════════════════════════════════════════

@router.get("/reports", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def reports_index(request: Request):
    sessions  = analytics_service.list_finished_sessions()
    quizzes   = analytics_service.list_quizzes_with_stats()
    students  = analytics_service.list_students_with_stats()
    return templates.TemplateResponse(
        request,
        "teacher/reports.html",
        {
            "app_title": APP_TITLE,
            "sessions":  sessions,
            "quizzes":   quizzes,
            "students":  students,
        },
    )


# ─── Quiz-level report ───────────────────────────────────────────

@router.get("/reports/quiz/{quiz_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_teacher)])
async def report_quiz(request: Request, quiz_id: int):
    report = analytics_service.build_quiz_report(quiz_id)
    if report is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "teacher/report_quiz.html",
        {"app_title": APP_TITLE, "report": report},
    )


@router.get("/reports/quiz/{quiz_id}/export.xlsx",
            dependencies=[Depends(require_teacher)])
async def report_quiz_xlsx(quiz_id: int):
    if not _HAS_XLSX:
        raise HTTPException(500, "xlsxwriter not installed")
    report = analytics_service.build_quiz_report(quiz_id)
    if report is None:
        raise HTTPException(status_code=404)

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {"in_memory": True})

    bold    = wb.add_format({"bold": True, "font_size": 11})
    header  = wb.add_format({"bold": True, "bg_color": "#6366f1", "font_color": "#FFFFFF",
                              "border": 1, "font_size": 11, "align": "center"})
    title_f = wb.add_format({"bold": True, "font_size": 14, "font_color": "#4f46e5"})
    pct_f   = wb.add_format({"num_format": '0.0"%"', "border": 1})
    num_f   = wb.add_format({"num_format": "#,##0", "border": 1})
    text_f  = wb.add_format({"border": 1})
    good_f  = wb.add_format({"bg_color": "#dcfce7", "border": 1})
    bad_f   = wb.add_format({"bg_color": "#fee2e2", "border": 1})
    sub_h   = wb.add_format({"bold": True, "bg_color": "#e0e7ff", "border": 1})

    quiz  = report["quiz"]
    ov    = report["overview"]
    sess  = report["sessions"]
    qs    = report["questions"]

    # Sheet 1 – Summary
    ws1 = wb.add_worksheet("Résumé")
    ws1.set_column("A:A", 28); ws1.set_column("B:B", 18); ws1.set_column("C:H", 14)

    ws1.write("A1", f"Rapport quiz — {quiz['title']}", title_f)
    ws1.write("A2", f"Catégorie: {quiz.get('category') or '—'}")
    ws1.write("A3", f"Questions: {len(quiz['questions'])}")

    ws1.write("A5", "Vue d'ensemble", bold)
    kpis = [
        ("Sessions jouées",   ov["total_sessions"]),
        ("Joueurs au total",  ov["total_players"]),
        ("Taux réussite moy.", f"{ov['avg_success_rate']}%"),
    ]
    for i, (k, v) in enumerate(kpis):
        ws1.write(5 + i, 0, k, sub_h); ws1.write(5 + i, 1, v, text_f)

    # Sessions trend table
    ws1.write("A10", "Session", header); ws1.write("B10", "Date", header)
    ws1.write("C10", "Joueurs", header); ws1.write("D10", "Taux réussite (%)", header)
    ws1.write("E10", "Score moyen", header)
    for i, s in enumerate(sess):
        r = 10 + i
        ws1.write(r, 0, s["session_code"], text_f)
        ws1.write(r, 1, (s["started_at"] or "")[:10], text_f)
        ws1.write(r, 2, s["player_count"], num_f)
        ws1.write(r, 3, s["success_rate"], pct_f)
        ws1.write(r, 4, s["avg_score"], num_f)

    if sess:
        ch = wb.add_chart({"type": "line"})
        ch.add_series({
            "name": "Taux de réussite (%)",
            "categories": ["Résumé", 10, 0, 9 + len(sess), 0],
            "values":     ["Résumé", 10, 3, 9 + len(sess), 3],
            "marker": {"type": "circle"}, "line": {"color": "#6366f1", "width": 2.5},
            "data_labels": {"value": True, "num_format": '0"%"'},
        })
        ch.set_title({"name": "Évolution du taux de réussite par session"})
        ch.set_y_axis({"name": "Réussite (%)", "min": 0, "max": 100})
        ch.set_size({"width": 560, "height": 300}); ch.set_style(10)
        ws1.insert_chart("G5", ch)

    # Sheet 2 – Questions
    ws2 = wb.add_worksheet("Questions")
    ws2.set_column("A:A", 50); ws2.set_column("B:E", 16)

    ws2.write("A1", "Difficulté par question", title_f)
    ws2.write("A3", "Question", header); ws2.write("B3", "Réponses", header)
    ws2.write("C3", "Correctes", header); ws2.write("D3", "Taux réussite (%)", header)
    ws2.write("E3", "Tps moyen (s)", header)

    for i, q in enumerate(qs):
        r = 3 + i
        fmt = good_f if q["success_rate"] >= 60 else (bad_f if q["success_rate"] < 40 else text_f)
        ws2.write(r, 0, q["text"], text_f)
        ws2.write(r, 1, q["total_answers"], num_f)
        ws2.write(r, 2, q["correct_count"], num_f)
        ws2.write(r, 3, q["success_rate"], pct_f)
        ws2.write(r, 4, q["avg_response_seconds"] or 0, num_f)

    if qs:
        ch2 = wb.add_chart({"type": "bar"})
        ch2.add_series({
            "name": "Taux de réussite (%)",
            "categories": ["Questions", 3, 0, 2 + len(qs), 0],
            "values":     ["Questions", 3, 3, 2 + len(qs), 3],
            "fill": {"color": "#6366f1"},
            "data_labels": {"value": True, "num_format": '0"%"'},
        })
        ch2.set_title({"name": "Difficulté par question"})
        ch2.set_x_axis({"name": "Réussite (%)", "min": 0, "max": 100})
        ch2.set_size({"width": 500, "height": 300}); ch2.set_style(10)
        ws2.insert_chart("G3", ch2)

    wb.close(); output.seek(0)
    slug = _filename_slug(quiz["title"])
    return StreamingResponse(output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stats_quiz_{slug}.xlsx"'})


# ─── Student-level report ────────────────────────────────────────

@router.get("/reports/student/{student_id}", response_class=HTMLResponse,
            dependencies=[Depends(require_teacher)])
async def report_student(request: Request, student_id: int):
    report = analytics_service.build_student_report(student_id)
    if report is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "teacher/report_student.html",
        {"app_title": APP_TITLE, "report": report},
    )


@router.get("/reports/student/{student_id}/export.xlsx",
            dependencies=[Depends(require_teacher)])
async def report_student_xlsx(student_id: int):
    if not _HAS_XLSX:
        raise HTTPException(500, "xlsxwriter not installed")
    report = analytics_service.build_student_report(student_id)
    if report is None:
        raise HTTPException(status_code=404)

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {"in_memory": True})

    bold    = wb.add_format({"bold": True, "font_size": 11})
    header  = wb.add_format({"bold": True, "bg_color": "#6366f1", "font_color": "#FFFFFF",
                              "border": 1, "font_size": 11, "align": "center"})
    title_f = wb.add_format({"bold": True, "font_size": 14, "font_color": "#4f46e5"})
    pct_f   = wb.add_format({"num_format": '0.0"%"', "border": 1})
    num_f   = wb.add_format({"num_format": "#,##0", "border": 1})
    text_f  = wb.add_format({"border": 1})
    sub_h   = wb.add_format({"bold": True, "bg_color": "#e0e7ff", "border": 1})

    st  = report["student"]
    ov  = report["overview"]
    ses = report["sessions"]

    ws1 = wb.add_worksheet("Résumé")
    ws1.set_column("A:A", 28); ws1.set_column("B:B", 18); ws1.set_column("C:H", 14)

    ws1.write("A1", f"Rapport élève — {st['pseudo']}", title_f)
    ws1.write("A3", "Vue d'ensemble", bold)
    kpis = [
        ("Sessions jouées",        ov["total_sessions"]),
        ("Score total",             ov["total_score"]),
        ("Taux de réussite moyen", f"{ov['avg_success_rate']}%"),
        ("Réponses correctes",     f"{ov['total_correct']} / {ov['total_questions']}"),
    ]
    for i, (k, v) in enumerate(kpis):
        ws1.write(3 + i, 0, k, sub_h); ws1.write(3 + i, 1, v, text_f)

    ws1.write("A9", "Session",   header); ws1.write("B9", "Quiz", header)
    ws1.write("C9", "Date",      header); ws1.write("D9", "Score", header)
    ws1.write("E9", "Taux (%)",  header); ws1.write("F9", "Rang", header)
    ws1.write("G9", "Joueurs",   header)

    for i, s in enumerate(ses):
        r = 9 + i
        ws1.write(r, 0, s["session_code"],           text_f)
        ws1.write(r, 1, s.get("quiz_title") or "—",  text_f)
        ws1.write(r, 2, (s["started_at"] or "")[:10], text_f)
        ws1.write(r, 3, s["total_score"],             num_f)
        ws1.write(r, 4, s["success_rate"],            pct_f)
        ws1.write(r, 5, s["rank"] or "—",             text_f)
        ws1.write(r, 6, s["total_players"],           num_f)

    if ses:
        ch = wb.add_chart({"type": "column"})
        ch.add_series({
            "name": "Score",
            "categories": ["Résumé", 9, 0, 8 + len(ses), 0],
            "values":     ["Résumé", 9, 3, 8 + len(ses), 3],
            "fill": {"color": "#6366f1"}, "data_labels": {"value": True},
        })
        ch.add_series({
            "name": "Taux de réussite (%)",
            "categories": ["Résumé", 9, 0, 8 + len(ses), 0],
            "values":     ["Résumé", 9, 4, 8 + len(ses), 4],
            "type": "line", "y2_axis": True,
            "line": {"color": "#22c55e", "width": 2.5},
            "marker": {"type": "circle"},
        })
        ch.set_title({"name": f"Progression de {st['pseudo']}"})
        ch.set_y2_axis({"name": "Réussite (%)", "min": 0, "max": 100})
        ch.set_size({"width": 600, "height": 320}); ch.set_style(10)
        ws1.insert_chart("I3", ch)

    wb.close(); output.seek(0)
    slug = _filename_slug(st["pseudo"])
    return StreamingResponse(output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stats_eleve_{slug}.xlsx"'})


# ─── Session-level report ────────────────────────────────────────

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
    writer.writerow(["Mode", report["session"].get("mode") or "NORMAL"])
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
    writer.writerow(["Question", "Texte", "Taux de reussite", "Bonnes reponses",
                     "Reponses", "Sans reponse", "Temps moyen (s)"])
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

    writer.writerow(["Classement final"])
    writer.writerow(["Rang", "Eleve", "Score total", "Taux de reussite", "Bonnes reponses", "Temps moyen (s)"])
    for s in sorted(report["students"], key=lambda x: -x["total_score"]):
        rank = next((r["rank"] for r in report["leaderboard"] if r["id"] == s["id"]), "—")
        writer.writerow([
            rank, s["nickname"], s["total_score"],
            f"{s['success_rate']}%", s["correct_answers"],
            s["avg_response_seconds"] if s["avg_response_seconds"] is not None else "",
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


@router.get("/reports/{session_id}/export.xlsx", dependencies=[Depends(require_teacher)])
async def report_export_xlsx(session_id: int):
    """Export session report as Excel workbook with embedded charts."""
    if not _HAS_XLSX:
        raise HTTPException(500, "xlsxwriter not installed — run: pip install xlsxwriter")
    report = analytics_service.build_session_report(session_id)
    if report is None:
        raise HTTPException(status_code=404)

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {"in_memory": True})

    # ── Formats ──────────────────────────────────────────────────
    bold    = wb.add_format({"bold": True, "font_size": 11})
    header  = wb.add_format({"bold": True, "bg_color": "#6366f1", "font_color": "#FFFFFF",
                              "border": 1, "font_size": 11, "align": "center"})
    title_f = wb.add_format({"bold": True, "font_size": 14, "font_color": "#4f46e5"})
    pct_f   = wb.add_format({"num_format": '0.0"%"', "border": 1})
    num_f   = wb.add_format({"num_format": "#,##0", "border": 1})
    text_f  = wb.add_format({"border": 1})
    good_f  = wb.add_format({"bg_color": "#dcfce7", "border": 1})
    bad_f   = wb.add_format({"bg_color": "#fee2e2", "border": 1})
    mid_f   = wb.add_format({"bg_color": "#fef9c3", "border": 1})
    sub_h   = wb.add_format({"bold": True, "bg_color": "#e0e7ff", "border": 1})
    rank_f  = wb.add_format({"bold": True, "font_size": 12, "border": 1, "align": "center"})

    ov         = report["overview"]
    quiz       = report["quiz"]
    questions  = report["questions"]
    students   = report["students"]
    leaderboard = report["leaderboard"]
    session    = report["session"]

    # ── Sheet 1: Résumé ───────────────────────────────────────────
    ws1 = wb.add_worksheet("Résumé")
    ws1.set_column("A:A", 30); ws1.set_column("B:B", 18); ws1.set_column("C:I", 14)

    ws1.write("A1", f"Rapport — {quiz['title']}", title_f)
    ws1.write("A2", f"Session: {session['session_code']}  |  Mode: {session.get('mode','NORMAL')}")
    ws1.write("A3", f"Début: {session.get('started_at','?')}")
    ws1.write("A4", f"Fin: {session.get('ended_at','?')}")

    ws1.write("A6", "Vue d'ensemble", bold)
    kpis = [
        ("Élèves",               ov["player_count"]),
        ("Questions",            ov["question_count"]),
        ("Taux réussite moyen",  f"{ov['average_success_rate']}%"),
        ("Score moyen",          ov["average_score"]),
        ("Score minimum",        ov["min_score"]),
        ("Score maximum",        ov["max_score"]),
    ]
    for i, (k, v) in enumerate(kpis):
        ws1.write(6 + i, 0, k, sub_h)
        ws1.write(6 + i, 1, v, text_f)

    # Question success table (for chart)
    ws1.write("A14", "Question",       header)
    ws1.write("B14", "Réussite (%)",   header)
    ws1.write("C14", "Correctes",      header)
    ws1.write("D14", "Réponses tot.",  header)
    ws1.write("E14", "Sans réponse",   header)
    ws1.write("F14", "Tps moyen (s)",  header)

    for i, q in enumerate(questions):
        r = 14 + i
        sr_fmt = good_f if q["success_rate"] >= 70 else (bad_f if q["success_rate"] < 40 else mid_f)
        ws1.write(r, 0, f"Q{q['number']} — {q['text'][:48]}", text_f)
        ws1.write(r, 1, q["success_rate"],   sr_fmt)
        ws1.write(r, 2, q["correct_count"],  num_f)
        ws1.write(r, 3, q["answer_count"],   num_f)
        ws1.write(r, 4, q["unanswered_count"], num_f)
        ws1.write(r, 5, q["avg_response_seconds"] or 0, num_f)

    # Chart: question success rates
    ch1 = wb.add_chart({"type": "column"})
    ch1.add_series({
        "name": "Taux de réussite (%)",
        "categories": ["Résumé", 14, 0, 13 + len(questions), 0],
        "values":     ["Résumé", 14, 1, 13 + len(questions), 1],
        "fill": {"color": "#6366f1"},
        "data_labels": {"value": True, "num_format": '0"%"'},
    })
    ch1.set_title({"name": "Taux de réussite par question"})
    ch1.set_y_axis({"name": "Réussite (%)", "min": 0, "max": 100})
    ch1.set_size({"width": 600, "height": 320}); ch1.set_style(10)
    ws1.insert_chart("H6", ch1)

    # Chart: score distribution doughnut
    dist_data = ov.get("score_distribution", [])
    if dist_data:
        dist_row = 14 + len(questions) + 2
        ws1.write(dist_row, 0, "Distribution des scores", bold)
        ws1.write(dist_row + 1, 0, "Tranche", header)
        ws1.write(dist_row + 1, 1, "Élèves", header)
        for i, b in enumerate(dist_data):
            ws1.write(dist_row + 2 + i, 0, b["label"], text_f)
            ws1.write(dist_row + 2 + i, 1, b["count"],  num_f)

        ch2 = wb.add_chart({"type": "pie"})
        ch2.add_series({
            "name": "Distribution des scores",
            "categories": ["Résumé", dist_row + 2, 0, dist_row + 1 + len(dist_data), 0],
            "values":     ["Résumé", dist_row + 2, 1, dist_row + 1 + len(dist_data), 1],
            "data_labels": {"percentage": True, "category": True},
        })
        ch2.set_title({"name": "Distribution des scores"})
        ch2.set_size({"width": 400, "height": 280}); ch2.set_style(10)
        ws1.insert_chart("H22", ch2)

    # ── Sheet 2: Classement ────────────────────────────────────────
    ws_rank = wb.add_worksheet("Classement")
    ws_rank.set_column("A:A", 8); ws_rank.set_column("B:B", 24); ws_rank.set_column("C:F", 16)

    ws_rank.write("A1", "Classement final", title_f)
    ws_rank.write("A3", "Rang",    header)
    ws_rank.write("B3", "Élève",   header)
    ws_rank.write("C3", "Score",   header)
    ws_rank.write("D3", "Réussite (%)", header)
    ws_rank.write("E3", "Correctes",   header)
    ws_rank.write("F3", "Tps moyen (s)", header)

    score_map = {s["id"]: s for s in students}
    for i, lb in enumerate(leaderboard):
        r = 3 + i
        stu = score_map.get(lb["id"], {})
        medal = "🥇" if lb["rank"] == 1 else "🥈" if lb["rank"] == 2 else "🥉" if lb["rank"] == 3 else str(lb["rank"])
        row_fmt = (
            wb.add_format({"bg_color": "#fef9c3", "border": 1}) if lb["rank"] == 1 else
            wb.add_format({"bg_color": "#f3f4f6", "border": 1}) if lb["rank"] == 2 else
            wb.add_format({"bg_color": "#fef3e2", "border": 1}) if lb["rank"] == 3 else text_f
        )
        ws_rank.write(r, 0, medal, rank_f)
        ws_rank.write(r, 1, lb["nickname"],           row_fmt)
        ws_rank.write(r, 2, lb["total_score"],        num_f)
        ws_rank.write(r, 3, stu.get("success_rate", 0), pct_f)
        ws_rank.write(r, 4, stu.get("correct_answers", 0), num_f)
        ws_rank.write(r, 5, stu.get("avg_response_seconds") or 0, num_f)

    # Score bar chart for ranking sheet
    ch_rank = wb.add_chart({"type": "bar"})
    ch_rank.add_series({
        "name": "Score",
        "categories": ["Classement", 3, 1, 2 + len(leaderboard), 1],
        "values":     ["Classement", 3, 2, 2 + len(leaderboard), 2],
        "fill": {"color": "#6366f1"}, "data_labels": {"value": True},
    })
    ch_rank.set_title({"name": "Scores des élèves"})
    ch_rank.set_size({"width": 560, "height": 360}); ch_rank.set_style(10)
    ws_rank.insert_chart("H3", ch_rank)

    # ── Sheet 3: Questions ─────────────────────────────────────────
    ws2 = wb.add_worksheet("Questions")
    ws2.set_column("A:A", 50); ws2.set_column("B:H", 16)

    ws2.write("A1", "Détail par question", title_f)
    ws2.write("A2", "Choix corrects surlignés en vert",
              wb.add_format({"italic": True, "font_color": "#16a34a"}))

    row = 3
    for q in questions:
        ws2.write(row, 0, f"Q{q['number']} — {q['text']}", bold)
        sr_color = "#16a34a" if q["success_rate"] >= 70 else "#dc2626" if q["success_rate"] < 40 else "#d97706"
        ws2.write(row, 1, f"Réussite: {q['success_rate']}%",
                  wb.add_format({"bold": True, "font_color": sr_color}))
        row += 1
        ws2.write(row, 0, "Choix",       header); ws2.write(row, 1, "Réponses", header)
        ws2.write(row, 2, "Pourcentage", header); ws2.write(row, 3, "Correct ?", header)
        row += 1
        for choice in q["distribution"]:
            fmt = good_f if choice.get("is_correct") else text_f
            ws2.write(row, 0, choice["choice_text"], fmt)
            ws2.write(row, 1, choice["count"],       fmt)
            ws2.write(row, 2, f"{choice['percent']}%", fmt)
            ws2.write(row, 3, "Oui" if choice.get("is_correct") else "Non", fmt)
            row += 1
        row += 1

    # ── Sheet 4: Élèves ────────────────────────────────────────────
    ws3 = wb.add_worksheet("Élèves")
    ws3.set_column("A:A", 24); ws3.set_column("B:F", 16)

    ws3.write("A1", "Vue par élève", title_f)
    ws3.write("A3", "Élève",            header); ws3.write("B3", "Score total",    header)
    ws3.write("C3", "Réussite (%)",     header); ws3.write("D3", "Correctes",      header)
    ws3.write("E3", "Tps moyen (s)",    header)

    sorted_students = sorted(students, key=lambda s: s["total_score"], reverse=True)
    for i, s in enumerate(sorted_students):
        r = 3 + i
        ws3.write(r, 0, s["nickname"],                  text_f)
        ws3.write(r, 1, s["total_score"],               num_f)
        ws3.write(r, 2, s["success_rate"],              pct_f)
        ws3.write(r, 3, s["correct_answers"],           num_f)
        ws3.write(r, 4, s["avg_response_seconds"] or 0, num_f)

    ch4 = wb.add_chart({"type": "column"})
    ch4.add_series({
        "name": "Score total",
        "categories": ["Élèves", 3, 0, 2 + len(students), 0],
        "values":     ["Élèves", 3, 1, 2 + len(students), 1],
        "fill": {"color": "#6366f1"}, "data_labels": {"value": True},
    })
    ch4.add_series({
        "name": "Réussite (%)",
        "categories": ["Élèves", 3, 0, 2 + len(students), 0],
        "values":     ["Élèves", 3, 2, 2 + len(students), 2],
        "type": "line", "y2_axis": True,
        "line": {"color": "#22c55e", "width": 2},
        "marker": {"type": "circle"},
    })
    ch4.set_title({"name": "Scores et réussite par élève"})
    ch4.set_y2_axis({"name": "Réussite (%)", "min": 0, "max": 100})
    ch4.set_size({"width": 700, "height": 360}); ch4.set_style(10)
    ws3.insert_chart("G3", ch4)

    # ── Sheet 5: Détails ───────────────────────────────────────────
    ws4 = wb.add_worksheet("Détails")
    ws4.set_column("A:A", 22); ws4.set_column("B:F", 14)

    ws4.write("A1", "Détails par élève", title_f)
    ws4.write("A3", "Élève",           header); ws4.write("B3", "Question",       header)
    ws4.write("C3", "Résultat",        header); ws4.write("D3", "Réponse choisie", header)
    ws4.write("E3", "Temps (s)",       header); ws4.write("F3", "Points",         header)

    row = 3
    for s in students:
        for q_row in s["questions"]:
            fmt = good_f if q_row["is_correct"] else text_f
            ws4.write(row, 0, s["nickname"],                         text_f)
            ws4.write(row, 1, f"Q{q_row['number']}",                 text_f)
            ws4.write(row, 2, "✓ Réussie" if q_row["is_correct"] else "✗ Ratée", fmt)
            ws4.write(row, 3, q_row["selected_choice"],              text_f)
            ws4.write(row, 4, q_row["response_seconds"] or 0,        num_f)
            ws4.write(row, 5, q_row["points"],                       num_f)
            row += 1

    wb.close()
    output.seek(0)

    quiz_slug = _filename_slug(report["quiz"]["title"])
    timestamp = _filename_slug(report["session"].get("ended_at") or "session")
    filename = f"rapport_{quiz_slug}_{timestamp}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
            "leaderboard_top_n": LEADERBOARD_TOP_N,
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
