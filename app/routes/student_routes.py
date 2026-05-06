"""Student pages (no session codes — one shared room)."""
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import APP_TITLE, AVATAR_ACCESSORIES, AVATAR_CHARACTERS, AVATAR_COLORS, TEMPLATES_DIR, DEFAULT_QUESTIONS_PER_STUDENT
from ..services import player_service, session_service, profile_service, random_assignment_service
from ..websocket_manager import manager


router = APIRouter(tags=["student"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)

PLAYER_COOKIE = "player_token"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    profile_token = request.cookies.get(profile_service.PROFILE_COOKIE)
    cur = session_service.get_current_session()

    if profile_token:
        profile = profile_service.get_profile_by_token(profile_token)
        if profile:
            if cur and cur["state"] not in ("FINISHED",):
                return RedirectResponse(url="/play", status_code=303)
            return RedirectResponse(url="/profile", status_code=303)

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
        },
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    profile_token = request.cookies.get(profile_service.PROFILE_COOKIE)
    if not profile_token:
        return RedirectResponse(url="/", status_code=303)
    profile = profile_service.get_profile_by_token(profile_token)
    if not profile:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request,
        "student/profile.html",
        {
            "app_title": APP_TITLE,
            "avatar_characters": AVATAR_CHARACTERS,
            "avatar_colors": AVATAR_COLORS,
            "avatar_accessories": AVATAR_ACCESSORIES,
            "profile": profile,
        },
    )


@router.post("/profile/update")
async def update_profile(
    request: Request,
    nickname: str = Form(...),
    avatar_character: str = Form(...),
    avatar_color: str = Form(...),
    avatar_accessory: str = Form(""),
):
    profile_token = request.cookies.get(profile_service.PROFILE_COOKIE)
    profile = profile_service.get_profile_by_token(profile_token) if profile_token else None

    nickname = nickname.strip()[:20]
    if not nickname:
        return RedirectResponse(url="/profile", status_code=303)

    profile = profile_service.create_or_update_profile(
        nickname=nickname,
        character=avatar_character,
        color=avatar_color,
        accessory=avatar_accessory,
    )

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(profile_service.PROFILE_COOKIE, profile["profile_token"], httponly=True, samesite="lax")
    return resp


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

    if session["state"] not in ("WAITING", "LOBBY"):
        return _error(
            request,
            nickname,
            "Un quiz est deja en cours. Demandez au professeur de le terminer.",
        )

    if player_service.nickname_taken(session["id"], nickname):
        return _error(request, nickname, "Ce pseudo est deja pris. Choisissez-en un autre.")

    profile = profile_service.create_or_update_profile(
        nickname=nickname,
        character=avatar_character,
        color=avatar_color,
        accessory=avatar_accessory,
    )

    player = player_service.add_player(
        session_id=session["id"],
        nickname=nickname,
        character=avatar_character,
        color=avatar_color,
        accessory=avatar_accessory,
        profile_id=profile["id"],
    )

    quiz_mode = session.get("quiz_mode", "UNIFIED")
    if quiz_mode == "RANDOM" and session.get("quiz_id"):
        random_assignment_service.assign_random_questions(
            session_id=session["id"],
            player_id=player["id"],
            quiz_id=session["quiz_id"],
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
    resp.set_cookie(profile_service.PROFILE_COOKIE, profile["profile_token"], httponly=True, samesite="lax")
    return resp


def _error(request, nickname, message):
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

    quiz_mode = cur.get("quiz_mode", "UNIFIED")
    player_questions = []
    if quiz_mode == "RANDOM":
        player_questions = random_assignment_service.get_player_questions(cur["id"], player["id"])

    return templates.TemplateResponse(
        request,
        "student/play.html",
        {
            "app_title": APP_TITLE,
            "session": cur,
            "player": player,
            "quiz_mode": quiz_mode,
            "player_questions": player_questions,
        },
    )


@router.get("/leave")
async def leave():
    resp = RedirectResponse(url="/", status_code=303)
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
