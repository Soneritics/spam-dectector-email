"""IMAP access: fetch pending messages, extract content, expunge after send.

Implements FR-001/FR-004/FR-011/FR-018.
"""

from __future__ import annotations

import email
import logging
import re
from email import policy
from email.message import EmailMessage
from email.utils import parseaddr

from .config import Settings
from .models import ContentSource, IncomingRequest

logger = logging.getLogger("spam_watcher.mailbox")

WATCHER_HEADER = "X-Spam-Watcher"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw: str) -> str:
    import html as _html

    return _html.unescape(_TAG_RE.sub(" ", raw)).strip()


def _message_text(message: EmailMessage) -> str:
    """Return the best textual content of a message (prefer text/plain, else stripped text/html)."""
    try:
        plain = message.get_body(preferencelist=("plain",))
        if plain is not None:
            return str(plain.get_content()).strip()
        rich = message.get_body(preferencelist=("html",))
        if rich is not None:
            return _strip_html(str(rich.get_content()))
    except (KeyError, AttributeError, LookupError):
        pass
    return ""


def _attached_original(message: EmailMessage) -> EmailMessage | None:
    """Return the first attached original message (`message/rfc822` or `.eml`), if any (FR-004)."""
    for part in message.walk():
        if part is message:
            continue
        if part.get_content_type() == "message/rfc822":
            try:
                content = part.get_content()
            except Exception:  # noqa: BLE001 - fall back to raw payload
                content = None
            if isinstance(content, EmailMessage):
                return content
            payload = part.get_payload()
            if isinstance(payload, list) and payload and isinstance(payload[0], EmailMessage):
                return payload[0]  # type: ignore[return-value]
        filename = part.get_filename()
        if filename and filename.lower().endswith(".eml"):
            try:
                raw = part.get_content()
                data = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
                return email.message_from_bytes(data, policy=policy.default)  # type: ignore[return-value]
            except Exception:  # noqa: BLE001 - malformed attachment: fall through
                continue
    return None


def extract_content(message: EmailMessage) -> tuple[str, ContentSource]:
    """Extract the content to classify: attached original first, otherwise the body (FR-004)."""
    try:
        original = _attached_original(message)
        if original is not None:
            text = _message_text(original)
            if text:
                return text, ContentSource.ATTACHED_ORIGINAL
        return _message_text(message), ContentSource.MESSAGE_BODY
    except Exception:  # noqa: BLE001 - malformed MIME must never crash the watcher (T027a)
        logger.warning("content_extraction_failed")
        return "", ContentSource.MESSAGE_BODY


def build_incoming_request(uid: str, message: EmailMessage) -> IncomingRequest:
    """Build an ``IncomingRequest`` from a fetched message; never raises on malformed input."""
    from_address = parseaddr(message.get("From", ""))[1].lower()
    reply_to = parseaddr(message.get("Reply-To", ""))[1] or None
    subject = str(message.get("Subject", "") or "")
    content, source = extract_content(message)
    is_self = message.get(WATCHER_HEADER) is not None
    return IncomingRequest(
        message_uid=uid,
        from_address=from_address,
        reply_to_address=reply_to,
        subject=subject,
        content_to_classify=content.strip(),
        content_source=source,
        is_self_generated=is_self,
    )


class Mailbox:
    """Thin IMAP wrapper over ``imap-tools`` for fetching and permanently expunging messages."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _connect(self):
        # Imported lazily so unit tests for extraction do not require imap-tools.
        from imap_tools import MailBox, MailBoxStartTls, MailBoxUnencrypted

        host = self._settings.imap_host
        port = self._settings.imap_port
        if port == 993:
            box = MailBox(host, port)
        else:
            try:  # TLS preferred; fall back to plaintext when unsupported (Transport security)
                box = MailBoxStartTls(host, port)
            except Exception:  # noqa: BLE001
                box = MailBoxUnencrypted(host, port)
        return box.login(self._settings.imap_username, self._settings.imap_password)

    def fetch_pending(self) -> list[IncomingRequest]:
        """Return every message currently in the mailbox as a pending request (FR-001)."""
        requests: list[IncomingRequest] = []
        with self._connect() as box:
            for msg in box.fetch(mark_seen=False):
                try:
                    parsed = email.message_from_bytes(msg.obj.as_bytes(), policy=policy.default)
                    requests.append(build_incoming_request(str(msg.uid), parsed))  # type: ignore[arg-type]
                except Exception:  # noqa: BLE001 - never let one bad message stop the batch
                    logger.warning("message_parse_failed", extra={"uid": getattr(msg, "uid", None)})
        return requests

    def expunge(self, uid: str) -> None:
        """Permanently remove a processed message (delete + expunge, not Trash) (FR-011/FR-018)."""
        with self._connect() as box:
            box.delete([uid])
