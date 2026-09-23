"""Builds and sends multipart HTML + plain-text notifications via SMTP.

Implements FR-007/FR-008/FR-009/FR-010/FR-019.
"""

from __future__ import annotations

import html
import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from .config import Settings
from .detector import DetectorError
from .models import (
    ClassificationResult,
    IncomingRequest,
    Notification,
    NotificationKind,
)

WATCHER_HEADER = "X-Spam-Watcher"


class Notifier:
    """Constructs verdict/error notifications and delivers them (Reply-To else From, plus CC)."""

    def __init__(
        self,
        settings: Settings,
        smtp_factory: Callable[[], smtplib.SMTP] | None = None,
    ) -> None:
        self._settings = settings
        self._smtp_factory = smtp_factory or self._default_smtp

    # ---- building -------------------------------------------------------

    def build_verdict(self, request: IncomingRequest, result: ClassificationResult) -> Notification:
        verdict = "SPAM" if result.spam else "Not spam"
        colour = "#c0392b" if result.spam else "#1e8449"
        confidence_pct = round(result.confidence * 100)
        source = (
            "the attached original message"
            if request.content_source.value == "attached_original"
            else "the received message body"
        )
        injection = "Yes" if result.prompt_injection_detected else "No"
        reason = result.reason or "(no reason provided)"

        text_body = (
            f"Spam check result: {verdict}\n"
            f"Confidence: {confidence_pct}%\n"
            f"Prompt injection detected: {injection}\n"
            f"Reason: {reason}\n"
            f"Content evaluated: {source}\n"
        )
        html_body = (
            "<html><body>"
            f"<p>Spam check result: "
            f'<strong style="color:{colour}">{html.escape(verdict)}</strong></p>'
            f"<ul>"
            f"<li>Confidence: {confidence_pct}%</li>"
            f"<li>Prompt injection detected: {injection}</li>"
            f"<li>Reason: {html.escape(reason)}</li>"
            f"<li>Content evaluated: {html.escape(source)}</li>"
            f"</ul></body></html>"
        )
        return self._notification(request, NotificationKind.VERDICT, text_body, html_body)

    def build_error(self, request: IncomingRequest, error: DetectorError) -> Notification:
        category = getattr(error, "category", "error")
        message = getattr(error, "message", str(error))
        text_body = (
            "Your message could not be checked for spam.\n"
            f"Reason: {message}\n"
            f"Category: {category}\n"
        )
        html_body = (
            "<html><body>"
            "<p>Your message could not be checked for spam.</p>"
            f"<ul><li>Reason: {html.escape(message)}</li>"
            f"<li>Category: {html.escape(category)}</li></ul>"
            "</body></html>"
        )
        return self._notification(request, NotificationKind.ERROR, text_body, html_body)

    def _notification(
        self,
        request: IncomingRequest,
        kind: NotificationKind,
        text_body: str,
        html_body: str,
    ) -> Notification:
        return Notification(
            to_address=request.target_address,
            cc_addresses=list(self._settings.cc_list),
            subject=f"Spam check: {request.subject}",
            kind=kind,
            html_body=html_body,
            text_body=text_body,
            headers={WATCHER_HEADER: "reply"},
        )

    def to_email_message(self, notification: Notification) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._settings.smtp_username
        message["To"] = notification.to_address
        if notification.cc_addresses:
            message["Cc"] = ", ".join(notification.cc_addresses)
        message["Subject"] = notification.subject
        for key, value in notification.headers.items():
            message[key] = value
        message.set_content(notification.text_body)
        message.add_alternative(notification.html_body, subtype="html")
        return message

    # ---- sending --------------------------------------------------------

    def send(self, notification: Notification) -> None:
        message = self.to_email_message(notification)
        recipients = [notification.to_address, *notification.cc_addresses]
        smtp = self._smtp_factory()
        try:
            smtp.send_message(message, to_addrs=recipients)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001 - best-effort close
                pass

    def _default_smtp(self) -> smtplib.SMTP:
        host = self._settings.smtp_host
        port = self._settings.smtp_port
        if port == 465:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            smtp = smtplib.SMTP(host, port, timeout=30)
            try:  # TLS preferred; fall back to plaintext when unsupported (Transport security)
                smtp.starttls()
            except smtplib.SMTPNotSupportedError:
                pass
        smtp.login(self._settings.smtp_username, self._settings.smtp_password)
        return smtp
