import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from .config import settings

log = logging.getLogger("ieumsae.mail")

class MailDeliveryError(Exception):
    pass


SUBJECTS = {
    "signup": "[이음새] 회원가입 인증 코드",
    "password_reset": "[이음새] 비밀번호 재설정 코드",
    "find_id": "[이음새] 아이디 안내",
}


async def send(to: str, kind: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = SUBJECTS[kind]
    msg.set_content(body)
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=Path(settings.smtp_password_file).read_text().strip() if settings.smtp_password_file else None,
            start_tls=settings.smtp_starttls,
            timeout=10,
        )
    except (aiosmtplib.SMTPException, OSError) as e:

        log.error("MAIL_FAILED")
        raise MailDeliveryError() from None
