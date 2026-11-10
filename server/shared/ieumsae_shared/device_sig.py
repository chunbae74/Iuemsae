import hashlib
import re
import threading
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

from .b64 import B64Error, b64d, b64e

SIG_VERSION = "IEUMSAE-SIG-V1"
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_SKEW_MS = 60_000


class SignatureError(Exception):
    pass


def canonical(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    body_hash = b64e(hashlib.sha256(body).digest())
    return "\n".join([SIG_VERSION, method.upper(), path, timestamp, nonce, body_hash]).encode()


def load_device_key(spki_b64: str) -> ec.EllipticCurvePublicKey:
    try:
        key = load_der_public_key(b64d(spki_b64, max_len=512))
    except (B64Error, ValueError) as e:
        raise SignatureError("기기 공개키 형식 오류") from e
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise SignatureError("P-256 키가 아닙니다")
    return key


class NonceCache:


    def __init__(self, ttl_ms: int = MAX_SKEW_MS * 2, max_items: int = 200_000):
        self._seen: dict[str, int] = {}
        self._ttl = ttl_ms
        self._max = max_items
        self._lock = threading.Lock()

    def add(self, key: str, now_ms: int) -> bool:
        with self._lock:
            if len(self._seen) > self._max // 2:
                cutoff = now_ms - self._ttl
                self._seen = {k: t for k, t in self._seen.items() if t > cutoff}
            if key in self._seen or len(self._seen) >= self._max:
                return False
            self._seen[key] = now_ms
            return True


def verify_request(
    *,
    device_key_b64: str,
    device_id: str,
    method: str,
    path: str,
    timestamp: str | None,
    nonce: str | None,
    signature: str | None,
    body: bytes,
    nonces: NonceCache,
    now_ms: int | None = None,
) -> None:
    if not timestamp or not nonce or not signature:
        raise SignatureError("서명 헤더가 없습니다")

    if not (timestamp.isascii() and timestamp.isdigit() and len(timestamp) <= 15) or not NONCE_RE.match(nonce):
        raise SignatureError("서명 헤더 형식 오류")
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    if abs(now - int(timestamp)) > MAX_SKEW_MS:
        raise SignatureError("요청 시각이 허용 범위를 벗어났습니다")
    key = load_device_key(device_key_b64)
    try:
        sig = b64d(signature, max_len=128)
        key.verify(sig, canonical(method, path, timestamp, nonce, body), ec.ECDSA(hashes.SHA256()))
    except (B64Error, InvalidSignature) as e:
        raise SignatureError("서명이 맞지 않습니다") from e
    if not nonces.add(f"{device_id}:{nonce}", now):
        raise SignatureError("이미 사용한 요청입니다")
