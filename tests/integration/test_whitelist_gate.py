"""Integration: only authorized senders are served (US2, SC-002/FR-003/FR-015)."""

from __future__ import annotations

from helpers import FakeDetector, FakeMailbox, FakeSMTP, make_request, make_settings
from spam_watcher.models import ClassificationResult
from spam_watcher.notifier import Notifier
from spam_watcher.processor import Processor


def _run(request):
    settings = make_settings()
    mailbox = FakeMailbox([request])
    detector = FakeDetector(result=ClassificationResult(True, 0.9, False, "x"))
    sent: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))
    Processor(settings, mailbox, detector, notifier).run_once()
    return detector, sent, mailbox


def test_non_whitelisted_sender_ignored():
    detector, sent, mailbox = _run(make_request(from_address="user@evil.com"))
    assert detector.calls == 0
    assert sent == []
    assert mailbox.expunged == []


def test_self_generated_message_skipped():
    detector, sent, mailbox = _run(
        make_request(from_address="user@example.com", is_self_generated=True)
    )
    assert detector.calls == 0
    assert sent == []
    assert mailbox.expunged == []
