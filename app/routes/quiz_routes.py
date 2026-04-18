"""JSON API for quiz CRUD (used by teacher UI)."""
from typing import List, Optional

from fastapi import APIRouter, Body, Cookie, HTTPException

from ..config import TEACHER_PASSWORD
from ..services import quiz_service


router = APIRouter(prefix="/api/quizzes", tags=["quiz-api"])


def _require(auth: Optional[str]):
    if auth != TEACHER_PASSWORD:
        raise HTTPException(status_code=401, detail="teacher login required")


@router.get("")
async def list_quizzes(teacher_auth: Optional[str] = Cookie(default=None)):
    _require(teacher_auth)
    return quiz_service.list_quizzes()


@router.get("/{quiz_id}")
async def get_quiz(quiz_id: int, teacher_auth: Optional[str] = Cookie(default=None)):
    _require(teacher_auth)
    quiz = quiz_service.get_quiz(quiz_id)
    if quiz is None:
        raise HTTPException(404)
    return quiz


@router.post("")
async def create_quiz(
    payload: dict = Body(...),
    teacher_auth: Optional[str] = Cookie(default=None),
):
    _require(teacher_auth)
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title required")
    quiz_id = quiz_service.create_quiz(
        title=title,
        description=payload.get("description", ""),
        category=payload.get("category", ""),
    )
    for q in payload.get("questions", []):
        quiz_service.add_question(
            quiz_id=quiz_id,
            question_text=q["question_text"],
            time_limit=int(q.get("time_limit_seconds", 20)),
            correct_index=int(q.get("correct_choice_index", 0)),
            explanation=q.get("explanation", ""),
            choices=q.get("choices", []),
        )
    return {"id": quiz_id}


@router.put("/{quiz_id}")
async def update_quiz(
    quiz_id: int,
    payload: dict = Body(...),
    teacher_auth: Optional[str] = Cookie(default=None),
):
    _require(teacher_auth)
    quiz_service.update_quiz(
        quiz_id=quiz_id,
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        category=payload.get("category", ""),
    )
    # Replace all questions with the new list
    current = quiz_service.get_quiz(quiz_id)
    for q in current["questions"]:
        quiz_service.delete_question(q["id"])
    for q in payload.get("questions", []):
        quiz_service.add_question(
            quiz_id=quiz_id,
            question_text=q["question_text"],
            time_limit=int(q.get("time_limit_seconds", 20)),
            correct_index=int(q.get("correct_choice_index", 0)),
            explanation=q.get("explanation", ""),
            choices=q.get("choices", []),
        )
    return {"ok": True}


@router.delete("/{quiz_id}")
async def delete_quiz(quiz_id: int, teacher_auth: Optional[str] = Cookie(default=None)):
    _require(teacher_auth)
    quiz_service.delete_quiz(quiz_id)
    return {"ok": True}


@router.post("/{quiz_id}/duplicate")
async def duplicate_quiz(quiz_id: int, teacher_auth: Optional[str] = Cookie(default=None)):
    _require(teacher_auth)
    new_id = quiz_service.duplicate_quiz(quiz_id)
    return {"id": new_id}
