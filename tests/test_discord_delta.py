"""Tests for last_reported_at-based delta logic in kktix/report.py."""

import httpx

from argus.database import get_conn
from argus.kktix.report import build_payload, send_report


SPRINT_URL = "https://discord.com/api/webhooks/sprint-delta-test"
MEETUP_URL = "https://discord.com/api/webhooks/meetup-delta-test"


def _make_response(status_code: int, url: str) -> httpx.Response:
    req = httpx.Request("POST", url)
    return httpx.Response(status_code, request=req)


def _mock_client_factory(posts: list, url_map: dict | None = None):
    """Return a MockClient class that records posts and returns 204."""

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            posts.append((url, json))
            return _make_response(204, url)

    return MockClient


def _insert_event(channel: str, event_slug: str, event_name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel) VALUES (?, ?, ?)"
            " ON CONFLICT(event_slug) DO NOTHING",
            (event_slug, event_name, channel),
        )


def _insert_ticket(
    ticket_id: int,
    ticket_name: str,
    event_slug: str,
    order_id: int,
    paid_at: str | None = None,
    cancelled_at: str | None = None,
    order_state: str = "activated",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state, paid_at, cancelled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(ticket_id) DO NOTHING""",
            (
                ticket_id,
                ticket_name,
                event_slug,
                order_id,
                order_state,
                paid_at,
                cancelled_at,
            ),
        )


# ---------------------------------------------------------------------------
# build_payload unit tests
# ---------------------------------------------------------------------------


def test_build_payload_first_report_no_delta():
    """First report (last_reported_at=None): description shows count only, no delta."""
    rows = [
        {
            "event_slug": "ev1",
            "event_name": "Event One",
            "ticket_name": "一般票",
            "cnt": 5,
        }
    ]
    event_meta = [
        {"event_slug": "ev1", "event_name": "Event One", "last_reported_at": None}
    ]

    payload = build_payload(rows, event_meta, {})

    embed = payload["embeds"][0]
    desc = embed["description"]
    assert "(+" not in desc
    assert "一般票　5" in desc
    assert "Total　5" in desc
    assert embed["color"] == 0x888780


def test_build_payload_second_report_increase():
    """Second report with new tickets: description shows positive delta."""
    rows = [
        {
            "event_slug": "ev1",
            "event_name": "Event One",
            "ticket_name": "一般票",
            "cnt": 8,
        }
    ]
    event_meta = [
        {
            "event_slug": "ev1",
            "event_name": "Event One",
            "last_reported_at": "2026-04-18T06:00:00",
        }
    ]
    prev_counts: dict[tuple[str, str], int] = {("ev1", "一般票"): 5}

    payload = build_payload(rows, event_meta, prev_counts)

    embed = payload["embeds"][0]
    desc = embed["description"]
    assert "一般票　8　(+3)" in desc
    assert "Total　8　(+3)" in desc
    assert embed["color"] == 0x1D9E75


def test_build_payload_second_report_decrease():
    """Second report with cancellations: description shows negative delta."""
    rows = [
        {
            "event_slug": "ev1",
            "event_name": "Event One",
            "ticket_name": "一般票",
            "cnt": 3,
        }
    ]
    event_meta = [
        {
            "event_slug": "ev1",
            "event_name": "Event One",
            "last_reported_at": "2026-04-18T06:00:00",
        }
    ]
    prev_counts: dict[tuple[str, str], int] = {("ev1", "一般票"): 5}

    payload = build_payload(rows, event_meta, prev_counts)

    embed = payload["embeds"][0]
    desc = embed["description"]
    assert "一般票　3　(-2)" in desc
    assert "Total　3　(-2)" in desc
    assert embed["color"] == 0xE24B4A


# ---------------------------------------------------------------------------
# Integration: send_report sets last_reported_at after first send
# ---------------------------------------------------------------------------


def test_first_report_sets_last_reported_at(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)

    _insert_event("SPRINT", "sprint-event", "Sprint Event")
    _insert_ticket(1, "一般票", "sprint-event", 101, paid_at="2026-04-18T06:00:00")

    posts: list = []
    import argus.discord as discord_module

    monkeypatch.setattr(discord_module.httpx, "Client", _mock_client_factory(posts))

    # Before send: last_reported_at is NULL
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()
    assert row["last_reported_at"] is None

    send_report()

    assert len(posts) == 1
    embed = posts[0][1]["embeds"][0]
    # First report: no delta in description
    assert "(+" not in embed["description"]

    # After send: last_reported_at is set
    with get_conn() as conn:
        row = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()
    assert row["last_reported_at"] is not None


def test_second_report_shows_increase_delta(monkeypatch):
    """After first report, a new ticket bought → delta ▲ appears on second report."""
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)

    _insert_event("SPRINT", "sprint-event", "Sprint Event")
    _insert_ticket(1, "一般票", "sprint-event", 101, paid_at="2026-04-17T06:00:00")

    posts: list = []
    import argus.discord as discord_module

    monkeypatch.setattr(discord_module.httpx, "Client", _mock_client_factory(posts))

    # First report — sets last_reported_at to roughly now (test runs ~2026-04-22)
    send_report()
    assert len(posts) == 1

    # Add a new ticket with a paid_at AFTER the current last_reported_at (future date)
    _insert_ticket(2, "一般票", "sprint-event", 102, paid_at="2099-12-31T00:00:00")

    # Second report — should detect the new ticket as delta (paid_at > lra)
    send_report()
    assert len(posts) == 2

    embed = posts[1][1]["embeds"][0]
    assert "(+1)" in embed["description"]


def test_second_report_shows_decrease_delta(monkeypatch):
    """After first report, a ticket is cancelled → delta ▼ on second report."""
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)

    _insert_event("SPRINT", "sprint-event", "Sprint Event")
    # Two tickets active before first report
    _insert_ticket(1, "一般票", "sprint-event", 101, paid_at="2026-04-17T06:00:00")
    _insert_ticket(2, "一般票", "sprint-event", 102, paid_at="2026-04-17T07:00:00")

    posts: list = []
    import argus.discord as discord_module

    monkeypatch.setattr(discord_module.httpx, "Client", _mock_client_factory(posts))

    # First report
    send_report()
    assert len(posts) == 1

    # Capture the last_reported_at set after first report
    with get_conn() as conn:
        lra = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()["last_reported_at"]
    assert lra is not None

    # Cancel ticket 2 after the first report (cancelled_at > lra — use a far-future date)
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET order_state = 'cancelled', cancelled_at = '2099-12-31T10:00:00'"
            " WHERE ticket_id = 2"
        )

    # Second report — ticket 2 is cancelled so active count drops from 2 to 1
    send_report()
    assert len(posts) == 2

    embed = posts[1][1]["embeds"][0]
    assert "(-1)" in embed["description"]


def test_multichannel_report_isolation(monkeypatch):
    """Reporting for channel A must not update last_reported_at for channel B."""
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)
    monkeypatch.setenv("DISCORD_WEBHOOK_MEETUP", MEETUP_URL)

    _insert_event("SPRINT", "sprint-event", "Sprint Event")
    _insert_event("MEETUP", "meetup-event", "Meetup Event")

    import argus.discord as discord_module

    posts: list = []
    monkeypatch.setattr(discord_module.httpx, "Client", _mock_client_factory(posts))

    send_report()
    assert len(posts) == 2

    with get_conn() as conn:
        sprint_lra = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()["last_reported_at"]
        meetup_lra = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'meetup-event'"
        ).fetchone()["last_reported_at"]

    # Both channels must have been updated
    assert sprint_lra is not None
    assert meetup_lra is not None

    # Now mock only SPRINT to succeed; MEETUP fails — SPRINT should still update
    import argus.discord as discord_module2

    class PartialFailClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            if url == MEETUP_URL:
                raise httpx.ConnectError("simulated failure")
            return _make_response(204, url)

    monkeypatch.setattr(discord_module2.httpx, "Client", PartialFailClient)

    # Record meetup lra before second send (sprint_lra already captured above)
    meetup_lra_before = meetup_lra

    send_report()

    with get_conn() as conn:
        sprint_lra_after = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()["last_reported_at"]
        meetup_lra_after = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'meetup-event'"
        ).fetchone()["last_reported_at"]

    # SPRINT succeeded: its lra should be updated (or at least non-null)
    assert sprint_lra_after is not None
    # MEETUP failed: its lra should NOT have changed (update happens after raise_for_status)
    assert meetup_lra_after == meetup_lra_before
