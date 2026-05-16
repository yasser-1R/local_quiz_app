"""Student pages (no session codes — one shared room)."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import (
    APP_TITLE, AVATAR_ACCESSORIES, AVATAR_CHARACTERS, AVATAR_COLORS,
    TEMPLATES_DIR, RANDOM_ANSWER_DISPLAY_SECONDS,
)
from ..services import player_service, session_service, student_service
from ..websocket_manager import manager


router = APIRouter(tags=["student"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

PLAYER_COOKIE = "player_token"
STUDENT_COOKIE = "student_auth"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # If already has a valid token for the CURRENT session, skip straight in.
    token = request.cookies.get(PLAYER_COOKIE)
    cur = session_service.get_current_session()
    if token and cur:
        player = player_service.get_player_by_token(token)
        if player and player["session_id"] == cur["id"]:
            return RedirectResponse(url="/play", status_code=303)

    # Always default to BLOCKED — teacher must explicitly open the session
    connection_mode = (cur.get("connection_mode") or "BLOCKED") if cur else "BLOCKED"

    # In LOGIN mode: if already authenticated, redirect to join (skip login form)
    if connection_mode == "LOGIN":
        student_token = request.cookies.get(STUDENT_COOKIE)
        if student_token:
            student = student_service.get_student_by_token(student_token)
            if student and cur and cur["state"] in ("WAITING", "LOBBY"):
                # Check not already in session
                if not player_service.nickname_taken(cur["id"], student["pseudo"]):
                    return templates.TemplateResponse(
                        request,
                        "student/join.html",
                        {
                            "app_title": APP_TITLE,
                            "avatar_characters": AVATAR_CHARACTERS,
                            "avatar_colors": AVATAR_COLORS,
                            "avatar_accessories": AVATAR_ACCESSORIES,
                            "error": None,
                            "nickname": student["pseudo"],
                            "connection_mode": "LOGIN_AUTOFILL",
                            "student": student,
                        },
                    )

    return templates.TemplateResponse(
        request,
        "student/join.html",
        {
            "app_title": APP_TITLE,
            "avatar_characters": AVATAR_CHARACTERS,
            "avatar_colors": AVATAR_COLORS,
            "avatar_accessories": AVATAR_ACCESSORIES,
            "error": None,
            "nickname": "",
            "connection_mode": connection_mode,
            "student": None,
        },
    )


@router.post("/join")
async def do_join(
    request: Request,
    nickname: str = Form(...),
    avatar_character: str = Form(...),
    avatar_color: str = Form(...),
    avatar_accessory: str = Form(""),
):
    nickname = nickname.strip()[:20]
    if not nickname:
        return _error(request, nickname, "Veuillez entrer un pseudo.")

    session = session_service.ensure_current_session()
    connection_mode = session.get("connection_mode") or "BLOCKED"

    # BLOCKED mode: reject directly
    if connection_mode == "BLOCKED":
        return _error(request, nickname, "La session est verrouillée. Attendez le professeur.")

    # SIGNUP, LOGIN, and BOTH modes must go through /auth/* endpoints
    if connection_mode in ("SIGNUP", "LOGIN", "BOTH"):
        return _error(
            request, nickname,
            "Ce mode de connexion nécessite un compte. Utilisez le formulaire ci-dessous.",
        )

    if session["state"] not in ("WAITING", "LOBBY"):
        return _error(
            request,
            nickname,
            "Un quiz est déjà en cours. Demandez au professeur de le terminer.",
        )

    if player_service.nickname_taken(session["id"], nickname):
        return _error(request, nickname, "Ce pseudo est déjà pris. Choisissez-en un autre.")

    player = player_service.add_player(
        session_id=session["id"],
        nickname=nickname,
        character=avatar_character,
        color=avatar_color,
        accessory=avatar_accessory,
    )

    players = player_service.list_players(session["id"])
    await manager.broadcast(
        session["session_code"],
        {
            "type": "player_joined",
            "player": _public_player(player),
            "players": [_public_player(p) for p in players],
            "total": len(players),
        },
    )

    resp = RedirectResponse(url="/play", status_code=303)
    resp.set_cookie(PLAYER_COOKIE, player["token"], httponly=True, samesite="lax")
    return resp


def _error(request, nickname, message):
    cur = session_service.get_current_session()
    connection_mode = (cur.get("connection_mode") or "BLOCKED") if cur else "BLOCKED"
    return templates.TemplateResponse(
        request,
        "student/join.html",
        {
            "app_title": APP_TITLE,
            "avatar_characters": AVATAR_CHARACTERS,
            "avatar_colors": AVATAR_COLORS,
            "avatar_accessories": AVATAR_ACCESSORIES,
            "error": message,
            "nickname": nickname,
            "connection_mode": connection_mode,
            "student": None,
        },
        status_code=400,
    )


@router.get("/play", response_class=HTMLResponse)
async def play_page(request: Request):
    token = request.cookies.get(PLAYER_COOKIE)
    cur = session_service.get_current_session()
    if not token or not cur:
        return RedirectResponse(url="/", status_code=303)
    player = player_service.get_player_by_token(token)
    if player is None or player["session_id"] != cur["id"]:
        resp = RedirectResponse(url="/", status_code=303)
        resp.delete_cookie(PLAYER_COOKIE)
        return resp

    return templates.TemplateResponse(
        request,
        "student/play.html",
        {
            "app_title": APP_TITLE,
            "session": cur,
            "player": player,
            "random_answer_display_seconds": RANDOM_ANSWER_DISPLAY_SECONDS,
        },
    )


@router.get("/leave")
async def leave():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(PLAYER_COOKIE)
    return resp


@router.get("/leave-all")
async def leave_all():
    """Clear ALL session cookies — used when quiz resets or multiple students share one PC."""
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(PLAYER_COOKIE)
    resp.delete_cookie(STUDENT_COOKIE)
    return resp


def _public_player(p: dict) -> dict:
    return {
        "id": p["id"],
        "nickname": p["nickname"],
        "avatar_character": p.get("avatar_character") or "🦊",
        "avatar_color": p.get("avatar_color") or "#6366f1",
        "avatar_accessory": p.get("avatar_accessory") or "",
        "is_connected": bool(p.get("is_connected", True)),
    }
