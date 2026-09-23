"""Unit tests for CC list parsing (FR-009)."""

from __future__ import annotations

from spam_watcher.config import parse_cc_list


def test_splits_trims_and_drops_empties():
    assert parse_cc_list("a@x.com; ;  b@y.com ") == ["a@x.com", "b@y.com"]


def test_empty_inputs():
    assert parse_cc_list("") == []
    assert parse_cc_list("   ") == []


def test_trailing_separator():
    assert parse_cc_list("a@x.com;") == ["a@x.com"]
