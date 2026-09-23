"""Unit tests for content extraction and request building (FR-004)."""

from __future__ import annotations

from email.message import EmailMessage

from spam_watcher.mailbox import build_incoming_request, extract_content
from spam_watcher.models import ContentSource


def _plain(from_addr: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = from_addr
    message["Subject"] = subject
    message.set_content(body)
    return message


def test_body_used_when_no_attachment():
    content, source = extract_content(_plain("a@example.com", "hi", "hello world"))
    assert content.strip() == "hello world"
    assert source == ContentSource.MESSAGE_BODY


def test_attached_rfc822_preferred_over_body():
    inner = _plain("orig@x.com", "orig", "ORIGINAL SPAM BODY")
    outer = _plain("a@example.com", "fwd", "see attached")
    outer.add_attachment(inner)
    content, source = extract_content(outer)
    assert "ORIGINAL SPAM BODY" in content
    assert source == ContentSource.ATTACHED_ORIGINAL


def test_eml_attachment_used():
    inner = _plain("orig@x.com", "orig", "EML SPAM BODY")
    outer = _plain("a@example.com", "fwd", "see attached")
    outer.add_attachment(
        inner.as_bytes(), maintype="application", subtype="octet-stream", filename="original.eml"
    )
    content, source = extract_content(outer)
    assert "EML SPAM BODY" in content
    assert source == ContentSource.ATTACHED_ORIGINAL


def test_first_of_multiple_rfc822_attachments():
    outer = _plain("a@example.com", "fwd", "see attached")
    outer.add_attachment(_plain("o1@x.com", "o1", "FIRST BODY"))
    outer.add_attachment(_plain("o2@x.com", "o2", "SECOND BODY"))
    content, source = extract_content(outer)
    assert "FIRST BODY" in content
    assert "SECOND BODY" not in content
    assert source == ContentSource.ATTACHED_ORIGINAL


def test_empty_when_no_content():
    message = EmailMessage()
    message["From"] = "a@example.com"
    content, _ = extract_content(message)
    assert content == ""


def test_build_incoming_request_parses_headers():
    message = _plain("User <user@Example.com>", "subj", "body text")
    message["Reply-To"] = "reply@example.com"
    request = build_incoming_request("42", message)
    assert request.from_address == "user@example.com"
    assert request.reply_to_address == "reply@example.com"
    assert request.subject == "subj"
    assert request.target_address == "reply@example.com"


def test_self_generated_header_detected():
    message = _plain("a@example.com", "s", "b")
    message["X-Spam-Watcher"] = "reply"
    assert build_incoming_request("1", message).is_self_generated is True
