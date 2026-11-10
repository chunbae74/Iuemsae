import asyncio
import base64
import hmac
import logging
import time

import httpx

from .config import settings

log = logging.getLogger("ieumsae.integrity")
SCOPE = "https://www.googleapis.com/auth/playintegrity"


class IntegrityError(Exception):
    pass


def _access_token() -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        settings.integrity_service_account_file, scopes=[SCOPE]
    )
    import requests

    class BoundedRequest(Request):
        def __call__(self, *args, **kwargs):
            kwargs["timeout"] = 10
            return super().__call__(*args, **kwargs)

    with requests.Session() as session:
        creds.refresh(BoundedRequest(session=session))
    return creds.token


async def verify_integrity(token: str | None, challenge: bytes) -> None:
    if not token or len(token) > 8192:
        raise IntegrityError("무결성 토큰이 없습니다")
    bearer = await asyncio.to_thread(_access_token)
    url = f"https://playintegrity.googleapis.com/v1/{settings.android_package}:decodeIntegrityToken"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json={"integrity_token": token}, headers={"Authorization": f"Bearer {bearer}"})
    if r.status_code != 200:
        log.warning("INTEGRITY_REJECTED")
        raise IntegrityError("무결성 토큰을 확인하지 못했습니다")
    payload = r.json().get("tokenPayloadExternal", {})
    req = payload.get("requestDetails", {})
    try:
        issued_at = int(req.get("timestampMillis", 0))
    except (ValueError, TypeError):
        raise IntegrityError("무결성 토큰 시각이 올바르지 않습니다")
    if abs(int(time.time() * 1000) - issued_at) > settings.device_challenge_ttl_sec * 1000:
        raise IntegrityError("무결성 토큰이 만료되었습니다")
    expected_nonce = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    if not hmac.compare_digest(str(req.get("nonce", "")).rstrip("="), expected_nonce):
        raise IntegrityError("nonce가 다릅니다")
    if req.get("requestPackageName") != settings.android_package:
        raise IntegrityError("패키지가 다릅니다")
    if payload.get("appIntegrity", {}).get("appRecognitionVerdict") != "PLAY_RECOGNIZED":
        raise IntegrityError("정품 앱이 아닙니다")
    verdicts = payload.get("deviceIntegrity", {}).get("deviceRecognitionVerdict", [])
    if "MEETS_DEVICE_INTEGRITY" not in verdicts:
        raise IntegrityError("기기 무결성을 만족하지 않습니다")
