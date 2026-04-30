"""Tests for argus.dashboard.queries (time series + event listing)."""

from datetime import datetime, timedelta, timezone

from argus.dashboard.queries import (
    clear_webhook_logs,
    count_webhook_logs,
    delete_event,
    delete_webhook_log,
    get_timeseries,
    list_events,
    list_webhook_logs,
)
from argus.database import get_conn


def _insert_event(
    slug: str,
    name: str = "Event",
    channel: str | None = "SPRINT",
    start_at: str | None = None,
    capacity: int | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO events
               (event_slug, event_name, channel, start_at, capacity)
               VALUES (?, ?, ?, ?, ?)""",
            (slug, name, channel, start_at, capacity),
        )


_TID = [0]


def _insert_ticket(
    event_slug: str,
    ticket_name: str,
    paid_at: str | None,
    cancelled_at: str | None = None,
    state: str = "activated",
) -> None:
    _TID[0] += 1
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO tickets
               (ticket_id, ticket_name, event_slug, order_id, order_state, paid_at, cancelled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_TID[0], ticket_name, event_slug, _TID[0], state, paid_at, cancelled_at),
        )


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


def test_list_events_returns_events_with_channel():
    _insert_event("ev1", channel="SPRINT", start_at="2026-05-01T01:00:00")
    _insert_event("ev2", channel="MEETUP", start_at="2026-04-20T01:00:00")
    rows = list_events()
    slugs = [r["event_slug"] for r in rows]
    assert "ev1" in slugs and "ev2" in slugs


def test_list_events_excludes_null_channel():
    _insert_event("ev1", channel="SPRINT")
    _insert_event("ev_null", channel=None)
    rows = list_events()
    slugs = [r["event_slug"] for r in rows]
    assert "ev1" in slugs
    assert "ev_null" not in slugs


def test_list_events_orders_by_start_at_desc():
    _insert_event("older", start_at="2026-04-01T01:00:00")
    _insert_event("newer", start_at="2026-06-01T01:00:00")
    _insert_event("nullstart", start_at=None)
    rows = list_events()
    slugs = [r["event_slug"] for r in rows]
    # Non-null start_at first (newer → older), NULLs last
    assert slugs.index("newer") < slugs.index("older") < slugs.index("nullstart")


# ---------------------------------------------------------------------------
# get_timeseries — basic shape
# ---------------------------------------------------------------------------


def test_timeseries_unknown_event_returns_none():
    assert get_timeseries("does-not-exist") is None


def test_timeseries_no_tickets_returns_empty_datasets():
    _insert_event("empty", start_at="2026-05-01T01:00:00")
    result = get_timeseries("empty")
    assert result is not None
    assert result["labels"] == []
    assert result["datasets"] == []
    assert result["event"]["event_slug"] == "empty"


def test_timeseries_includes_event_metadata():
    _insert_event("ev1", name="Test Event", start_at="2026-05-01T01:00:00", capacity=30)
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    result = get_timeseries("ev1")
    assert result["event"]["event_name"] == "Test Event"
    assert result["event"]["start_at"] == "2026-05-01T01:00:00"
    assert result["event"]["capacity"] == 30


# ---------------------------------------------------------------------------
# get_timeseries — counts
# ---------------------------------------------------------------------------


def test_timeseries_counts_per_day():
    """Tickets paid on different days produce a cumulative time series."""
    # All times stored as UTC; settings.report_timezone defaults to Asia/Taipei (+08:00)
    # 2026-04-25T03:00:00 UTC = 2026-04-25 11:00 Taipei → on day 2026-04-25 in TZ
    # 2026-04-26T03:00:00 UTC = 2026-04-26 11:00 Taipei → on day 2026-04-26 in TZ
    _insert_event("ev1", start_at="2026-04-27T16:00:00")  # 2026-04-28 in Taipei
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T04:00:00")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-26T03:00:00")
    _insert_ticket("ev1", "早鳥票", paid_at="2026-04-25T05:00:00")

    result = get_timeseries("ev1")
    labels = result["labels"]

    # Range: 2026-04-25 (first paid in Taipei) → 2026-04-28 (event start in Taipei)
    assert labels == ["2026-04-25", "2026-04-26", "2026-04-27", "2026-04-28"]

    datasets = {d["name"]: d["data"] for d in result["datasets"]}
    assert datasets["Total"] == [3, 4, 4, 4]
    assert datasets["一般票"] == [2, 3, 3, 3]
    assert datasets["早鳥票"] == [1, 1, 1, 1]


def test_timeseries_excludes_cancelled_after_cancellation():
    """A ticket cancelled mid-range should drop off the count after that date."""
    # start_at 2026-04-28T03:00:00 UTC = 2026-04-28 11:00 Taipei → day 2026-04-28
    _insert_event("ev1", start_at="2026-04-28T03:00:00")
    # Paid 2026-04-25 in Taipei, cancelled 2026-04-27 in Taipei (UTC: -8h)
    _insert_ticket(
        "ev1",
        "一般票",
        paid_at="2026-04-25T03:00:00",
        cancelled_at="2026-04-27T03:00:00",
        state="cancelled",
    )
    result = get_timeseries("ev1")
    datasets = {d["name"]: d["data"] for d in result["datasets"]}
    # Day 2026-04-25 (Taipei 23:59:59 = UTC 15:59:59): paid_at=03:00 ≤ 15:59 → counted (1)
    # Day 2026-04-26: still active (cancelled_at=2026-04-27T03:00 > 2026-04-26T15:59:59 UTC) → 1
    # Day 2026-04-27: cancelled_at=2026-04-27T03:00 ≤ 2026-04-27T15:59:59 UTC → 0
    # Day 2026-04-28: 0
    assert datasets["Total"] == [1, 1, 0, 0]


def test_timeseries_uses_today_when_start_at_missing(monkeypatch):
    """Without start_at, range extends to today (in Taipei)."""
    _insert_event("ev1", start_at=None)
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    result = get_timeseries("ev1")
    # Should have at least one day, ending today (Taipei date)
    assert len(result["labels"]) >= 1
    today_taipei = datetime.now(timezone(timedelta(hours=8))).date()
    assert result["labels"][-1] == today_taipei.isoformat()


def test_timeseries_range_starts_from_first_paid_at():
    _insert_event("ev1", start_at="2026-04-30T16:00:00")  # Day 2026-05-01 in Taipei
    # First paid: 2026-04-25 in Taipei
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    # Later paid: 2026-04-28 in Taipei
    _insert_ticket("ev1", "一般票", paid_at="2026-04-28T03:00:00")
    result = get_timeseries("ev1")
    assert result["labels"][0] == "2026-04-25"


def test_timeseries_caps_at_today_for_future_start_at():
    """If start_at is in the future, labels stop at today and start_marker_label is None."""
    # start_at far in the future
    _insert_event("ev1", start_at="2099-01-01T00:00:00")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")

    result = get_timeseries("ev1")
    today_taipei = datetime.now(timezone(timedelta(hours=8))).date()
    assert result["labels"][-1] == today_taipei.isoformat()
    assert result["start_marker_label"] is None


def test_timeseries_start_marker_for_past_start_at():
    """If start_at is in the past, start_marker_label points to that local date."""
    _insert_event("ev1", start_at="2026-04-26T03:00:00")  # 2026-04-26 in Taipei (past)
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")

    result = get_timeseries("ev1")
    assert result["start_marker_label"] == "2026-04-26"
    # Range stops at start_at (it's already past)
    assert result["labels"][-1] == "2026-04-26"


def test_timeseries_no_marker_when_start_at_unset():
    _insert_event("ev1", start_at=None)
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    result = get_timeseries("ev1")
    assert result["start_marker_label"] is None


def test_timeseries_only_paid_tickets_count():
    """Tickets without paid_at are not counted."""
    _insert_event("ev1", start_at="2026-04-26T16:00:00")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev1", "一般票", paid_at=None)  # not paid yet
    result = get_timeseries("ev1")
    datasets = {d["name"]: d["data"] for d in result["datasets"]}
    assert datasets["一般票"] == [1, 1, 1]


def test_timeseries_total_equals_sum_of_ticket_types():
    _insert_event("ev1", start_at="2026-04-26T16:00:00")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev1", "早鳥票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev1", "VIP", paid_at="2026-04-26T03:00:00")
    result = get_timeseries("ev1")
    datasets = {d["name"]: d["data"] for d in result["datasets"]}

    for i in range(len(result["labels"])):
        per_type_sum = sum(
            datasets[name][i]
            for name in datasets
            if name != "Total"
        )
        assert datasets["Total"][i] == per_type_sum


def test_timeseries_isolates_events():
    """Counts for one event must not include another event's tickets."""
    _insert_event("ev1", start_at="2026-04-26T16:00:00")
    _insert_event("ev2", start_at="2026-04-26T16:00:00")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev2", "一般票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev2", "一般票", paid_at="2026-04-25T04:00:00")
    r1 = get_timeseries("ev1")
    r2 = get_timeseries("ev2")
    assert {d["name"]: d["data"][0] for d in r1["datasets"]}["Total"] == 1
    assert {d["name"]: d["data"][0] for d in r2["datasets"]}["Total"] == 2


# ---------------------------------------------------------------------------
# delete_event
# ---------------------------------------------------------------------------


def test_delete_event_removes_event_row():
    _insert_event("ev1")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")

    assert delete_event("ev1") is True

    with get_conn() as conn:
        ev_count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_slug = ?", ("ev1",)
        ).fetchone()[0]
        ticket_count = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE event_slug = ?", ("ev1",)
        ).fetchone()[0]
    assert ev_count == 0
    assert ticket_count == 0


def test_delete_event_unknown_returns_false():
    assert delete_event("does-not-exist") is False


def test_delete_event_isolates_other_events():
    _insert_event("ev1")
    _insert_event("ev2")
    _insert_ticket("ev1", "一般票", paid_at="2026-04-25T03:00:00")
    _insert_ticket("ev2", "一般票", paid_at="2026-04-25T03:00:00")

    delete_event("ev1")

    with get_conn() as conn:
        # ev2 untouched
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_slug = ?", ("ev2",)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE event_slug = ?", ("ev2",)
            ).fetchone()[0]
            == 1
        )


# ---------------------------------------------------------------------------
# webhook_logs queries
# ---------------------------------------------------------------------------


def _insert_webhook_log(method: str = "POST", channel: str | None = "SPRINT",
                       headers: str = '{"x-kktix-secret":"***"}',
                       body: str = '{"batch_id":"x","notifications":[]}') -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO webhook_logs (method, channel, headers, body)
               VALUES (?, ?, ?, ?)""",
            (method, channel, headers, body),
        )
        return cur.lastrowid


def test_list_webhook_logs_newest_first():
    id1 = _insert_webhook_log(channel="A")
    id2 = _insert_webhook_log(channel="B")
    id3 = _insert_webhook_log(channel="C")
    rows = list_webhook_logs()
    ids = [r["id"] for r in rows]
    assert ids == [id3, id2, id1]


def test_list_webhook_logs_respects_limit_offset():
    for _ in range(5):
        _insert_webhook_log()
    page1 = list_webhook_logs(limit=2, offset=0)
    page2 = list_webhook_logs(limit=2, offset=2)
    assert len(page1) == 2 and len(page2) == 2
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


def test_count_webhook_logs():
    assert count_webhook_logs() == 0
    _insert_webhook_log()
    _insert_webhook_log()
    assert count_webhook_logs() == 2


def test_delete_webhook_log_existing():
    log_id = _insert_webhook_log()
    other_id = _insert_webhook_log()
    assert delete_webhook_log(log_id) is True
    remaining = [r["id"] for r in list_webhook_logs()]
    assert log_id not in remaining
    assert other_id in remaining


def test_delete_webhook_log_unknown():
    assert delete_webhook_log(99999) is False


def test_clear_webhook_logs_returns_count_and_empties_table():
    for _ in range(3):
        _insert_webhook_log()
    deleted = clear_webhook_logs()
    assert deleted == 3
    assert count_webhook_logs() == 0


def test_clear_webhook_logs_empty():
    assert clear_webhook_logs() == 0
