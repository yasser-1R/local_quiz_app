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
from .services import player_service, session_service, quiz_service, random_assignment_service, scoring_service, answer_service
from .websocket_manager import manager
from . import seed


def create_app() -> FastAPI:
    init_db()
    seed.ensure_demo_quiz()

    app = FastAPI(title=APP_TITLE)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(student_routes.router)
    app.include_router(teacher_routes.router)
    app.include_router(display_routes.router)
    app.include_router(quiz_routes.router)
    app.include_router(session_routes.router)

    @app.websocket("/ws/teacher")
    async def ws_teacher(websocket: WebSocket):
        session = session_service.ensure_current_session()
        code = session["session_code"]
        await manager.connect_teacher(code, websocket)
        await websocket.send_text(json.dumps({
            "type": "session_state",
            "state": session["state"],
            "quiz_id": session.get("quiz_id"),
            "current_question_index": session.get("current_question_index"),
            "quiz_mode": session.get("quiz_mode", "UNIFIED"),
        }))
        if session["state"] == "QUESTION_ACTIVE" and session.get("quiz_mode", "UNIFIED") == "UNIFIED":
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

    @app.websocket("/ws/display")
    async def ws_display(websocket: WebSocket):
        session = session_service.ensure_current_session()
        code = session["session_code"]
        await manager.connect_display(code, websocket)
        await websocket.send_text(json.dumps({
            "type": "session_state",
            "state": session["state"],
            "quiz_id": session.get("quiz_id"),
            "quiz_mode": session.get("quiz_mode", "UNIFIED"),
        }))
        if session["state"] == "QUESTION_ACTIVE" and session.get("quiz_mode", "UNIFIED") == "UNIFIED":
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

        quiz_mode = session.get("quiz_mode", "UNIFIED")

        if quiz_mode == "UNIFIED":
            if session["state"] == "QUESTION_ACTIVE":
                q = session_service.current_question(session)
                if q is not None:
                    await websocket.send_text(json.dumps({
                        "type": "question_started",
                        "index": session["current_question_index"],
                        "question": session_service.question_public(q),
                        "started_at": session["current_question_started"],
                    }))
        else:
            if session["state"] == "QUESTION_ACTIVE":
                player_questions = random_assignment_service.get_player_questions(
                    session["id"], player["id"]
                )
                if player_questions:
                    first_q = player_questions[0]
                    quiz = quiz_service.get_quiz(session["quiz_id"])
                    q_data = next(
                        (q for q in quiz["questions"] if q["id"] == first_q["id"]),
                        None
                    )
                    if q_data:
                        await websocket.send_text(json.dumps({
                            "type": "random_question_started",
                            "index": 0,
                            "total": len(player_questions),
                            "question": session_service.question_public(q_data),
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

                    if quiz_mode == "RANDOM":
                        result = await _submit_random_answer(code, token, choice_id, elapsed)
                    else:
                        result = await session_routes.submit_answer_and_notify(
                            code, token, choice_id, elapsed
                        )
                    await websocket.send_text(json.dumps({
                        "type": "answer_result", **result
                    }))

                    if quiz_mode == "RANDOM":
                        player_questions = random_assignment_service.get_player_questions(
                            session["id"], player["id"]
                        )
                        question_ids = [q["id"] for q in player_questions]
                        all_done = random_assignment_service.player_has_answered_all(
                            session["id"], player["id"], question_ids
                        )
                        if all_done:
                            await websocket.send_text(json.dumps({
                                "type": "student_finished",
                            }))
                        else:
                            answered_ids = set()
                            conn_result = __import__("app.database", fromlist=["get_connection"]).get_connection()
                            try:
                                rows = conn_result.execute(
                                    "SELECT question_id FROM answers WHERE session_id=? AND player_id=?",
                                    (session["id"], player["id"]),
                                ).fetchall()
                                answered_ids = {r["question_id"] for r in rows}
                            finally:
                                conn_result.close()

                            next_q = None
                            next_idx = 0
                            for i, pq in enumerate(player_questions):
                                if pq["id"] not in answered_ids:
                                    next_q = pq
                                    next_idx = i
                                    break

                            if next_q:
                                quiz = quiz_service.get_quiz(session["quiz_id"])
                                q_data = next(
                                    (q for q in quiz["questions"] if q["id"] == next_q["id"]),
                                    None
                                )
                                if q_data:
                                    await websocket.send_text(json.dumps({
                                        "type": "random_question_started",
                                        "index": next_idx,
                                        "total": len(player_questions),
                                        "question": session_service.question_public(q_data),
                                    }))
        except WebSocketDisconnect:
            await manager.disconnect_student(code, token)
            player_service.set_connected(token, False)

    async def _submit_random_answer(
        session_code: str, player_token: str, choice_id: int, client_elapsed_ms: int
    ) -> dict:
        session = session_service.get_session_by_code(session_code)
        if session is None:
            return {"ok": False, "reason": "no session"}

        player = player_service.get_player_by_token(player_token)
        if player is None or player["session_id"] != session["id"]:
            return {"ok": False, "reason": "unknown player"}

        player_questions = random_assignment_service.get_player_questions(
            session["id"], player["id"]
        )
        question_ids = [q["id"] for q in player_questions]

        answered_ids = set()
        from app.database import get_connection
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT question_id FROM answers WHERE session_id=? AND player_id=?",
                (session["id"], player["id"]),
            ).fetchall()
            answered_ids = {r["question_id"] for r in rows}
        finally:
            conn.close()

        current_q = None
        for pq in player_questions:
            if pq["id"] not in answered_ids:
                current_q = pq
                break

        if current_q is None:
            return {"ok": False, "reason": "no more questions"}

        quiz = quiz_service.get_quiz(session["quiz_id"])
        q_data = next((q for q in quiz["questions"] if q["id"] == current_q["id"]), None)
        if q_data is None:
            return {"ok": False, "reason": "question not found"}

        valid_choice_ids = {c["id"] for c in q_data["choices"]}
        if choice_id not in valid_choice_ids:
            return {"ok": False, "reason": "bad choice"}

        total_ms = q_data["time_limit_seconds"] * 1000
        elapsed = min(max(client_elapsed_ms, 0), total_ms)

        correct_choice_id = q_data["choices"][q_data["correct_choice_index"]]["id"]
        correct_text = q_data["choices"][q_data["correct_choice_index"]]["choice_text"]

        is_correct = choice_id == correct_choice_id
        points = scoring_service.compute_score(is_correct, elapsed, total_ms)

        from app.database import db_cursor
        with db_cursor() as cur:
            cur.execute(
                """
                INSERT OR IGNORE INTO answers
                  (session_id, question_id, player_id, selected_choice_id,
                   response_time_ms, is_correct, points_awarded)
                VALUES (?,?,?,?,?,?,?)
                """,
                (session["id"], q_data["id"], player["id"], choice_id, elapsed, 1 if is_correct else 0, points),
            )

        total_score = answer_service.player_total_score(session["id"], player["id"])

        return {
            "ok": True,
            "accepted": True,
            "is_correct": is_correct,
            "points": points,
            "total_score": total_score,
            "correct_text": correct_text,
        }

    @app.get("/home")
    async def home_redirect():
        return RedirectResponse(url="/")

    return app


app = create_app()
