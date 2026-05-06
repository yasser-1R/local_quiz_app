"""
Quiz Bot Generator - Simulates realistic student players with persistent profiles.

Features:
    - Persistent student profiles (same avatar across sessions)
    - Variable skill levels (some students perform better than others)
    - Realistic response time distribution
    - Support for both UNIFIED and RANDOM quiz modes
    - Configurable bot count
    - Rich progress display
    - Bot skill distribution: 20% excellent, 50% average, 30% struggling

Usage:
    python bot_generator.py
    python bot_generator.py --host 192.168.1.10 --port 8000 --count 30
    python bot_generator.py --count 10 --seed 42  (reproducible bots)
"""
import argparse
import asyncio
import json
import random
import time
import sys
from dataclasses import dataclass, field
from typing import Optional

import httpx
import websockets

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
DEFAULT_BOT_COUNT = 20

FIRST_NAMES = [
    "ياسين", "محمد", "فاطمة", "عمر", "سارة", "أحمد", "ليلى",
    "كريم", "نور", "حسن", "آمنة", "علي", "هدى", "رشيد",
    "آدم", "آية", "يوسف", "مريم", "طارق", "دينا",
    "خالد", "زينب", "إبراهيم", "سلمى", "عبدالله", "رانيا",
    "سعيد", "نادية", "مصطفى", "لينا", "وليد", "داليا",
    "أمير", "جنى", "حسام", "ملك", "زياد", "تالا",
    "ماجد", "ريم", "عائشة", "بلال", "حنان", "سمير",
    "رزان", "فارس", "غادة", "أنس", "صفا", "هيثم",
]

CHARACTERS = [
    "🦊", "🐻", "🐼", "🐨", "🐯", "🦁",
    "🐸", "🐵", "🦄", "🐙", "🦖", "🐢",
    "🦉", "🐲", "🐳", "🦜", "🦩", "🦎",
    "🐞", "🦋", "🐝", "🦕", "🐺", "🐰",
    "🐶", "🐱", "🦝", "🐧", "🦔", "🐹",
]

COLORS = [
    "#ef4444", "#f97316", "#eab308", "#22c55e",
    "#14b8a6", "#3b82f6", "#a855f7", "#ec4899",
]

ACCESSORIES = [
    "", "👑", "🎩", "🧢", "🎉", "🕶️", "⭐", "❤️", "🔥", "🎀",
]


class SkillLevel:
    EXCELLENT = "excellent"
    AVERAGE = "average"
    STRUGGLING = "struggling"

SKILL_CONFIG = {
    SkillLevel.EXCELLENT: {
        "correct_rate": (0.80, 0.95),
        "response_time": (1.5, 5.0),
        "weight": 0.20,
        "label": "⭐ Excellent",
    },
    SkillLevel.AVERAGE: {
        "correct_rate": (0.45, 0.70),
        "response_time": (3.0, 10.0),
        "weight": 0.50,
        "label": "📚 Moyen",
    },
    SkillLevel.STRUGGLING: {
        "correct_rate": (0.15, 0.40),
        "response_time": (6.0, 15.0),
        "weight": 0.30,
        "label": "💪 En difficulte",
    },
}


@dataclass
class BotProfile:
    nickname: str
    character: str
    color: str
    accessory: str
    skill: str
    correct_rate: tuple
    response_range: tuple
    player_token: Optional[str] = None
    profile_token: Optional[str] = None
    answered: int = 0
    correct: int = 0
    total_points: int = 0
    current_question: int = 0


def assign_skill() -> tuple:
    r = random.random()
    cumulative = 0
    for skill, config in SKILL_CONFIG.items():
        cumulative += config["weight"]
        if r <= cumulative:
            return (
                skill,
                config["correct_rate"],
                config["response_time"],
            )
    return (
        SkillLevel.AVERAGE,
        SKILL_CONFIG[SkillLevel.AVERAGE]["correct_rate"],
        SKILL_CONFIG[SkillLevel.AVERAGE]["response_time"],
    )


used_names = set()


def make_bot_profile() -> BotProfile:
    while True:
        base = random.choice(FIRST_NAMES)
        suffix = random.randint(1, 99)
        name = f"{base}{suffix}"
        if name not in used_names:
            used_names.add(name)
            break

    skill, correct_rate, response_range = assign_skill()

    return BotProfile(
        nickname=name,
        character=random.choice(CHARACTERS),
        color=random.choice(COLORS),
        accessory=random.choice(ACCESSORIES),
        skill=skill,
        correct_rate=correct_rate,
        response_range=response_range,
    )


class BotDisplay:
    def __init__(self, total: int):
        self.total = total
        self.joined = 0
        self.connected = 0
        self.failed = 0
        self.errors = []
        self._start = time.time()

    def print_header(self, host: str, port: int):
        print(f"\n{'=' * 60}")
        print(f"  Quiz Bot Generator v2")
        print(f"  Server: {host}:{port}")
        print(f"  Bots: {self.total}")
        print(f"{'=' * 60}\n")

    def joined(self, name: str, skill: str):
        self.joined += 1
        self._update()
        print(f"  [{self.joined}/{self.total}] + {name} ({skill})")

    def connected(self, name: str):
        self.connected += 1

    def failed(self, name: str, reason: str):
        self.failed += 1
        self._update()
        print(f"  [{self.failed} FAIL] - {name}: {reason}")

    def answered(self, name: str, q: int, correct: bool, points: int):
        status = "✅" if correct else "❌"
        pts = f"+{points}" if correct else ""
        print(f"    {status} {name}: Q{q} {pts}")

    def finished(self, name: str, score: int, correct: int, total: int):
        rate = f"{correct}/{total}" if total else "0/0"
        print(f"  🏁 {name}: {score} pts ({rate})")

    def done(self):
        elapsed = time.time() - self._start
        print(f"\n{'=' * 60}")
        print(f"  Terminé en {elapsed:.1f}s")
        print(f"  Reussites: {self.joined} joins | {self.connected} connectes | {self.failed} echecs")
        print(f"{'=' * 60}\n")

    def _update(self):
        progress = self.joined + self.failed
        if self.total > 0:
            pct = progress / self.total * 100
            bar_len = 30
            filled = int(bar_len * progress / self.total)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"  [{bar}] {progress}/{self.total} ({pct:.0f}%)")


def should_answer_correctly(bot: BotProfile) -> bool:
    low, high = bot.correct_rate
    threshold = random.uniform(low, high)
    return random.random() < threshold


def get_response_time(bot: BotProfile) -> float:
    low, high = bot.response_range
    return random.uniform(low, high)


async def join_and_run_bot(
    host: str,
    port: int,
    bot: BotProfile,
    display: BotDisplay,
) -> None:
    url = f"http://{host}:{port}"

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{url}/join",
                data={
                    "nickname": bot.nickname,
                    "avatar_character": bot.character,
                    "avatar_color": bot.color,
                    "avatar_accessory": bot.accessory,
                },
                follow_redirects=True,
            )
        except Exception as e:
            display.failed(bot.nickname, str(e))
            return

        token = None
        if resp.cookies:
            token = resp.cookies.get("player_token")
        if not token:
            for r in resp.history:
                if r.cookies.get("player_token"):
                    token = r.cookies.get("player_token")
                    break

        if not token:
            display.failed(bot.nickname, "No token received")
            return

        bot.player_token = token
        display.joined(bot.nickname, SKILL_CONFIG[bot.skill]["label"])

        await _ws_loop(host, port, token, bot, display)


async def _ws_loop(
    host: str,
    port: int,
    token: str,
    bot: BotProfile,
    display: BotDisplay,
) -> None:
    uri = f"ws://{host}:{port}/ws/student/{token}"
    try:
        async with websockets.connect(uri) as ws:
            display.connected(bot.nickname)

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=120)
                except asyncio.TimeoutError:
                    break

                msg = json.loads(raw)
                mtype = msg.get("type")

                if mtype == "question_started":
                    await _handle_question(ws, msg, bot, display)

                elif mtype == "random_question_started":
                    await _handle_question(ws, msg, bot, display)

                elif mtype == "answer_result":
                    is_correct = msg.get("is_correct", False)
                    points = msg.get("points", 0)
                    bot.answered += 1
                    if is_correct:
                        bot.correct += 1
                        bot.total_points += points
                    display.answered(
                        bot.nickname,
                        bot.current_question,
                        is_correct,
                        points,
                    )

                elif mtype == "session_finished":
                    display.finished(
                        bot.nickname,
                        bot.total_points,
                        bot.correct,
                        bot.answered,
                    )
                    break

                elif mtype == "bulk_correction":
                    board = msg.get("board", [])
                    me = next((p for p in board if p.get("nickname") == bot.nickname), None)
                    if me:
                        display.finished(
                            bot.nickname,
                            me.get("total_score", bot.total_points),
                            bot.correct,
                            bot.answered,
                        )
                    break

                elif mtype == "quiz_reset":
                    print(f"  🔄 {bot.nickname}: Quiz reset")
                    break

    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        print(f"  ⚠ {bot.nickname}: {e}")


async def _handle_question(
    ws,
    msg: dict,
    bot: BotProfile,
    display: BotDisplay,
):
    bot.current_question = msg.get("index", 0) + 1
    choices = msg.get("question", {}).get("choices", [])
    if not choices:
        return

    delay = get_response_time(bot)
    await asyncio.sleep(delay)

    if should_answer_correctly(bot):
        correct_idx = msg.get("question", {}).get("correct_choice_index")
        if correct_idx is not None and correct_idx < len(choices):
            pick = choices[correct_idx]
        else:
            pick = random.choice(choices)
    else:
        wrong_choices = choices[:]
        correct_idx = msg.get("question", {}).get("correct_choice_index")
        if correct_idx is not None and correct_idx < len(wrong_choices):
            wrong_choices.pop(correct_idx)
        if wrong_choices:
            pick = random.choice(wrong_choices)
        else:
            pick = random.choice(choices)

    elapsed_ms = int(delay * 1000)
    await ws.send(json.dumps({
        "type": "submit_answer",
        "choice_id": pick["id"],
        "elapsed_ms": elapsed_ms,
    }))


async def main():
    parser = argparse.ArgumentParser(
        description="Quiz Bot Generator v2 - Realistic student simulation"
    )
    parser.add_argument("--host", type=str, default=SERVER_HOST, help="Server host")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="Server port")
    parser.add_argument("--count", type=int, default=DEFAULT_BOT_COUNT, help="Number of bots")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--stagger", type=float, default=0.3, help="Delay between bot joins (seconds)")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    display = BotDisplay(args.count)
    display.print_header(args.host, args.port)

    bots = [make_bot_profile() for _ in range(args.count)]

    print("  Bot distribution:")
    skill_counts = {}
    for b in bots:
        skill_counts[b.skill] = skill_counts.get(b.skill, 0) + 1
    for skill, count in sorted(skill_counts.items()):
        label = SKILL_CONFIG[skill]["label"]
        print(f"    {label}: {count} bots")
    print()

    tasks = []
    for bot in bots:
        tasks.append(join_and_run_bot(args.host, args.port, bot, display))
        await asyncio.sleep(args.stagger)

    await asyncio.gather(*tasks)
    display.done()

    total_correct = sum(b.correct for b in bots)
    total_answered = sum(b.answered for b in bots)
    overall_rate = (total_correct / total_answered * 100) if total_answered else 0
    print(f"  Classement global des bots:")
    print(f"    Total bonnes reponses: {total_correct}/{total_answered} ({overall_rate:.1f}%)")
    print(f"    Points totaux: {sum(b.total_points for b in bots)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
