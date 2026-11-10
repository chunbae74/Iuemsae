import logging
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ieumsae_shared.b64 import B64Error, b64d, b64e
from ieumsae_shared.device_sig import SignatureError, load_device_key
from ieumsae_shared.tokens import AccessClaims

from .. import sessions
from ..revocation import checker
from ..attestation import AttestationError, verify_attestation
from ..config import settings
from ..db import get_db
from ..deps import current_claims, current_user, general_limit
from ..integrity import IntegrityError, verify_integrity
from ..models import Device, DeviceChallenge, RefreshToken, User
from ..schemas import DeviceRegisterReq
from ..security import secret_hash
from ..sessions import now

router = APIRouter(prefix="/device", tags=["device"])
log = logging.getLogger("ieumsae.device")


@router.post("/challenge", dependencies=[Depends(general_limit)])
async def challenge(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    raw = secrets.token_bytes(32)
    await db.execute(delete(DeviceChallenge).where(DeviceChallenge.expires_at < now()))
    db.add(
        DeviceChallenge(
            challenge_hash=secret_hash("challenge", raw),
            user_id=user.id,
            expires_at=now() + timedelta(seconds=settings.device_challenge_ttl_sec),
        )
    )
    await db.commit()
    return {"challenge": b64e(raw), "expiresIn": settings.device_challenge_ttl_sec}


@router.post("/register", status_code=201, dependencies=[Depends(general_limit)])
async def register(
    body: DeviceRegisterReq,
    claims: AccessClaims = Depends(current_claims),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        raw = b64d(body.challenge, max_len=64)
        load_device_key(body.publicKey)
    except (B64Error, SignatureError):
        raise HTTPException(400, "invalid_request")

    ch = (
        await db.execute(
            select(DeviceChallenge).where(DeviceChallenge.challenge_hash == secret_hash("challenge", raw)).with_for_update()
        )
    ).scalar_one_or_none()
    if ch is None or ch.used or ch.user_id != user.id or ch.expires_at < now():
        raise HTTPException(400, "invalid_challenge")
    ch.used = True
    await db.commit()

    try:
        result = verify_attestation(body.keyAttestationChain, body.publicKey, raw)
        await checker.check(body.keyAttestationChain)
        await verify_integrity(body.integrityToken, raw)
    except AttestationError as e:

        log.warning("ATTESTATION_REJECTED")
        raise HTTPException(400, "attestation_failed")
    except IntegrityError as e:
        log.warning("ATTESTATION_REJECTED")
        raise HTTPException(400, "integrity_failed")


    mine = (
        (await db.execute(select(Device).where(Device.user_id == user.id).order_by(Device.created_at)))
        .scalars()
        .all()
    )
    for old in mine[: max(0, len(mine) - settings.max_devices_per_user + 1)]:
        await revoke_device_sessions(db, old.id)
        await db.delete(old)

    device = Device(
        user_id=user.id, public_key=result.public_key_b64, security_level=result.security_level, sdk_int=body.sdkInt
    )
    db.add(device)
    await db.flush()
    if claims.session_id:

        await sessions.bind_device(db, uuid.UUID(claims.session_id), user.id, device.id)
    await db.commit()
    return {"deviceId": str(device.id), "securityLevel": device.security_level}


@router.delete("/{device_id}", status_code=204)
async def unregister(device_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    try:
        did = uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(404, "not_found")
    device = await db.get(Device, did)
    if device is None or device.user_id != user.id:
        raise HTTPException(404, "not_found")
    await revoke_device_sessions(db, device.id)
    await db.delete(device)
    await db.commit()
    return Response(status_code=204)


async def revoke_device_sessions(db: AsyncSession, device_id: uuid.UUID):
    families = (await db.scalars(select(RefreshToken.family_id).where(
        RefreshToken.device_id == device_id, RefreshToken.revoked_at.is_(None)
    ).distinct())).all()
    for family in families:
        await sessions.revoke_family(db, family)
