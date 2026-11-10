import base64
import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import CommunicationProfile, Consent

async def current_consent(db: AsyncSession, user_id: uuid.UUID) -> Consent | None:
    return (
        await db.execute(
            select(Consent).where(Consent.user_id == user_id).order_by(Consent.id.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def record_consent(db: AsyncSession, user_id: uuid.UUID, **changes: bool) -> Consent:

    prev = await current_consent(db, user_id)
    row = Consent(
        user_id=user_id,
        terms=prev.terms if prev else True,
        privacy=prev.privacy if prev else True,
        sensitive_voice=prev.sensitive_voice if prev else True,
        sensitive_profile=prev.sensitive_profile if prev else False,
        tts_overseas=prev.tts_overseas if prev else False,
        version=settings.consent_version,
    )
    for k, v in changes.items():
        setattr(row, k, v)
    db.add(row)
    return row


@lru_cache
def _key() -> bytes:
    key = base64.b64decode(Path(settings.profile_key_file).read_text().strip())
    if len(key) != 32:
        raise ValueError("profile_data_key는 32바이트여야 합니다")
    return key


def _seal(user_id: uuid.UUID, data: dict) -> bytes:
    nonce = os.urandom(12)

    return nonce + AESGCM(_key()).encrypt(nonce, json.dumps(data).encode(), str(user_id).encode())


def _open(user_id: uuid.UUID, blob: bytes) -> dict:
    return json.loads(AESGCM(_key()).decrypt(blob[:12], blob[12:], str(user_id).encode()))


async def save_communication(
    db: AsyncSession, user_id: uuid.UUID, speech: int | None, comprehension: int | None, show: bool
) -> None:
    data = {"speechLevel": speech, "comprehensionLevel": comprehension, "showToListener": show}
    row = await db.get(CommunicationProfile, user_id)
    if row is None:
        db.add(CommunicationProfile(user_id=user_id, ciphertext=_seal(user_id, data)))
    else:
        row.ciphertext = _seal(user_id, data)
        row.updated_at = datetime.now(timezone.utc)


async def load_communication(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    row = await db.get(CommunicationProfile, user_id)
    return _open(user_id, row.ciphertext) if row else None


async def delete_communication(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(CommunicationProfile).where(CommunicationProfile.user_id == user_id))
