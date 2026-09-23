"""Typed configuration loaded and validated from environment variables (FR-013/FR-021)."""

from __future__ import annotations

import re

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Field names that hold secrets and must never be logged (FR-014).
SECRET_FIELDS = (
    "imap_password",
    "smtp_password",
    "detector_functions_key",
    "detector_openai_key",
)


class ConfigError(Exception):
    """Raised when configuration is missing or invalid; message names offending settings only."""


def parse_cc_list(raw: str) -> list[str]:
    """Split a semicolon-separated CC string, trimming whitespace and dropping empties (FR-009)."""
    return [part.strip() for part in (raw or "").split(";") if part.strip()]


class Settings(BaseSettings):
    """All runtime configuration. Env var names match field names (case-insensitive)."""

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str

    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str

    whitelist_regex: str
    cc_addresses: str = ""

    detector_url: str
    detector_functions_key: str
    detector_openai_key: str
    detector_model: str = ""

    poll_interval_seconds: int = 45
    retry_max_attempts: int = 3
    retry_window_seconds: int = 90

    @field_validator("imap_port", "smtp_port")
    @classmethod
    def _valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("must be between 1 and 65535")
        return value

    @field_validator("whitelist_regex")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"is not a valid regular expression ({exc})") from None
        return value

    @field_validator("detector_url")
    @classmethod
    def _valid_url(cls, value: str) -> str:
        if not re.match(r"^https?://", value):
            raise ValueError("must be an absolute http(s) URL")
        return value

    @field_validator("cc_addresses")
    @classmethod
    def _valid_cc(cls, value: str) -> str:
        for addr in parse_cc_list(value):
            if not _EMAIL_RE.match(addr):
                raise ValueError(f"contains an invalid email address: {addr!r}")
        return value

    @field_validator("poll_interval_seconds")
    @classmethod
    def _valid_poll(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than 0")
        return value

    @field_validator("retry_max_attempts")
    @classmethod
    def _valid_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be at least 1")
        return value

    @field_validator("retry_window_seconds")
    @classmethod
    def _valid_window(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be 0 or greater")
        return value

    @property
    def whitelist_pattern(self) -> re.Pattern[str]:
        """Compiled, case-insensitive whitelist pattern (FR-002)."""
        return re.compile(self.whitelist_regex, re.IGNORECASE)

    @property
    def cc_list(self) -> list[str]:
        """Parsed CC recipients (FR-009)."""
        return parse_cc_list(self.cc_addresses)

    def secret_values(self) -> list[str]:
        """Non-empty secret values, for log redaction (FR-014)."""
        return [v for v in (getattr(self, f) for f in SECRET_FIELDS) if v]


def load_settings() -> Settings:
    """Load and validate configuration, failing fast with a non-sensitive error (FR-021)."""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            loc = err.get("loc") or ("?",)
            name = str(loc[0]).upper()
            problems.append(f"{name} {err.get('msg')}")
        raise ConfigError("Invalid configuration: " + "; ".join(problems)) from None
