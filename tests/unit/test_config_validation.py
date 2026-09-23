"""Unit tests for configuration validation and fail-fast loading (FR-013/FR-021)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from helpers import BASE_CONFIG, make_settings
from spam_watcher.config import ConfigError, Settings, load_settings


def _set_env(monkeypatch, config: dict) -> None:
    for key, value in config.items():
        monkeypatch.setenv(key.upper(), str(value))


def test_valid_config_loads(monkeypatch):
    _set_env(monkeypatch, BASE_CONFIG)
    settings = load_settings()
    assert settings.imap_port == 993
    assert settings.retry_max_attempts == 3


@pytest.mark.parametrize(
    "override",
    [
        {"imap_port": 70000},
        {"smtp_port": 0},
        {"whitelist_regex": "([unclosed"},
        {"detector_url": "detector.example.com"},
        {"cc_addresses": "a@example.com; not-an-email"},
        {"poll_interval_seconds": 0},
        {"retry_max_attempts": 0},
    ],
)
def test_invalid_values_rejected(override):
    with pytest.raises(ValidationError):
        make_settings(**override)


def test_missing_required_field_names_setting(monkeypatch):
    config = dict(BASE_CONFIG)
    _set_env(monkeypatch, config)
    monkeypatch.delenv("DETECTOR_URL", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "DETECTOR_URL" in str(exc.value)


def test_config_error_never_echoes_secret(monkeypatch):
    config = dict(BASE_CONFIG)
    config["imap_port"] = 70000  # invalid, forces an error
    _set_env(monkeypatch, config)
    with pytest.raises(ConfigError) as exc:
        load_settings()
    message = str(exc.value)
    assert "imap-secret" not in message
    assert "func-secret" not in message
    assert "IMAP_PORT" in message


def test_secret_values_exposed_for_redaction():
    settings = make_settings()
    assert set(settings.secret_values()) == {
        "imap-secret",
        "smtp-secret",
        "func-secret",
        "openai-secret",
    }


def test_settings_env_names_match(monkeypatch):
    _set_env(monkeypatch, BASE_CONFIG)
    monkeypatch.setenv("CC_ADDRESSES", "a@example.com;b@example.com")
    settings = Settings()
    assert settings.cc_list == ["a@example.com", "b@example.com"]
