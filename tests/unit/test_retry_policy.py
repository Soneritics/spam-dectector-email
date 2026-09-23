"""Unit tests for the detector retry policy (FR-010/FR-016/FR-020)."""

from __future__ import annotations

import httpx
import pytest

from helpers import make_settings
from spam_watcher.detector import (
    DeterministicDetectorError,
    SpamDetectorClient,
    TransientDetectorError,
)


def _client(settings, handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return SpamDetectorClient(settings, client=client, sleep=lambda _s: None)


def _ok(spam=True):
    return {
        "result": {
            "spam": spam,
            "confidence": 0.9,
            "promptInjectionDetected": False,
            "reason": "why",
        },
        "httpCode": 200,
        "isError": False,
    }


def test_success_maps_result():
    result = _client(make_settings(), lambda _r: httpx.Response(200, json=_ok(True))).classify("c")
    assert result.spam is True
    assert result.confidence == 0.9
    assert result.reason == "why"


def test_deterministic_400_not_retried():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(400, json={"isError": True, "errorMessage": "empty body"})

    with pytest.raises(DeterministicDetectorError):
        _client(make_settings(), handler).classify("x")
    assert calls["n"] == 1


def test_transient_502_then_success():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json=_ok(False))

    result = _client(make_settings(), handler).classify("x")
    assert result.spam is False
    assert calls["n"] == 2


def test_transient_exhausts_configured_attempts():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(TransientDetectorError):
        _client(make_settings(retry_max_attempts=3), handler).classify("x")
    assert calls["n"] == 3


def test_unexpected_status_treated_as_transient():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(418, text="teapot")

    with pytest.raises(TransientDetectorError):
        _client(make_settings(retry_max_attempts=2), handler).classify("x")
    assert calls["n"] == 2
