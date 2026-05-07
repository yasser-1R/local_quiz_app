"""
Quiz Bot Generator - Simulates student players adaptively.

Polls the session until it opens, then joins according to the connection_mode
(GUEST or SIGNUP). Handles both NORMAL and RANDOM quiz modes automatically.

Usage:
    python bot_generator.py
    python bot_generator.py --host 192.168.1.10 --port 8000 --bots 10
"""
import argparse
import asyncio
import json
import random
import string

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

used_names: set[str] = set()


def make_nickname() -> str:
    while True:
        base = random.choice(FIRST_NAMES)
        suffix = random.randint(1, 99)
        name = f"{base}{suffix}"
        if name not in used_names:
            used_names.add(name)
            return name


def make_password() -> str:
    return "bot_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


async def wait_for_open_session(client: httpx.AsyncClient, url: str, nickname: str) -> dict:
    """Poll /api/session/current until the session is open for joining. Returns session info."""
    while True:
        try:
            r = await client.get(f"{url}/api/session/current", timeout=5)
            data = r.json()
        except Exception:
            await asyncio.sleep(3)
            continue

        state = data.get("state", "NONE")
        conn_mode = data.get("connection_mode", "BLOCKED")

        if state in ("NONE", "FINISHED"):
            print(f"  [{nickname}] No active session, waiting...")
            await asyncio.sleep(3)
            continue

        if conn_mode == "BLOCKED":
            await asyncio.sleep(3)
            continue

        if conn_mode not in ("GUEST", "SIGNUP", "LOGIN"):
            print(f"  [{nickname}] Unknown connection_mode '{conn_mode}', waiting...")
            await asyncio.sleep(3)
            continue

        return data


async def join_as_guest(
    client: httpx.AsyncClient, url: str, nickname: str,
    character: str, color: str, accessory: str,
) -> str | None:
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
            timeout=10,
        )
    except Exception as e:
        print(f"  [{nickname}] Guest join error: {e}")
        return None

    token = resp.cookies.get("player_token")
    if not token:
        for r in resp.history:
            token = r.cookies.get("player_token")
            if token:
                break
    return token


async def join_as_signup(
    client: httpx.AsyncClient, url: str, nickname: str,
    character: str, color: str, accessory: str,
) -> str | None:
    password = make_password()
    try:
        resp = await client.post(
            f"{url}/auth/signup",
            data={
                "nickname": nickname,
                "password": password,
                "avatar_character": character,
                "avatar_color": color,
                "avatar_accessory": accessory,
            },
            follow_redirects=True,
            timeout=10,
        )
    except Exception as e:
        print(f"  [{nickname}] Signup error: {e}")
        return None

    token = resp.cookies.get("player_token")
    if not token:
        for r in resp.history:
            token = r.cookies.get("player_token")
            if token:
                break
    return token


async def run_bot(host: str, port: int, nickname: str) -> None:
    url = f"http://{host}:{port}"
    character = random.choice(CHARACTERS)
    color = random.choice(COLORS)
    accessory = random.choice(ACCESSORIES)

    async with httpx.AsyncClient() as client:
        session_info = await wait_for_open_session(client, url, nickname)
        conn_mode = session_info.get("connection_mode", "GUEST")
        quiz_mode = session_info.get("mode", "NORMAL")

        if conn_mode == "GUEST":
            token = await join_as_guest(client, url, nickname, character, color, accessory)
        elif conn_mode == "SIGNUP":
            token = await join_as_signup(client, url, nickname, character, color, accessory)
        else:
            print(f"  [{nickname}] Mode '{conn_mode}' not supported by bots, skipping.")
            return

    if not token:
        print(f"  [{nickname}] Failed to get player token, giving up.")
        return

    print(f"  [{nickname}] Joined! (conn={conn_mode}, quiz={quiz_mode})")
    await _ws_loop(host, port, token, nickname)


async def _ws_loop(host: str, port: int, token: str, nickname: str) -> None:
    uri = f"ws://{host}:{port}/ws/student/{token}"
    try:
        async with websockets.connect(uri) as ws:
            print(f"  [{nickname}] WebSocket connected")
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                msg = json.loads(raw)
                mtype = msg.get("type")

                if mtype == "question_started":
                    mode = msg.get("mode", "normal")
                    choices = msg.get("question", {}).get("choices", [])
                    time_limit = msg.get("question", {}).get("time_limit", 30)
                    if choices:
                        delay = random.uniform(1.5, min(time_limit * 0.8, 15))
                        await asyncio.sleep(delay)
                        pick = random.choice(choices)
                        await ws.send(json.dumps({
                            "type": "submit_answer",
                            "choice_id": pick["id"],
                            "elapsed_ms": int(delay * 1000),
                        }))
                        print(f"  [{nickname}] Answered Q{msg.get('index', '?') + 1} ({mode})")

                elif mtype == "answer_result":
                    if msg.get("mode") == "random" and not msg.get("player_done", False):
                        # Random mode: wait a bit then request next question
                        await asyncio.sleep(random.uniform(2, 5))
                        await ws.send(json.dumps({"type": "request_next_question"}))

                elif mtype == "random_quiz_complete":
                    score = msg.get("total_score", 0)
                    print(f"  [{nickname}] Random quiz complete! Score: {score}")

                elif mtype == "session_finished":
                    print(f"  [{nickname}] Session finished")
                    break

                elif mtype == "quiz_reset":
                    print(f"  [{nickname}] Quiz reset, disconnecting")
                    break

    except asyncio.TimeoutError:
        print(f"  [{nickname}] Timed out waiting for server")
    except websockets.ConnectionClosed:
        print(f"  [{nickname}] Connection closed")
    except Exception as e:
        print(f"  [{nickname}] Error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Quiz Bot Generator")
    parser.add_argument("--host", type=str, default=SERVER_HOST)
    parser.add_argument("--port", type=int, default=SERVER_PORT)
    parser.add_argument("--bots", type=int, default=BOT_COUNT)
    args = parser.parse_args()

    print(f"\n{'=' * 50}")
    print(f"  Quiz Bot Generator — {args.bots} bots")
    print(f"  Server: {args.host}:{args.port}")
    print(f"  Will wait for session to open before joining")
    print(f"{'=' * 50}\n")

    tasks = []
    for _ in range(args.bots):
        nickname = make_nickname()
        tasks.append(run_bot(args.host, args.port, nickname))
        await asyncio.sleep(0.3)

    await asyncio.gather(*tasks)
    print(f"\nAll {args.bots} bots processed!")


if __name__ == "__main__":
    asyncio.run(main())
