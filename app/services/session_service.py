"""Session / game flow management (single-room, codeless model)."""
import time
from typing import Optional

from ..database import db_cursor, get_connection
from ..utils.code_generator import generate_session_code
from ..config import DEFAULT_QUESTIONS_PER_STUDENT
from . import quiz_service
from . import random_assignment_service


STATES = ("WAITING", "LOBBY", "QUESTION_ACTIVE", "QUESTION_CLOSED", "LEADERBOARD", "FINISHED")
QUIZ_MODES = ("UNIFIED", "RANDOM")


def _new_code() -> str:
    return generate_session_code()


def _create_raw(quiz_id: Optional[int], state: str) -> dict:
    for _ in range(20):
        code = _new_code()
        try:
            with db_cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (quiz_id, session_code, state) VALUES (?,?,?)",
                    (quiz_id, code, state),
                )
                sid = cur.lastrowid
            return {"id": sid, "session_code": code, "state": state, "quiz_id": quiz_id}
        except Exception:
            continue
    raise RuntimeError("Could not generate a unique session code")


def get_session_by_code(code: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_code=?", (code.upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_session(session_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_current_session() -> Optional[dict]:
    """Latest non-finished session (the one players see / play in). None if all finished."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE state != 'FINISHED' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def ensure_current_session() -> dict:
    """Return the current session, creating an empty WAITING one if none exists."""
    s = get_current_session()
    if s is not None:
        return s
    return _create_raw(quiz_id=None, state="WAITING")


def latest_finished_session() -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE state = 'FINISHED' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def launch_quiz(quiz_id: int, quiz_mode: str = "UNIFIED", num_questions: int = DEFAULT_QUESTIONS_PER_STUDENT) -> dict:
    """
    Attach a quiz to the current session so teacher can start it.
    quiz_mode: "UNIFIED" (same questions for all) or "RANDOM" (different questions per student)
    """
    quiz = quiz_service.get_quiz(quiz_id)
    if quiz is None or not quiz["questions"]:
        raise ValueError("quiz must exist and have at least one question")

    if quiz_mode not in QUIZ_MODES:
        quiz_mode = "UNIFIED"

    cur_session = get_current_session()
    if cur_session is None:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (quiz_id, session_code, state, quiz_mode) VALUES (?,?,?,?)",
                (quiz_id, _new_code(), "LOBBY", quiz_mode),
            )
            sid = cur.lastrowid
        session = get_session(sid)
        return session

    if cur_session["state"] == "WAITING":
        with db_cursor() as cur:
            cur.execute(
                "UPDATE sessions SET quiz_id=?, state='LOBBY', quiz_mode=? WHERE id=?",
                (quiz_id, quiz_mode, cur_session["id"]),
            )
        return get_session(cur_session["id"])

    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET state='FINISHED', ended_at=CURRENT_TIMESTAMP WHERE id=?",
            (cur_session["id"],),
        )
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (quiz_id, session_code, state, quiz_mode) VALUES (?,?,?,?)",
            (quiz_id, _new_code(), "LOBBY", quiz_mode),
        )
        sid = cur.lastrowid
    return get_session(sid)


def update_state(session_id: int, state: str) -> None:
    assert state in STATES, state
    with db_cursor() as cur:
        cur.execute("UPDATE sessions SET state=? WHERE id=?", (state, session_id))


def set_current_question(session_id: int, index: int, started_at: Optional[float]) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET current_question_index=?, current_question_started=? "
            "WHERE id=?",
            (index, started_at, session_id),
        )


def current_question(session: dict) -> Optional[dict]:
    if session.get("quiz_id") is None:
        return None
    quiz = quiz_service.get_quiz(session["quiz_id"])
    if quiz is None:
        return None
    idx = session["current_question_index"]
    if idx is None or idx < 0 or idx >= len(quiz["questions"]):
        return None
    return quiz["questions"][idx]


def question_public(q: dict) -> dict:
    """Strip answer key before sending to students."""
    return {
        "id": q["id"],
        "text": q["question_text"],
        "time_limit": q["time_limit_seconds"],
        "choices": [
            {"id": c["id"], "text": c["choice_text"], "order": c["choice_order"]}
            for c in q["choices"]
        ],
    }


def mark_started(session_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET started_at=CURRENT_TIMESTAMP WHERE id=? AND started_at IS NULL",
            (session_id,),
        )


def mark_ended(session_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET ended_at=CURRENT_TIMESTAMP, state='FINISHED' WHERE id=?",
            (session_id,),
        )


def is_question_still_open(session: dict) -> bool:
    if session["state"] != "QUESTION_ACTIVE":
        return False
    q = current_question(session)
    if q is None:
        return False
    started = session["current_question_started"] or 0
    return (time.time() - started) <= q["time_limit_seconds"]
