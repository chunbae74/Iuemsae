import threading
import time
import uuid
from collections import deque
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ieumsae_shared.tokens import AccessClaims, AccessTokenVerifier, TokenError, bearer

from .config import settings
from .db import get_db
from .models import User, RefreshToken, Device
from .sessions import now
from .security import password_version

_verifier: AccessTokenVerifier | None = None


def verifier() -> AccessTokenVerifier:
    global _verifier
    if _verifier is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        priv = load_pem_private_key(Path(settings.jwt_private_key_file).read_bytes(), password=None)
        pub = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        _verifier = AccessTokenVerifier(pub)
    return _verifier


async def current_claims(request: Request) -> AccessClaims:
    token = bearer(request.headers.get("authorization"))
    if not token:
        raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
    try:
        return verifier().verify(token)
    except TokenError:
        raise HTTPException(401, "invalid_token", headers={"WWW-Authenticate": "Bearer"})


async def current_user(claims: AccessClaims = Depends(current_claims), db: AsyncSession = Depends(get_db)) -> User:
    user = await db.get(User, uuid.UUID(claims.user_id))
    if user is None:
        raise HTTPException(401, "invalid_token")

    if claims.password_version != password_version(user.password_changed_at):
        raise HTTPException(401, "invalid_token")
    active = await db.scalar(select(RefreshToken.id).where(
        RefreshToken.user_id == user.id,
        RefreshToken.family_id == uuid.UUID(claims.session_id),
        RefreshToken.revoked_at.is_(None), RefreshToken.used_at.is_(None),
        RefreshToken.expires_at > now(),
    ).limit(1))
    if active is None:
        raise HTTPException(401, "invalid_token")
    if claims.device_id:
        device = await db.get(Device, uuid.UUID(claims.device_id))
        if device is None or device.user_id != user.id or device.public_key != claims.device_key:
            raise HTTPException(401, "invalid_token")
    return user


class RateLimiter:


    def __init__(self, limit: int, window_sec: int):
        self.limit = limit
        self.window = window_sec
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:


        ip = request.client.host if request.client else "unknown"
        key = f"{request.scope['path']}|{ip}"
        now = time.monotonic()
        with self._lock:
            if key not in self._hits and len(self._hits) >= 100_000:
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - self.window}
                if len(self._hits) >= 100_000:
                    raise HTTPException(429, "too_many_requests")
            q = self._hits.setdefault(key, deque())
            while q and q[0] < now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(429, "too_many_requests", headers={"Retry-After": str(self.window)})
            q.append(now)
            if len(self._hits) > 100_000:
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - self.window}


email_limit = RateLimiter(5, 600)
login_limit = RateLimiter(20, 300)
general_limit = RateLimiter(60, 60)
