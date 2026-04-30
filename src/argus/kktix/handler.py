import logging

from argus.database import get_conn
from argus.timeutil import to_utc


logger = logging.getLogger(__name__)


def _is_kktix_test_notification(event: dict) -> bool:
    return event.get("slug") == "event-slug" and event.get("name") == "Event Name"


def handle_notification(notification: dict, channel: str) -> list[str]:
    type_ = notification.get("type")
    event = notification.get("event", {})
    order = notification.get("order", {})

    event_slug = event.get("slug")
    event_name = event.get("name")
    order_id = order.get("id")

    if _is_kktix_test_notification(event):
        logger.info(
            "kktix: ignored test webhook notification type=%s channel=%s",
            type_,
            channel,
        )
        return []

    new_slugs: list[str] = []

    if type_ == "order_activated_paid":
        contact = notification.get("contact", {})
        tickets = notification.get("tickets", [])

        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO events (event_slug, event_name, channel)
                   VALUES (?, ?, ?)
                   ON CONFLICT(event_slug) DO NOTHING""",
                (event_slug, event_name, channel),
            )
            if cur.rowcount == 1:
                new_slugs.append(event_slug)
            conn.executemany(
                """INSERT INTO tickets
                   (ticket_id, ticket_name, event_slug, order_id, order_state,
                    contact_name, contact_email, paid_at)
                   VALUES (?, ?, ?, ?, 'activated', ?, ?, ?)
                   ON CONFLICT(ticket_id) DO NOTHING""",
                [
                    (
                        t["id"],
                        t["name"],
                        event_slug,
                        order_id,
                        contact.get("name"),
                        contact.get("email"),
                        to_utc(order.get("paid_at")),
                    )
                    for t in tickets
                ],
            )

    elif type_ == "order_cancelled":
        with get_conn() as conn:
            conn.execute(
                """UPDATE tickets
                   SET order_state = 'cancelled',
                       cancelled_at = ?
                   WHERE order_id = ?""",
                (to_utc(order.get("cancelled_at")), order_id),
            )

    return new_slugs
