from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models import User

from .config import settings
from .models import User
from .security import verify_password
from .sessions import now


def is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > now())


async def check_password(db: AsyncSession, user: User, password: str, *, error_code: str = "invalid_password") -> None:

    user = (await db.execute(
        select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if is_locked(user):
        verify_password(None, password)
        raise HTTPException(423, "account_locked")
    if verify_password(user.password_hash, password):
        user.failed_logins = 0
        user.locked_until = None
        return
    user.failed_logins += 1
    if user.failed_logins >= settings.login_max_failures:
        user.locked_until = now() + timedelta(seconds=settings.login_lock_sec)
        user.failed_logins = 0
    await db.commit()
    raise HTTPException(401 if error_code == "invalid_credentials" else 400, error_code)
