"""Tests for argus.auth (OAuth + session guard helpers)."""

from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest

from argus.auth import is_email_allowed, require_login
from argus.config import Settings
import argus.config


def _patch_allowed_emails(monkeypatch, emails: tuple[str, ...]) -> None:
    new_settings = Settings(
        report_hour=argus.config.settings.report_hour,
        report_minute=argus.config.settings.report_minute,
        report_timezone=argus.config.settings.report_timezone,
        db_path=argus.config.settings.db_path,
        healthcheck_db_timeout=argus.config.settings.healthcheck_db_timeout,
        kktix_organization=argus.config.settings.kktix_organization,
        allowed_emails=emails,
    )
    monkeypatch.setattr(argus.config, "settings", new_settings)
    # auth.py reads settings.allowed_emails at call time, so this is enough.


# ---------------------------------------------------------------------------
# is_email_allowed
# ---------------------------------------------------------------------------


def test_is_email_allowed_in_list(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com", "bob@example.com"))
    assert is_email_allowed("alice@example.com") is True


def test_is_email_allowed_case_insensitive(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("Alice@Example.com",))
    assert is_email_allowed("alice@EXAMPLE.com") is True


def test_is_email_allowed_not_in_list(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com",))
    assert is_email_allowed("eve@evil.com") is False


def test_is_email_allowed_empty_email(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com",))
    assert is_email_allowed("") is False


def test_is_email_allowed_empty_allowlist(monkeypatch):
    _patch_allowed_emails(monkeypatch, ())
    assert is_email_allowed("alice@example.com") is False


# ---------------------------------------------------------------------------
# require_login
# ---------------------------------------------------------------------------


def _fake_request(session: dict) -> MagicMock:
    req = MagicMock()
    req.session = session
    return req


async def test_require_login_no_session(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com",))
    with pytest.raises(HTTPException) as exc:
        await require_login(_fake_request({}))
    assert exc.value.status_code == 401


async def test_require_login_email_not_allowed(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com",))
    with pytest.raises(HTTPException) as exc:
        await require_login(_fake_request({"user": {"email": "eve@evil.com"}}))
    assert exc.value.status_code == 401


async def test_require_login_user_missing_email(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com",))
    with pytest.raises(HTTPException) as exc:
        await require_login(_fake_request({"user": {}}))
    assert exc.value.status_code == 401


async def test_require_login_returns_email(monkeypatch):
    _patch_allowed_emails(monkeypatch, ("alice@example.com",))
    email = await require_login(_fake_request({"user": {"email": "alice@example.com"}}))
    assert email == "alice@example.com"
