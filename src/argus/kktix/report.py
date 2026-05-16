from datetime import datetime, timedelta, timezone
import logging
import sqlite3

from argus import discord
from argus.channels import resolve_webhook_url
from argus.database import get_conn
from argus.timeutil import utcnow_iso


logger = logging.getLogger(__name__)

_COLOR_INCREASE = 0x1D9E75
_COLOR_DECREASE = 0xE24B4A
_COLOR_NEUTRAL = 0x888780


def build_payload(
    rows: list[dict],
    event_meta: list[dict],
    prev_counts: dict[tuple[str, str], int],
) -> dict:
    tw = timezone(timedelta(hours=8))
    now_str = datetime.now(tw).strftime("%Y-%m-%d %H:%M")

    first_report_slugs = {
        e["event_slug"] for e in event_meta if e["last_reported_at"] is None
    }

    event_map: dict[str, dict] = {}
    for row in rows:
        slug = row["event_slug"]
        if slug not in event_map:
            event_map[slug] = {"name": row["event_name"], "tickets": []}
        event_map[slug]["tickets"].append(row)

    embeds = []
    for slug, data in event_map.items():
        total_now = 0
        total_prev = 0
        is_first = slug in first_report_slugs
        lines = []

        for t in data["tickets"]:
            ticket_name = t["ticket_name"]
            count = t["cnt"]
            total_now += count
            if is_first:
                lines.append(f"{ticket_name}　{count}")
            else:
                prev = prev_counts.get((slug, ticket_name), 0)
                total_prev += prev
                diff = count - prev
                delta = f"(+{diff})" if diff >= 0 else f"({diff})"
                lines.append(f"{ticket_name}　{count}　{delta}")

        lines.append("─────────────")
        if is_first:
            lines.append(f"**Total　{total_now}**")
            color = _COLOR_NEUTRAL
        else:
            total_diff = total_now - total_prev
            total_delta = f"(+{total_diff})" if total_diff >= 0 else f"({total_diff})"
            lines.append(f"**Total　{total_now}　{total_delta}**")
            color = (
                _COLOR_INCREASE
                if total_diff > 0
                else _COLOR_DECREASE
                if total_diff < 0
                else _COLOR_NEUTRAL
            )

        embeds.append(
            {
                "title": f"🎟️ {data['name']}",
                "description": "\n".join(lines),
                "color": color,
            }
        )

    if not embeds:
        embeds.append(
            {
                "title": "📋 Argus Daily Registration Summary",
                "description": "No active event registrations.",
                "color": _COLOR_NEUTRAL,
            }
        )

    return {
        "content": f"📊 **Argus Daily Registration Summary**　{now_str} (Asia/Taipei)",
        "embeds": embeds,
    }


def send_report() -> None:
    # Only report on channels that have events whose start_at has not yet passed.
    # Events with start_at IS NULL (not yet enriched) are included as well.
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT channel FROM events
               WHERE channel IS NOT NULL
                 AND (start_at IS NULL OR start_at > ?)""",
            (utcnow_iso(),),
        ).fetchall()
        channels = [r["channel"] for r in rows]
        if not channels:
            logger.info("send_report: no active events found, skipping")
            return
        for ch in channels:
            try:
                _send_report_for_channel(conn, ch)
            except Exception:
                logger.exception("failed to send report for channel %s", ch)


def _send_report_for_channel(conn: sqlite3.Connection, channel: str) -> None:
    url = resolve_webhook_url(channel)

    # 1. Fetch all events for this channel (with last_reported_at)
    event_rows = conn.execute(
        "SELECT event_slug, event_name, last_reported_at FROM events WHERE channel = ?",
        (channel,),
    ).fetchall()

    # 2. now_count per (event_slug, ticket_name)
    now_rows = conn.execute(
        """SELECT t.event_slug, e.event_name, t.ticket_name, COUNT(*) AS cnt
           FROM tickets t
           JOIN events e ON e.event_slug = t.event_slug
           WHERE e.channel = ? AND t.order_state = 'activated'
           GROUP BY t.event_slug, t.ticket_name""",
        (channel,),
    ).fetchall()

    # 3. prev_count: query once per event that has a last_reported_at
    prev_counts: dict[tuple[str, str], int] = {}
    for ev in event_rows:
        lra = ev["last_reported_at"]
        if lra is None:
            continue
        for r in conn.execute(
            """SELECT ticket_name, COUNT(*) AS cnt
               FROM tickets
               WHERE event_slug = ?
                 AND paid_at IS NOT NULL AND paid_at <= ?
                 AND (cancelled_at IS NULL OR cancelled_at > ?)
               GROUP BY ticket_name""",
            (ev["event_slug"], lra, lra),
        ):
            prev_counts[(ev["event_slug"], r["ticket_name"])] = r["cnt"]

    event_meta = [dict(r) for r in event_rows]
    rows = [dict(r) for r in now_rows]
    payload = build_payload(rows, event_meta, prev_counts)

    ok = discord.post(url, **payload)
    if ok:
        conn.execute(
            "UPDATE events SET last_reported_at = ? WHERE channel = ?",
            (utcnow_iso(), channel),
        )
