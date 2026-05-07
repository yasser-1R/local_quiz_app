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
    auth_routes,
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
    app.include_router(auth_routes.router)
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

        await websocket.send_text(json.dumps({
            "type": "session_state",
            "state": session["state"],
            "mode": session.get("mode", "NORMAL"),
            "connection_mode": session.get("connection_mode", "GUEST"),
            "quiz_id": session.get("quiz_id"),
            "current_question_index": session.get("current_question_index"),
        }))

        # If question is active (normal mode), send current question
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
                    "mode": "normal",
                }))

        # If in random mode, send initial player progress
        if session["state"] == "RANDOM_ACTIVE":
            players = player_service.list_players(session["id"])
            progress_list = []
            for p in players:
                total = session_service.count_random_questions(session["id"], p["id"])
                prog = max(0, p.get("random_progress", 0))
                progress_list.append({
                    "id": p["id"],
                    "nickname": p["nickname"],
                    "avatar_character": p.get("avatar_character") or "🦊",
                    "avatar_color": p.get("avatar_color") or "#6366f1",
                    "avatar_accessory": p.get("avatar_accessory") or "",
                    "is_connected": bool(p.get("is_connected", True)),
                    "progress": prog,
                    "total": total,
                    "finished": prog >= total and total > 0,
                })
            await websocket.send_text(json.dumps({
                "type": "player_progress",
                "players": progress_list,
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

        await websocket.send_text(json.dumps({
            "type": "session_state",
            "state": session["state"],
            "mode": session.get("mode", "NORMAL"),
            "quiz_id": session.get("quiz_id"),
        }))

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
                    "mode": "normal",
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
                    "mode": "normal",
                }))

        elif session["state"] == "RANDOM_ACTIVE":
            # Re-fetch player to get current progress
            player = player_service.get_player_by_token(token)
            order_index = player.get("random_progress", 0)
            total = session_service.count_random_questions(session["id"], player["id"])

            if order_index >= total and total > 0:
                # Player already finished
                from .services import answer_service
                await websocket.send_text(json.dumps({
                    "type": "random_quiz_complete",
                    "total_score": answer_service.player_total_score(session["id"], player["id"]),
                }))
            elif order_index >= 0:
                q = session_service.get_player_random_question(
                    player["id"], session["id"], order_index
                )
                if q is not None:
                    import time
                    await websocket.send_text(json.dumps({
                        "type": "question_started",
                        "index": order_index,
                        "total": total,
                        "question": session_service.question_public(q),
                        "started_at": time.time(),
                        "mode": "random",
                    }))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                msg_type = msg.get("type")

                if msg_type == "submit_answer":
                    choice_id = int(msg.get("choice_id", 0))
                    elapsed = int(msg.get("elapsed_ms", 0))
                    # Re-fetch session to get latest state
                    session = session_service.get_session(player["session_id"])

                    if session and session["state"] == "RANDOM_ACTIVE":
                        result = await session_routes.submit_random_answer_and_notify(
                            code, token, choice_id, elapsed
                        )
                        await websocket.send_text(json.dumps({
                            "type": "answer_result",
                            **result,
                            "mode": "random",
                        }))
                    else:
                        result = await session_routes.submit_answer_and_notify(
                            code, token, choice_id, elapsed
                        )
                        await websocket.send_text(json.dumps({
                            "type": "answer_result",
                            **result,
                            "mode": "normal",
                        }))

                elif msg_type == "request_next_question":
                    # Student (in random mode) is ready for their next question
                    session = session_service.get_session(player["session_id"])
                    if session and session["state"] == "RANDOM_ACTIVE":
                        await session_routes.send_next_random_question(code, token)

        except WebSocketDisconnect:
            await manager.disconnect_student(code, token)
            player_service.set_connected(token, False)

    @app.get("/home")
    async def home_redirect():
        return RedirectResponse(url="/")

    return app


app = create_app()
