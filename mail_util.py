"""Send email via SMTP (stdlib). Configure with SMTP_* environment variables."""
import os
import smtplib
import ssl
from email.message import EmailMessage


def smtp_configured() -> bool:
    if os.environ.get("SMTP_ENABLED", "1").lower() in ("0", "false", "no"):
        return False
    host = (os.environ.get("SMTP_HOST") or "").strip()
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = os.environ.get("SMTP_PASSWORD") or ""
    return bool(host and user and password)


def send_mail(to: str, subject: str, body: str) -> None:
    if not smtp_configured():
        raise RuntimeError("SMTP is not configured")

    host = os.environ["SMTP_HOST"].strip()
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"].strip()
    password = os.environ["SMTP_PASSWORD"]
    from_addr = (os.environ.get("SMTP_FROM") or user).strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "1").lower() not in ("0", "false", "no")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(body)

    if use_tls and port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls(context=ssl.create_default_context())
        smtp.login(user, password)
        smtp.send_message(msg)
