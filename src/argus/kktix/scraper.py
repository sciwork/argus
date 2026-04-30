from dataclasses import dataclass
import logging
import re

import httpx

from argus import config
from argus.database import get_conn
from argus.timeutil import to_utc


logger = logging.getLogger(__name__)

_KKTIX_URL = "https://{org}.kktix.cc/events/{slug}"
_SCRAPE_TIMEOUT = 10.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# JSON-LD startDate field
_JSONLD_START_RE = re.compile(r'"startDate"\s*:\s*"([^"]+)"')
# fa-male icon followed by "current / total"
_CAPACITY_RE = re.compile(r'fa-male"></i>\s*\d+\s*/\s*(\d+)')


@dataclass(frozen=True)
class EventDetails:
    start_at: str | None  # UTC ISO "%Y-%m-%dT%H:%M:%S"
    capacity: int | None


async def fetch_event_details(slug: str) -> EventDetails:
    """Fetch KKTIX event page and parse details.

    Requires KKTIX_ORGANIZATION to be set (e.g. "example"), which is the
    subdomain of the organizer's KKTIX page (https://{org}.kktix.cc).
    """
    org = config.settings.kktix_organization
    if not org:
        raise RuntimeError("KKTIX_ORGANIZATION env var is not set")
    url = _KKTIX_URL.format(org=org, slug=slug)
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=_SCRAPE_TIMEOUT, headers=_HEADERS
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return parse_event_html(resp.text)


def parse_event_html(html: str) -> EventDetails:
    return EventDetails(
        start_at=_parse_start_at(html),
        capacity=_parse_capacity(html),
    )


def _parse_start_at(html: str) -> str | None:
    # Prefer JSON-LD structured data: "startDate":"2026-04-25T09:00:00.000+08:00"
    m = _JSONLD_START_RE.search(html)
    if not m:
        logger.warning("kktix: startDate not found in JSON-LD")
        return None
    raw = m.group(1)
    try:
        return to_utc(raw)
    except ValueError:
        logger.warning("kktix: invalid startDate: %r", raw)
        return None


def _parse_capacity(html: str) -> int | None:
    # <i class="fa fa-male"></i>0 / 30  →  30
    m = _CAPACITY_RE.search(html)
    if not m:
        logger.warning("kktix: capacity pattern not found")
        return None
    return int(m.group(1))


async def enrich_event(slug: str) -> None:
    """Fetch and store start_at + capacity for a newly created event.
    Skips if start_at is already populated. Swallows all exceptions."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT start_at FROM events WHERE event_slug = ?", (slug,)
            ).fetchone()
        if row is None or row["start_at"] is not None:
            return

        details = await fetch_event_details(slug)

        with get_conn() as conn:
            conn.execute(
                """UPDATE events
                   SET start_at = COALESCE(?, start_at),
                       capacity = COALESCE(?, capacity)
                   WHERE event_slug = ? AND start_at IS NULL""",
                (details.start_at, details.capacity, slug),
            )
        logger.info(
            "kktix: enriched event %s start_at=%s capacity=%s",
            slug,
            details.start_at,
            details.capacity,
        )
    except Exception:
        logger.exception("kktix: failed to enrich event %s", slug)
