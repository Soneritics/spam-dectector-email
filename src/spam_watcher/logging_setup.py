"""Structured JSON logging with secret redaction (FR-014/FR-017)."""

from __future__ import annotations

import logging
from collections.abc import Iterable

try:  # python-json-logger >= 3
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # python-json-logger 2.x
    from pythonjsonlogger.jsonlogger import JsonFormatter

_REDACTION = "***"


class SecretRedactor(logging.Filter):
    """Replaces known secret substrings in log messages so they never reach the output."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def _scrub(self, value: str) -> str:
        for secret in self._secrets:
            if secret and secret in value:
                value = value.replace(secret, _REDACTION)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._scrub_arg(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._scrub_arg(a) for a in record.args)
        return True

    def _scrub_arg(self, arg: object) -> object:
        return self._scrub(arg) if isinstance(arg, str) else arg


def configure_logging(level: int = logging.INFO, secrets: Iterable[str] = ()) -> None:
    """Install a JSON stream handler on the root logger with secret redaction."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(SecretRedactor(secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
