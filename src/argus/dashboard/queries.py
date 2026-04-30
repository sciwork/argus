"""Time series queries for the dashboard.

All timestamps in the DB are stored as UTC ISO 8601 (no offset, no microseconds).
For display, day boundaries are computed in the configured `REPORT_TIMEZONE`.
"""

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from argus import config
from argus.database import get_conn


_UTC = ZoneInfo("UTC")


def get_event(slug: str) -> dict[str, Any] | None:
    """Return event metadata for a single event, or None if not found."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT event_slug, event_name, channel, start_at, capacity"
            " FROM events WHERE event_slug = ?",
            (slug,),
        ).fetchone()
    return dict(row) if row else None


def list_webhook_logs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Return recent webhook log entries, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, method, channel, headers, body, created_at
               FROM webhook_logs
               ORDER BY id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def count_webhook_logs() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM webhook_logs").fetchone()[0]


def delete_webhook_log(log_id: int) -> bool:
    """Delete a single webhook log entry. Returns True if deleted, False if not found."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM webhook_logs WHERE id = ?", (log_id,))
        return cur.rowcount > 0


def clear_webhook_logs() -> int:
    """Delete all webhook log entries. Returns the number of rows removed."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM webhook_logs")
        return cur.rowcount


def delete_event(slug: str) -> bool:
    """Delete an event and all of its tickets atomically.

    Returns True if the event existed and was deleted, False if not found.
    Children (tickets) are deleted first, then the event row, in a single
    transaction (the sqlite3 connection commits at context-manager exit, or
    rolls back on exception).
    """
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM events WHERE event_slug = ?", (slug,)
        ).fetchone()
        if existing is None:
            return False
        conn.execute("DELETE FROM tickets WHERE event_slug = ?", (slug,))
        conn.execute("DELETE FROM events WHERE event_slug = ?", (slug,))
    return True


def list_events() -> list[dict[str, Any]]:
    """Return all events that have a channel assigned, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT event_slug, event_name, channel, start_at, capacity
               FROM events
               WHERE channel IS NOT NULL
               ORDER BY start_at IS NULL, start_at DESC, event_slug"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_timeseries(slug: str) -> dict[str, Any] | None:
    """Return event metadata + per-day time series for charting.

    Range: from the local date of the first paid_at, through min(today, start_at).
    The chart never extends into the future — if `start_at` is in the future,
    the chart stops at today, and the response includes `start_marker_label = None`
    so the frontend can suppress the "Event start" annotation.

    Returns None if the event doesn't exist; returns empty datasets if the
    event has no tickets yet.
    """
    with get_conn() as conn:
        event_row = conn.execute(
            "SELECT event_slug, event_name, channel, start_at, capacity"
            " FROM events WHERE event_slug = ?",
            (slug,),
        ).fetchone()
        if event_row is None:
            return None
        event = dict(event_row)

        first_paid = conn.execute(
            "SELECT MIN(paid_at) FROM tickets"
            " WHERE event_slug = ? AND paid_at IS NOT NULL",
            (slug,),
        ).fetchone()[0]

        if not first_paid:
            return {
                "event": event,
                "labels": [],
                "datasets": [],
                "start_marker_label": None,
            }

        tz = ZoneInfo(config.settings.report_timezone)
        today = datetime.now(tz).date()
        start_day = _utc_iso_to_local_date(first_paid, tz)
        if event["start_at"]:
            start_at_local = _utc_iso_to_local_date(event["start_at"], tz)
            end_day = min(start_at_local, today)
            # The "Event start" marker only makes sense if start_at falls within
            # the displayed range. If it's in the future, suppress the marker.
            start_marker_label = (
                start_at_local.isoformat() if start_at_local <= today else None
            )
        else:
            end_day = today
            start_marker_label = None

        days = _date_range(start_day, end_day)
        boundaries = [_end_of_day_utc(d, tz) for d in days]

        ticket_names = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT ticket_name FROM tickets"
                " WHERE event_slug = ? ORDER BY ticket_name",
                (slug,),
            )
        ]

        # One query per day. For typical ranges (≤90 days) this is fast enough
        # on indexed paid_at; if it ever becomes a bottleneck, fold into a
        # single CTE-based query.
        per_day: list[dict[str, int]] = []
        for boundary in boundaries:
            rows = conn.execute(
                """SELECT ticket_name, COUNT(*) AS cnt
                   FROM tickets
                   WHERE event_slug = ?
                     AND paid_at IS NOT NULL AND paid_at <= ?
                     AND (cancelled_at IS NULL OR cancelled_at > ?)
                   GROUP BY ticket_name""",
                (slug, boundary, boundary),
            ).fetchall()
            per_day.append({r["ticket_name"]: r["cnt"] for r in rows})

    datasets: list[dict[str, Any]] = [
        {"name": "Total", "data": [sum(d.values()) for d in per_day]},
    ]
    for name in ticket_names:
        datasets.append({"name": name, "data": [d.get(name, 0) for d in per_day]})

    return {
        "event": event,
        "labels": [d.isoformat() for d in days],
        "datasets": datasets,
        "start_marker_label": start_marker_label,
    }


def _utc_iso_to_local_date(utc_iso: str, tz: ZoneInfo) -> date:
    """Convert a stored UTC ISO 8601 string (no offset) to a local date."""
    return datetime.fromisoformat(utc_iso).replace(tzinfo=_UTC).astimezone(tz).date()


def _end_of_day_utc(d: date, tz: ZoneInfo) -> str:
    """End-of-day-D-in-tz expressed as UTC ISO 8601 string (no offset, no microseconds)."""
    next_midnight = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz)
    end = next_midnight - timedelta(seconds=1)
    return end.astimezone(_UTC).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d = d + timedelta(days=1)
    return days
