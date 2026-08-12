"""Time series queries for the dashboard.

All timestamps in the DB are stored as UTC ISO 8601 (no offset, no microseconds).
For display, day boundaries are computed in the configured `REPORT_TIMEZONE`.
"""

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from argus import config
from argus.database import Event, Ticket, WebhookLog, get_conn


_UTC = ZoneInfo("UTC")


def get_event(slug: str) -> dict[str, Any] | None:
    """Return event metadata for a single event, or None if not found."""
    with get_conn() as conn:
        row = conn.get(Event, slug)
    if row is None:
        return None
    return _event_dict(row)


def list_webhook_logs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Return recent webhook log entries, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            select(
                WebhookLog.id,
                WebhookLog.method,
                WebhookLog.channel,
                WebhookLog.headers,
                WebhookLog.body,
                WebhookLog.created_at,
            )
            .order_by(WebhookLog.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    return [dict(r._mapping) for r in rows]


def count_webhook_logs() -> int:
    """Return the number of stored webhook logs."""
    with get_conn() as conn:
        return conn.scalar(select(func.count()).select_from(WebhookLog)) or 0


def delete_webhook_log(log_id: int) -> bool:
    """Delete a single webhook log entry. Returns True if deleted, False if not found."""
    with get_conn() as conn:
        row = conn.get(WebhookLog, log_id)
        if row is None:
            return False
        conn.delete(row)
        return True


def clear_webhook_logs() -> int:
    """Delete all webhook log entries. Returns the number of rows removed."""
    with get_conn() as conn:
        count = conn.scalar(select(func.count()).select_from(WebhookLog)) or 0
        conn.query(WebhookLog).delete(synchronize_session=False)
        return count


def delete_event(slug: str) -> bool:
    """Delete an event and all of its tickets atomically.

    Returns True if the event existed and was deleted, False if not found.
    Children (tickets) are deleted first, then the event row, in a single
    transaction (the ORM session commits at context-manager exit, or rolls back
    on exception).
    """
    with get_conn() as conn:
        existing = conn.get(Event, slug)
        if existing is None:
            return False
        conn.query(Ticket).filter(Ticket.event_slug == slug).delete(
            synchronize_session=False
        )
        conn.delete(existing)
    return True


def list_events() -> list[dict[str, Any]]:
    """Return all events that have a channel assigned, newest first."""
    with get_conn() as conn:
        rows = conn.scalars(
            select(Event)
            .where(Event.channel.is_not(None))
            .order_by(Event.start_at.is_(None), Event.start_at.desc(), Event.event_slug)
        ).all()
    return [_event_dict(r) for r in rows]


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
        event_row = conn.get(Event, slug)
        if event_row is None:
            return None
        event = _event_dict(event_row)

        first_paid = conn.scalar(
            select(func.min(Ticket.paid_at)).where(
                Ticket.event_slug == slug, Ticket.paid_at.is_not(None)
            )
        )

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

        ticket_names = list(
            conn.scalars(
                select(Ticket.ticket_name)
                .where(Ticket.event_slug == slug)
                .distinct()
                .order_by(Ticket.ticket_name)
            )
        )

        # One query per day. For typical ranges (≤90 days) this is fast enough
        # on indexed paid_at; if it ever becomes a bottleneck, fold into a
        # single CTE-based query.
        per_day: list[dict[str, int]] = []
        for boundary in boundaries:
            rows = conn.execute(
                select(Ticket.ticket_name, func.count().label("cnt"))
                .where(
                    Ticket.event_slug == slug,
                    Ticket.paid_at.is_not(None),
                    Ticket.paid_at <= boundary,
                    or_(Ticket.cancelled_at.is_(None), Ticket.cancelled_at > boundary),
                )
                .group_by(Ticket.ticket_name)
            ).all()
            per_day.append({r.ticket_name: r.cnt for r in rows})

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


def _event_dict(event: Event) -> dict[str, Any]:
    return {
        "event_slug": event.event_slug,
        "event_name": event.event_name,
        "channel": event.channel,
        "start_at": event.start_at,
        "capacity": event.capacity,
    }
