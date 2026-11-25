"""Zero-dependency email notification for new evaluator access requests."""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_RESEND_FROM = "Empório da Música <onboarding@resend.dev>"


def build_notification_body(name: str, email: str, note: str, admin_url: str | None = None) -> tuple[str, str]:
    subject = f"[Empório da Música] Nova solicitação de acesso: {name}"
    lines = [
        "Você recebeu uma nova solicitação de acesso para testar o agente do Empório da Música.",
        "",
        f"Nome: {name}",
        f"E-mail: {email}",
    ]
    if note:
        lines.append(f"Observação: {note}")
    if admin_url:
        lines.extend(["", f"Aprove ou recuse em: {admin_url}"])
    return subject, "\n".join(lines)


class EmailNotifier:
    """Sends access-request notifications via Resend HTTP API or SMTP (stdlib only)."""

    def __init__(
        self,
        notify_email: str,
        resend_api_key: str | None = None,
        resend_from: str = DEFAULT_RESEND_FROM,
        smtp_host: str | None = None,
        smtp_port: int = 465,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        opener=urllib.request.urlopen,
        timeout: float = 6.0,
    ) -> None:
        self._notify_email = notify_email.strip()
        self._resend_api_key = resend_api_key.strip() if resend_api_key else None
        self._resend_from = resend_from.strip() or DEFAULT_RESEND_FROM
        self._smtp_host = smtp_host.strip() if smtp_host else None
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user.strip() if smtp_user else None
        self._smtp_password = smtp_password
        self._opener = opener
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._notify_email and (self._resend_api_key or (self._smtp_host and self._smtp_user and self._smtp_password)))

    def notify_new_request(self, name: str, email: str, note: str = "", admin_url: str | None = None) -> bool:
        if not self.configured:
            return False
        subject, text_body = build_notification_body(name, email, note, admin_url)
        if self._resend_api_key:
            return self._send_resend(subject, text_body)
        return self._send_smtp(subject, text_body)

    def _send_resend(self, subject: str, text_body: str) -> bool:
        payload = json.dumps(
            {
                "from": self._resend_from,
                "to": [self._notify_email],
                "subject": subject,
                "text": text_body,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            RESEND_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._resend_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                return 200 <= getattr(resp, "status", 200) < 300
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            logger.warning("Failed to send Resend notification: %s", exc)
            return False

    def _send_smtp(self, subject: str, text_body: str) -> bool:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._smtp_user
        msg["To"] = self._notify_email
        msg.set_content(text_body)
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, context=context, timeout=self._timeout) as server:
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.warning("Failed to send SMTP notification: %s", exc)
            return False
