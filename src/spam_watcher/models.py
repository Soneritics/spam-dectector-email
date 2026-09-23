"""In-memory value objects that flow through one processing pass.

See specs/001-imap-spam-watcher/data-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ContentSource(StrEnum):
    """Which part of the received message was classified."""

    ATTACHED_ORIGINAL = "attached_original"
    MESSAGE_BODY = "message_body"


class NotificationKind(StrEnum):
    """Whether an outbound message conveys a verdict or an error."""

    VERDICT = "verdict"
    ERROR = "error"


@dataclass
class IncomingRequest:
    """A message fetched from the monitored mailbox (FR-004)."""

    message_uid: str
    from_address: str
    reply_to_address: str | None
    subject: str
    content_to_classify: str
    content_source: ContentSource
    is_self_generated: bool = False

    @property
    def target_address(self) -> str:
        """Reply-To when present, otherwise From (FR-007)."""
        return self.reply_to_address or self.from_address


@dataclass
class ClassificationResult:
    """Parsed ``apiResult_spamResult`` outcome from the detector."""

    spam: bool
    confidence: float
    prompt_injection_detected: bool
    reason: str
    is_error: bool = False
    http_code: int | None = None
    error_message: str | None = None


@dataclass
class Notification:
    """An outbound reply or error email (FR-008/FR-010)."""

    to_address: str
    cc_addresses: list[str]
    subject: str
    kind: NotificationKind
    html_body: str
    text_body: str
    headers: dict[str, str] = field(default_factory=dict)
