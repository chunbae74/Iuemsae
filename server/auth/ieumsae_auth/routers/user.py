from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from .. import lockout, profile
from ..db import get_db
from ..deps import current_user, general_limit
from ..models import EmailCode, User
from ..schemas import CommunicationUpdateReq, DeleteUserReq, TtsConsentReq
from ..security import mask_email

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile")
async def get_profile(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    consent = await profile.current_consent(db, user.id)
    return {
        "userId": str(user.id),
        "loginId": user.login_id,
        "email": mask_email(user.email),
        "createdAt": int(user.created_at.timestamp() * 1000),
        "communication": await profile.load_communication(db, user.id),
        "consents": {
            "sensitiveProfile": bool(consent and consent.sensitive_profile),
            "ttsOverseas": bool(consent and consent.tts_overseas),
        },
    }


@router.put("/communication", status_code=204, dependencies=[Depends(general_limit)])
async def put_communication(
    body: CommunicationUpdateReq, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    if not body.consent:
        raise HTTPException(400, "consent_required")
    await profile.save_communication(db, user.id, body.speechLevel, body.comprehensionLevel, body.showToListener)
    consent = await profile.current_consent(db, user.id)
    if not (consent and consent.sensitive_profile):
        await profile.record_consent(db, user.id, sensitive_profile=True)
    await db.commit()
    return Response(status_code=204)


@router.delete("/communication", status_code=204)
async def delete_communication(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):

    await profile.delete_communication(db, user.id)
    await profile.record_consent(db, user.id, sensitive_profile=False)
    await db.commit()
    return Response(status_code=204)


@router.put("/consents/tts", status_code=204, dependencies=[Depends(general_limit)])
async def put_tts_consent(body: TtsConsentReq, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):

    await profile.record_consent(db, user.id, tts_overseas=body.agree)
    await db.commit()
    return Response(status_code=204)


@router.delete("", status_code=204, dependencies=[Depends(general_limit)])
async def withdraw(body: DeleteUserReq, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await lockout.check_password(db, user, body.password)

    await db.execute(delete(EmailCode).where(EmailCode.email == user.email))
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)
