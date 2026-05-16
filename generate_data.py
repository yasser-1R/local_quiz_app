"""
Populate the database with realistic test data for statistics.
Clears all existing sessions (cascades to players/answers/scores),
then creates ~30 finished sessions across all quizzes.
Run from the project root: python generate_data.py
"""
import hashlib
import os
import random
import secrets
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quizzes.db")

BASE_POINTS = 500
MAX_SPEED_BONUS = 500

CHARACTERS = [
    "🦊", "🐻", "🐼", "🐨", "🐯", "🦁",
    "🐸", "🐵", "🦄", "🐙", "🦖", "🐢",
    "🦉", "🐲", "🐳", "🦜", "🦩", "🦎",
    "🐞", "🦋", "🐝", "🦕", "🐺", "🐰",
    "🐶", "🐱", "🦝", "🐧", "🦔", "🐹",
]
COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#a855f7", "#ec4899"]
ACCESSORIES = ["", "👑", "🎩", "🧢", "🎉", "🕶️", "⭐", "❤️", "🔥", "🎀"]

# 30 French-style student names for a Moroccan classroom
NEW_STUDENTS = [
    ("ahmed_k",    "test1234"), ("leila_b",    "test1234"), ("omar_t",     "test1234"),
    ("fatima_z",   "test1234"), ("younes_m",   "test1234"), ("sara_n",     "test1234"),
    ("karim_a",    "test1234"), ("nadia_h",    "test1234"), ("tarik_r",    "test1234"),
    ("amina_s",    "test1234"), ("yassine_d",  "test1234"), ("soukaina_f", "test1234"),
    ("mehdi_l",    "test1234"), ("hajar_o",    "test1234"), ("amine_c",    "test1234"),
    ("zineb_m",    "test1234"), ("rachid_b",   "test1234"), ("houda_k",    "test1234"),
    ("abdelali_n", "test1234"), ("khadija_r",  "test1234"), ("hamza_s",    "test1234"),
    ("meriem_a",   "test1234"), ("bilal_t",    "test1234"), ("loubna_h",   "test1234"),
    ("mouad_z",    "test1234"), ("chaimae_f",  "test1234"), ("anass_b",    "test1234"),
    ("siham_k",    "test1234"), ("otmane_l",   "test1234"), ("rim_a",      "test1234"),
]


def _hash_password(pwd: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt, 200_000)
    return salt.hex() + ":" + key.hex()


def compute_score(is_correct: bool, elapsed_ms: int, total_ms: int) -> int:
    if not is_correct:
        return 0
    remaining = max(0, total_ms - elapsed_ms)
    bonus = int(MAX_SPEED_BONUS * (remaining / total_ms)) if total_ms > 0 else 0
    return BASE_POINTS + bonus


def random_code(conn) -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(random.choices(chars, k=6))
        if not conn.execute("SELECT 1 FROM sessions WHERE session_code=?", (code,)).fetchone():
            return code


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # ── 1. Clear existing sessions (cascades to players / answers / scores) ──
    print("Clearing sessions...")
    conn.execute("DELETE FROM sessions")
    conn.commit()

    # ── 2. Load all quizzes with their questions + choices ──
    print("Loading quiz data...")
    quizzes = [dict(r) for r in conn.execute(
        "SELECT * FROM quizzes WHERE id IN (SELECT DISTINCT quiz_id FROM questions)"
    ).fetchall()]

    quiz_data = {}
    for q in quizzes:
        questions = conn.execute(
            "SELECT * FROM questions WHERE quiz_id=? ORDER BY question_order, id", (q["id"],)
        ).fetchall()
        q_list = []
        for question in questions:
            choices = conn.execute(
                "SELECT id FROM choices WHERE question_id=? ORDER BY choice_order, id",
                (question["id"],)
            ).fetchall()
            q_list.append({
                "id": question["id"],
                "correct_idx": question["correct_choice_index"],
                "choice_ids": [c["id"] for c in choices],
                "total_ms": question["time_limit_seconds"] * 1000,
            })
        quiz_data[q["id"]] = {"title": q["title"], "questions": q_list}

    print(f"  {len(quizzes)} quizzes, {sum(len(v['questions']) for v in quiz_data.values())} questions total")

    # ── 3. Ensure student accounts exist ──
    print("Creating student accounts...")
    existing = {r["pseudo"] for r in conn.execute("SELECT pseudo FROM students").fetchall()}
    for pseudo, pwd in NEW_STUDENTS:
        if pseudo not in existing:
            conn.execute(
                "INSERT INTO students (pseudo, password_hash, avatar_character, avatar_color, avatar_accessory, auth_token) "
                "VALUES (?,?,?,?,?,?)",
                (pseudo, _hash_password(pwd),
                 random.choice(CHARACTERS), random.choice(COLORS), random.choice(ACCESSORIES),
                 secrets.token_urlsafe(24))
            )
    conn.commit()

    all_students = [dict(r) for r in conn.execute(
        "SELECT id, pseudo, avatar_character, avatar_color, avatar_accessory FROM students"
    ).fetchall()]
    print(f"  {len(all_students)} total students")

    # ── 4. Build session schedule (10 weeks × up to 3 sessions/week) ──
    base_date = datetime(2025, 9, 1, 8, 0)
    schedule = []
    quiz_ids = [q["id"] for q in quizzes]

    for week in range(12):
        week_start = base_date + timedelta(weeks=week)
        for day_offset in [0, 2, 4]:               # Mon / Wed / Fri
            session_date = week_start + timedelta(days=day_offset, hours=random.randint(0, 3))
            quiz_id = random.choice(quiz_ids)
            n_players = random.randint(8, min(22, len(all_students)))
            schedule.append({
                "quiz_id": quiz_id,
                "date": session_date,
                "n_players": n_players,
                "mode": random.choices(["NORMAL", "RANDOM"], weights=[3, 1])[0],
            })

    # Keep 32 sessions, sorted chronologically
    random.shuffle(schedule)
    schedule = sorted(schedule[:32], key=lambda x: x["date"])
    print(f"Creating {len(schedule)} sessions...")

    for sc in schedule:
        quiz_id = sc["quiz_id"]
        questions = quiz_data[quiz_id]["questions"]
        n_q = len(questions)
        if n_q == 0:
            continue

        code = random_code(conn)
        started_at = sc["date"]
        ended_at = started_at + timedelta(minutes=n_q * 2 + random.randint(4, 12))

        conn.execute(
            "INSERT INTO sessions (quiz_id, session_code, state, mode, connection_mode, "
            "current_question_index, started_at, ended_at) VALUES (?,?,'FINISHED',?,'BLOCKED',?,?,?)",
            (quiz_id, code, sc["mode"], n_q - 1,
             started_at.strftime("%Y-%m-%d %H:%M:%S"),
             ended_at.strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # ── Select players ──
        players_sample = random.sample(all_students, sc["n_players"])
        player_rows = []
        for stu in players_sample:
            token = secrets.token_urlsafe(24)
            conn.execute(
                "INSERT INTO players (session_id, token, nickname, avatar_character, avatar_color, "
                "avatar_accessory, student_id, random_progress, is_connected) VALUES (?,?,?,?,?,?,?,?,1)",
                (session_id, token, stu["pseudo"],
                 stu["avatar_character"] or random.choice(CHARACTERS),
                 stu["avatar_color"] or random.choice(COLORS),
                 stu["avatar_accessory"] or "",
                 stu["id"], n_q)
            )
            conn.commit()
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            player_rows.append(pid)

        # Each player gets a "skill" level drawn from a distribution
        skill = {pid: min(0.95, max(0.10, random.gauss(0.62, 0.20))) for pid in player_rows}

        # ── Create answers ──
        for q in questions:
            correct_id = q["choice_ids"][q["correct_idx"]]
            wrong_ids  = [c for c in q["choice_ids"] if c != correct_id]
            total_ms   = q["total_ms"]

            for pid in player_rows:
                # ~8 % chance a player skips a question (was slow / distracted)
                if random.random() < 0.08:
                    continue

                sk = skill[pid]
                is_correct = random.random() < sk

                if is_correct:
                    # Fast answers: beta(2,5) concentrates probability near start of timer
                    ratio = random.betavariate(2, 5)
                    elapsed_ms = int(ratio * total_ms)
                    chosen_id = correct_id
                else:
                    # Wrong answers tend to be later in the timer
                    ratio = min(1.0, random.betavariate(3, 2))
                    elapsed_ms = int(ratio * total_ms)
                    chosen_id = random.choice(wrong_ids) if wrong_ids else correct_id

                pts = compute_score(is_correct, elapsed_ms, total_ms)
                conn.execute(
                    "INSERT INTO answers (session_id, question_id, player_id, selected_choice_id, "
                    "response_time_ms, is_correct, points_awarded) VALUES (?,?,?,?,?,?,?)",
                    (session_id, q["id"], pid, chosen_id, elapsed_ms, int(is_correct), pts)
                )

        conn.commit()

        # ── Create final_scores ──
        scores = conn.execute(
            "SELECT player_id, SUM(points_awarded) AS total, SUM(is_correct) AS correct, "
            "AVG(response_time_ms) AS avg_t FROM answers WHERE session_id=? GROUP BY player_id "
            "ORDER BY total DESC",
            (session_id,)
        ).fetchall()

        for rank, row in enumerate(scores, 1):
            conn.execute(
                "INSERT INTO final_scores (session_id, player_id, total_score, correct_answers, "
                "average_response_time, final_rank) VALUES (?,?,?,?,?,?)",
                (session_id, row["player_id"], row["total"], row["correct"],
                 int(row["avg_t"] or 0), rank)
            )
        conn.commit()

        title_short = quiz_data[quiz_id]["title"][:35]
        print(f"  Session {session_id:3d} | {title_short:<35} | {len(player_rows):2d} players | {sc['mode']}")

    # ── Summary ──
    n_sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE state='FINISHED'").fetchone()[0]
    n_players  = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    n_answers  = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    n_scores   = conn.execute("SELECT COUNT(*) FROM final_scores").fetchone()[0]
    conn.close()

    print(f"\nDone!")
    print(f"  Finished sessions : {n_sessions}")
    print(f"  Players           : {n_players}")
    print(f"  Answers           : {n_answers}")
    print(f"  Final scores      : {n_scores}")


if __name__ == "__main__":
    main()
