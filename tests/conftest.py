"""Pytest fixtures (shared fakes/helpers live in tests/helpers.py)."""

from __future__ import annotations

import pytest

from helpers import make_settings


@pytest.fixture
def settings():
    return make_settings()
