"""Quiz CRUD operations."""
from typing import List, Optional

from ..database import db_cursor, get_connection


def list_quizzes() -> List[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT q.id, q.title, q.description, q.category, q.created_at, "
            "       (SELECT COUNT(*) FROM questions WHERE quiz_id=q.id) AS question_count "
            "FROM quizzes q ORDER BY q.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_quiz(quiz_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
        if row is None:
            return None
        quiz = dict(row)
        questions = conn.execute(
            "SELECT * FROM questions WHERE quiz_id=? ORDER BY question_order, id",
            (quiz_id,),
        ).fetchall()
        quiz["questions"] = []
        for q in questions:
            q = dict(q)
            choices = conn.execute(
                "SELECT * FROM choices WHERE question_id=? ORDER BY choice_order, id",
                (q["id"],),
            ).fetchall()
            q["choices"] = [dict(c) for c in choices]
            quiz["questions"].append(q)
        return quiz
    finally:
        conn.close()


def create_quiz(title: str, description: str, category: str) -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO quizzes (title, description, category) VALUES (?,?,?)",
            (title, description, category),
        )
        return cur.lastrowid


def update_quiz(quiz_id: int, title: str, description: str, category: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE quizzes SET title=?, description=?, category=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (title, description, category, quiz_id),
        )


def delete_quiz(quiz_id: int) -> None:
    with db_cursor() as cur:
        # Find sessions linked to this quiz
        session_rows = cur.execute(
            "SELECT id FROM sessions WHERE quiz_id=?", (quiz_id,)
        ).fetchall()
        session_ids = [r["id"] for r in session_rows]

        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            # answers and final_scores lack ON DELETE CASCADE, remove them first
            cur.execute(
                f"DELETE FROM final_scores WHERE session_id IN ({placeholders})",
                session_ids,
            )
            cur.execute(
                f"DELETE FROM answers WHERE session_id IN ({placeholders})",
                session_ids,
            )
            # players has ON DELETE CASCADE toward sessions, but we delete sessions next
            cur.execute(
                f"DELETE FROM sessions WHERE id IN ({placeholders})",
                session_ids,
            )

        # questions/choices have ON DELETE CASCADE, so deleting quiz is enough
        cur.execute("DELETE FROM quizzes WHERE id=?", (quiz_id,))


def duplicate_quiz(quiz_id: int) -> int:
    original = get_quiz(quiz_id)
    if original is None:
        raise ValueError("quiz not found")
    new_id = create_quiz(
        original["title"] + " (copy)",
        original["description"] or "",
        original["category"] or "",
    )
    for q in original["questions"]:
        qid = add_question(
            new_id,
            q["question_text"],
            q["time_limit_seconds"],
            q["correct_choice_index"],
            q.get("explanation", ""),
            [c["choice_text"] for c in q["choices"]],
        )
    return new_id


def add_question(
    quiz_id: int,
    question_text: str,
    time_limit: int,
    correct_index: int,
    explanation: str,
    choices: List[str],
) -> int:
    with db_cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(question_order), -1)+1 FROM questions WHERE quiz_id=?",
            (quiz_id,),
        )
        order = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO questions (quiz_id, question_text, question_order, "
            "time_limit_seconds, correct_choice_index, explanation) VALUES (?,?,?,?,?,?)",
            (quiz_id, question_text, order, time_limit, correct_index, explanation),
        )
        qid = cur.lastrowid
        for i, text in enumerate(choices):
            cur.execute(
                "INSERT INTO choices (question_id, choice_text, choice_order) VALUES (?,?,?)",
                (qid, text, i),
            )
        return qid


def delete_question(question_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM questions WHERE id=?", (question_id,))


def update_question(
    question_id: int,
    question_text: str,
    time_limit: int,
    correct_index: int,
    explanation: str,
    choices: List[str],
) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE questions SET question_text=?, time_limit_seconds=?, "
            "correct_choice_index=?, explanation=? WHERE id=?",
            (question_text, time_limit, correct_index, explanation, question_id),
        )
        cur.execute("DELETE FROM choices WHERE question_id=?", (question_id,))
        for i, text in enumerate(choices):
            cur.execute(
                "INSERT INTO choices (question_id, choice_text, choice_order) VALUES (?,?,?)",
                (question_id, text, i),
            )
