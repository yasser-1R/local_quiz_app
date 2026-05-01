"""
Quiz Bot Generator - Simulates 20 Arabic-named student players.

Usage:
    python bot_generator.py
    python bot_generator.py --host 192.168.1.10 --port 8000
"""
import argparse
import asyncio
import json
import random

import httpx
import websockets

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
BOT_COUNT = 20

FIRST_NAMES = [
    "ياسين", "محمد", "فاطمة", "عمر", "سارة", "أحمد", "ليلى",
    "كريم", "نور", "حسن", "آمنة", "علي", "هدى", "رشيد",
    "آدم", "آية", "يوسف", "مريم", "طارق", "دينا",
    "خالد", "زينب", "إبراهيم", "سلمى", "عبدالله", "رانيا",
    "سعيد", "نادية", "مصطفى", "لينا", "وليد", "داليا",
    "أمير", "جنى", "حسام", "ملك", "زياد", "تالا",
    "ماجد", "ريم",
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

used_names = set()


def make_nickname() -> str:
    while True:
        base = random.choice(FIRST_NAMES)
        suffix = random.randint(1, 99)
        name = f"{base}{suffix}"
        if name not in used_names:
            used_names.add(name)
            return name


async def join_bot(host: str, port: int, nickname: str) -> None:
    url = f"http://{host}:{port}"
    character = random.choice(CHARACTERS)
    color = random.choice(COLORS)
    accessory = random.choice(ACCESSORIES)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{url}/join",
                data={
                    "nickname": nickname,
                    "avatar_character": character,
                    "avatar_color": color,
                    "avatar_accessory": accessory,
                },
                follow_redirects=True,
            )
        except Exception as e:
            print(f"  [{nickname}] Failed to join: {e}")
            return

        token = None
        if resp.cookies:
            token = resp.cookies.get("player_token")
        if not token:
            for r in resp.history:
                if r.cookies.get("player_token"):
                    token = r.cookies.get("player_token")
                    break

        if token:
            print(f"  [{nickname}] Joined!")
        else:
            print(f"  [{nickname}] Join failed (no token)")
            return

        await _ws_loop(host, port, token, nickname)


async def _ws_loop(host: str, port: int, token: str, nickname: str) -> None:
    uri = f"ws://{host}:{port}/ws/student/{token}"
    try:
        async with websockets.connect(uri) as ws:
            print(f"  [{nickname}] Connected")
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
                msg = json.loads(raw)
                mtype = msg.get("type")

                if mtype == "question_started":
                    choices = msg.get("question", {}).get("choices", [])
                    if choices:
                        delay = random.uniform(1.5, 12)
                        await asyncio.sleep(delay)
                        pick = random.choice(choices)
                        await ws.send(json.dumps({
                            "type": "submit_answer",
                            "choice_id": pick["id"],
                            "elapsed_ms": int(delay * 1000),
                        }))
                        print(f"  [{nickname}] Answered Q{msg.get('index', '?') + 1}")

                elif mtype == "answer_result":
                    ok = msg.get("is_correct")
                    pts = msg.get("points", 0)
                    if ok:
                        print(f"  [{nickname}] Correct +{pts}")

                elif mtype == "session_finished":
                    print(f"  [{nickname}] Session ended")
                    break

    except asyncio.TimeoutError:
        pass
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        print(f"  [{nickname}] Error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Quiz Bot Generator (20 bots)")
    parser.add_argument("--host", type=str, default=SERVER_HOST, help="Server host")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="Server port")
    args = parser.parse_args()

    print(f"\n{'=' * 50}")
    print(f"  Quiz Bot Generator — {BOT_COUNT} bots")
    print(f"  Server: {args.host}:{args.port}")
    print(f"{'=' * 50}\n")

    tasks = []
    for i in range(BOT_COUNT):
        nickname = make_nickname()
        tasks.append(join_bot(args.host, args.port, nickname))
        await asyncio.sleep(0.3)

    await asyncio.gather(*tasks)
    print(f"\nAll {BOT_COUNT} bots processed!")


if __name__ == "__main__":
    asyncio.run(main())
