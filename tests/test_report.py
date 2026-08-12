from sqlalchemy import select
import httpx

from argus import discord
from argus.database import Event
from argus.kktix import report
from argus.kktix.handler import handle_notification


def _paid_notification():
    """Return an event notification with tickets for the report workflow."""
    return {
        "type": "order_activated_paid",
        "event": {"slug": "event-1", "name": "Event One"},
        "order": {"id": 1001, "paid_at": "2026-08-12T09:00:00+08:00"},
        "contact": {"name": "Ada", "email": "ada@example.com"},
        "tickets": [
            {"id": 501, "name": "General"},
            {"id": 502, "name": "General"},
            {"id": 503, "name": "VIP"},
        ],
    }


class _FakeDiscordClient:
    def __init__(self, response, requests):
        self._response = response
        self._requests = requests

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def post(self, url, json):
        self._requests.append((url, json))
        return self._response


def test_send_report_posts_payload_from_active_event_tickets(session, monkeypatch):
    """Build and send a Discord report from active event and ticket records."""
    monkeypatch.setenv("DISCORD_WEBHOOK_OPS", "https://example.com/webhook")
    monkeypatch.setattr(report, "utcnow_iso", lambda: "2026-08-13T00:00:00")

    event_slug = "event-1"
    assert handle_notification(_paid_notification(), channel="OPS") == [event_slug]

    requests = []
    monkeypatch.setattr(
        discord.httpx,
        "Client",
        lambda: _FakeDiscordClient(httpx.Response(204), requests),
    )

    report.send_report()

    expected_payload = report.build_payload(
        rows=[
            {
                "event_slug": event_slug,
                "event_name": "Event One",
                "ticket_name": "General",
                "cnt": 2,
            },
            {
                "event_slug": event_slug,
                "event_name": "Event One",
                "ticket_name": "VIP",
                "cnt": 1,
            },
        ],
        event_meta=[{"event_slug": event_slug, "last_reported_at": None}],
        prev_counts={},
    )
    assert requests == [("https://example.com/webhook", expected_payload)]
    session.expire_all()
    event = session.scalar(select(Event).where(Event.event_slug == event_slug))
    assert event is not None
    assert event.last_reported_at == "2026-08-13T00:00:00"


def test_send_report_keeps_timestamp_when_discord_rejects_payload(session, monkeypatch):
    """Leave a report pending when Discord rejects its payload."""
    monkeypatch.setenv("DISCORD_WEBHOOK_OPS", "https://example.com/webhook")
    monkeypatch.setattr(report, "utcnow_iso", lambda: "2026-08-13T00:00:00")
    event_slug = "event-1"
    assert handle_notification(_paid_notification(), channel="OPS") == [event_slug]
    monkeypatch.setattr(
        discord.httpx,
        "Client",
        lambda: _FakeDiscordClient(httpx.Response(500, text="Discord unavailable"), []),
    )

    report.send_report()

    session.expire_all()
    event = session.scalar(select(Event).where(Event.event_slug == event_slug))
    assert event is not None
    assert event.last_reported_at is None
