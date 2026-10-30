"""Outgoing email. SMTP works for both Mailpit (local inbox) and real providers (Brevo/Resend)."""

import asyncio
import html
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from seomaster_core.config import Settings


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    async def send(self, email: Email) -> None:
        await asyncio.to_thread(self._send, email)

    def _send(self, email: Email) -> None:
        msg = EmailMessage()
        msg["From"] = self.s.email_from
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
            if self.s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.s.smtp_user:
                smtp.login(self.s.smtp_user, self.s.smtp_password.get_secret_value())
            smtp.send_message(msg)


@dataclass
class MemoryMailer:
    """Test double: keeps sent emails in memory."""

    outbox: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.outbox.append(email)


def verification_email(to: str, name: str | None, url: str) -> Email:
    hello = f"Hi {name}," if name else "Hi,"
    text = (
        f"{hello}\n\nConfirm your email to finish creating your SeoMaster account:\n{url}\n\n"
        "The link expires in 48 hours. If you didn't sign up, ignore this email."
    )
    safe_url = html.escape(url, quote=True)
    body = (
        f"<p>{html.escape(hello)}</p>"
        "<p>Confirm your email to finish creating your SeoMaster account:</p>"
        f'<p><a href="{safe_url}" style="background:#0f766e;color:#fff;padding:10px 16px;'
        'border-radius:6px;text-decoration:none">Verify email</a></p>'
        '<p style="color:#6b7280">The link expires in 48 hours. If you didn\'t sign up, '
        "ignore this email.</p>"
    )
    return Email(to=to, subject="Verify your SeoMaster email", text=text, html=body)
