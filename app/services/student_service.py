"""Persistent student account management."""
import hashlib
import os
import secrets
from typing import Optional

from ..database import db_cursor, get_connection


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + key.hex()


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return secrets.compare_digest(computed, expected)
    except Exception:
        return False


def get_student_by_pseudo(pseudo: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM students WHERE LOWER(pseudo) = LOWER(?)", (pseudo,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_student_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM students WHERE auth_token = ?", (token,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_student(
    pseudo: str, password: str, character: str, color: str, accessory: str
) -> dict:
    token = secrets.token_urlsafe(24)
    pw_hash = _hash_password(password)
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO students
               (pseudo, password_hash, avatar_character, avatar_color, avatar_accessory, auth_token)
               VALUES (?,?,?,?,?,?)""",
            (pseudo, pw_hash, character, color, accessory, token),
        )
        sid = cur.lastrowid
    return {
        "id": sid,
        "pseudo": pseudo,
        "avatar_character": character,
        "avatar_color": color,
        "avatar_accessory": accessory,
        "auth_token": token,
    }


def authenticate_student(pseudo: str, password: str) -> Optional[dict]:
    student = get_student_by_pseudo(pseudo)
    if student is None:
        return None
    if not _verify_password(password, student["password_hash"]):
        return None
    # Rotate token on each login
    token = secrets.token_urlsafe(24)
    with db_cursor() as cur:
        cur.execute("UPDATE students SET auth_token=? WHERE id=?", (token, student["id"]))
    student = dict(student)
    student["auth_token"] = token
    return student


def get_student_stats(student_id: int) -> dict:
    """Get historical performance across all finished quiz sessions."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                s.id                                        AS session_id,
                s.started_at,
                s.ended_at,
                COALESCE(q.title, 'Quiz')                  AS quiz_title,
                COALESCE(SUM(a.points_awarded), 0)         AS total_score,
                COALESCE(SUM(a.is_correct), 0)             AS correct_answers,
                COUNT(DISTINCT a.id)                       AS answered_count,
                COUNT(DISTINCT qs.id)                      AS total_questions
            FROM students st
            JOIN players p   ON p.student_id = st.id
            JOIN sessions s  ON s.id = p.session_id
            LEFT JOIN answers   a  ON a.player_id = p.id AND a.session_id = s.id
            LEFT JOIN questions qs ON qs.quiz_id = s.quiz_id
            LEFT JOIN quizzes   q  ON q.id = s.quiz_id
            WHERE st.id = ?
              AND s.state = 'FINISHED'
              AND s.quiz_id IS NOT NULL
            GROUP BY s.id
            ORDER BY s.id ASC
            """,
            (student_id,),
        ).fetchall()

        sessions = []
        for r in rows:
            d = dict(r)
            tq = d["total_questions"] or 0
            ca = d["correct_answers"] or 0
            d["success_rate"] = round((ca / tq * 100), 1) if tq else 0
            sessions.append(d)

        return {"sessions": sessions}
    finally:
        conn.close()
