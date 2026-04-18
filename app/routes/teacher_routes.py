"""
Teacher pages + teacher session-control API.
URLs are now codeless — the current session is resolved on the server.
"""
import io
import base64

import qrcode
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import TEACHER_PASSWORD, TEMPLATES_DIR, APP_TITLE, PORT
from ..services import quiz_service, session_service, player_service, scoring_service
from ..utils.network_utils import get_local_ip


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
def _qr_for(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@router.get("/lobby", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def lobby(request: Request):
    session = session_service.ensure_current_session()
    quiz = (
        quiz_service.get_quiz(session["quiz_id"])
        if session.get("quiz_id") is not None
        else None
    )
    players = player_service.list_players(session["id"])

    ip = get_local_ip()
    join_url = f"http://{ip}:{PORT}/"
    qr_b64 = _qr_for(join_url)

    return templates.TemplateResponse(
        request,
        "teacher/lobby.html",
        {
            "app_title": APP_TITLE,
            "session": session,
            "quiz": quiz,
            "players": players,
            "join_url": join_url,
            "qr_b64": qr_b64,
            "local_ip": ip,
            "port": PORT,
        },
    )


@router.get("/control", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def control(request: Request):
    session = session_service.get_current_session()
    if session is None or session.get("quiz_id") is None:
        return RedirectResponse(url="/teacher", status_code=303)
    quiz = quiz_service.get_quiz(session["quiz_id"])
    return templates.TemplateResponse(
        request,
        "teacher/control.html",
        {
            "app_title": APP_TITLE,
            "session": session,
            "quiz": quiz,
        },
    )


@router.get("/results", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
async def results(request: Request):
    # Show results of the most recent FINISHED session (or current if it's finished).
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
