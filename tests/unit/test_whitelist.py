"""Unit tests for whitelist matching semantics (FR-002/FR-003)."""

from __future__ import annotations

import re

from spam_watcher.processor import matches_whitelist

PATTERN = re.compile(r"^.*@example\.com$", re.IGNORECASE)


def test_matches_whitelisted_address():
    assert matches_whitelist("user@example.com", PATTERN) is True


def test_case_insensitive():
    assert matches_whitelist("User@EXAMPLE.com", PATTERN) is True


def test_non_matching_domain_rejected():
    assert matches_whitelist("user@evil.com", PATTERN) is False


def test_empty_address_rejected():
    assert matches_whitelist("", PATTERN) is False
