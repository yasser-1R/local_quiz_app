"""
WebSocket connection manager.

Keeps three pools of sockets per session:
    - teacher sockets
    - student sockets (keyed by player token)
    - display sockets
"""
import asyncio
import json
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.teachers: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.displays: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.students: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    # ----- connect / disconnect -----
    async def connect_teacher(self, code: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.teachers[code].add(ws)

    async def connect_display(self, code: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.displays[code].add(ws)

    async def connect_student(self, code: str, token: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            # if same token reconnects, replace old socket
            old = self.students[code].get(token)
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass
            self.students[code][token] = ws

    async def disconnect_teacher(self, code: str, ws: WebSocket) -> None:
        async with self._lock:
            self.teachers[code].discard(ws)

    async def disconnect_display(self, code: str, ws: WebSocket) -> None:
        async with self._lock:
            self.displays[code].discard(ws)

    async def disconnect_student(self, code: str, token: str) -> None:
        async with self._lock:
            self.students[code].pop(token, None)

    async def close_students(self, code: str) -> None:
        """Close all student WebSocket connections for a session code."""
        async with self._lock:
            students_dict = self.students.get(code, {})
            for token, ws in list(students_dict.items()):
                try:
                    await ws.close()
                except Exception:
                    pass
            self.students[code] = {}

    # ----- broadcast helpers -----
    async def _safe_send(self, ws: WebSocket, payload: str) -> bool:
        try:
            await ws.send_text(payload)
            return True
        except Exception:
            return False

    async def broadcast(self, code: str, message: dict) -> None:
        payload = json.dumps(message)
        targets = (
            list(self.teachers.get(code, set()))
            + list(self.displays.get(code, set()))
            + list(self.students.get(code, {}).values())
        )
        await asyncio.gather(*(self._safe_send(ws, payload) for ws in targets))

    async def send_to_teachers(self, code: str, message: dict) -> None:
        payload = json.dumps(message)
        targets = list(self.teachers.get(code, set()))
        await asyncio.gather(*(self._safe_send(ws, payload) for ws in targets))

    async def send_to_displays(self, code: str, message: dict) -> None:
        payload = json.dumps(message)
        targets = list(self.displays.get(code, set()))
        await asyncio.gather(*(self._safe_send(ws, payload) for ws in targets))

    async def send_to_students(self, code: str, message: dict) -> None:
        payload = json.dumps(message)
        targets = list(self.students.get(code, {}).values())
        await asyncio.gather(*(self._safe_send(ws, payload) for ws in targets))

    async def send_to_player(self, code: str, token: str, message: dict) -> None:
        ws = self.students.get(code, {}).get(token)
        if ws is None:
            return
        await self._safe_send(ws, json.dumps(message))


manager = ConnectionManager()
