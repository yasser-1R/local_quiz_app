"""Teacher analytics/reporting helpers."""
from __future__ import annotations

from ..database import get_connection
from . import quiz_service, scoring_service


# ─────────────────────────────────────────────
#  LIST HELPERS  (used by reports index page)
# ─────────────────────────────────────────────

def list_finished_sessions() -> list[dict]:
    """Return archived quiz sessions newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.quiz_id, s.session_code, s.started_at, s.ended_at, s.mode,
                   q.title AS quiz_title,
                   COUNT(DISTINCT p.id) AS player_count,
                   COUNT(DISTINCT qs.id) AS question_count
            FROM sessions s
            LEFT JOIN quizzes q ON q.id = s.quiz_id
            LEFT JOIN players p ON p.session_id = s.id
            LEFT JOIN questions qs ON qs.quiz_id = s.quiz_id
            WHERE s.state = 'FINISHED' AND s.quiz_id IS NOT NULL
            GROUP BY s.id
            ORDER BY s.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_quizzes_with_stats() -> list[dict]:
    """Return all quizzes with aggregated finished-session statistics."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT q.id, q.title, q.description, q.category, q.created_at,
                   COUNT(DISTINCT s.id)  AS session_count,
                   COUNT(DISTINCT p.id)  AS total_players,
                   COUNT(DISTINCT qs.id) AS question_count
            FROM quizzes q
            LEFT JOIN sessions s  ON s.quiz_id = q.id AND s.state = 'FINISHED'
            LEFT JOIN players  p  ON p.session_id = s.id
            LEFT JOIN questions qs ON qs.quiz_id = q.id
            GROUP BY q.id
            ORDER BY session_count DESC, q.id DESC
        """).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            if d['session_count'] > 0:
                sr = conn.execute("""
                    SELECT COUNT(CASE WHEN a.is_correct = 1 THEN 1 END) AS correct,
                           COUNT(a.id) AS total
                    FROM answers a
                    JOIN sessions s ON s.id = a.session_id
                    WHERE s.quiz_id = ? AND s.state = 'FINISHED'
                """, (d['id'],)).fetchone()
                d['avg_success_rate'] = (
                    round(sr['correct'] / sr['total'] * 100, 1)
                    if sr and sr['total'] else 0
                )
            else:
                d['avg_success_rate'] = 0
            result.append(d)
        return result
    finally:
        conn.close()


def list_students_with_stats() -> list[dict]:
    """Return all student accounts with performance statistics."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT st.id, st.pseudo, st.avatar_character, st.avatar_color,
                   st.avatar_accessory, st.created_at,
                   COUNT(DISTINCT p.session_id)         AS session_count,
                   COALESCE(SUM(a.points_awarded), 0)   AS total_score,
                   COALESCE(SUM(a.is_correct), 0)       AS total_correct,
                   COUNT(a.id)                           AS total_answers
            FROM students st
            LEFT JOIN players  p  ON p.student_id = st.id
            LEFT JOIN sessions s  ON s.id = p.session_id AND s.state = 'FINISHED'
            LEFT JOIN answers  a  ON a.player_id = p.id AND a.session_id = s.id
            GROUP BY st.id
            ORDER BY total_score DESC
        """).fetchall()

        result = []
        for row in rows:
            d = dict(row)
            d['success_rate'] = (
                round(d['total_correct'] / d['total_answers'] * 100, 1)
                if d['total_answers'] else 0
            )
            result.append(d)
        return result
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  SESSION REPORT
# ─────────────────────────────────────────────

def build_session_report(session_id: int) -> dict | None:
    conn = get_connection()
    try:
        session = conn.execute(
            "SELECT * FROM sessions WHERE id=? AND quiz_id IS NOT NULL",
            (session_id,),
        ).fetchone()
        if session is None:
            return None
        session = dict(session)

        quiz = quiz_service.get_quiz(session["quiz_id"])
        if quiz is None:
            return None

        players = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, nickname, avatar_character, avatar_color, avatar_accessory
                FROM players
                WHERE session_id=?
                ORDER BY joined_at, id
                """,
                (session_id,),
            ).fetchall()
        ]
        player_count = len(players)

        answers = [
            dict(r)
            for r in conn.execute(
                """
                SELECT a.*, p.nickname
                FROM answers a
                JOIN players p ON p.id = a.player_id
                WHERE a.session_id=?
                """,
                (session_id,),
            ).fetchall()
        ]
        answers_by_question: dict[int, list[dict]] = {}
        answers_by_player_question: dict[tuple[int, int], dict] = {}
        for answer in answers:
            answers_by_question.setdefault(answer["question_id"], []).append(answer)
            answers_by_player_question[(answer["player_id"], answer["question_id"])] = answer

        question_reports = []
        total_correct_ratio = 0.0
        for idx, q in enumerate(quiz["questions"], start=1):
            q_answers = answers_by_question.get(q["id"], [])
            correct_count = sum(1 for a in q_answers if a["is_correct"])
            success_rate = (correct_count / player_count * 100) if player_count else 0
            total_correct_ratio += success_rate

            response_times = [
                a["response_time_ms"] for a in q_answers if a["response_time_ms"] is not None
            ]
            avg_response_ms = (
                round(sum(response_times) / len(response_times)) if response_times else None
            )

            distribution = []
            for choice in q["choices"]:
                count = sum(1 for a in q_answers if a["selected_choice_id"] == choice["id"])
                percent = (count / player_count * 100) if player_count else 0
                distribution.append({
                    "choice_id": choice["id"],
                    "choice_text": choice["choice_text"],
                    "choice_order": choice["choice_order"],
                    "count": count,
                    "percent": round(percent, 1),
                    "is_correct": choice["choice_order"] == q["correct_choice_index"],
                })

            unanswered = max(player_count - len(q_answers), 0)
            if player_count:
                distribution.append({
                    "choice_id": None,
                    "choice_text": "Sans reponse",
                    "choice_order": 99,
                    "count": unanswered,
                    "percent": round(unanswered / player_count * 100, 1),
                    "is_correct": False,
                })

            question_reports.append({
                "number": idx,
                "id": q["id"],
                "text": q["question_text"],
                "success_rate": round(success_rate, 1),
                "correct_count": correct_count,
                "answer_count": len(q_answers),
                "unanswered_count": unanswered,
                "avg_response_ms": avg_response_ms,
                "avg_response_seconds": _seconds(avg_response_ms),
                "distribution": distribution,
            })

        leaderboard = scoring_service.leaderboard(session_id)
        score_by_player = {p["id"]: p for p in leaderboard}

        student_reports = []
        for player in players:
            rows = []
            times = []
            correct_answers = 0
            for idx, q in enumerate(quiz["questions"], start=1):
                answer = answers_by_player_question.get((player["id"], q["id"]))
                selected_choice = None
                if answer is not None:
                    selected_choice = next(
                        (
                            c["choice_text"]
                            for c in q["choices"]
                            if c["id"] == answer["selected_choice_id"]
                        ),
                        None,
                    )
                    if answer["response_time_ms"] is not None:
                        times.append(answer["response_time_ms"])
                    if answer["is_correct"]:
                        correct_answers += 1
                rows.append({
                    "number": idx,
                    "question": q["question_text"],
                    "answered": answer is not None,
                    "is_correct": bool(answer["is_correct"]) if answer else False,
                    "selected_choice": selected_choice or "Sans reponse",
                    "response_seconds": _seconds(answer["response_time_ms"]) if answer else None,
                    "points": answer["points_awarded"] if answer else 0,
                })

            avg_ms = round(sum(times) / len(times)) if times else None
            board_row = score_by_player.get(player["id"], {})
            # Lookup student_id if player has one
            p_row = conn.execute(
                "SELECT student_id FROM players WHERE id=?", (player["id"],)
            ).fetchone()
            student_reports.append({
                **player,
                "student_id": p_row["student_id"] if p_row else None,
                "questions": rows,
                "total_score": board_row.get("total_score", 0),
                "correct_answers": correct_answers,
                "success_rate": round((correct_answers / len(quiz["questions"]) * 100), 1)
                if quiz["questions"] else 0,
                "avg_response_ms": avg_ms,
                "avg_response_seconds": _seconds(avg_ms),
            })

        score_values = [p["total_score"] for p in leaderboard]
        class_success = (
            round(total_correct_ratio / len(question_reports), 1) if question_reports else 0
        )
        problematic = sorted(question_reports, key=lambda q: q["success_rate"])[:3]

        return {
            "session": session,
            "quiz": quiz,
            "players": players,
            "questions": question_reports,
            "students": student_reports,
            "leaderboard": leaderboard,
            "overview": {
                "player_count": player_count,
                "question_count": len(question_reports),
                "average_success_rate": class_success,
                "average_score": round(sum(score_values) / len(score_values), 1)
                if score_values else 0,
                "min_score": min(score_values) if score_values else 0,
                "max_score": max(score_values) if score_values else 0,
                "problematic_questions": problematic,
                "score_distribution": _score_distribution(score_values),
            },
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  QUIZ REPORT  (all sessions of one quiz)
# ─────────────────────────────────────────────

def build_quiz_report(quiz_id: int) -> dict | None:
    """Aggregated report for a quiz across every finished session."""
    conn = get_connection()
    try:
        quiz = quiz_service.get_quiz(quiz_id)
        if quiz is None:
            return None

        sessions = conn.execute("""
            SELECT s.id, s.session_code, s.started_at, s.ended_at, s.mode,
                   COUNT(DISTINCT p.id) AS player_count
            FROM sessions s
            LEFT JOIN players p ON p.session_id = s.id
            WHERE s.quiz_id = ? AND s.state = 'FINISHED'
            GROUP BY s.id
            ORDER BY s.id ASC
        """, (quiz_id,)).fetchall()
        sessions = [dict(s) for s in sessions]

        n_questions = len(quiz["questions"])

        session_stats = []
        for sess in sessions:
            sid = sess["id"]
            n_players = sess["player_count"]

            row = conn.execute("""
                SELECT COUNT(*)               AS total,
                       SUM(is_correct)        AS correct,
                       SUM(points_awarded)    AS pts
                FROM answers WHERE session_id=?
            """, (sid,)).fetchone()

            total   = row["total"] or 0
            correct = row["correct"] or 0
            denom   = n_players * n_questions if n_players and n_questions else 0
            sr      = round(correct / denom * 100, 1) if denom else 0
            avg_sc  = round((row["pts"] or 0) / n_players, 0) if n_players else 0

            session_stats.append({
                **sess,
                "answer_count":  total,
                "correct_count": correct,
                "success_rate":  sr,
                "avg_score":     avg_sc,
            })

        # Per-question stats across ALL sessions of this quiz
        question_stats = []
        for q in quiz["questions"]:
            q_ans = conn.execute("""
                SELECT a.is_correct, a.response_time_ms, a.selected_choice_id
                FROM answers a
                JOIN sessions s ON s.id = a.session_id
                WHERE a.question_id=? AND s.quiz_id=? AND s.state='FINISHED'
            """, (q["id"], quiz_id)).fetchall()

            n_total   = len(q_ans)
            n_correct = sum(1 for a in q_ans if a["is_correct"])
            times     = [a["response_time_ms"] for a in q_ans if a["response_time_ms"]]
            avg_ms    = round(sum(times) / len(times)) if times else None

            distribution = []
            for choice in q["choices"]:
                cnt = sum(1 for a in q_ans if a["selected_choice_id"] == choice["id"])
                distribution.append({
                    "choice_text": choice["choice_text"],
                    "count":       cnt,
                    "percent":     round(cnt / n_total * 100, 1) if n_total else 0,
                    "is_correct":  choice["choice_order"] == q["correct_choice_index"],
                })

            question_stats.append({
                "id":                  q["id"],
                "text":                q["question_text"],
                "total_answers":       n_total,
                "correct_count":       n_correct,
                "success_rate":        round(n_correct / n_total * 100, 1) if n_total else 0,
                "avg_response_seconds": _seconds(avg_ms),
                "distribution":        distribution,
            })

        total_sessions = len(sessions)
        total_players  = sum(s["player_count"] for s in sessions)
        avg_success    = (
            round(sum(s["success_rate"] for s in session_stats) / total_sessions, 1)
            if total_sessions else 0
        )

        sorted_ss = sorted(session_stats, key=lambda s: s["success_rate"])
        return {
            "quiz":      quiz,
            "sessions":  session_stats,
            "questions": question_stats,
            "overview": {
                "total_sessions":   total_sessions,
                "total_players":    total_players,
                "avg_success_rate": avg_success,
                "best_session":     sorted_ss[-1] if sorted_ss else None,
                "worst_session":    sorted_ss[0]  if sorted_ss else None,
            },
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  STUDENT REPORT  (one student, all sessions)
# ─────────────────────────────────────────────

def build_student_report(student_id: int) -> dict | None:
    """Report for a student account across every finished session."""
    conn = get_connection()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE id=?", (student_id,)
        ).fetchone()
        if student is None:
            return None
        student = dict(student)

        parts = conn.execute("""
            SELECT p.id AS player_id, p.session_id, p.nickname AS player_nickname,
                   s.session_code, s.started_at, s.ended_at,
                   q.id AS quiz_id, q.title AS quiz_title,
                   COUNT(DISTINCT qs.id) AS question_count
            FROM players p
            JOIN sessions s  ON s.id = p.session_id AND s.state = 'FINISHED'
            LEFT JOIN quizzes   q  ON q.id  = s.quiz_id
            LEFT JOIN questions qs ON qs.quiz_id = q.id
            WHERE p.student_id = ?
            GROUP BY p.id
            ORDER BY s.id ASC
        """, (student_id,)).fetchall()
        parts = [dict(p) for p in parts]

        session_reports = []
        for part in parts:
            pid     = part["player_id"]
            q_count = part["question_count"] or 1

            ans = conn.execute("""
                SELECT is_correct, points_awarded, response_time_ms
                FROM answers WHERE player_id=?
            """, (pid,)).fetchall()

            n_correct   = sum(1 for a in ans if a["is_correct"])
            total_score = sum(a["points_awarded"] for a in ans)
            times       = [a["response_time_ms"] for a in ans if a["response_time_ms"]]
            avg_ms      = round(sum(times) / len(times)) if times else None

            # Rank within that session
            rank_row = conn.execute("""
                WITH sc AS (
                    SELECT player_id, SUM(points_awarded) AS score
                    FROM answers WHERE session_id=? GROUP BY player_id
                )
                SELECT COUNT(*)+1 AS rank
                FROM sc
                WHERE score > (SELECT COALESCE(score,0) FROM sc WHERE player_id=?)
            """, (part["session_id"], pid)).fetchone()
            rank = rank_row["rank"] if rank_row else None

            total_in_session = conn.execute(
                "SELECT COUNT(*) AS cnt FROM players WHERE session_id=?",
                (part["session_id"],)
            ).fetchone()["cnt"]

            session_reports.append({
                **part,
                "total_score":         total_score,
                "correct_answers":     n_correct,
                "success_rate":        round(n_correct / q_count * 100, 1),
                "avg_response_seconds": _seconds(avg_ms),
                "rank":                rank,
                "total_players":       total_in_session,
            })

        total_score     = sum(s["total_score"]     for s in session_reports)
        total_correct   = sum(s["correct_answers"] for s in session_reports)
        total_questions = sum(s["question_count"]  for s in session_reports)
        avg_success     = (
            round(total_correct / total_questions * 100, 1) if total_questions else 0
        )
        best = (
            max(session_reports, key=lambda s: s["success_rate"])
            if session_reports else None
        )

        return {
            "student":  student,
            "sessions": session_reports,
            "overview": {
                "total_sessions":    len(session_reports),
                "total_score":       total_score,
                "total_correct":     total_correct,
                "total_questions":   total_questions,
                "avg_success_rate":  avg_success,
                "best_session":      best,
            },
        }
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  INTERNAL HELPERS
# ─────────────────────────────────────────────

def _seconds(ms: int | None) -> float | None:
    return round(ms / 1000, 2) if ms is not None else None


def _score_distribution(scores: list[int]) -> list[dict]:
    if not scores:
        return []
    max_score = max(scores)
    if max_score <= 0:
        return [{"label": "0", "count": len(scores), "percent": 100}]

    buckets = [
        ("0–25 %",  0,    0.25),
        ("25–50 %", 0.25, 0.50),
        ("50–75 %", 0.50, 0.75),
        ("75–100 %", 0.75, 1.01),
    ]
    result = []
    for label, low, high in buckets:
        count = sum(1 for s in scores if low <= (s / max_score) < high)
        result.append({
            "label":   label,
            "count":   count,
            "percent": round(count / len(scores) * 100, 1),
        })
    return result
