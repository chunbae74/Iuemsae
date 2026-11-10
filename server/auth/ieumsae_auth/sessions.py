import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import Device, RefreshToken, User
from .profile import current_consent
from .security import issue_access_token, new_refresh_token, password_version, secret_hash


def now() -> datetime:
    return datetime.now(timezone.utc)


class RefreshError(Exception):
    pass


async def _issue(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID, device: Device | None) -> dict:
    raw = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=secret_hash("refresh", raw),
            device_id=device.id if device else None,
            expires_at=now() + timedelta(seconds=settings.refresh_ttl_sec),
        )
    )
    user = await db.get(User, user_id)
    if user is None:

        raise RefreshError()
    consent = await current_consent(db, user_id)
    access = issue_access_token(
        user_id,
        family_id,
        password_version(user.password_changed_at),
        device.id if device else None,
        device.public_key if device else None,
        tts_overseas=bool(consent and consent.tts_overseas),
    )
    return {
        "accessToken": access,
        "accessTokenExpiresIn": settings.access_ttl_sec,
        "refreshToken": raw,
        "refreshTokenExpiresIn": settings.refresh_ttl_sec,
    }


async def start(db: AsyncSession, user_id: uuid.UUID, device: Device | None = None) -> dict:
    return await _issue(db, user_id, uuid.uuid4(), device)


async def rotate(db: AsyncSession, raw: str) -> dict:
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == secret_hash("refresh", raw)).with_for_update())
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise RefreshError()
    if row.used_at is not None:

        await revoke_family(db, row.family_id)
        await db.commit()
        raise RefreshError()
    if row.expires_at < now():
        raise RefreshError()
    row.used_at = now()
    device = await db.get(Device, row.device_id) if row.device_id else None
    return await _issue(db, row.user_id, row.family_id, device)


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now())
    )


async def revoke_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now())
    )


async def bind_device(db: AsyncSession, family_id: uuid.UUID, user_id: uuid.UUID, device_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(device_id=device_id)
    )
