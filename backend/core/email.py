# backend/core/email.py

import smtplib
from email.mime.text import MIMEText

from backend.core.config import settings

# SMTP로 이메일을 발송. SMTP_HOST가 설정 안 되어 있으면 콘솔 출력으로 대체
def send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST:
        print(f"[email] SMTP_HOST 미설정 - 콘솔 출력으로 대체\nTo: {to_email}\nSubject: {subject}\n{body}")
        return

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    reset_url = f"{settings.FRONTEND_PASSWORD_RESET_URL}?token={reset_token}"
    subject = "[Re:Call] 비밀번호 재설정 안내"
    body = (
        f"비밀번호를 재설정하려면 아래 링크를 눌러주세요.\n\n{reset_url}\n\n"
        f"이 링크는 {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES}분 동안만 유효합니다.\n"
        "본인이 요청하지 않았다면 이 메일을 무시하세요."
    )
    send_email(to_email, subject, body)