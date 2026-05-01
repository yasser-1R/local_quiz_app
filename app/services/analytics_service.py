"""Teacher analytics/reporting helpers."""
from __future__ import annotations

from ..database import get_connection
from . import quiz_service, scoring_service


def list_finished_sessions() -> list[dict]:
    """Return archived quiz sessions newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.quiz_id, s.session_code, s.started_at, s.ended_at,
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
            student_reports.append({
                **player,
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


def _seconds(ms: int | None) -> float | None:
    return round(ms / 1000, 2) if ms is not None else None


def _score_distribution(scores: list[int]) -> list[dict]:
    if not scores:
        return []
    max_score = max(scores)
    if max_score <= 0:
        return [{"label": "0", "count": len(scores), "percent": 100}]

    buckets = [
        ("0-25%", 0, 0.25),
        ("25-50%", 0.25, 0.50),
        ("50-75%", 0.50, 0.75),
        ("75-100%", 0.75, 1.01),
    ]
    result = []
    for label, low, high in buckets:
        count = sum(1 for s in scores if low <= (s / max_score) < high)
        result.append({
            "label": label,
            "count": count,
            "percent": round(count / len(scores) * 100, 1),
        })
    return result
