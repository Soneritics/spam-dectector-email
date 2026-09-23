"""Contract test: detector request shaping and response handling.

See specs/001-imap-spam-watcher/contracts/spam-detector-api.md.
"""

from __future__ import annotations

import httpx

from helpers import make_settings
from spam_watcher.detector import SpamDetectorClient

_OK = {
    "result": {"spam": True, "confidence": 0.5, "promptInjectionDetected": False, "reason": "r"},
    "httpCode": 200,
    "isError": False,
}


def _client(settings, handler):
    return SpamDetectorClient(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _s: None
    )


def test_request_shape_and_required_headers():
    settings = make_settings(detector_model="")
    captured: dict = {}

    def handler(request):
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["content"] = request.content
        return httpx.Response(200, json=_OK)

    _client(settings, handler).classify("raw email body")
    assert captured["method"] == "POST"
    assert captured["url"] == settings.detector_url
    assert captured["headers"]["x-functions-key"] == "func-secret"
    assert captured["headers"]["x-openai-api-key"] == "openai-secret"
    assert captured["headers"]["content-type"].startswith("text/plain")
    assert "x-openai-model" not in captured["headers"]
    assert captured["content"] == b"raw email body"


def test_model_header_only_when_configured():
    settings = make_settings(detector_model="gpt-4o-mini")
    captured: dict = {}

    def handler(request):
        captured["headers"] = request.headers
        return httpx.Response(200, json=_OK)

    _client(settings, handler).classify("body")
    assert captured["headers"]["x-openai-model"] == "gpt-4o-mini"


def test_success_response_mapped_to_result():
    result = _client(make_settings(), lambda _r: httpx.Response(200, json=_OK)).classify("body")
    assert result.spam is True
    assert result.confidence == 0.5
    assert result.is_error is False
