"""Manual test: sends REAL Discord webhooks for visual format inspection.

This test is skipped by default. To run it, source your .env (so
DISCORD_WEBHOOK_SPRINT is set to a real URL) and opt in:

    set -a && source .env && set +a
    ARGUS_MANUAL_TEST=1 hatch run pytest tests/test_discord_format_manual.py -v -s

Sends a single Discord message containing four embeds covering:
    - Event A: first report (no prior snapshot, no delta shown)
    - Event B: registrations increased since last report (▲)
    - Event C: registrations decreased since last report (▼)
    - Event D: no change since last report (─)
"""

import os

import pytest

from argus.database import get_conn
from argus.kktix.report import send_report


# Capture the real URL at import time, before the autouse fixture clears it.
_REAL_SPRINT_URL = os.environ.get("DISCORD_WEBHOOK_SPRINT")
_MANUAL_FLAG = os.environ.get("ARGUS_MANUAL_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not (_MANUAL_FLAG and _REAL_SPRINT_URL),
    reason="manual test: set ARGUS_MANUAL_TEST=1 and source DISCORD_WEBHOOK_SPRINT to run",
)


CHANNEL = "SPRINT"
FUTURE_START = "2026-12-01T01:00:00"
LAST_REPORT = "2026-04-20T00:00:00"


def _insert_event(slug: str, name: str, last_reported_at: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO events (event_slug, event_name, channel, start_at, last_reported_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (slug, name, CHANNEL, FUTURE_START, last_reported_at),
        )


def _insert_ticket(
    tid: int,
    event_slug: str,
    ticket_name: str,
    order_id: int,
    paid_at: str,
    cancelled_at: str | None = None,
    state: str = "activated",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state, paid_at, cancelled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, ticket_name, event_slug, order_id, state, paid_at, cancelled_at),
        )


def test_send_real_discord_report(monkeypatch):
    # Re-establish the real webhook URL for this test only (autouse fixture cleared it)
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", _REAL_SPRINT_URL)

    # Event A — first report (no last_reported_at)
    _insert_event("event-a", "Event A")
    _insert_ticket(1, "event-a", "一般票", 101, "2026-04-18T03:00:00")
    _insert_ticket(2, "event-a", "一般票", 102, "2026-04-19T04:00:00")
    _insert_ticket(3, "event-a", "早鳥票", 103, "2026-04-17T02:00:00")

    # Event B — increased since last report (+3 一般票, +1 早鳥票)
    _insert_event("event-b", "Event B", last_reported_at=LAST_REPORT)
    _insert_ticket(4, "event-b", "一般票", 201, "2026-04-18T03:00:00")
    _insert_ticket(5, "event-b", "早鳥票", 202, "2026-04-18T04:00:00")
    _insert_ticket(6, "event-b", "一般票", 203, "2026-04-21T03:00:00")
    _insert_ticket(7, "event-b", "一般票", 204, "2026-04-21T04:00:00")
    _insert_ticket(8, "event-b", "一般票", 205, "2026-04-22T03:00:00")
    _insert_ticket(9, "event-b", "早鳥票", 206, "2026-04-22T04:00:00")

    # Event C — decreased since last report (2 cancelled after lra)
    _insert_event("event-c", "Event C", last_reported_at=LAST_REPORT)
    _insert_ticket(10, "event-c", "一般票", 301, "2026-04-18T03:00:00")
    _insert_ticket(11, "event-c", "一般票", 302, "2026-04-18T04:00:00")
    _insert_ticket(12, "event-c", "一般票", 303, "2026-04-18T05:00:00")
    _insert_ticket(
        13,
        "event-c",
        "一般票",
        304,
        "2026-04-18T06:00:00",
        cancelled_at="2026-04-21T03:00:00",
        state="cancelled",
    )
    _insert_ticket(
        14,
        "event-c",
        "一般票",
        305,
        "2026-04-18T07:00:00",
        cancelled_at="2026-04-21T04:00:00",
        state="cancelled",
    )

    # Event D — no change since last report
    _insert_event("event-d", "Event D", last_reported_at=LAST_REPORT)
    _insert_ticket(15, "event-d", "一般票", 401, "2026-04-18T03:00:00")
    _insert_ticket(16, "event-d", "一般票", 402, "2026-04-19T03:00:00")
    _insert_ticket(17, "event-d", "早鳥票", 403, "2026-04-17T03:00:00")

    print("\nSending real Discord report to SPRINT (4 events)...")
    send_report()
    print("Done. Check Discord channel.")
