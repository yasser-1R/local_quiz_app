"""
FastAPI application entry point.

Single-room model: all WebSocket URLs are codeless. The server resolves the
"current session" from the database and routes messages on its internal code.
"""
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_TITLE, STATIC_DIR
from .database import init_db
from .routes import (
    display_routes,
    quiz_routes,
    session_routes,
    student_routes,
    teacher_routes,
)
from .services import player_service, session_service, quiz_service
from .websocket_manager import manager
from . import seed  # seeds demo quiz on first run


def create_app() -> FastAPI:
    init_db()
    seed.ensure_demo_quiz()

    app = FastAPI(title=APP_TITLE)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # HTTP routes
    app.include_router(student_routes.router)
    app.include_router(teacher_routes.router)
    app.include_router(display_routes.router)
    app.include_router(quiz_routes.router)
    app.include_router(session_routes.router)

    # --- WebSocket: teacher control (codeless, always current room) ---
    @app.websocket("/ws/teacher")
    async def ws_teacher(websocket: WebSocket):
        session = session_service.ensure_current_session()
        code = session["session_code"]
        await manager.connect_teacher(code, websocket)
        # Always send current session state on connect so control page knows where we are
        await websocket.send_text(json.dumps({
            "type": "session_state",
            "state": session["state"],
            "quiz_id": session.get("quiz_id"),
            "current_question_index": session.get("current_question_index"),
        }))
        # If question is already active, send it too
        if session["state"] == "QUESTION_ACTIVE":
            q = session_service.current_question(session)
            if q is not None:
                quiz = quiz_service.get_quiz(session["quiz_id"])
                await websocket.send_text(json.dumps({
                    "type": "question_started",
                    "index": session["current_question_index"],
                    "total": len(quiz["questions"]),
                    "question": session_service.question_public(q),
                    "started_at": session["current_question_started"],
                }))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect_teacher(code, websocket)

    # --- WebSocket: display (codeless) ---
    @app.websocket("/ws/display")
    async def ws_display(websocket: WebSocket):
        session = session_service.ensure_current_session()
        code = session["session_code"]
        await manager.connect_display(code, websocket)
        # Always send current session state on connect
        await websocket.send_text(json.dumps({
            "type": "session_state",
            "state": session["state"],
            "quiz_id": session.get("quiz_id"),
        }))
        # If question is already active, send it too
        if session["state"] == "QUESTION_ACTIVE":
            q = session_service.current_question(session)
            if q is not None:
                quiz = quiz_service.get_quiz(session["quiz_id"])
                await websocket.send_text(json.dumps({
                    "type": "question_started",
                    "index": session["current_question_index"],
                    "total": len(quiz["questions"]),
                    "question": session_service.question_public(q),
                    "started_at": session["current_question_started"],
                }))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect_display(code, websocket)

    # --- WebSocket: student (player token only) ---
    @app.websocket("/ws/student/{token}")
    async def ws_student(websocket: WebSocket, token: str):
        player = player_service.get_player_by_token(token)
        if player is None:
            await websocket.close(code=4404)
            return
        session = session_service.get_session(player["session_id"])
        if session is None:
            await websocket.close(code=4404)
            return
        code = session["session_code"]

        await manager.connect_student(code, token, websocket)
        player_service.set_connected(token, True)

        # Catch the student up with current state
        if session["state"] == "QUESTION_ACTIVE":
            q = session_service.current_question(session)
            if q is not None:
                await websocket.send_text(json.dumps({
                    "type": "question_started",
                    "index": session["current_question_index"],
                    "question": session_service.question_public(q),
                    "started_at": session["current_question_started"],
                }))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "submit_answer":
                    choice_id = int(msg.get("choice_id", 0))
                    elapsed = int(msg.get("elapsed_ms", 0))
                    result = await session_routes.submit_answer_and_notify(
                        code, token, choice_id, elapsed
                    )
                    await websocket.send_text(json.dumps({
                        "type": "answer_result", **result
                    }))
        except WebSocketDisconnect:
            await manager.disconnect_student(code, token)
            player_service.set_connected(token, False)

    @app.get("/home")
    async def home_redirect():
        return RedirectResponse(url="/")

    return app


app = create_app()
