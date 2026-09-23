"""Integration: data handling — expunge after send, no secret leakage (FR-018/SC-009)."""

from __future__ import annotations

from helpers import FakeDetector, FakeMailbox, FakeSMTP, make_request, make_settings
from spam_watcher.models import ClassificationResult
from spam_watcher.notifier import Notifier
from spam_watcher.processor import Processor


def test_message_expunged_and_no_secret_in_outbound():
    settings = make_settings()
    request = make_request(message_uid="11", from_address="user@example.com")
    mailbox = FakeMailbox([request])
    detector = FakeDetector(result=ClassificationResult(True, 0.7, False, "reason"))
    sent: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))

    Processor(settings, mailbox, detector, notifier).run_once()

    assert mailbox.expunged == ["11"]
    assert mailbox.fetch_pending() == []
    message, _to = sent[0]
    rendered = message.as_string()
    assert settings.detector_functions_key not in rendered
    assert settings.imap_password not in rendered
