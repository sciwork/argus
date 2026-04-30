import httpx

from argus.database import get_conn
from argus.kktix.scraper import EventDetails, enrich_event


def _insert_event(slug: str, start_at: str | None = None, capacity: int | None = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO events (event_slug, event_name, channel, start_at, capacity)
               VALUES (?, ?, ?, ?, ?)""",
            (slug, "Test Event", "SPRINT", start_at, capacity),
        )


async def test_skips_when_start_at_already_set(monkeypatch):
    _insert_event("my-event", start_at="2026-04-25T01:00:00")

    called = []

    async def fake_fetch(slug):
        called.append(slug)
        return EventDetails(start_at="2026-04-25T01:00:00", capacity=30)

    monkeypatch.setattr("argus.kktix.scraper.fetch_event_details", fake_fetch)

    await enrich_event("my-event")

    assert called == []


async def test_populates_start_at_and_capacity_when_null(monkeypatch):
    _insert_event("my-event", start_at=None, capacity=None)

    async def fake_fetch(slug):
        return EventDetails(start_at="2026-04-25T01:00:00", capacity=30)

    monkeypatch.setattr("argus.kktix.scraper.fetch_event_details", fake_fetch)

    await enrich_event("my-event")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT start_at, capacity FROM events WHERE event_slug = 'my-event'"
        ).fetchone()
    assert row["start_at"] == "2026-04-25T01:00:00"
    assert row["capacity"] == 30


async def test_swallows_network_error(monkeypatch):
    _insert_event("my-event", start_at=None)

    async def fake_fetch(slug):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("argus.kktix.scraper.fetch_event_details", fake_fetch)

    # Should not raise
    await enrich_event("my-event")

    # start_at remains None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT start_at FROM events WHERE event_slug = 'my-event'"
        ).fetchone()
    assert row["start_at"] is None


async def test_skips_when_event_not_found(monkeypatch):
    called = []

    async def fake_fetch(slug):
        called.append(slug)
        return EventDetails(start_at="2026-04-25T01:00:00", capacity=30)

    monkeypatch.setattr("argus.kktix.scraper.fetch_event_details", fake_fetch)

    await enrich_event("nonexistent-event")

    assert called == []
