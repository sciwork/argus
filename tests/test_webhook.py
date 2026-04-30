import os

from fastapi.testclient import TestClient
import pytest


os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["DISCORD_WEBHOOK_SPRINT"] = "https://discord.com/api/webhooks/sprint-test"
# argus.main reads SESSION_SECRET at import time and refuses to boot without it.
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from argus.config import Secrets  # noqa: E402
from argus.database import get_conn  # noqa: E402
from argus.main import app  # noqa: E402
import argus.config  # noqa: E402


@pytest.fixture(autouse=True)
def setup_secrets(monkeypatch):
    """conftest.use_tmp_db handles the DB + settings; this fixture just sets secrets."""
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_SPRINT", "https://discord.com/api/webhooks/sprint-test"
    )
    new_secrets = Secrets(
        webhook_secret="test-secret",
        google_oauth_client_id="",
        google_oauth_client_secret="",
        session_secret="test-session-secret",
    )
    monkeypatch.setattr(argus.config, "secrets", new_secrets)


client = TestClient(app)

SPRINT_URL = "/webhook/kktix/sprint"

ACTIVATED_PAYLOAD = {
    "batch_id": "test001",
    "notifications": [
        {
            "type": "order_activated_paid",
            "event": {"name": "Test Event", "slug": "test-event"},
            "order": {
                "id": 1001,
                "state": "activated",
                "paid_at": "2026-04-18T10:00:00+08:00",
            },
            "contact": {"name": "Test User", "email": "test@example.com", "mobile": ""},
            "tickets": [
                {
                    "id": 5001,
                    "name": "一般票",
                    "price_cents": 0,
                    "price_currency": "TWD",
                },
                {
                    "id": 5002,
                    "name": "早鳥票",
                    "price_cents": 0,
                    "price_currency": "TWD",
                },
            ],
        }
    ],
}

CANCELLED_PAYLOAD = {
    "batch_id": "test002",
    "notifications": [
        {
            "type": "order_cancelled",
            "event": {"name": "Test Event", "slug": "test-event"},
            "order": {
                "id": 1001,
                "state": "cancelled",
                "cancelled_at": "2026-04-18T11:00:00+08:00",
            },
        }
    ],
}


def test_webhook_log_redacts_sensitive_headers():
    """webhook_logs.headers must mask the secret and other sensitive values."""
    import json as _json

    resp = client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={
            "x-kktix-secret": "test-secret",
            "Authorization": "Bearer leak-me",
            "Cookie": "session=abc",
        },
    )
    assert resp.status_code == 200

    with get_conn() as conn:
        row = conn.execute(
            "SELECT headers FROM webhook_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    headers = _json.loads(row["headers"])

    # Compare keys case-insensitively (Starlette lowercases headers)
    lower = {k.lower(): v for k, v in headers.items()}
    assert lower["x-kktix-secret"] == "***"
    assert lower["authorization"] == "***"
    assert lower["cookie"] == "***"

    # The raw secret values must NOT appear anywhere in the stored headers
    raw = _json.dumps(headers)
    assert "test-secret" not in raw
    assert "leak-me" not in raw
    assert "session=abc" not in raw


def test_webhook_accepts_lowercase_channel():
    resp = client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel FROM events WHERE event_slug = 'test-event'"
        ).fetchone()
    assert row is not None
    assert row["channel"] == "SPRINT"


def test_webhook_ignores_kktix_test_notification(caplog):
    payload = {
        "notifications": [
            {
                "type": "order_activated_paid",
                "event": {"name": "Event Name", "slug": "event-slug"},
                "order": {
                    "id": 123,
                    "status": "activated",
                    "created_at": "2024-12-25 12:00:00",
                    "payment_status": "paid",
                    "paid_at": "2024-12-25 12:30:00",
                    "total_amount": 4000,
                    "currency": "TWD",
                },
                "contact": {"name": "***", "email": "***"},
                "tickets": [
                    {
                        "price": 1000,
                        "name": "normal",
                        "id": 12,
                        "attendee": {
                            "name": "User_1",
                            "email": "user_1@example.com",
                        },
                    }
                ],
            },
            {
                "type": "order_cancelled",
                "event": {"name": "Event Name", "slug": "event-slug"},
                "order": {
                    "id": 123,
                    "status": "cancelled",
                    "cancelled_at": "2024-12-25 13:00:00",
                },
            },
        ]
    }

    with caplog.at_level("INFO", logger="argus.kktix.handler"):
        resp = client.post(
            SPRINT_URL,
            json=payload,
            headers={"x-kktix-secret": "test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert "ignored test webhook notification" in caplog.text

    with get_conn() as conn:
        log_row = conn.execute(
            "SELECT id FROM webhook_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        event_row = conn.execute(
            "SELECT event_slug FROM events WHERE event_slug = 'event-slug'"
        ).fetchone()
        ticket_row = conn.execute(
            "SELECT ticket_id FROM tickets WHERE event_slug = 'event-slug'"
        ).fetchone()

    assert log_row is not None
    assert event_row is None
    assert ticket_row is None


def test_webhook_accepts_mixed_case():
    resp = client.post(
        "/webhook/kktix/Sprint",
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200

    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel FROM events WHERE event_slug = 'test-event'"
        ).fetchone()
    assert row is not None
    assert row["channel"] == "SPRINT"


def test_webhook_unauthorized_still_returns_401():
    resp = client.post(SPRINT_URL, json=ACTIVATED_PAYLOAD)
    assert resp.status_code == 401

    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel FROM webhook_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["channel"] == "SPRINT"


def test_webhook_unknown_channel_returns_503(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_UNKNOWNCHANNEL", raising=False)
    resp = client.post(
        "/webhook/kktix/unknownchannel",
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "channel_not_configured"
    assert body["channel"] == "UNKNOWNCHANNEL"

    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel FROM webhook_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["channel"] == "UNKNOWNCHANNEL"


def test_webhook_invalid_channel_returns_400():
    resp = client.post(
        "/webhook/kktix/bad-name",
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_channel"

    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel FROM webhook_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["channel"] is None


def test_webhook_legacy_path_404():
    resp = client.post(
        "/webhook",
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 404


def test_webhook_cancelled_preserves_channel():
    # First activate an event via SPRINT channel
    client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    # Then cancel the order
    resp = client.post(
        SPRINT_URL,
        json=CANCELLED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200

    with get_conn() as conn:
        event_row = conn.execute(
            "SELECT channel FROM events WHERE event_slug = 'test-event'"
        ).fetchone()
        ticket_row = conn.execute(
            "SELECT order_state FROM tickets WHERE order_id = 1001 LIMIT 1"
        ).fetchone()
    assert event_row["channel"] == "SPRINT"
    assert ticket_row["order_state"] == "cancelled"


def test_activated_paid_at_stored_as_utc():
    """paid_at in DB should be UTC without timezone offset."""
    resp = client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200

    with get_conn() as conn:
        row = conn.execute(
            "SELECT paid_at FROM tickets WHERE ticket_id = 5001"
        ).fetchone()
    assert row is not None
    paid_at = row["paid_at"]
    # Should be UTC: no +/- offset, no Z suffix
    assert paid_at == "2026-04-18T02:00:00"


def test_cancelled_at_stored_as_utc():
    """cancelled_at in DB should be UTC without timezone offset."""
    # First activate
    client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    # Then cancel
    resp = client.post(
        SPRINT_URL,
        json=CANCELLED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200

    with get_conn() as conn:
        row = conn.execute(
            "SELECT cancelled_at FROM tickets WHERE order_id = 1001 LIMIT 1"
        ).fetchone()
    assert row is not None
    cancelled_at = row["cancelled_at"]
    # cancelled_at in payload is 2026-04-18T11:00:00+08:00 → UTC 03:00:00
    assert cancelled_at == "2026-04-18T03:00:00"


def test_webhook_two_channels_isolated(monkeypatch):
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_MEETUP", "https://discord.com/api/webhooks/meetup-test"
    )

    sprint_payload = {
        "batch_id": "sp001",
        "notifications": [
            {
                "type": "order_activated_paid",
                "event": {"name": "Sprint Event", "slug": "sprint-event"},
                "order": {
                    "id": 2001,
                    "state": "activated",
                    "paid_at": "2026-04-18T10:00:00+08:00",
                },
                "contact": {
                    "name": "Alice",
                    "email": "alice@example.com",
                    "mobile": "",
                },
                "tickets": [
                    {
                        "id": 6001,
                        "name": "一般票",
                        "price_cents": 0,
                        "price_currency": "TWD",
                    }
                ],
            }
        ],
    }
    meetup_payload = {
        "batch_id": "mu001",
        "notifications": [
            {
                "type": "order_activated_paid",
                "event": {"name": "Meetup Event", "slug": "meetup-event"},
                "order": {
                    "id": 3001,
                    "state": "activated",
                    "paid_at": "2026-04-18T10:00:00+08:00",
                },
                "contact": {"name": "Bob", "email": "bob@example.com", "mobile": ""},
                "tickets": [
                    {
                        "id": 7001,
                        "name": "一般票",
                        "price_cents": 0,
                        "price_currency": "TWD",
                    }
                ],
            }
        ],
    }

    client.post(
        "/webhook/kktix/sprint",
        json=sprint_payload,
        headers={"x-kktix-secret": "test-secret"},
    )
    client.post(
        "/webhook/kktix/meetup",
        json=meetup_payload,
        headers={"x-kktix-secret": "test-secret"},
    )

    with get_conn() as conn:
        sprint_row = conn.execute(
            "SELECT channel FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()
        meetup_row = conn.execute(
            "SELECT channel FROM events WHERE event_slug = 'meetup-event'"
        ).fetchone()

    assert sprint_row["channel"] == "SPRINT"
    assert meetup_row["channel"] == "MEETUP"


def test_first_webhook_schedules_enrichment(monkeypatch):
    """First webhook for a new slug → background task enrich_event is scheduled."""
    enrich_calls = []

    async def fake_enrich(slug):
        enrich_calls.append(slug)

    monkeypatch.setattr("argus.kktix.scraper.enrich_event", fake_enrich)
    monkeypatch.setattr("argus.kktix.router.enrich_event", fake_enrich)

    resp = client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200
    # TestClient runs background tasks synchronously, so fake_enrich should have been called
    assert enrich_calls == ["test-event"]


def test_second_webhook_same_slug_no_enrichment(monkeypatch):
    """Second webhook for same slug → rowcount=0 on conflict, no task added."""
    enrich_calls = []

    async def fake_enrich(slug):
        enrich_calls.append(slug)

    monkeypatch.setattr("argus.kktix.scraper.enrich_event", fake_enrich)
    monkeypatch.setattr("argus.kktix.router.enrich_event", fake_enrich)

    # First request — creates the event row
    client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    enrich_calls.clear()

    # Second request — same slug, ON CONFLICT DO NOTHING → rowcount=0
    resp = client.post(
        SPRINT_URL,
        json=ACTIVATED_PAYLOAD,
        headers={"x-kktix-secret": "test-secret"},
    )
    assert resp.status_code == 200
    assert enrich_calls == []
