import asyncio
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field

from .crypto import EphemeralKey
from fastapi import HTTPException


def _wipe(buf: bytearray | None) -> None:
    if buf is not None:
        for i in range(len(buf)):
            buf[i] = 0


@dataclass
class SttSession:
    session_id: str
    user_id: str
    device_id: str
    mode: str
    expires_at: int
    ephemeral: EphemeralKey | None
    session_key: bytearray | None = None
    chunks: dict[int, bytearray] = field(default_factory=dict)
    last_timestamp: int = 0
    finalizing: bool = False

    def wipe(self) -> None:
        self.ephemeral = None
        _wipe(self.session_key)
        self.session_key = None
        for c in self.chunks.values():
            _wipe(c)
        self.chunks.clear()


class SessionStore:
    def __init__(self, ttl_sec: int, max_per_user: int):
        if not 1 <= ttl_sec <= 300 or not 1 <= max_per_user <= 10:
            raise ValueError("invalid_session_limits")
        self._ttl_ms = ttl_sec * 1000
        self._max_per_user = max_per_user
        self._items: dict[str, SttSession] = {}
        self._lock = threading.Lock()

    def create(self, user_id: str, device_id: str, mode: str) -> SttSession:
        now = int(time.time() * 1000)
        with self._lock:
            mine = sorted(
                (s for s in self._items.values() if s.user_id == user_id), key=lambda s: s.expires_at
            )

            if len(mine) >= self._max_per_user or len(self._items) >= 256:
                raise HTTPException(429, "too_many_requests")
            sid = str(uuid.UUID(bytes=secrets.token_bytes(16), version=4))
            s = SttSession(sid, user_id, device_id, mode, now + self._ttl_ms, EphemeralKey())
            self._items[sid] = s
            return s

    def get(self, session_id: str, user_id: str, device_id: str) -> SttSession | None:
        now = int(time.time() * 1000)
        with self._lock:
            s = self._items.get(session_id)
            if s is None:
                return None
            if s.expires_at < now:
                self._items.pop(session_id, None)
                s.wipe()
                return None

            if not secrets.compare_digest(s.user_id, user_id) or not secrets.compare_digest(s.device_id, device_id):
                return None
            return s

    def remove(self, session_id: str) -> None:
        with self._lock:
            s = self._items.pop(session_id, None)
        if s is not None:
            s.wipe()

    def purge_expired(self) -> int:
        now = int(time.time() * 1000)
        with self._lock:
            dead = [sid for sid, s in self._items.items() if s.expires_at < now]
            gone = [self._items.pop(sid) for sid in dead]
        for s in gone:
            s.wipe()
        return len(gone)

    def wipe_all(self) -> None:
        with self._lock:
            items, self._items = list(self._items.values()), {}
        for s in items:
            s.wipe()

    async def janitor(self, interval: float = 5.0) -> None:
        while True:
            await asyncio.sleep(interval)
            self.purge_expired()
