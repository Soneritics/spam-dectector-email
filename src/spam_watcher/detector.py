"""HTTP client for the Spam Detector Azure Function with bounded retry.

Implements FR-005/FR-006/FR-010/FR-016/FR-020.
See specs/001-imap-spam-watcher/contracts/spam-detector-api.md.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import httpx

from .config import Settings
from .models import ClassificationResult

_DETERMINISTIC_STATUSES = {400, 413}


class DetectorError(Exception):
    """Base class for classification failures. Carries a non-sensitive category + message."""

    def __init__(self, category: str, message: str, http_code: int | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.http_code = http_code


class TransientDetectorError(DetectorError):
    """A failure that may succeed on retry (timeout, connectivity, 5xx, unexpected status)."""


class DeterministicDetectorError(DetectorError):
    """A failure that will not succeed on retry (empty/oversized/rejected content)."""


class SpamDetectorClient:
    """Submits raw content and returns a ``ClassificationResult`` or raises ``DetectorError``."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0))
        self._owns_client = client is None
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "x-functions-key": self._settings.detector_functions_key,
            "x-openai-api-key": self._settings.detector_openai_key,
            "Content-Type": "text/plain",
        }
        if self._settings.detector_model:
            headers["x-openai-model"] = self._settings.detector_model
        return headers

    def classify(self, content: str) -> ClassificationResult:
        """Classify ``content`` with bounded exponential backoff on transient failures."""
        attempts = max(1, self._settings.retry_max_attempts)
        window = max(0, self._settings.retry_window_seconds)
        elapsed = 0.0
        last: TransientDetectorError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._attempt(content)
            except DeterministicDetectorError:
                raise
            except TransientDetectorError as exc:
                last = exc
                if attempt >= attempts:
                    break
                delay = min(2.0 * (2 ** (attempt - 1)), max(window - elapsed, 0.0))
                delay += random.uniform(0.0, 0.25)
                elapsed += delay
                self._sleep(delay)
        assert last is not None
        raise last

    def _attempt(self, content: str) -> ClassificationResult:
        try:
            response = self._client.post(
                self._settings.detector_url,
                content=content.encode("utf-8"),
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise TransientDetectorError("timeout", "The spam detector timed out.") from exc
        except httpx.RequestError as exc:
            raise TransientDetectorError(
                "connectivity", "The spam detector could not be reached."
            ) from exc

        code = response.status_code
        if code in _DETERMINISTIC_STATUSES:
            raise DeterministicDetectorError(
                "content_rejected", self._error_message(response, code), code
            )
        if code >= 500:
            raise TransientDetectorError(
                "server_error", "The spam detector reported a server error.", code
            )
        if code != 200:
            raise TransientDetectorError(
                "unexpected_status", f"The spam detector returned status {code}.", code
            )

        data = response.json()
        if data.get("isError"):
            http_code = data.get("httpCode")
            message = data.get("errorMessage") or "The spam detector reported an error."
            if isinstance(http_code, int) and http_code >= 500:
                raise TransientDetectorError("upstream_error", message, http_code)
            raise DeterministicDetectorError("detector_error", message, http_code)

        result = data.get("result") or {}
        return ClassificationResult(
            spam=bool(result.get("spam")),
            confidence=float(result.get("confidence") or 0.0),
            prompt_injection_detected=bool(result.get("promptInjectionDetected")),
            reason=str(result.get("reason") or ""),
            is_error=False,
            http_code=200,
        )

    @staticmethod
    def _error_message(response: httpx.Response, code: int) -> str:
        try:
            body = response.json()
            message = body.get("errorMessage")
            if message:
                return str(message)
        except (ValueError, AttributeError):
            pass
        if code == 413:
            return "The message was too large to classify."
        return "The request was rejected (empty or invalid content)."
