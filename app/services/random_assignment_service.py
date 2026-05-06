"""Random question assignment from question bank."""
import random
from typing import Optional

from ..database import db_cursor, get_connection
from ..config import DEFAULT_QUESTIONS_PER_STUDENT


def assign_random_questions(
    session_id: int,
    player_id: int,
    quiz_id: int,
    num_questions: int = DEFAULT_QUESTIONS_PER_STUDENT,
) -> list[dict]:
    """Assign a random subset of questions to a player for this session."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM questions WHERE quiz_id=? ORDER BY question_order",
            (quiz_id,),
        ).fetchall()
        all_questions = [dict(r) for r in rows]
    finally:
        conn.close()

    if len(all_questions) <= num_questions:
        assigned = all_questions
    else:
        assigned = random.sample(all_questions, num_questions)

    with db_cursor() as cur:
        for order, q in enumerate(assigned):
            cur.execute(
                "INSERT INTO session_player_questions "
                "(session_id, player_id, question_id, question_order) "
                "VALUES (?,?,?,?)",
                (session_id, player_id, q["id"], order),
            )

    return assigned


def get_player_questions(session_id: int, player_id: int) -> list[dict]:
    """Get questions assigned to a specific player in a session."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT q.*, spq.question_order
            FROM session_player_questions spq
            JOIN questions q ON q.id = spq.question_id
            WHERE spq.session_id=? AND spq.player_id=?
            ORDER BY spq.question_order
            """,
            (session_id, player_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_player_question_ids(session_id: int, player_id: int) -> list[int]:
    """Get just the question IDs assigned to a player."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT question_id FROM session_player_questions "
            "WHERE session_id=? AND player_id=? ORDER BY question_order",
            (session_id, player_id),
        ).fetchall()
        return [r["question_id"] for r in rows]
    finally:
        conn.close()


def get_unified_questions(quiz_id: int) -> list[dict]:
    """Get all questions for unified mode."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM questions WHERE quiz_id=? ORDER BY question_order",
            (quiz_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def player_has_answered_all(session_id: int, player_id: int, question_ids: list[int]) -> bool:
    """Check if a player has answered all their assigned questions."""
    if not question_ids:
        return False
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(question_ids))
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM answers "
            f"WHERE session_id=? AND player_id=? AND question_id IN ({placeholders})",
            [session_id, player_id] + question_ids,
        ).fetchone()
        return row["c"] == len(question_ids)
    finally:
        conn.close()


def get_all_player_completion(session_id: int) -> list[dict]:
    """Get completion status for all players in a session."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.id AS player_id, p.nickname,
                   p.avatar_character, p.avatar_color, p.avatar_accessory,
                   COUNT(DISTINCT a.question_id) AS answered_count,
                   (SELECT COUNT(*) FROM session_player_questions spq WHERE spq.player_id = p.id AND spq.session_id = ?) AS total_questions
            FROM players p
            LEFT JOIN answers a ON a.player_id = p.id AND a.session_id = ?
            WHERE p.session_id = ?
            GROUP BY p.id
            ORDER BY p.nickname
            """,
            (session_id, session_id, session_id),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_unified_completion(session_id: int, total_questions: int) -> list[dict]:
    """Get completion status for all players in unified mode."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.id AS player_id, p.nickname,
                   p.avatar_character, p.avatar_color, p.avatar_accessory,
                   COUNT(a.id) AS answered_count
            FROM players p
            LEFT JOIN answers a ON a.player_id = p.id AND a.session_id = ?
            WHERE p.session_id = ?
            GROUP BY p.id
            ORDER BY p.nickname
            """,
            (session_id, session_id),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["total_questions"] = total_questions
            result.append(d)
        return result
    finally:
        conn.close()
