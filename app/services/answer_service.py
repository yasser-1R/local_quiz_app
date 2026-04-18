"""Answer submission and tallying."""
from ..database import db_cursor, get_connection
from . import scoring_service


def record_answer(
    session_id: int,
    question_id: int,
    player_id: int,
    selected_choice_id: int,
    response_time_ms: int,
    total_time_ms: int,
    correct_choice_id: int,
) -> dict:
    is_correct = selected_choice_id == correct_choice_id
    points = scoring_service.compute_score(is_correct, response_time_ms, total_time_ms)

    with db_cursor() as cur:
        # INSERT OR IGNORE -- server accepts only the first answer per player per question
        cur.execute(
            """
            INSERT OR IGNORE INTO answers
              (session_id, question_id, player_id, selected_choice_id,
               response_time_ms, is_correct, points_awarded)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                session_id, question_id, player_id, selected_choice_id,
                response_time_ms, 1 if is_correct else 0, points,
            ),
        )
        # Was it actually inserted? If not, fetch the existing row.
        if cur.rowcount == 0:
            row = cur.execute(
                "SELECT is_correct, points_awarded FROM answers "
                "WHERE session_id=? AND question_id=? AND player_id=?",
                (session_id, question_id, player_id),
            ).fetchone()
            return {
                "accepted": False,
                "is_correct": bool(row["is_correct"]),
                "points": row["points_awarded"],
            }
    return {"accepted": True, "is_correct": is_correct, "points": points}


def answer_count(session_id: int, question_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM answers WHERE session_id=? AND question_id=?",
            (session_id, question_id),
        ).fetchone()
        return row["c"]
    finally:
        conn.close()


def choice_distribution(session_id: int, question_id: int) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT selected_choice_id, COUNT(*) AS c FROM answers "
            "WHERE session_id=? AND question_id=? GROUP BY selected_choice_id",
            (session_id, question_id),
        ).fetchall()
        return {r["selected_choice_id"]: r["c"] for r in rows}
    finally:
        conn.close()


def player_total_score(session_id: int, player_id: int) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(points_awarded),0) AS s FROM answers "
            "WHERE session_id=? AND player_id=?",
            (session_id, player_id),
        ).fetchone()
        return row["s"]
    finally:
        conn.close()
