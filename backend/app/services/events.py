"""Live updates over WebSocket. Sync endpoints publish; the async loop delivers."""
import asyncio
import json
import threading
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = defaultdict(set)
        self._admins: set[int] = set()
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket, user_id: int, is_admin: bool) -> None:
        await ws.accept()
        with self._lock:
            self._conns[user_id].add(ws)
            if is_admin:
                self._admins.add(user_id)

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        with self._lock:
            self._conns[user_id].discard(ws)
            if not self._conns[user_id]:
                self._conns.pop(user_id, None)
                self._admins.discard(user_id)

    async def _send(self, targets: list[WebSocket], message: str) -> None:
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                pass

    def publish(self, event: str, data: dict | None = None, user_ids: list[int] | None = None, admins: bool = True) -> None:
        """Thread-safe. user_ids=None broadcasts to everyone connected."""
        if self.loop is None or self.loop.is_closed():
            return
        message = json.dumps({"event": event, "data": data or {}})
        with self._lock:
            if user_ids is None:
                targets = [ws for s in self._conns.values() for ws in s]
            else:
                ids = set(user_ids) | (self._admins if admins else set())
                targets = [ws for uid in ids for ws in self._conns.get(uid, ())]
        if targets:
            asyncio.run_coroutine_threadsafe(self._send(targets, message), self.loop)


manager = ConnectionManager()
