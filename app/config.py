"""Application configuration."""
import os

# Server
HOST = "0.0.0.0"   # 0.0.0.0 = reachable from other PCs on the LAN
PORT = 8000

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "quizzes.db")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# Teacher login (very simple protection for v1)
TEACHER_PASSWORD = "teacher"

# App
APP_TITLE = "Local Classroom Quiz"

# Game
DEFAULT_QUESTION_TIME = 20          # seconds
BASE_POINTS = 500
MAX_SPEED_BONUS = 500

# Quiz modes
QUIZ_MODES = ["UNIFIED", "RANDOM"]
DEFAULT_QUESTIONS_PER_STUDENT = 10  # default number of questions in random mode

# Avatars: Kahoot-style — pick a character + a background color + an accessory
AVATAR_CHARACTERS = [
    "🦊", "🐻", "🐼", "🐨", "🐯", "🦁",
    "🐸", "🐵", "🦄", "🐙", "🦖", "🐢",
    "🦉", "🐲", "🐳", "🦜", "🦩", "🦎",
    "🐞", "🦋", "🐝", "🦕", "🐺", "🐰",
    "🐶", "🐱", "🦝", "🐧", "🦔", "🐹",
]

AVATAR_COLORS = [
    {"name": "red",    "value": "#ef4444"},
    {"name": "orange", "value": "#f97316"},
    {"name": "amber",  "value": "#eab308"},
    {"name": "green",  "value": "#22c55e"},
    {"name": "teal",   "value": "#14b8a6"},
    {"name": "blue",   "value": "#3b82f6"},
    {"name": "purple", "value": "#a855f7"},
    {"name": "pink",   "value": "#ec4899"},
]

# Accessory is a small emoji overlay on top of the character
AVATAR_ACCESSORIES = [
    {"name": "none",      "value": ""},
    {"name": "crown",     "value": "👑"},
    {"name": "top-hat",   "value": "🎩"},
    {"name": "cap",       "value": "🧢"},
    {"name": "party",     "value": "🎉"},
    {"name": "glasses",   "value": "🕶️"},
    {"name": "star",      "value": "⭐"},
    {"name": "heart",     "value": "❤️"},
    {"name": "flame",     "value": "🔥"},
    {"name": "bow",       "value": "🎀"},
]
