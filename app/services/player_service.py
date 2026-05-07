"""Player join / reconnect logic."""
from typing import Optional

from ..config import AVATAR_CHARACTERS, AVATAR_COLORS, AVATAR_ACCESSORIES
from ..database import db_cursor, get_connection
from ..utils.code_generator import generate_player_token


def _player_row(row) -> dict:
    d = dict(row)
    d.setdefault("avatar_character", "🦊")
    d.setdefault("avatar_color", "#6366f1")
    d.setdefault("avatar_accessory", "")
    d.setdefault("student_id", None)
    d.setdefault("random_progress", -1)
    return d


def list_players(session_id: int) -> list:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, token, nickname, avatar_character, avatar_color, avatar_accessory, "
            "       student_id, random_progress, is_connected "
            "FROM players WHERE session_id=? ORDER BY joined_at",
            (session_id,),
        ).fetchall()
        return [_player_row(r) for r in rows]
    finally:
        conn.close()


def nickname_taken(session_id: int, nickname: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM players WHERE session_id=? AND LOWER(nickname)=LOWER(?)",
            (session_id, nickname),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _valid(character: str, color: str, accessory: str):
    if character not in AVATAR_CHARACTERS:
        character = AVATAR_CHARACTERS[0]
    if color not in [c["value"] for c in AVATAR_COLORS]:
        color = AVATAR_COLORS[0]["value"]
    valid_acc = [a["value"] for a in AVATAR_ACCESSORIES]
    if accessory not in valid_acc:
        accessory = ""
    return character, color, accessory


def add_player(
    session_id: int,
    nickname: str,
    character: str,
    color: str,
    accessory: str,
    student_id: Optional[int] = None,
) -> dict:
    character, color, accessory = _valid(character, color, accessory)
    token = generate_player_token()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO players "
            "(session_id, token, nickname, avatar_character, avatar_color, avatar_accessory, student_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, token, nickname, character, color, accessory, student_id),
        )
        pid = cur.lastrowid
    return {
        "id": pid,
        "session_id": session_id,
        "token": token,
        "nickname": nickname,
        "avatar_character": character,
        "avatar_color": color,
        "avatar_accessory": accessory,
        "student_id": student_id,
        "random_progress": -1,
    }


def get_player_by_token(token: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM players WHERE token=?", (token,)
        ).fetchone()
        return _player_row(row) if row else None
    finally:
        conn.close()


def set_connected(token: str, connected: bool) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE players SET is_connected=? WHERE token=?",
            (1 if connected else 0, token),
        )


def update_random_progress(player_id: int, new_progress: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE players SET random_progress=? WHERE id=?",
            (new_progress, player_id),
        )


def move_player_to_session(player_id: int, new_session_id: int) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE players SET session_id=? WHERE id=?",
            (new_session_id, player_id),
        )
