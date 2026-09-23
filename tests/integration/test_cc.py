"""Integration: CC recipients on replies and errors (US4, SC-007/FR-009)."""

from __future__ import annotations

from helpers import FakeDetector, FakeMailbox, FakeSMTP, make_request, make_settings
from spam_watcher.models import ClassificationResult
from spam_watcher.notifier import Notifier
from spam_watcher.processor import Processor


def _run(settings, request, detector):
    mailbox = FakeMailbox([request])
    sent: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))
    Processor(settings, mailbox, detector, notifier).run_once()
    return sent


def test_cc_applied_to_verdict():
    settings = make_settings(cc_addresses="sec@example.com; ; ops@example.com")
    request = make_request(from_address="user@example.com", reply_to_address=None)
    detector = FakeDetector(result=ClassificationResult(True, 0.9, False, "x"))
    sent = _run(settings, request, detector)
    _message, to_addrs = sent[0]
    assert to_addrs == ["user@example.com", "sec@example.com", "ops@example.com"]


def test_no_cc_addresses_sender_only():
    settings = make_settings(cc_addresses="")
    request = make_request(from_address="user@example.com", reply_to_address=None)
    detector = FakeDetector(result=ClassificationResult(False, 0.1, False, "x"))
    sent = _run(settings, request, detector)
    _message, to_addrs = sent[0]
    assert to_addrs == ["user@example.com"]
