"""
Seed fake student accounts for bot testing in LOGIN mode.

Creates 40 student accounts with predictable credentials.
Run this ONCE before using bots in LOGIN connection mode.

Usage:
    python seed_students.py
    python seed_students.py --reset   # delete existing bot accounts first
"""
import argparse
import os
import sys

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db, db_cursor, get_connection
from app.services.student_service import create_student, get_student_by_pseudo

BOT_PASSWORD = "bot_pass1234"

PSEUDOS = [
    "Bot_Yassin", "Bot_Mohammed", "Bot_Fatima", "Bot_Omar", "Bot_Sara",
    "Bot_Ahmed", "Bot_Layla", "Bot_Karim", "Bot_Nour", "Bot_Hassan",
    "Bot_Amina", "Bot_Ali", "Bot_Huda", "Bot_Rachid", "Bot_Adam",
    "Bot_Aya", "Bot_Youssef", "Bot_Mariam", "Bot_Tarek", "Bot_Dina",
    "Bot_Khalid", "Bot_Zainab", "Bot_Ibrahim", "Bot_Salma", "Bot_Abdullah",
    "Bot_Rania", "Bot_Said", "Bot_Nadia", "Bot_Mustafa", "Bot_Lina",
    "Bot_Walid", "Bot_Dalia", "Bot_Amir", "Bot_Jana", "Bot_Hossam",
    "Bot_Malak", "Bot_Ziad", "Bot_Tala", "Bot_Majid", "Bot_Rim",
]

CHARACTERS = ["🦊","🐻","🐼","🐨","🐯","🦁","🐸","🐵","🦄","🐙",
               "🦖","🐢","🦉","🐲","🐳","🦜","🦩","🦎","🐞","🦋",
               "🐝","🦕","🐺","🐰","🐶","🐱","🦝","🐧","🦔","🐹",
               "🌟","🎯","🚀","🎮","🏆","🎨","🌈","🦸","🧙","🎭"]
COLORS = ["#ef4444","#f97316","#eab308","#22c55e",
          "#14b8a6","#3b82f6","#a855f7","#ec4899",
          "#6366f1","#8b5cf6"]
ACCESSORIES = ["", "👑", "🎩", "🧢", "🎉", "🕶️", "⭐", "❤️", "🔥", "🎀"]


def seed(reset: bool = False) -> None:
    init_db()

    if reset:
        print("Deleting existing bot accounts...")
        with db_cursor() as cur:
            for pseudo in PSEUDOS:
                cur.execute("DELETE FROM students WHERE pseudo=?", (pseudo,))
        print("Done.\n")

    created = 0
    skipped = 0
    for i, pseudo in enumerate(PSEUDOS):
        existing = get_student_by_pseudo(pseudo)
        if existing:
            skipped += 1
            print(f"  [skip] {pseudo} already exists")
            continue
        char = CHARACTERS[i % len(CHARACTERS)]
        color = COLORS[i % len(COLORS)]
        acc = ACCESSORIES[i % len(ACCESSORIES)]
        create_student(pseudo, BOT_PASSWORD, char, color, acc)
        created += 1
        print(f"  [ok]   Created: {pseudo}")

    print(f"\n{'='*40}")
    print(f"  Created : {created}")
    print(f"  Skipped : {skipped} (already exist)")
    print(f"  Password: {BOT_PASSWORD}")
    print(f"  Total   : {len(PSEUDOS)} bot accounts available")
    print(f"{'='*40}")
    print("\nYou can now run bots in LOGIN mode:")
    print("  python bot_generator.py --mode LOGIN")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed fake student accounts for bot testing")
    parser.add_argument("--reset", action="store_true", help="Delete existing bot accounts first")
    args = parser.parse_args()
    seed(reset=args.reset)
