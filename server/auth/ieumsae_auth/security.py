import hashlib
import hmac
import re
import secrets
import time
import uuid
from functools import lru_cache
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from ieumsae_shared.tokens import AUDIENCE, ISSUER, JWT_ALG

from .config import settings


_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))

LOGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{3,19}$")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored: str | None, password: str) -> bool:

    try:
        return _ph.verify(stored or _DUMMY_HASH, password) and stored is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problem(password: str, login_id: str | None = None) -> str | None:

    if len(password) > 64:
        return "비밀번호는 64자 이하여야 해요"
    kinds = sum(
        bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]")
    )
    if not ((kinds >= 3 and len(password) >= 8) or (kinds >= 2 and len(password) >= 10)):
        return "영문·숫자·특수문자 중 3가지를 섞어 8자 이상, 또는 2가지를 섞어 10자 이상으로 만들어 주세요"
    if re.search(r"(.)\1\1\1", password):
        return "같은 문자를 4번 이상 이어 쓸 수 없어요"
    if login_id and login_id.lower() in password.lower():
        return "비밀번호에 아이디를 넣을 수 없어요"
    return None


def secret_hash(kind: str, data: str | bytes) -> bytes:


    raw = data.encode() if isinstance(data, str) else data
    return hmac.new(_pepper(), kind.encode() + b"|" + raw, hashlib.sha256).digest()


@lru_cache
def _pepper() -> bytes:
    pepper = Path(settings.email_pepper_file).read_bytes().strip()
    if len(pepper) < 32:
        raise ValueError("invalid_secret_length")
    return pepper


def code_hash(email: str, purpose: str, code: str) -> bytes:
    return hmac.new(_pepper(), f"{purpose}|{email}|{code}".encode(), hashlib.sha256).digest()


def new_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@lru_cache
def _jwt_key():
    return load_pem_private_key(Path(settings.jwt_private_key_file).read_bytes(), password=None)


def password_version(changed_at) -> int:
    return int(changed_at.timestamp() * 1000)


def issue_access_token(
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    pw_version: int,
    device_id: uuid.UUID | None = None,
    device_key: str | None = None,
    tts_overseas: bool = False,
) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(user_id),
        "sid": str(family_id),
        "pwv": pw_version,

        "tts": tts_overseas,
        "iat": now,
        "exp": now + settings.access_ttl_sec,
        "jti": secrets.token_urlsafe(12),
        "typ": "access",
    }
    if device_id and device_key:

        claims["cnf"] = {"did": str(device_id), "dkey": device_key}
    return jwt.encode(claims, _jwt_key(), algorithm=JWT_ALG)


def issue_email_token(email: str, purpose: str) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": f"{AUDIENCE}:email",
        "sub": email,
        "purpose": purpose,
        "iat": now,
        "exp": now + settings.email_token_ttl_sec,
        "jti": secrets.token_urlsafe(12),
        "typ": "email",
    }
    return jwt.encode(claims, _jwt_key(), algorithm=JWT_ALG)


def verify_email_token(token: str, purpose: str) -> str | None:
    try:
        claims = jwt.decode(
            token,
            _jwt_key().public_key(),
            algorithms=[JWT_ALG],
            audience=f"{AUDIENCE}:email",
            issuer=ISSUER,
            options={"require": ["exp", "sub", "purpose", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    if claims.get("typ") != "email" or claims.get("purpose") != purpose:
        return None
    return str(claims["sub"])


def new_refresh_token() -> str:
    return "rt_" + secrets.token_urlsafe(32)


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:2] + "***" if len(local) > 2 else local[:1] + "***") + "@" + domain
