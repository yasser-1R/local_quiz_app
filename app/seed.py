"""Seed a demo quiz on first run so the teacher has something to launch."""
from .services import quiz_service


DEMO_TITLE = "Demo: General Knowledge"


def ensure_demo_quiz() -> None:
    existing = quiz_service.list_quizzes()
    if any(q["title"] == DEMO_TITLE for q in existing):
        return
    quiz_id = quiz_service.create_quiz(
        title=DEMO_TITLE,
        description="A small sample quiz to try the app.",
        category="General",
    )
    questions = [
        {
            "q": "What is the capital of France?",
            "choices": ["London", "Berlin", "Paris", "Madrid"],
            "correct": 2,
            "time": 15,
            "explanation": "Paris is the capital and largest city of France.",
        },
        {
            "q": "Which planet is known as the Red Planet?",
            "choices": ["Venus", "Mars", "Jupiter", "Saturn"],
            "correct": 1,
            "time": 15,
            "explanation": "Mars appears red because of iron oxide on its surface.",
        },
        {
            "q": "5 + 7 × 2 = ?",
            "choices": ["24", "19", "17", "14"],
            "correct": 1,
            "time": 20,
            "explanation": "Multiplication before addition: 7 × 2 = 14, then 5 + 14 = 19.",
        },
        {
            "q": "Who wrote 'Romeo and Juliet'?",
            "choices": [
                "Charles Dickens",
                "William Shakespeare",
                "Mark Twain",
                "Victor Hugo",
            ],
            "correct": 1,
            "time": 15,
            "explanation": "Written by William Shakespeare around 1595.",
        },
        {
            "q": "What is the largest ocean on Earth?",
            "choices": ["Atlantic", "Indian", "Arctic", "Pacific"],
            "correct": 3,
            "time": 15,
            "explanation": "The Pacific Ocean is the largest and deepest.",
        },
    ]
    for item in questions:
        quiz_service.add_question(
            quiz_id=quiz_id,
            question_text=item["q"],
            time_limit=item["time"],
            correct_index=item["correct"],
            explanation=item["explanation"],
            choices=item["choices"],
        )
