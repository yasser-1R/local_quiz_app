"""Student authentication routes (signup / login / logout)."""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import APP_TITLE, AVATAR_ACCESSORIES, AVATAR_CHARACTERS, AVATAR_COLORS, TEMPLATES_DIR
from ..services import player_service, session_service, student_service

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

STUDENT_COOKIE = "student_auth"
PLAYER_COOKIE = "player_token"


def _render_join(request: Request, *, error: str = None, nickname: str = "", mode: str = "GUEST"):
    return templates.TemplateResponse(
        request,
        "student/join.html",
        {
            "app_title": APP_TITLE,
            "avatar_characters": AVATAR_CHARACTERS,
            "avatar_colors": AVATAR_COLORS,
            "avatar_accessories": AVATAR_ACCESSORIES,
            "error": error,
            "nickname": nickname,
            "connection_mode": mode,
            "student": None,
        },
    )


def _effective_error_mode(fallback: str) -> str:
    """If the current session uses BOTH mode, return BOTH_SIGNUP or BOTH_LOGIN instead."""
    s = session_service.get_current_session()
    if s and s.get("connection_mode") == "BOTH":
        return "BOTH_" + fallback  # BOTH_SIGNUP or BOTH_LOGIN
    return fallback


@router.post("/signup")
async def do_signup(
    request: Request,
    nickname: str = Form(...),
    password: str = Form(...),
    avatar_character: str = Form(...),
    avatar_color: str = Form(...),
    avatar_accessory: str = Form(""),
):
    nickname = nickname.strip()[:20]
    signup_mode = _effective_error_mode("SIGNUP")
    if not nickname:
        return _render_join(request, error="Veuillez entrer un pseudo.", mode=signup_mode)
    if len(password) < 4:
        return _render_join(
            request, error="Mot de passe trop court (min. 4 caractères).",
            nickname=nickname, mode=signup_mode,
        )

    session = session_service.ensure_current_session()
    if session["state"] not in ("WAITING", "LOBBY"):
        return _render_join(
            request,
            error="Un quiz est déjà en cours. Demandez au professeur de le terminer.",
            mode=signup_mode,
        )

    # Check nickname not taken in current session
    if player_service.nickname_taken(session["id"], nickname):
        return _render_join(
            request, error="Ce pseudo est déjà pris. Choisissez-en un autre.",
            nickname=nickname, mode=signup_mode,
        )

    # Check student account doesn't already exist
    if student_service.get_student_by_pseudo(nickname) is not None:
        return _render_join(
            request, error="Un compte existe déjà avec ce pseudo. Utilisez la connexion.",
            nickname=nickname, mode=signup_mode,
        )

    # Create persistent student account
    student = student_service.create_student(
        pseudo=nickname,
        password=password,
        character=avatar_character,
        color=avatar_color,
        accessory=avatar_accessory,
    )

    # Create game player linked to this student
    player = player_service.add_player(
        session_id=session["id"],
        nickname=nickname,
        character=avatar_character,
        color=avatar_color,
        accessory=avatar_accessory,
        student_id=student["id"],
    )

    from ..websocket_manager import manager
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
    resp.set_cookie(STUDENT_COOKIE, student["auth_token"], httponly=True, samesite="lax")
    return resp


@router.post("/login")
async def do_login(
    request: Request,
    nickname: str = Form(...),
    password: str = Form(...),
):
    nickname = nickname.strip()[:20]
    login_mode = _effective_error_mode("LOGIN")

    student = student_service.authenticate_student(nickname, password)
    if student is None:
        return _render_join(
            request, error="Pseudo ou mot de passe incorrect.",
            nickname=nickname, mode=login_mode,
        )

    session = session_service.ensure_current_session()
    if session["state"] not in ("WAITING", "LOBBY"):
        return _render_join(
            request,
            error="Un quiz est déjà en cours. Demandez au professeur de le terminer.",
            mode=login_mode,
        )

    # Use stored avatar for this student
    character = student.get("avatar_character") or AVATAR_CHARACTERS[0]
    color = student.get("avatar_color") or AVATAR_COLORS[0]["value"]
    accessory = student.get("avatar_accessory") or ""

    # Check nickname not already in this session
    if player_service.nickname_taken(session["id"], nickname):
        return _render_join(
            request, error="Vous êtes déjà dans cette session.",
            nickname=nickname, mode=login_mode,
        )

    player = player_service.add_player(
        session_id=session["id"],
        nickname=nickname,
        character=character,
        color=color,
        accessory=accessory,
        student_id=student["id"],
    )

    from ..websocket_manager import manager
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
    resp.set_cookie(STUDENT_COOKIE, student["auth_token"], httponly=True, samesite="lax")
    return resp


@router.get("/logout")
async def student_logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(STUDENT_COOKIE)
    resp.delete_cookie(PLAYER_COOKIE)
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
