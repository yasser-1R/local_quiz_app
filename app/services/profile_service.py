"""Student profile management (persistent across sessions)."""
from typing import Optional

from ..config import AVATAR_CHARACTERS, AVATAR_COLORS, AVATAR_ACCESSORIES
from ..database import db_cursor, get_connection
from ..utils.code_generator import generate_player_token


def get_profile_by_token(token: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM student_profiles WHERE profile_token=?", (token,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_profile_by_nickname(nickname: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM student_profiles WHERE LOWER(nickname)=LOWER(?)", (nickname,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_profile_progress_data(profile_id: int) -> dict:
    """Get progress data for a student profile (for chart display)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT s.id AS session_id, s.session_code, s.started_at, s.ended_at,
                   q.title AS quiz_title,
                   COUNT(DISTINCT a.id) AS answered,
                   SUM(a.is_correct) AS correct,
                   SUM(a.points_awarded) AS total_points
            FROM players p
            JOIN sessions s ON s.id = p.session_id
            LEFT JOIN quizzes q ON q.id = s.quiz_id
            LEFT JOIN answers a ON a.player_id = p.id AND a.session_id = s.id
            WHERE p.profile_id = ? AND s.state = 'FINISHED'
            GROUP BY s.id
            ORDER BY s.started_at
            """,
            (profile_id,),
        ).fetchall()

        sessions = []
        for r in rows:
            d = dict(r)
            session_row = conn.execute("SELECT quiz_id FROM sessions WHERE id=?", (d["session_id"],)).fetchone()
            total_q = 0
            if session_row and session_row["quiz_id"]:
                total_q = conn.execute(
                    "SELECT COUNT(*) AS c FROM questions WHERE quiz_id=?",
                    (session_row["quiz_id"],)
                ).fetchone()["c"]
            d["total_questions"] = total_q
            d["success_rate"] = round((d["correct"] / d["answered"] * 100), 1) if d["answered"] else 0
            d["answered"] = d["answered"] or 0
            d["correct"] = d["correct"] or 0
            d["total_points"] = d["total_points"] or 0
            sessions.append(d)

        return {
            "sessions": sessions,
        }
    finally:
        conn.close()


def create_or_update_profile(
    nickname: str,
    character: str,
    color: str,
    accessory: str,
) -> dict:
    """Create new profile or update existing one with same nickname."""
    existing = get_profile_by_nickname(nickname)
    if existing:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE student_profiles SET avatar_character=?, avatar_color=?, "
                "avatar_accessory=?, last_seen=CURRENT_TIMESTAMP WHERE nickname=?",
                (character, color, accessory, nickname),
            )
        return get_profile_by_nickname(nickname)

    token = generate_player_token()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO student_profiles "
            "(profile_token, nickname, avatar_character, avatar_color, avatar_accessory) "
            "VALUES (?,?,?,?,?)",
            (token, nickname, character, color, accessory),
        )
        pid = cur.lastrowid
    return {
        "id": pid,
        "profile_token": token,
        "nickname": nickname,
        "avatar_character": character,
        "avatar_color": color,
        "avatar_accessory": accessory,
    }


PROFILE_COOKIE = "student_profile_token"
