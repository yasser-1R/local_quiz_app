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
