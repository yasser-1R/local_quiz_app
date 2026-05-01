"""Reset quiz state (keeps all your quizzes)."""
import sqlite3
from app.config import DB_PATH

def reset():
    print("Resetting quiz state...")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Clear all answers and sessions
    cur.execute("DELETE FROM answers")
    cur.execute("DELETE FROM sessions")

    conn.commit()
    conn.close()
    print("Done! Quiz state cleared. Your quizzes are still saved.")

if __name__ == "__main__":
    reset()
