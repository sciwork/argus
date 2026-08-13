from contextlib import contextmanager
import sqlite3

import httpx
import pytest

from argus import discord
from argus.database import _CREATE_TABLES_SQL
from argus.kktix import report


@pytest.fixture
def report_db(monkeypatch):
    """Provide one in-memory SQLite database to the report workflow."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_CREATE_TABLES_SQL)

    @contextmanager
    def get_conn():
        # Every SQLite :memory: connection is isolated, so report code must reuse this one.
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    monkeypatch.setattr(report, "get_conn", get_conn)
    try:
        yield conn
    finally:
        conn.close()


def _insert_event(db, start_at=None):
    """Insert one reportable event and return its slug."""
    db.execute(
        """INSERT INTO events (event_slug, event_name, channel, start_at)
           VALUES (?, ?, ?, ?)""",
        ("event-1", "Event One", "OPS", start_at),
    )
    return "event-1"


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


def test_send_report_posts_payload_from_active_event_tickets(report_db, monkeypatch):
    """Build and send a Discord report from active event and ticket records."""
    monkeypatch.setenv("DISCORD_WEBHOOK_OPS", "https://example.com/webhook")
    monkeypatch.setattr(report, "utcnow_iso", lambda: "2026-08-13T00:00:00")

    event_slug = _insert_event(report_db, start_at="2026-08-15T02:00:00")
    report_db.executemany(
        """INSERT INTO tickets
           (ticket_id, ticket_name, event_slug, order_id, order_state, paid_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            (501, "General", event_slug, 1001, "activated", "2026-08-12T01:00:00"),
            (502, "General", event_slug, 1002, "activated", "2026-08-12T02:00:00"),
            (503, "VIP", event_slug, 1003, "activated", "2026-08-12T03:00:00"),
        ],
    )
    report_db.commit()

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
    row = report_db.execute(
        "SELECT last_reported_at FROM events WHERE event_slug = ?", (event_slug,)
    ).fetchone()
    assert row[0] == "2026-08-13T00:00:00"


def test_send_report_keeps_timestamp_when_discord_rejects_payload(
    report_db, monkeypatch
):
    """Leave a report pending when Discord rejects its payload."""
    monkeypatch.setenv("DISCORD_WEBHOOK_OPS", "https://example.com/webhook")
    monkeypatch.setattr(report, "utcnow_iso", lambda: "2026-08-13T00:00:00")
    event_slug = _insert_event(report_db)
    report_db.commit()
    monkeypatch.setattr(
        discord.httpx,
        "Client",
        lambda: _FakeDiscordClient(httpx.Response(500, text="Discord unavailable"), []),
    )

    report.send_report()

    row = report_db.execute(
        "SELECT last_reported_at FROM events WHERE event_slug = ?", (event_slug,)
    ).fetchone()
    assert row[0] is None
