"""Display / projector pages (codeless — always shows the current room)."""
import io
import base64

import qrcode
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import APP_TITLE, PORT, TEMPLATES_DIR
from ..services import quiz_service, session_service, player_service
from ..utils.network_utils import get_local_ip


router = APIRouter(prefix="/display", tags=["display"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("", response_class=HTMLResponse)
async def display_session(request: Request):
    session = session_service.ensure_current_session()
    quiz = (
        quiz_service.get_quiz(session["quiz_id"])
        if session.get("quiz_id") is not None
        else None
    )
    players = player_service.list_players(session["id"])

    ip = get_local_ip()
    join_url = f"http://{ip}:{PORT}/"
    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return templates.TemplateResponse(
        request,
        "display/session.html",
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
