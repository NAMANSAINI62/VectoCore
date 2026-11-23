"""SMTP email delivery service for passwordless OTP sign-in (Gmail App Password compatible)."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """Return True when SMTP host, user, and password are configured."""
    settings = get_settings()
    return bool(settings.SMTP_HOST.strip() and settings.SMTP_USER.strip() and settings.SMTP_PASSWORD.strip())


def _send_smtp_sync(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    settings = get_settings()
    sender = (settings.SMTP_FROM_EMAIL or settings.SMTP_USER).strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"VectoCore <{sender}>" if "<" not in sender else sender
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST.strip(), settings.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        if settings.SMTP_USE_TLS:
            server.starttls()
            server.ehlo()
        server.login(settings.SMTP_USER.strip(), settings.SMTP_PASSWORD.strip())
        server.send_message(msg)


async def send_otp_email(
    to_email: str,
    otp_code: str,
    expire_minutes: int = 5,
    purpose: str = "sign-in",
) -> None:
    """Send a 6-digit verification OTP email via configured SMTP."""
    if not is_smtp_configured():
        raise RuntimeError(
            "Email OTP is not configured yet. Add SMTP_HOST, SMTP_USER, and SMTP_PASSWORD to backend/.env."
        )

    is_reset = purpose == "password-reset"
    title = "Reset your VectoCore password" if is_reset else "Sign in to VectoCore"
    subject = (
        f"{otp_code} is your VectoCore password reset code"
        if is_reset
        else f"{otp_code} is your VectoCore sign-in code"
    )
    text_body = (
        f"Your VectoCore verification code is: {otp_code}\n\n"
        f"This code expires in {expire_minutes} minutes. Do not share it with anyone."
    )
    html_body = f"""
    <div style="font-family:system-ui,-apple-system,sans-serif;max-width:460px;margin:0 auto;padding:24px;border:1px solid #e4e4e7;border-radius:12px;">
      <h2 style="margin:0 0 12px;font-size:18px;color:#18181b;">{title}</h2>
      <p style="margin:0 0 16px;font-size:14px;color:#52525b;">Enter this 6-digit verification code to continue:</p>
      <div style="font-size:28px;font-weight:700;letter-spacing:6px;padding:14px 18px;background:#f4f4f5;border-radius:8px;text-align:center;color:#18181b;">
        {otp_code}
      </div>
      <p style="margin:16px 0 0;font-size:12px;color:#71717a;">
        This code expires in {expire_minutes} minutes. If you didn't request this, you can safely ignore this email.
      </p>
    </div>
    """
    await asyncio.to_thread(_send_smtp_sync, to_email, subject, text_body, html_body)
    logger.info("Sent %s OTP email via SMTP to %s", purpose, to_email)
