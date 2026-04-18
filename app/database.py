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
    current_question_index   INTEGER NOT NULL DEFAULT -1,
    current_question_started REAL,
    started_at               TEXT,
    ended_at                 TEXT,
    FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
);

CREATE TABLE IF NOT EXISTS players (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL,
    token             TEXT UNIQUE NOT NULL,
    nickname          TEXT NOT NULL,
    avatar_character  TEXT,
    avatar_color      TEXT,
    avatar_accessory  TEXT,
    joined_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    is_connected      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
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
    # drop any leftover tmp from a previous failed run
    conn.execute(f"DROP TABLE IF EXISTS {tmp}")
    conn.execute(f"ALTER TABLE {tname} RENAME TO {tmp}")
    # Re-run SCHEMA — because every CREATE has IF NOT EXISTS, only the missing
    # ones (the ones we just renamed away) actually get created.
    conn.executescript(SCHEMA)
    new_cols = _column_names(conn, tname)
    old_cols = _column_names(conn, tmp)
    shared = [c for c in new_cols if c in old_cols]
    cols_csv = ",".join(shared)
    conn.execute(f"INSERT INTO {tname} ({cols_csv}) SELECT {cols_csv} FROM {tmp}")
    conn.execute(f"DROP TABLE {tmp}")


def _migrate(conn) -> None:
    """Add columns / relax constraints for DBs that were created by older versions."""
    # IMPORTANT: on SQLite 3.26+, ALTER TABLE ... RENAME also rewrites foreign
    # key references in OTHER tables. That breaks us: when we rename sessions →
    # sessions_old and then recreate `sessions`, the players/answers FKs point
    # to the now-dropped sessions_old. Turning on "legacy_alter_table" keeps
    # the old behaviour (FK text untouched) while we rebuild.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")

    try:
        # ---- step 1: repair any table whose FK still references sessions_old
        # (happens on a DB that was touched by the previous, buggy migration).
        for tname in ("players", "answers", "final_scores"):
            sql = _table_sql(conn, tname)
            if "sessions_old" in sql:
                _rebuild_table(conn, tname)

        # drop any orphan sessions_old left behind
        conn.execute("DROP TABLE IF EXISTS sessions_old")

        # ---- step 2: players table — add avatar_* columns if missing
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

        # ---- step 3: sessions.quiz_id used to be NOT NULL → rebuild to allow NULL
        sql = _table_sql(conn, "sessions")
        if "quiz_id                  INTEGER NOT NULL" in sql:
            _rebuild_table(conn, "sessions")
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
