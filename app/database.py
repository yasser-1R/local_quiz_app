"""SQLite database helpers, schema, and lightweight migrations."""
import sqlite3
from contextlib import contextmanager
from .config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS quizzes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    category      TEXT,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id               INTEGER NOT NULL,
    question_text         TEXT NOT NULL,
    question_order        INTEGER NOT NULL DEFAULT 0,
    time_limit_seconds    INTEGER NOT NULL DEFAULT 20,
    image_path            TEXT,
    explanation           TEXT,
    correct_choice_index  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS choices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id   INTEGER NOT NULL,
    choice_text   TEXT NOT NULL,
    choice_order  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id                  INTEGER,
    session_code             TEXT UNIQUE NOT NULL,
    state                    TEXT NOT NULL DEFAULT 'WAITING',
    mode                     TEXT NOT NULL DEFAULT 'NORMAL',
    connection_mode          TEXT NOT NULL DEFAULT 'BLOCKED',
    current_question_index   INTEGER NOT NULL DEFAULT -1,
    current_question_started REAL,
    started_at               TEXT,
    ended_at                 TEXT,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
);

CREATE TABLE IF NOT EXISTS students (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    pseudo           TEXT UNIQUE NOT NULL,
    password_hash    TEXT NOT NULL,
    avatar_character TEXT,
    avatar_color     TEXT,
    avatar_accessory TEXT,
    auth_token       TEXT,
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS players (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL,
    token             TEXT UNIQUE NOT NULL,
    nickname          TEXT NOT NULL,
    avatar_character  TEXT,
    avatar_color      TEXT,
    avatar_accessory  TEXT,
    student_id        INTEGER,
    random_progress   INTEGER NOT NULL DEFAULT -1,
    joined_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    is_connected      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE IF NOT EXISTS answers (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           INTEGER NOT NULL,
    question_id          INTEGER NOT NULL,
    player_id            INTEGER NOT NULL,
    selected_choice_id   INTEGER,
    submitted_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    response_time_ms     INTEGER,
    is_correct           INTEGER NOT NULL DEFAULT 0,
    points_awarded       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(session_id, question_id, player_id)
);

CREATE TABLE IF NOT EXISTS final_scores (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             INTEGER NOT NULL,
    player_id              INTEGER NOT NULL,
    total_score            INTEGER NOT NULL DEFAULT 0,
    correct_answers        INTEGER NOT NULL DEFAULT 0,
    average_response_time  INTEGER,
    final_rank             INTEGER
);

CREATE TABLE IF NOT EXISTS player_question_orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL,
    player_id   INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    UNIQUE(session_id, player_id, order_index),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


def _column_names(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_sql(conn, name):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return (row["sql"] or "") if row else ""


def _rebuild_table(conn, tname):
    """Rename `tname` to a scratch name, recreate from SCHEMA, copy shared columns back."""
    tmp = f"{tname}__migrate_tmp"
    conn.execute(f"DROP TABLE IF EXISTS {tmp}")
    conn.execute(f"ALTER TABLE {tname} RENAME TO {tmp}")
    conn.executescript(SCHEMA)
    new_cols = _column_names(conn, tname)
    old_cols = _column_names(conn, tmp)
    shared = [c for c in new_cols if c in old_cols]
    cols_csv = ",".join(shared)
    conn.execute(f"INSERT INTO {tname} ({cols_csv}) SELECT {cols_csv} FROM {tmp}")
    conn.execute(f"DROP TABLE {tmp}")


def _migrate(conn) -> None:
    """Add columns / relax constraints for DBs that were created by older versions."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")

    try:
        # Repair any table whose FK still references sessions_old
        for tname in ("players", "answers", "final_scores"):
            sql = _table_sql(conn, tname)
            if "sessions_old" in sql:
                _rebuild_table(conn, tname)

        conn.execute("DROP TABLE IF EXISTS sessions_old")

        # players table — add avatar_* columns if missing (legacy)
        cols = _column_names(conn, "players")
        if "avatar_character" not in cols:
            if "avatar" in cols:
                conn.execute("ALTER TABLE players ADD COLUMN avatar_character TEXT")
                conn.execute("ALTER TABLE players ADD COLUMN avatar_color TEXT")
                conn.execute("ALTER TABLE players ADD COLUMN avatar_accessory TEXT")
                conn.execute(
                    "UPDATE players SET avatar_character = avatar "
                    "WHERE avatar_character IS NULL"
                )
            else:
                conn.execute("ALTER TABLE players ADD COLUMN avatar_character TEXT")
                conn.execute("ALTER TABLE players ADD COLUMN avatar_color TEXT")
                conn.execute("ALTER TABLE players ADD COLUMN avatar_accessory TEXT")

        # players — add student_id and random_progress if missing
        if "student_id" not in cols:
            conn.execute("ALTER TABLE players ADD COLUMN student_id INTEGER")
        if "random_progress" not in cols:
            conn.execute(
                "ALTER TABLE players ADD COLUMN random_progress INTEGER NOT NULL DEFAULT -1"
            )

        # sessions.quiz_id used to be NOT NULL → rebuild to allow NULL
        sql = _table_sql(conn, "sessions")
        if "quiz_id                  INTEGER NOT NULL" in sql:
            _rebuild_table(conn, "sessions")

        # sessions — add mode and connection_mode if missing
        cols = _column_names(conn, "sessions")
        if "mode" not in cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'NORMAL'"
            )
        if "connection_mode" not in cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN connection_mode TEXT NOT NULL DEFAULT 'BLOCKED'"
            )
        # Ensure WAITING/LOBBY sessions default to BLOCKED, not GUEST
        conn.execute(
            "UPDATE sessions SET connection_mode='BLOCKED' "
            "WHERE state IN ('WAITING', 'LOBBY') AND connection_mode='GUEST'"
        )

    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("PRAGMA foreign_keys = ON")


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
