from pathlib import Path
import json
import logging
import sqlite3

from jinja2 import Environment, FileSystemLoader

from argus import discord
from argus.channels import resolve_webhook_url
from argus.database import get_conn
from argus.timeutil import utcnow_iso


logger = logging.getLogger(__name__)

_COLOR_INCREASE = 0x1D9E75
_COLOR_DECREASE = 0xE24B4A
_COLOR_NEUTRAL = 0x888780
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_templates = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=False)


def build_payload(
    rows: list[dict],
    event_meta: list[dict],
    prev_counts: dict[tuple[str, str], int],
) -> dict:
    first_report_slugs = {
        e["event_slug"] for e in event_meta if e["last_reported_at"] is None
    }

    event_map: dict[str, dict] = {}
    for row in rows:
        slug = row["event_slug"]
        if slug not in event_map:
            event_map[slug] = {"name": row["event_name"], "tickets": []}
        event_map[slug]["tickets"].append(row)

    events = []
    for slug, data in event_map.items():
        total_now = 0
        total_prev = 0
        is_first = slug in first_report_slugs
        ticket_rows = []

        for t in data["tickets"]:
            ticket_name = t["ticket_name"]
            count = t["cnt"]
            total_now += count
            if is_first:
                ticket_rows.append({"name": ticket_name, "count": count, "delta": None})
            else:
                prev = prev_counts.get((slug, ticket_name), 0)
                total_prev += prev
                diff = count - prev
                delta = f"+{diff}" if diff >= 0 else str(diff)
                ticket_rows.append(
                    {"name": ticket_name, "count": count, "delta": delta}
                )

        if is_first:
            color = _COLOR_NEUTRAL
            total_delta = None
        else:
            total_diff = total_now - total_prev
            total_delta = f"+{total_diff}" if total_diff >= 0 else str(total_diff)
            color = (
                _COLOR_INCREASE
                if total_diff > 0
                else _COLOR_DECREASE
                if total_diff < 0
                else _COLOR_NEUTRAL
            )

        events.append(
            {
                "name": data["name"],
                "tickets": ticket_rows,
                "total": total_now,
                "total_delta": total_delta,
                "color": color,
            }
        )

    # Keep Discord's payload schema and display text in the JSON template.
    template = _templates.get_template("report.json.j2")
    return json.loads(
        template.render(
            events=events,
        )
    )


def send_report() -> None:
    # Only report on channels that have events whose start_at has not yet passed.
    # Events with start_at IS NULL (not yet enriched) are included as well.
    now = utcnow_iso()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT channel, event_slug, event_name, last_reported_at FROM events
               WHERE channel IS NOT NULL
                 AND (start_at IS NULL OR start_at > ?)""",
            (now,),
        ).fetchall()

        ## channel_event_map example:
        ## {
        ##   "channel1": {
        ##       "event_slug1": {
        ##           "event_slug": "event_slug1",
        ##           "event_name": "Event 1",
        ##           "last_reported_at": "2024-06-01T00:00:00Z"
        ##       },
        ##       "event_slug2": {
        ##           "event_slug": "event_slug2",
        ##           "event_name": "Event 2",
        ##           "last_reported_at": None
        ##       }
        ##   },
        ##   "channel2": {"event_slug3": {...}},
        ## }

        channel_event_map: dict[str, dict[str, dict]] = {}
        for r in rows:
            ch = r["channel"]
            slug = r["event_slug"]
            if ch not in channel_event_map:
                channel_event_map[ch] = {}
            channel_event_map[ch][slug] = {
                "event_slug": slug,
                "event_name": r["event_name"],
                "last_reported_at": r["last_reported_at"],
            }

        if not channel_event_map:
            logger.info("send_report: no active events found, skipping")
            return
        for ch, events in channel_event_map.items():
            try:
                _send_report_for_channel(conn, ch, events, now)
            except Exception:
                logger.exception("failed to send report for channel %s", ch)


def _send_report_for_channel(
    conn: sqlite3.Connection, channel: str, event_map: dict[str, dict], now: str
) -> None:
    url = resolve_webhook_url(channel)
    slugs = list(event_map.keys())
    placeholders = ",".join("?" * len(slugs))

    # 1. now_count per (event_slug, ticket_name)
    now_rows = conn.execute(
        f"""SELECT t.event_slug, e.event_name, t.ticket_name, COUNT(*) AS cnt
           FROM tickets t
           JOIN events e ON e.event_slug = t.event_slug
           WHERE t.event_slug IN ({placeholders}) AND t.order_state = 'activated'
           GROUP BY t.event_slug, t.ticket_name""",
        slugs,
    ).fetchall()

    # 2. prev_count: query once per event that has a last_reported_at
    prev_counts: dict[tuple[str, str], int] = {}
    for slug, ev in event_map.items():
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
            (slug, lra, lra),
        ):
            prev_counts[(slug, r["ticket_name"])] = r["cnt"]

    event_meta = [dict(r) for r in event_map.values()]
    rows = [dict(r) for r in now_rows]
    payload = build_payload(rows, event_meta, prev_counts)

    ok = discord.post(url, **payload)
    if ok:
        conn.execute(
            f"UPDATE events SET last_reported_at = ? WHERE event_slug IN ({placeholders})",
            [now, *slugs],
        )
