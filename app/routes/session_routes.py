"""JSON API for session control (single-room, codeless)."""
import time
from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException, Body

from ..config import TEACHER_PASSWORD
from ..services import (
    quiz_service,
    session_service,
    player_service,
    answer_service,
    scoring_service,
)
from ..websocket_manager import manager


router = APIRouter(prefix="/api/session", tags=["session-api"])


def _require_teacher(auth: Optional[str]):
    if auth != TEACHER_PASSWORD:
        raise HTTPException(status_code=401, detail="teacher login required")


def _public_player(p: dict) -> dict:
    return {
        "id": p["id"],
        "nickname": p["nickname"],
        "avatar_character": p.get("avatar_character") or "🦊",
        "avatar_color": p.get("avatar_color") or "#6366f1",
        "avatar_accessory": p.get("avatar_accessory") or "",
    }


# ---------- current session status ----------
@router.get("/current")
async def current_status():
    """Public endpoint — anyone can ask what the current room is doing."""
    s = session_service.get_current_session()
    if s is None:
        return {"state": "NONE"}
    return {
        "state": s["state"],
        "quiz_id": s.get("quiz_id"),
        "session_code": s["session_code"],
        "current_question_index": s["current_question_index"],
    }


# ---------- teacher control ----------
@router.post("/launch")
async def launch_quiz(
    payload: dict = Body(...),
    teacher_auth: Optional[str] = Cookie(default=None),
):
    _require_teacher(teacher_auth)
    quiz_id = int(payload.get("quiz_id", 0))
    try:
        session = session_service.launch_quiz(quiz_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Announce the new room so teacher/display/student pages can refresh if needed.
    await manager.broadcast(
        session["session_code"],
        {
            "type": "quiz_attached",
            "quiz_id": quiz_id,
        },
    )
    return {
        "ok": True,
        "session_code": session["session_code"],
        "state": session["state"],
    }


@router.post("/start")
async def start_session(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None or session.get("quiz_id") is None:
        raise HTTPException(400, "No quiz is ready to start")
    session_service.mark_started(session["id"])
    await _go_to_question(session["session_code"], 0)
    return {"ok": True}


@router.post("/next")
async def next_question(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    await _go_to_question(session["session_code"], session["current_question_index"] + 1)
    return {"ok": True}


@router.post("/skip")
async def skip_question(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    await _go_to_question(session["session_code"], session["current_question_index"] + 1)
    return {"ok": True}


@router.post("/end-question")
async def end_question(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    if session["state"] != "QUESTION_ACTIVE":
        return {"ok": True, "note": "question not active"}
    await _close_current_question(session)
    return {"ok": True}


@router.post("/show-scores")
async def show_scores(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    board = scoring_service.leaderboard(session["id"])
    board_before = scoring_service.leaderboard_before_current_question(session["id"])
    await manager.broadcast(
        session["session_code"], {
            "type": "scores_shown",
            "board": board,
            "board_before": board_before,
        }
    )
    return {"ok": True}


@router.post("/show-distribution")
async def show_distribution(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    if session["state"] != "QUESTION_CLOSED":
        return {"ok": True, "note": "question not closed"}
    payload = _question_distribution_payload(session)
    if payload is None:
        return {"ok": True, "note": "no current question"}
    await manager.broadcast(session["session_code"], payload)
    return {"ok": True}


@router.post("/show-leaderboard")
async def show_leaderboard(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    session_service.update_state(session["id"], "LEADERBOARD")
    board = scoring_service.leaderboard(session["id"])
    await manager.broadcast(
        session["session_code"], {"type": "show_leaderboard", "board": board}
    )
    return {"ok": True}


@router.post("/finish")
async def finish_session(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        raise HTTPException(404)
    session_service.mark_ended(session["id"])
    board = scoring_service.leaderboard(session["id"])
    await manager.broadcast(
        session["session_code"], {"type": "session_finished", "board": board}
    )
    return {"ok": True}


@router.post("/reset-session")
async def reset_session(teacher_auth: Optional[str] = Cookie(default=None)):
    _require_teacher(teacher_auth)
    session = session_service.get_current_session()
    if session is None:
        return {"ok": True}
    
    old_session_id = session["id"]
    old_code = session["session_code"]
    
    # Mark old session as finished
    session_service.mark_ended(old_session_id)
    
    # Create a new empty waiting session. Keep the old players attached to the
    # finished session so teacher reports remain historically accurate.
    session_service.ensure_current_session()
    
    # Close all student WebSocket connections for old session
    await manager.close_students(old_code)
    
    # Broadcast to old session code (for any remaining connections)
    await manager.broadcast(old_code, {"type": "quiz_reset"})
    
    return {"ok": True}


# ---------- helpers ----------
async def _go_to_question(code: str, index: int) -> None:
    """Activate a specific question index, or finish session if past the end."""
    session = session_service.get_session_by_code(code)
    quiz = quiz_service.get_quiz(session["quiz_id"])
    if index >= len(quiz["questions"]):
        session_service.mark_ended(session["id"])
        board = scoring_service.leaderboard(session["id"])
        await manager.broadcast(code, {"type": "session_finished", "board": board})
        return

    started_at = time.time()
    session_service.set_current_question(session["id"], index, started_at)
    session_service.update_state(session["id"], "QUESTION_ACTIVE")

    q = quiz["questions"][index]
    public_q = session_service.question_public(q)
    await manager.broadcast(
        code,
        {
            "type": "question_started",
            "index": index,
            "total": len(quiz["questions"]),
            "question": public_q,
            "started_at": started_at,
        },
    )


async def _close_current_question(session: dict) -> None:
    session_service.update_state(session["id"], "QUESTION_CLOSED")
    session = session_service.get_session(session["id"])
    payload = _question_distribution_payload(session)
    if payload is None:
        return

    payload["type"] = "question_ended"
    payload["board_before"] = []

    await manager.broadcast(session["session_code"], payload)


def _question_distribution_payload(session: dict) -> Optional[dict]:
    q = session_service.current_question(session)
    if q is None:
        return None
    public_q = session_service.question_public(q)
    correct_choice = q["choices"][q["correct_choice_index"]]
    dist = answer_service.choice_distribution(session["id"], q["id"])
    board = scoring_service.leaderboard(session["id"])
    total_players = len(player_service.list_players(session["id"]))
    return {
        "type": "distribution_shown",
        "question_id": q["id"],
        "question": public_q,
        "correct_choice_id": correct_choice["id"],
        "correct_choice_index": q["correct_choice_index"],
        "explanation": q.get("explanation") or "",
        "distribution": dist,
        "total_players": total_players,
        "board": board,
    }


# Called from the student WebSocket when an answer comes in.
async def submit_answer_and_notify(
    session_code: str, player_token: str, choice_id: int, client_elapsed_ms: int
) -> dict:
    session = session_service.get_session_by_code(session_code)
    if session is None:
        return {"ok": False, "reason": "no session"}
    if not session_service.is_question_still_open(session):
        return {"ok": False, "reason": "question closed"}

    q = session_service.current_question(session)
    if q is None:
        return {"ok": False, "reason": "no active question"}

    player = player_service.get_player_by_token(player_token)
    if player is None or player["session_id"] != session["id"]:
        return {"ok": False, "reason": "unknown player"}

    valid_choice_ids = {c["id"] for c in q["choices"]}
    if choice_id not in valid_choice_ids:
        return {"ok": False, "reason": "bad choice"}

    total_ms = q["time_limit_seconds"] * 1000
    server_elapsed_ms = int((time.time() - session["current_question_started"]) * 1000)
    elapsed = min(max(server_elapsed_ms, 0), total_ms)

    correct_choice_id = q["choices"][q["correct_choice_index"]]["id"]
    result = answer_service.record_answer(
        session_id=session["id"],
        question_id=q["id"],
        player_id=player["id"],
        selected_choice_id=choice_id,
        response_time_ms=elapsed,
        total_time_ms=total_ms,
        correct_choice_id=correct_choice_id,
    )

    total_score = answer_service.player_total_score(session["id"], player["id"])
    count = answer_service.answer_count(session["id"], q["id"])
    total_players = len(player_service.list_players(session["id"]))

    await manager.send_to_teachers(
        session_code,
        {
            "type": "answer_received",
            "question_id": q["id"],
            "count": count,
            "total_players": total_players,
        },
    )

    return {
        "ok": True,
        "accepted": result["accepted"],
        "is_correct": result["is_correct"],
        "points": result["points"],
        "total_score": total_score,
    }
