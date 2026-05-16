"""Session / game flow management (single-room, codeless model)."""
import random
import time
from typing import Optional

from ..database import db_cursor, get_connection
from ..utils.code_generator import generate_session_code
from . import quiz_service


STATES = (
    "WAITING", "LOBBY",
    "QUESTION_ACTIVE", "QUESTION_CLOSED", "LEADERBOARD",
    "RANDOM_ACTIVE",
    "FINISHED",
)


def _new_code() -> str:
    return generate_session_code()


def _create_raw(
    quiz_id: Optional[int],
    state: str,
    mode: str = "NORMAL",
    connection_mode: str | None = None,
) -> dict:
    if connection_mode is None:
        from ..config import DEFAULT_CONNECTION_MODE
        connection_mode = DEFAULT_CONNECTION_MODE
    for _ in range(20):
        code = _new_code()
        try:
            with db_cursor() as cur:
                cur.execute(
                    "INSERT INTO sessions (quiz_id, session_code, state, mode, connection_mode) "
                    "VALUES (?,?,?,?,?)",
                    (quiz_id, code, state, mode, connection_mode),
                )
                sid = cur.lastrowid
            return {
                "id": sid,
                "session_code": code,
                "state": state,
                "mode": mode,
                "connection_mode": connection_mode,
                "quiz_id": quiz_id,
                "current_question_index": -1,
                "current_question_started": None,
            }
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


def launch_quiz(quiz_id: int) -> dict:
    """
    Attach a quiz to the current session so teacher can start it.
    If current session is WAITING: attach quiz, move to LOBBY.
    If current session has a quiz already: mark it FINISHED, create new one in LOBBY.
    """
    quiz = quiz_service.get_quiz(quiz_id)
    if quiz is None or not quiz["questions"]:
        raise ValueError("quiz must exist and have at least one question")

    cur_session = get_current_session()
    if cur_session is None:
        return _create_raw(quiz_id=quiz_id, state="LOBBY")

    if cur_session["state"] == "WAITING":
        with db_cursor() as cur:
            cur.execute(
                "UPDATE sessions SET quiz_id=?, state='LOBBY' WHERE id=?",
                (quiz_id, cur_session["id"]),
            )
        return get_session(cur_session["id"])

    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET state='FINISHED', ended_at=CURRENT_TIMESTAMP WHERE id=?",
            (cur_session["id"],),
        )
    return _create_raw(quiz_id=quiz_id, state="LOBBY")


def update_state(session_id: int, state: str) -> None:
    assert state in STATES, state
    with db_cursor() as cur:
        cur.execute("UPDATE sessions SET state=? WHERE id=?", (state, session_id))


def update_settings(session_id: int, mode: str, connection_mode: str) -> None:
    """Update session mode and connection_mode (teacher can change before starting)."""
    if mode not in ("NORMAL", "RANDOM"):
        mode = "NORMAL"
    if connection_mode not in ("BLOCKED", "GUEST", "SIGNUP", "LOGIN", "BOTH"):
        connection_mode = "BLOCKED"
    with db_cursor() as cur:
        cur.execute(
            "UPDATE sessions SET mode=?, connection_mode=? WHERE id=?",
            (mode, connection_mode, session_id),
        )


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


# ---------- Random mode helpers ----------

def generate_player_question_orders(session_id: int) -> None:
    """
    For each player in the session, generate a random permutation of all quiz questions
    and store them in player_question_orders.
    """
    conn = get_connection()
    try:
        session = conn.execute(
            "SELECT quiz_id FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if session is None or session["quiz_id"] is None:
            return

        question_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM questions WHERE quiz_id=? ORDER BY question_order, id",
                (session["quiz_id"],),
            ).fetchall()
        ]

        players = conn.execute(
            "SELECT id FROM players WHERE session_id=?", (session_id,)
        ).fetchall()

    finally:
        conn.close()

    with db_cursor() as cur:
        for player in players:
            pid = player["id"]
            # Clear any existing orders for this player
            cur.execute(
                "DELETE FROM player_question_orders WHERE session_id=? AND player_id=?",
                (session_id, pid),
            )
            # Shuffle question order
            shuffled = list(question_ids)
            random.shuffle(shuffled)
            for idx, qid in enumerate(shuffled):
                cur.execute(
                    "INSERT INTO player_question_orders (session_id, player_id, question_id, order_index) "
                    "VALUES (?,?,?,?)",
                    (session_id, pid, qid, idx),
                )
            # Reset player progress to 0 (ready to receive first question)
            cur.execute(
                "UPDATE players SET random_progress=0 WHERE id=?", (pid,)
            )


def get_player_random_question(player_id: int, session_id: int, order_index: int) -> Optional[dict]:
    """Return the question at the given order_index in the player's random sequence."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT q.*, pqo.order_index
            FROM player_question_orders pqo
            JOIN questions q ON q.id = pqo.question_id
            WHERE pqo.player_id=? AND pqo.session_id=? AND pqo.order_index=?
            """,
            (player_id, session_id, order_index),
        ).fetchone()
        if row is None:
            return None
        q = dict(row)
        # Load choices
        choices = conn.execute(
            "SELECT * FROM choices WHERE question_id=? ORDER BY choice_order, id",
            (q["id"],),
        ).fetchall()
        q["choices"] = [dict(c) for c in choices]
        return q
    finally:
        conn.close()


def count_random_questions(session_id: int, player_id: int) -> int:
    """Total number of questions in a player's random order."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM player_question_orders "
            "WHERE session_id=? AND player_id=?",
            (session_id, player_id),
        ).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def all_players_finished_random(session_id: int) -> bool:
    """True when every connected player has completed their random quiz."""
    conn = get_connection()
    try:
        players = conn.execute(
            "SELECT p.id, p.random_progress, "
            "       COUNT(pqo.id) AS total_questions "
            "FROM players p "
            "LEFT JOIN player_question_orders pqo "
            "       ON pqo.player_id=p.id AND pqo.session_id=p.session_id "
            "WHERE p.session_id=? AND p.is_connected=1 "
            "GROUP BY p.id",
            (session_id,),
        ).fetchall()

        if not players:
            return False
        for p in players:
            if p["random_progress"] < p["total_questions"]:
                return False
        return True
    finally:
        conn.close()
