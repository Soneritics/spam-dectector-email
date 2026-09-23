"""Unit tests for notification building and sending (FR-008/FR-009/FR-010/FR-019)."""

from __future__ import annotations

from helpers import FakeSMTP, make_request, make_settings
from spam_watcher.detector import DeterministicDetectorError
from spam_watcher.models import ClassificationResult, ContentSource, NotificationKind
from spam_watcher.notifier import WATCHER_HEADER, Notifier


def test_build_verdict_fields():
    settings = make_settings(cc_addresses="a@example.com;b@example.com")
    request = make_request(
        subject="Check this",
        reply_to_address="reply@example.com",
        content_source=ContentSource.ATTACHED_ORIGINAL,
    )
    result = ClassificationResult(True, 0.92, True, "looks spammy")
    notification = Notifier(settings).build_verdict(request, result)
    assert notification.subject == "Spam check: Check this"
    assert notification.to_address == "reply@example.com"
    assert notification.cc_addresses == ["a@example.com", "b@example.com"]
    assert notification.kind == NotificationKind.VERDICT
    assert "SPAM" in notification.text_body
    assert "92%" in notification.text_body
    assert "attached original" in notification.text_body
    assert notification.headers[WATCHER_HEADER] == "reply"


def test_build_verdict_not_spam_uses_text():
    result = ClassificationResult(False, 0.1, False, "clean")
    notification = Notifier(make_settings()).build_verdict(make_request(), result)
    assert "Not spam" in notification.text_body


def test_build_error_has_message_and_no_original_content():
    request = make_request(content_to_classify="secret private body")
    error = DeterministicDetectorError("content_rejected", "message too large")
    notification = Notifier(make_settings()).build_error(request, error)
    assert notification.kind == NotificationKind.ERROR
    assert "message too large" in notification.text_body
    assert "secret private body" not in notification.text_body
    assert "secret private body" not in notification.html_body


def test_to_email_message_multipart_with_recipients_and_header():
    settings = make_settings(cc_addresses="cc@example.com")
    request = make_request(from_address="user@example.com", reply_to_address=None)
    result = ClassificationResult(True, 0.5, False, "r")
    notification = Notifier(settings).build_verdict(request, result)
    message = Notifier(settings).to_email_message(notification)
    assert message["To"] == "user@example.com"
    assert message["Cc"] == "cc@example.com"
    assert message["X-Spam-Watcher"] == "reply"
    assert message.get_content_type() == "multipart/alternative"
    subtypes = [part.get_content_type() for part in message.iter_parts()]
    assert "text/plain" in subtypes
    assert "text/html" in subtypes


def test_send_includes_cc_in_recipients():
    settings = make_settings(cc_addresses="cc@example.com")
    store: list = []
    notifier = Notifier(settings, smtp_factory=lambda: FakeSMTP(store))
    request = make_request(from_address="user@example.com", reply_to_address=None)
    notifier.send(notifier.build_verdict(request, ClassificationResult(False, 0.1, False, "r")))
    _message, to_addrs = store[0]
    assert to_addrs == ["user@example.com", "cc@example.com"]
