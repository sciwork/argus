import logging

import httpx

from argus.database import get_conn
from argus.kktix.report import send_report


SPRINT_URL = "https://discord.com/api/webhooks/sprint-test"
MEETUP_URL = "https://discord.com/api/webhooks/meetup-test"


def _make_response(status_code: int, url: str) -> httpx.Response:
    """Build a properly-bound httpx.Response so raise_for_status() works."""
    req = httpx.Request("POST", url)
    return httpx.Response(status_code, request=req)


def _insert_event_and_ticket(
    channel: str,
    event_slug: str,
    event_name: str,
    ticket_id: int,
    ticket_name: str,
    order_id: int,
) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel) VALUES (?, ?, ?)"
            " ON CONFLICT(event_slug) DO NOTHING",
            (event_slug, event_name, channel),
        )
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state)
               VALUES (?, ?, ?, ?, 'activated')
               ON CONFLICT(ticket_id) DO NOTHING""",
            (ticket_id, ticket_name, event_slug, order_id),
        )


# ---------------------------------------------------------------------------
# send_report() — no channels configured
# ---------------------------------------------------------------------------


def test_send_report_no_active_events_skips(caplog):
    # No events in DB → nothing to report
    with caplog.at_level(logging.INFO, logger="argus.kktix.report"):
        send_report()

    assert any("no active events" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# send_report() — fan-out per channel
# ---------------------------------------------------------------------------


def test_send_report_fans_out_per_channel(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)
    monkeypatch.setenv("DISCORD_WEBHOOK_MEETUP", MEETUP_URL)

    _insert_event_and_ticket("SPRINT", "sprint-event", "Sprint Event", 1, "一般票", 101)
    _insert_event_and_ticket("MEETUP", "meetup-event", "Meetup Event", 2, "一般票", 102)

    posts: list[tuple[str, dict]] = []

    import argus.discord as discord_module

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            import json as json_mod

            body = json_mod.loads(json_mod.dumps(json))
            posts.append((url, body))
            return _make_response(204, url)

    monkeypatch.setattr(discord_module.httpx, "Client", MockClient)

    send_report()

    assert len(posts) == 2
    urls = {p[0] for p in posts}
    assert SPRINT_URL in urls
    assert MEETUP_URL in urls

    # Each payload should only contain the channel's own event
    for url, payload in posts:
        embeds = payload.get("embeds", [])
        if url == SPRINT_URL:
            titles = [e.get("title", "") for e in embeds]
            assert any("Sprint Event" in t for t in titles)
            assert not any("Meetup Event" in t for t in titles)
        elif url == MEETUP_URL:
            titles = [e.get("title", "") for e in embeds]
            assert any("Meetup Event" in t for t in titles)
            assert not any("Sprint Event" in t for t in titles)


# ---------------------------------------------------------------------------
# Events with channel=NULL are excluded from all reports
# ---------------------------------------------------------------------------


def test_send_report_skips_events_without_channel(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)

    # Insert a NULL-channel event alongside a SPRINT event
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel) VALUES (?, ?, NULL)",
            ("null-event", "Null Channel Event"),
        )
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state)
               VALUES (99, '一般票', 'null-event', 999, 'activated')""",
        )
    _insert_event_and_ticket("SPRINT", "sprint-event", "Sprint Event", 1, "一般票", 101)

    posts: list[tuple[str, dict]] = []

    import argus.discord as discord_module

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            posts.append((url, json))
            return _make_response(204, url)

    monkeypatch.setattr(discord_module.httpx, "Client", MockClient)

    send_report()

    # Only SPRINT should receive a report; null-channel event must not appear
    assert len(posts) == 1
    url, payload = posts[0]
    assert url == SPRINT_URL
    titles = [e.get("title", "") for e in payload.get("embeds", [])]
    assert not any("Null Channel Event" in t for t in titles)


# ---------------------------------------------------------------------------
# One channel failure does not block others
# ---------------------------------------------------------------------------


def test_send_report_one_channel_failure_does_not_block_others(monkeypatch, caplog):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)
    monkeypatch.setenv("DISCORD_WEBHOOK_MEETUP", MEETUP_URL)

    _insert_event_and_ticket("SPRINT", "sprint-event", "Sprint Event", 1, "一般票", 101)
    _insert_event_and_ticket("MEETUP", "meetup-event", "Meetup Event", 2, "一般票", 102)

    posts: list[str] = []

    import argus.discord as discord_module

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            if url == SPRINT_URL:
                return _make_response(502, url)
            posts.append(url)
            return _make_response(204, url)

    monkeypatch.setattr(discord_module.httpx, "Client", MockClient)

    with caplog.at_level(logging.ERROR, logger="argus.discord"):
        send_report()

    # MEETUP should still succeed
    assert MEETUP_URL in posts
    # Error should be logged for SPRINT
    assert any(SPRINT_URL in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Reports are channel-scoped (last_reported_at per event)
# ---------------------------------------------------------------------------


def test_last_reported_at_is_channel_scoped(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)
    monkeypatch.setenv("DISCORD_WEBHOOK_MEETUP", MEETUP_URL)

    # Two channels, distinct events
    _insert_event_and_ticket(
        "SPRINT", "sprint-event", "Sprint Version", 1, "一般票", 101
    )
    _insert_event_and_ticket(
        "MEETUP", "meetup-event", "Meetup Version", 2, "一般票", 102
    )

    import argus.discord as discord_module

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            return _make_response(204, url)

    monkeypatch.setattr(discord_module.httpx, "Client", MockClient)

    send_report()

    with get_conn() as conn:
        sprint_lra = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'sprint-event'"
        ).fetchone()["last_reported_at"]
        meetup_lra = conn.execute(
            "SELECT last_reported_at FROM events WHERE event_slug = 'meetup-event'"
        ).fetchone()["last_reported_at"]

    assert sprint_lra is not None
    assert meetup_lra is not None


# ---------------------------------------------------------------------------
# Empty channel sends "no data" embed
# ---------------------------------------------------------------------------


def test_send_report_no_active_events_sends_no_request(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", SPRINT_URL)
    # No events in DB → send_report should make no HTTP requests

    posts: list = []

    import argus.discord as discord_module

    class MockClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json=None):
            posts.append(url)
            return _make_response(204, url)

    monkeypatch.setattr(discord_module.httpx, "Client", MockClient)

    send_report()

    assert len(posts) == 0
