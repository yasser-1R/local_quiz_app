"""Scoring calculations."""
from ..config import BASE_POINTS, MAX_SPEED_BONUS
from ..database import get_connection


def compute_score(is_correct: bool, response_time_ms: int, total_time_ms: int) -> int:
    """
    Kahoot-style scoring:
        correct = BASE_POINTS + speed_bonus (proportional to time left)
        wrong   = 0
    """
    if not is_correct:
        return 0
    if total_time_ms <= 0:
        return BASE_POINTS
    remaining = max(0, total_time_ms - response_time_ms)
    bonus = int(MAX_SPEED_BONUS * (remaining / total_time_ms))
    return BASE_POINTS + bonus


def leaderboard(session_id: int) -> list:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.id, p.nickname,
                   p.avatar_character, p.avatar_color, p.avatar_accessory,
                   COALESCE(SUM(a.points_awarded), 0) AS total_score,
                   COALESCE(SUM(a.is_correct), 0)   AS correct_answers
            FROM players p
            LEFT JOIN answers a ON a.player_id = p.id
            WHERE p.session_id = ?
            GROUP BY p.id
            ORDER BY total_score DESC, correct_answers DESC, p.nickname
            """,
            (session_id,),
        ).fetchall()
        result = []
        for i, r in enumerate(rows, start=1):
            d = dict(r)
            d["rank"] = i
            result.append(d)
        return result
    finally:
        conn.close()


def leaderboard_before_current_question(session_id: int) -> list:
    from . import session_service
    conn = get_connection()
    try:
        session = session_service.get_session(session_id)
        if not session or not session.get("quiz_id"):
            return []

        current_idx = session.get("current_question_index", 0)
        if current_idx <= 0:
            return []

        quiz_questions = conn.execute(
            "SELECT id FROM questions WHERE quiz_id = ? ORDER BY id",
            (session["quiz_id"],)
        ).fetchall()

        if current_idx >= len(quiz_questions):
            return []

        previous_question_ids = [q["id"] for q in quiz_questions[:current_idx]]

        if not previous_question_ids:
            return []

        placeholders = ",".join("?" * len(previous_question_ids))
        rows = conn.execute(
            f"""
            SELECT p.id, p.nickname,
                   p.avatar_character, p.avatar_color, p.avatar_accessory,
                   COALESCE(SUM(a.points_awarded), 0) AS total_score,
                   COALESCE(SUM(a.is_correct), 0)   AS correct_answers
            FROM players p
            LEFT JOIN answers a ON a.player_id = p.id AND a.question_id IN ({placeholders})
            WHERE p.session_id = ?
            GROUP BY p.id
            ORDER BY total_score DESC, correct_answers DESC, p.nickname
            """,
            previous_question_ids + [session_id],
        ).fetchall()

        result = []
        for i, r in enumerate(rows, start=1):
            d = dict(r)
            d["rank"] = i
            result.append(d)
        return result
    finally:
        conn.close()
