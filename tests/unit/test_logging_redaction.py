"""Unit tests for log secret redaction (FR-014/FR-017/SC-008)."""

from __future__ import annotations

import logging

from spam_watcher.logging_setup import SecretRedactor, configure_logging


def _record(msg, args=None):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


def test_redactor_scrubs_message():
    record = _record("token is s3cr3t here")
    SecretRedactor(["s3cr3t"]).filter(record)
    assert "s3cr3t" not in record.getMessage()
    assert "***" in record.getMessage()


def test_redactor_scrubs_args():
    record = _record("value=%s", ("pw123",))
    SecretRedactor(["pw123"]).filter(record)
    assert "pw123" not in record.getMessage()


def test_configure_logging_installs_redactor():
    configure_logging(secrets=["abc"])
    root = logging.getLogger()
    assert any(isinstance(f, SecretRedactor) for h in root.handlers for f in h.filters)
