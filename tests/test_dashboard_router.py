"""Tests for the Dashboard OAuth router (Phase 1 scaffolding)."""

from unittest.mock import AsyncMock, MagicMock
import os

from fastapi.testclient import TestClient
import pytest


# Set required env vars BEFORE importing the app, so SessionMiddleware has a key.
os.environ.setdefault("SESSION_SECRET", "test-session-secret-please-rotate")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("ALLOWED_EMAILS", "alice@example.com")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")

from argus.config import Secrets, Settings  # noqa: E402
from argus.main import app  # noqa: E402
import argus.auth as auth_module  # noqa: E402
import argus.config  # noqa: E402


@pytest.fixture(autouse=True)
def patch_oauth(monkeypatch):
    """Override settings/secrets with allowlist + dummy OAuth credentials per test."""
    new_settings = Settings(
        report_hour=argus.config.settings.report_hour,
        report_minute=argus.config.settings.report_minute,
        report_timezone=argus.config.settings.report_timezone,
        db_path=argus.config.settings.db_path,
        healthcheck_db_timeout=argus.config.settings.healthcheck_db_timeout,
        kktix_organization=argus.config.settings.kktix_organization,
        allowed_emails=("alice@example.com",),
    )
    new_secrets = Secrets(
        webhook_secret="test-secret",
        google_oauth_client_id="test-client-id",
        google_oauth_client_secret="test-client-secret",
        session_secret="test-session-secret-please-rotate",
    )
    monkeypatch.setattr(argus.config, "settings", new_settings)
    monkeypatch.setattr(argus.config, "secrets", new_secrets)
    auth_module.reset_oauth()


client = TestClient(app)


# ---------------------------------------------------------------------------
# /dashboard — protected, redirects to /dashboard/login when not authed
# ---------------------------------------------------------------------------


def test_dashboard_home_unauthed_redirects_to_login():
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard/login"


def test_dashboard_logout_clears_session_and_redirects():
    resp = client.get("/dashboard/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard/login"


# ---------------------------------------------------------------------------
# /dashboard/login — initiates OAuth flow
# ---------------------------------------------------------------------------


def test_dashboard_login_redirects_to_google():
    resp = client.get("/dashboard/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    # Authlib's authorize_redirect sends to Google's authorization endpoint
    assert location.startswith("https://accounts.google.com/")


# ---------------------------------------------------------------------------
# /dashboard/oauth/callback
# ---------------------------------------------------------------------------


def _fake_oauth(token: dict | Exception) -> MagicMock:
    """Build a fake OAuth instance whose google.authorize_access_token returns or raises."""
    fake = MagicMock()
    if isinstance(token, Exception):
        fake.google.authorize_access_token = AsyncMock(side_effect=token)
    else:
        fake.google.authorize_access_token = AsyncMock(return_value=token)
    return fake


def test_oauth_callback_happy_path(monkeypatch):
    fake = _fake_oauth({"userinfo": {"email": "alice@example.com"}})
    monkeypatch.setattr(auth_module, "get_oauth", lambda: fake)

    resp = client.get("/dashboard/oauth/callback", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_oauth_callback_email_not_allowed(monkeypatch):
    fake = _fake_oauth({"userinfo": {"email": "eve@evil.com"}})
    monkeypatch.setattr(auth_module, "get_oauth", lambda: fake)

    resp = client.get("/dashboard/oauth/callback", follow_redirects=False)
    assert resp.status_code == 403
    assert "Access denied" in resp.text


def test_oauth_callback_missing_email(monkeypatch):
    fake = _fake_oauth({"userinfo": {}})
    monkeypatch.setattr(auth_module, "get_oauth", lambda: fake)

    resp = client.get("/dashboard/oauth/callback", follow_redirects=False)
    assert resp.status_code == 400


def test_oauth_callback_token_exchange_fails(monkeypatch):
    fake = _fake_oauth(RuntimeError("simulated failure"))
    monkeypatch.setattr(auth_module, "get_oauth", lambda: fake)

    resp = client.get("/dashboard/oauth/callback", follow_redirects=False)
    assert resp.status_code == 400


def test_dashboard_home_after_successful_oauth(monkeypatch):
    """After OAuth success, the user can access /dashboard."""
    fake = _fake_oauth({"userinfo": {"email": "alice@example.com"}})
    monkeypatch.setattr(auth_module, "get_oauth", lambda: fake)

    # Simulate the redirect chain: callback sets session, then GET /dashboard with same client
    callback_resp = client.get("/dashboard/oauth/callback", follow_redirects=False)
    assert callback_resp.status_code == 302

    home_resp = client.get("/dashboard", follow_redirects=False)
    assert home_resp.status_code == 200
    assert "alice@example.com" in home_resp.text


# ---------------------------------------------------------------------------
# JSON API — auth required, list events, time series
# ---------------------------------------------------------------------------


def _login(monkeypatch):
    """Helper: simulate a successful OAuth login so subsequent client calls have a session."""
    fake = _fake_oauth({"userinfo": {"email": "alice@example.com"}})
    monkeypatch.setattr(auth_module, "get_oauth", lambda: fake)
    resp = client.get("/dashboard/oauth/callback", follow_redirects=False)
    assert resp.status_code == 302


def test_api_events_unauthed_returns_401():
    # Use a fresh client to avoid leaked session from previous tests
    fresh = TestClient(app)
    resp = fresh.get("/dashboard/api/events")
    assert resp.status_code == 401


def test_api_events_authed_returns_list(monkeypatch):
    from argus.database import get_conn

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel, start_at)"
            " VALUES (?, ?, ?, ?)",
            ("ev1", "Event One", "SPRINT", "2026-05-01T01:00:00"),
        )

    _login(monkeypatch)
    resp = client.get("/dashboard/api/events")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(e["event_slug"] == "ev1" for e in body)


def test_api_timeseries_unauthed_returns_401():
    fresh = TestClient(app)
    resp = fresh.get("/dashboard/api/events/whatever/timeseries")
    assert resp.status_code == 401


def test_api_timeseries_unknown_slug_returns_404(monkeypatch):
    _login(monkeypatch)
    resp = client.get("/dashboard/api/events/not-found/timeseries")
    assert resp.status_code == 404


def test_dashboard_home_rendered_html(monkeypatch):
    """After login, GET /dashboard renders the events list HTML."""
    from argus.database import get_conn

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel, start_at)"
            " VALUES (?, ?, ?, ?)",
            ("ev1", "Sprint 2026", "SPRINT", "2026-05-01T01:00:00"),
        )

    _login(monkeypatch)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Basic content checks
    assert "Sprint 2026" in resp.text
    assert "SPRINT" in resp.text
    assert "alice@example.com" in resp.text
    assert "/dashboard/events/ev1" in resp.text


def test_dashboard_event_page(monkeypatch):
    """GET /dashboard/events/{slug} renders the chart page."""
    from argus.database import get_conn

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel, start_at, capacity)"
            " VALUES (?, ?, ?, ?, ?)",
            ("ev1", "Sprint 2026", "SPRINT", "2026-05-01T01:00:00", 30),
        )

    _login(monkeypatch)
    resp = client.get("/dashboard/events/ev1")
    assert resp.status_code == 200
    assert "Sprint 2026" in resp.text
    # Chart.js script tag present
    assert "chart.js" in resp.text.lower()
    # API endpoint URL referenced in the JS
    assert "/dashboard/api/events" in resp.text


def test_dashboard_event_page_unknown_slug(monkeypatch):
    _login(monkeypatch)
    resp = client.get("/dashboard/events/does-not-exist")
    assert resp.status_code == 404


def test_dashboard_event_page_unauthed_redirects():
    fresh = TestClient(app)
    resp = fresh.get("/dashboard/events/anything", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard/login"


# ---------------------------------------------------------------------------
# Webhook log API
# ---------------------------------------------------------------------------


def _insert_webhook_log(channel: str = "SPRINT") -> int:
    from argus.database import get_conn

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO webhook_logs (method, channel, headers, body)
               VALUES (?, ?, ?, ?)""",
            ("POST", channel, '{"x-kktix-secret":"***"}', '{"batch_id":"x"}'),
        )
        return cur.lastrowid


def test_api_webhook_logs_unauthed_returns_401():
    fresh = TestClient(app)
    resp = fresh.get("/dashboard/api/webhook-logs")
    assert resp.status_code == 401


def test_api_webhook_logs_authed_returns_list(monkeypatch):
    _insert_webhook_log()
    _insert_webhook_log("MEETUP")
    _login(monkeypatch)
    resp = client.get("/dashboard/api/webhook-logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["limit"] == 100
    assert body["offset"] == 0


def test_api_webhook_logs_caps_limit(monkeypatch):
    _login(monkeypatch)
    resp = client.get("/dashboard/api/webhook-logs?limit=99999")
    assert resp.status_code == 200
    assert resp.json()["limit"] == 500  # capped


def test_api_delete_webhook_log_unauthed_returns_401():
    fresh = TestClient(app)
    resp = fresh.delete("/dashboard/api/webhook-logs/1")
    assert resp.status_code == 401


def test_api_delete_webhook_log_unknown_returns_404(monkeypatch):
    _login(monkeypatch)
    resp = client.delete("/dashboard/api/webhook-logs/99999")
    assert resp.status_code == 404


def test_api_delete_webhook_log_existing_returns_200(monkeypatch):
    log_id = _insert_webhook_log()
    _login(monkeypatch)
    resp = client.delete(f"/dashboard/api/webhook-logs/{log_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "deleted_id": log_id}


def test_api_clear_webhook_logs_unauthed_returns_401():
    fresh = TestClient(app)
    resp = fresh.delete("/dashboard/api/webhook-logs")
    assert resp.status_code == 401


def test_api_clear_webhook_logs_returns_count(monkeypatch):
    _insert_webhook_log()
    _insert_webhook_log()
    _insert_webhook_log()
    _login(monkeypatch)
    resp = client.delete("/dashboard/api/webhook-logs")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "deleted_count": 3}


def test_dashboard_webhook_logs_page_unauthed_redirects():
    fresh = TestClient(app)
    resp = fresh.get("/dashboard/webhook-logs", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard/login"


def test_dashboard_webhook_logs_page_authed_renders(monkeypatch):
    _insert_webhook_log()
    _login(monkeypatch)
    resp = client.get("/dashboard/webhook-logs")
    assert resp.status_code == 200
    assert "Webhook Logs" in resp.text


# ---------------------------------------------------------------------------
# Event delete API (existing)
# ---------------------------------------------------------------------------


def test_api_delete_event_unauthed_returns_401():
    fresh = TestClient(app)
    resp = fresh.delete("/dashboard/api/events/anything")
    assert resp.status_code == 401


def test_api_delete_event_unknown_slug_returns_404(monkeypatch):
    _login(monkeypatch)
    resp = client.delete("/dashboard/api/events/does-not-exist")
    assert resp.status_code == 404


def test_api_delete_event_removes_data(monkeypatch):
    from argus.database import get_conn

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel)"
            " VALUES (?, ?, ?)",
            ("ev1", "Event One", "SPRINT"),
        )
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state)
               VALUES (1, '一般票', 'ev1', 101, 'activated')""",
        )

    _login(monkeypatch)
    resp = client.delete("/dashboard/api/events/ev1")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "deleted_slug": "ev1"}

    with get_conn() as conn:
        ev_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_slug = ?", ("ev1",)
        ).fetchone()[0]
        ticket_count = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE event_slug = ?", ("ev1",)
        ).fetchone()[0]
    assert ev_count == 0
    assert ticket_count == 0


def test_api_trigger_report_unauthed_returns_401():
    fresh = TestClient(app)
    resp = fresh.post("/dashboard/api/report/trigger")
    assert resp.status_code == 401


def test_api_trigger_report_invokes_send_report(monkeypatch):
    """Authed POST → send_report is called once and 200 returned."""
    calls = []

    def fake_send_report():
        calls.append(1)

    monkeypatch.setattr("argus.dashboard.router.send_report", fake_send_report)

    _login(monkeypatch)
    resp = client.post("/dashboard/api/report/trigger")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "Report dispatched"}
    assert len(calls) == 1


def test_api_trigger_report_returns_500_on_failure(monkeypatch):
    """If send_report raises, endpoint surfaces 500."""

    def fake_send_report():
        raise RuntimeError("boom")

    monkeypatch.setattr("argus.dashboard.router.send_report", fake_send_report)

    _login(monkeypatch)
    resp = client.post("/dashboard/api/report/trigger")
    assert resp.status_code == 500


def test_api_timeseries_returns_expected_shape(monkeypatch):
    from argus.database import get_conn

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel, start_at, capacity)"
            " VALUES (?, ?, ?, ?, ?)",
            ("ev1", "Event One", "SPRINT", "2026-04-26T16:00:00", 30),
        )
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state, paid_at)
               VALUES (1, '一般票', 'ev1', 101, 'activated', '2026-04-25T03:00:00')""",
        )

    _login(monkeypatch)
    resp = client.get("/dashboard/api/events/ev1/timeseries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["event"]["event_slug"] == "ev1"
    assert body["event"]["capacity"] == 30
    assert isinstance(body["labels"], list) and len(body["labels"]) > 0
    names = {d["name"] for d in body["datasets"]}
    assert "Total" in names
    assert "一般票" in names
