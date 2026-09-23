"""Integration: error notifications on failure (US3, SC-004/FR-010)."""

from __future__ import annotations

from helpers import FakeDetector, FakeMailbox, FakeSMTP, make_request, make_settings
from spam_watcher.detector import TransientDetectorError
from spam_watcher.models import ClassificationResult
from spam_watcher.notifier import Notifier
from spam_watcher.processor import Processor


def _plain_body(message):
    return message.get_body(preferencelist=("plain",)).get_content()


def test_detector_failure_sends_error_and_expunges():
    settings = make_settings()
    request = make_request(message_uid="3")
    mailbox = FakeMailbox([request])
    detector = FakeDetector(error=TransientDetectorError("server_error", "detector exploded"))
    sent: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))

    Processor(settings, mailbox, detector, notifier).run_once()

    assert len(sent) == 1
    message, _to = sent[0]
    body = _plain_body(message)
    assert "detector exploded" in body
    assert settings.detector_functions_key not in body
    assert mailbox.expunged == ["3"]


def test_empty_content_error_without_detector_call():
    settings = make_settings()
    request = make_request(message_uid="4", content_to_classify="")
    mailbox = FakeMailbox([request])
    detector = FakeDetector(result=ClassificationResult(False, 0.0, False, ""))
    sent: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(sent))

    Processor(settings, mailbox, detector, notifier).run_once()

    assert detector.calls == 0
    assert len(sent) == 1
    assert mailbox.expunged == ["4"]
