"""
Email Service
=============
Sends notification emails via SMTP (Gmail App Password / any provider).
Uses Python's built-in smtplib — no external email library needed.

Supports both port 587 (STARTTLS) and port 465 (SSL).
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from config import get_settings

log = logging.getLogger(__name__)


def is_configured() -> bool:
    """Check whether SMTP credentials are present in settings."""
    settings = get_settings()
    user = (settings.smtp_user or "").strip()
    pwd = (settings.smtp_password or "").strip()
    return bool(user and pwd)


def _build_html_body(
    subject: str,
    body_lines: list[str],
    footer: str = "IBA Sukkur University Portal",
) -> str:
    """Build a simple styled HTML email body."""
    rows = "".join(f"<p style='margin:6px 0;color:#333;'>{line}</p>" for line in body_lines)
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:24px;border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#4F46E5;margin-bottom:16px;">{subject}</h2>
        {rows}
        <hr style="margin:24px 0;border:none;border-top:1px solid #eee;" />
        <p style="font-size:12px;color:#999;">{footer}</p>
    </div>
    """


def send_email(
    to_email: str,
    subject: str,
    body_lines: list[str],
) -> bool:
    """
    Send a single email.

    Returns True on success, False on failure (logged, never raises).
    Automatically picks SSL (port 465) or STARTTLS (port 587) based on config.
    """
    if not is_configured():
        log.warning("SMTP credentials not configured — skipping email to %s", to_email)
        return False

    settings = get_settings()
    smtp_host = settings.smtp_host
    smtp_port = settings.smtp_port
    smtp_user = settings.smtp_user
    smtp_password = settings.smtp_password
    from_email = settings.smtp_from_email or smtp_user

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    html = _build_html_body(subject, body_lines)
    msg.attach(MIMEText("\n".join(body_lines), "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        if smtp_port == 465:
            # SSL connection
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email, msg.as_string())
        else:
            # STARTTLS connection (port 587 or other)
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email, msg.as_string())
        log.info("✅ Email sent → %s | subject=%s", to_email, subject)
        return True
    except Exception as exc:
        log.error("❌ Failed to send email to %s: %s", to_email, exc)
        return False


def send_bulk_email(
    recipients: list[dict[str, str]],
    subject: str,
    body_lines: list[str],
) -> dict[str, Any]:
    """
    Send the same email to multiple recipients.

    Each item in `recipients` should have at least an "email" key.
    Returns {"sent": int, "failed": int, "total": int, "configured": bool}.
    """
    if not is_configured():
        log.warning("SMTP not configured — skipping bulk email to %d recipients", len(recipients))
        return {"sent": 0, "failed": 0, "total": len(recipients), "configured": False}

    sent = 0
    failed = 0
    for r in recipients:
        email = r.get("email", "").strip()
        if not email:
            failed += 1
            continue
        ok = send_email(email, subject, body_lines)
        if ok:
            sent += 1
        else:
            failed += 1

    return {"sent": sent, "failed": failed, "total": len(recipients), "configured": True}
