import hmac
import time
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ieumsae_shared.tokens import AccessClaims
from ieumsae_shared.device_sig import NonceCache, SignatureError, verify_request

from .. import lockout, mailer, profile, sessions
from ..config import settings
from ..db import get_db
from ..deps import current_claims, current_user, email_limit, general_limit, login_limit
from ..models import Consent, Device, EmailCode, RefreshToken, User
from ..schemas import (
    EmailCodeReq,
    EmailVerifyReq,
    FindIdReq,
    LoginReq,
    PasswordChangeReq,
    RefreshReq,
    ResetConfirmReq,
    ResetRequestReq,
    SignupReq,
)
from ..security import (
    LOGIN_ID_RE,
    code_hash,
    hash_password,
    issue_email_token,
    new_email_code,
    password_problem,
    secret_hash,
    verify_email_token,
    verify_password,
)
from ..sessions import now

router = APIRouter(prefix="/auth", tags=["auth"])
login_nonces = NonceCache()
MAX_CODES_PER_HOUR = 5


def _accepted() -> Response:
    return Response(status_code=202)


async def _create_code(db: AsyncSession, email: str, purpose: str, user_id: uuid.UUID | None) -> str | None:
    recent = await db.scalar(
        select(func.count()).select_from(EmailCode).where(
            EmailCode.email == email, EmailCode.created_at > now() - timedelta(hours=1)
        )
    )
    if recent >= MAX_CODES_PER_HOUR:
        return None

    await db.execute(
        update(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.consumed_at.is_(None))
        .values(consumed_at=now())
    )
    code = new_email_code()
    db.add(
        EmailCode(
            email=email,
            purpose=purpose,
            code_hash=code_hash(email, purpose, code),
            user_id=user_id,
            expires_at=now() + timedelta(seconds=settings.email_code_ttl_sec),
        )
    )
    return code


async def _check_code(db: AsyncSession, email: str, purpose: str, code: str) -> EmailCode | None:
    row = (
        await db.execute(
            select(EmailCode)
            .where(
                EmailCode.email == email,
                EmailCode.purpose == purpose,
                EmailCode.consumed_at.is_(None),
                EmailCode.expires_at > now(),
            )
            .order_by(EmailCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.attempts += 1
    if row.attempts > settings.email_code_max_attempts:
        row.consumed_at = now()
        return None
    if not hmac.compare_digest(row.code_hash, code_hash(email, purpose, code)):
        return None
    row.consumed_at = now()
    return row


@router.post("/email/code", status_code=202, dependencies=[Depends(email_limit)])
async def email_code(body: EmailCodeReq, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    exists = await db.scalar(select(User.id).where(User.email == email))
    if exists:

        await mailer.send(email, "signup", "이 메일로 이미 가입한 계정이 있어요. 아이디 찾기를 이용해 주세요.")
        return _accepted()
    code = await _create_code(db, email, "signup", None)
    await db.commit()
    if code:
        await mailer.send(email, "signup", f"이음새 회원가입 인증 코드는 {code} 입니다.\n5분 안에 입력해 주세요.")
    return _accepted()


@router.post("/email/verify", dependencies=[Depends(general_limit)])
async def email_verify(body: EmailVerifyReq, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    ok = await _check_code(db, email, body.purpose, body.code)
    await db.commit()
    if ok is None:
        raise HTTPException(400, "invalid_code")
    return {"emailToken": issue_email_token(email, body.purpose), "expiresIn": settings.email_token_ttl_sec}


@router.post("/signup", status_code=201, dependencies=[Depends(general_limit)])
async def signup(body: SignupReq, db: AsyncSession = Depends(get_db)):
    email = verify_email_token(body.emailToken, "signup")
    if email is None:
        raise HTTPException(400, "invalid_email_token")
    c = body.consents
    if not (c.terms and c.privacy and c.sensitiveVoice):
        raise HTTPException(400, "consent_required")
    if body.communication is not None and not c.sensitiveProfile:

        raise HTTPException(400, "consent_required")
    login_id = body.loginId.lower()
    if not LOGIN_ID_RE.match(login_id):
        raise HTTPException(400, "invalid_login_id")
    if problem := password_problem(body.password, login_id):
        raise HTTPException(400, {"code": "weak_password", "message": problem})
    if await db.scalar(select(User.id).where(User.login_id == login_id)):
        raise HTTPException(409, "login_id_taken")
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "email_taken")
    user = User(login_id=login_id, email=email, password_hash=hash_password(body.password), password_changed_at=now())
    db.add(user)
    await db.flush()
    db.add(
        Consent(
            user_id=user.id,
            terms=True,
            privacy=True,
            sensitive_voice=True,
            sensitive_profile=c.sensitiveProfile and body.communication is not None,
            tts_overseas=c.ttsOverseas,
            version=settings.consent_version,
        )
    )
    if body.communication is not None:
        m = body.communication
        await profile.save_communication(db, user.id, m.speechLevel, m.comprehensionLevel, m.showToListener)
    await db.commit()
    return {"userId": str(user.id)}


@router.post("/login", dependencies=[Depends(login_limit)])
async def login(body: LoginReq, request: Request, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(User).where(User.login_id == body.loginId.lower()).with_for_update())
    ).scalar_one_or_none()
    if user is None:
        verify_password(None, body.password)
        raise HTTPException(401, "invalid_credentials")
    await lockout.check_password(db, user, body.password, error_code="invalid_credentials")

    device = None
    if body.deviceId:
        device = await _proven_device(db, user, body.deviceId, request)
    tokens = await sessions.start(db, user.id, device)
    await db.commit()
    return {"userId": str(user.id), **tokens, "deviceRegistered": device is not None}


async def _proven_device(db: AsyncSession, user: User, device_id: str, request: Request) -> Device | None:

    try:
        did = uuid.UUID(device_id)
    except ValueError:
        return None
    device = await db.get(Device, did)
    if device is None or device.user_id != user.id or request.headers.get("x-device-id") != device_id:
        return None
    try:
        verify_request(
            device_key_b64=device.public_key,
            device_id=device_id,
            method=request.method,
            path=request.scope["path"],
            timestamp=request.headers.get("x-timestamp"),
            nonce=request.headers.get("x-nonce"),
            signature=request.headers.get("x-signature"),
            body=await request.body(),
            nonces=login_nonces,
            now_ms=int(time.time() * 1000),
        )
    except SignatureError:
        return None
    return device


@router.post("/refresh", dependencies=[Depends(general_limit)])
async def refresh(body: RefreshReq, db: AsyncSession = Depends(get_db)):
    try:
        tokens = await sessions.rotate(db, body.refreshToken)
    except sessions.RefreshError:
        raise HTTPException(401, "invalid_refresh_token")
    await db.commit()
    return tokens


@router.post("/logout", status_code=204)
async def logout(body: RefreshReq, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == secret_hash("refresh", body.refreshToken)))
    ).scalar_one_or_none()
    if row is not None:
        await sessions.revoke_family(db, row.family_id)
        await db.commit()
    return Response(status_code=204)


@router.put("/password", status_code=204, dependencies=[Depends(general_limit)])
async def change_password(body: PasswordChangeReq, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):

    await lockout.check_password(db, user, body.currentPassword)
    if problem := password_problem(body.newPassword, user.login_id):
        raise HTTPException(400, {"code": "weak_password", "message": problem})
    if verify_password(user.password_hash, body.newPassword):
        raise HTTPException(400, {"code": "same_password", "message": "지금 쓰는 비밀번호와 달라야 해요"})
    user.password_hash = hash_password(body.newPassword)
    user.password_changed_at = now()

    await sessions.revoke_user(db, user.id)
    await db.commit()
    return Response(status_code=204)


@router.post("/find-id", status_code=202, dependencies=[Depends(email_limit)])
async def find_id(body: FindIdReq, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is not None:
        await mailer.send(user.email, "find_id", f"이음새 아이디는 {user.login_id} 입니다.")
    return _accepted()


@router.post("/password-reset/request", status_code=202, dependencies=[Depends(email_limit)])
async def reset_request(body: ResetRequestReq, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.login_id == body.loginId.lower()))).scalar_one_or_none()
    if user is not None and hmac.compare_digest(user.email, body.email.lower()):
        code = await _create_code(db, user.email, "password_reset", user.id)
        await db.commit()
        if code:
            await mailer.send(user.email, "password_reset", f"비밀번호 재설정 코드는 {code} 입니다.\n5분 안에 입력해 주세요.")
    return _accepted()


@router.post("/password-reset/confirm", status_code=204, dependencies=[Depends(general_limit)])
async def reset_confirm(body: ResetConfirmReq, db: AsyncSession = Depends(get_db)):
    user = (
        await db.execute(select(User).where(User.login_id == body.loginId.lower()).with_for_update())
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(400, "invalid_code")
    if problem := password_problem(body.newPassword, user.login_id):
        raise HTTPException(400, {"code": "weak_password", "message": problem})
    row = await _check_code(db, user.email, "password_reset", body.code)
    if row is None or row.user_id != user.id:
        await db.commit()
        raise HTTPException(400, "invalid_code")
    user.password_hash = hash_password(body.newPassword)
    user.password_changed_at = now()
    user.failed_logins = 0
    user.locked_until = None
    await sessions.revoke_user(db, user.id)
    await db.commit()
    return Response(status_code=204)


@router.get("/session/status")
async def session_status(
    claims: AccessClaims = Depends(current_claims),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not claims.device_id:
        raise HTTPException(403, "device_not_registered")
    consent = await profile.current_consent(db, user.id)
    return {
        "active": True,
        "userId": str(user.id),
        "deviceId": claims.device_id,
        "ttsConsent": bool(consent and consent.tts_overseas),
    }
