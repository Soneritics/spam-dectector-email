"""Per-message orchestration: whitelist gate -> extract -> classify -> notify -> expunge."""

from __future__ import annotations

import logging
import re

from .config import Settings
from .detector import DetectorError, DeterministicDetectorError
from .models import IncomingRequest, Notification

logger = logging.getLogger("spam_watcher.processor")


def matches_whitelist(from_address: str, pattern: re.Pattern[str]) -> bool:
    """True when the From address matches the compiled whitelist pattern (FR-002/FR-003)."""
    return bool(from_address) and pattern.search(from_address) is not None


class Processor:
    """Drives one processing pass over the mailbox and handles a single message end to end."""

    def __init__(self, settings: Settings, mailbox, detector, notifier) -> None:
        self._settings = settings
        self._mailbox = mailbox
        self._detector = detector
        self._notifier = notifier
        self._pattern = settings.whitelist_pattern

    def run_once(self) -> None:
        for request in self._mailbox.fetch_pending():
            self.process(request)

    def process(self, request: IncomingRequest) -> None:
        # Self-reply-loop guard (FR-015).
        if request.is_self_generated:
            logger.info("skip_self_generated", extra={"uid": request.message_uid})
            return

        # Whitelist gate (FR-002/FR-003) — enforced before any classification.
        if not matches_whitelist(request.from_address, self._pattern):
            logger.info(
                "ignored_non_whitelisted",
                extra={"uid": request.message_uid, "sender": request.from_address},
            )
            return

        try:
            notification = self._build_notification(request)
        except Exception:  # noqa: BLE001 - unexpected; leave message for a later poll
            logger.exception("processing_error", extra={"uid": request.message_uid})
            return

        # Send first; only expunge after a successful send so nothing is lost (FR-011/FR-016).
        try:
            self._notifier.send(notification)
        except Exception:  # noqa: BLE001 - outgoing failure: retry on a later poll
            logger.error("send_failed_will_retry", extra={"uid": request.message_uid})
            return

        logger.info(
            "message_processed",
            extra={
                "uid": request.message_uid,
                "sender": request.from_address,
                "subject": request.subject,
                "decision": notification.kind.value,
            },
        )

        try:
            self._mailbox.expunge(request.message_uid)
        except Exception:  # noqa: BLE001 - expunge failure is non-fatal (may re-send once)
            logger.error("expunge_failed", extra={"uid": request.message_uid})

    def _build_notification(self, request: IncomingRequest) -> Notification:
        if not request.content_to_classify:
            error = DeterministicDetectorError(
                "empty_content", "The forwarded message had no content to classify."
            )
            return self._notifier.build_error(request, error)
        try:
            result = self._detector.classify(request.content_to_classify)
        except DetectorError as error:
            return self._notifier.build_error(request, error)
        return self._notifier.build_verdict(request, result)
