"""Integration: whitelisted forward -> verdict reply -> expunge (US1, SC-001/SC-005)."""

from __future__ import annotations

from helpers import FakeDetector, FakeMailbox, FakeSMTP, make_request, make_settings
from spam_watcher.models import ClassificationResult, ContentSource
from spam_watcher.notifier import Notifier
from spam_watcher.processor import Processor


def test_whitelisted_forward_gets_verdict_and_is_expunged():
    settings = make_settings()
    request = make_request(
        message_uid="7",
        from_address="user@example.com",
        content_source=ContentSource.ATTACHED_ORIGINAL,
    )
    mailbox = FakeMailbox([request])
    detector = FakeDetector(result=ClassificationResult(True, 0.88, False, "spammy"))
    sent: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))

    Processor(settings, mailbox, detector, notifier).run_once()

    assert detector.calls == 1
    assert len(sent) == 1
    message, to_addrs = sent[0]
    assert message["Subject"] == "Spam check: Please check"
    assert to_addrs == ["user@example.com"]
    assert mailbox.expunged == ["7"]
