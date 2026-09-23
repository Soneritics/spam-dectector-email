"""Integration: restart recovery — unsent message retried exactly once (SC-006/FR-011)."""

from __future__ import annotations

from helpers import FakeDetector, FakeMailbox, FakeSMTP, make_request, make_settings
from spam_watcher.models import ClassificationResult
from spam_watcher.notifier import Notifier
from spam_watcher.processor import Processor


def test_send_failure_leaves_message_then_processed_once():
    settings = make_settings()
    request = make_request(message_uid="9")
    mailbox = FakeMailbox([request])
    detector = FakeDetector(result=ClassificationResult(False, 0.2, False, "ok"))

    # First cycle: sending fails -> message must remain, not expunged.
    failed: list = []
    failing = Notifier(settings, smtp_factory=lambda: FakeSMTP(failed, fail=True))
    Processor(settings, mailbox, detector, failing).run_once()
    assert failed == []
    assert mailbox.expunged == []
    assert mailbox.fetch_pending() == [request]

    # Second cycle (post-restart): sending succeeds -> processed exactly once.
    sent: list = []
    working = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))
    Processor(settings, mailbox, detector, working).run_once()
    assert len(sent) == 1
    assert mailbox.expunged == ["9"]
    assert mailbox.fetch_pending() == []
