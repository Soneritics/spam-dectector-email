"""Shared test helpers and in-process fakes."""

from __future__ import annotations

import smtplib

from spam_watcher.config import Settings
from spam_watcher.models import ContentSource, IncomingRequest

BASE_CONFIG = {
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_username": "watch@example.com",
    "imap_password": "imap-secret",
    "smtp_host": "smtp.example.com",
    "smtp_port": 465,
    "smtp_username": "watch@example.com",
    "smtp_password": "smtp-secret",
    "whitelist_regex": r"^.*@example\.com$",
    "cc_addresses": "",
    "detector_url": "https://detector.example.com/spam-check/email",
    "detector_functions_key": "func-secret",
    "detector_openai_key": "openai-secret",
    "detector_model": "",
    "poll_interval_seconds": 45,
    "retry_max_attempts": 3,
    "retry_window_seconds": 90,
}


def make_settings(**overrides) -> Settings:
    return Settings(**{**BASE_CONFIG, **overrides})


def make_request(**overrides) -> IncomingRequest:
    data = {
        "message_uid": "1",
        "from_address": "user@example.com",
        "reply_to_address": None,
        "subject": "Please check",
        "content_to_classify": "buy cheap pills now",
        "content_source": ContentSource.MESSAGE_BODY,
        "is_self_generated": False,
    }
    data.update(overrides)
    return IncomingRequest(**data)


class FakeDetector:
    """Stand-in for SpamDetectorClient."""

    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def classify(self, content: str):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeSMTP:
    """Captures messages instead of sending; shares a store across factory calls."""

    def __init__(self, store: list, fail: bool = False) -> None:
        self._store = store
        self._fail = fail

    def send_message(self, message, to_addrs=None):
        if self._fail:
            raise smtplib.SMTPException("simulated send failure")
        self._store.append((message, to_addrs))

    def quit(self):
        pass


class FakeMailbox:
    """In-memory mailbox returning requests until they are expunged."""

    def __init__(self, requests) -> None:
        self._requests = list(requests)
        self.expunged: list[str] = []

    def fetch_pending(self):
        return list(self._requests)

    def expunge(self, uid: str) -> None:
        self.expunged.append(uid)
        self._requests = [r for r in self._requests if r.message_uid != uid]
