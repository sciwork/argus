from pathlib import Path

import pytest


def test_settings_defaults(monkeypatch):
    for key in (
        "REPORT_HOUR",
        "REPORT_MINUTE",
        "REPORT_TIMEZONE",
        "DB_PATH",
        "HEALTHCHECK_DB_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)

    from argus.config import Settings

    s = Settings.from_env()
    assert s.report_hour == 9
    assert s.report_minute == 0
    assert s.report_timezone == "Asia/Taipei"
    assert s.db_path == Path("argus.db")
    assert s.healthcheck_db_timeout == 1.0


def test_settings_type_conversion(monkeypatch):
    monkeypatch.setenv("REPORT_HOUR", "8")
    monkeypatch.setenv("REPORT_MINUTE", "30")
    monkeypatch.setenv("REPORT_TIMEZONE", "UTC")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")
    monkeypatch.setenv("HEALTHCHECK_DB_TIMEOUT", "2.5")

    from argus.config import Settings

    s = Settings.from_env()
    assert isinstance(s.report_hour, int)
    assert s.report_hour == 8
    assert isinstance(s.report_minute, int)
    assert s.report_minute == 30
    assert isinstance(s.report_timezone, str)
    assert s.report_timezone == "UTC"
    assert isinstance(s.db_path, Path)
    assert s.db_path == Path("/tmp/test.db")
    assert isinstance(s.healthcheck_db_timeout, float)
    assert s.healthcheck_db_timeout == 2.5


def test_secrets_repr_does_not_leak():
    from argus.config import Secrets

    s = Secrets(
        webhook_secret="super-secret",
        google_oauth_client_id="client-id-secret",
        google_oauth_client_secret="client-secret-secret",
        session_secret="session-secret-value",
    )
    r = repr(s)
    assert "super-secret" not in r
    assert "client-id-secret" not in r
    assert "client-secret-secret" not in r
    assert "session-secret-value" not in r
    assert "***" in r


def test_secrets_require_webhook_secret_empty():
    from argus.config import Secrets

    s = Secrets(
        webhook_secret="",
        google_oauth_client_id="",
        google_oauth_client_secret="",
        session_secret="",
    )
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        s.require_webhook_secret()


def test_secrets_require_webhook_secret_returns_value():
    from argus.config import Secrets

    s = Secrets(
        webhook_secret="my-secret",
        google_oauth_client_id="",
        google_oauth_client_secret="",
        session_secret="",
    )
    assert s.require_webhook_secret() == "my-secret"


def test_reload_picks_up_new_env(monkeypatch):
    monkeypatch.setenv("REPORT_HOUR", "7")
    monkeypatch.setenv("WEBHOOK_SECRET", "new-secret")

    import argus.config

    argus.config.reload()

    assert argus.config.settings.report_hour == 7
    assert argus.config.secrets.webhook_secret == "new-secret"
