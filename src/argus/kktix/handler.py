import logging

from sqlalchemy.exc import IntegrityError

from argus.database import Event, Ticket, get_conn
from argus.timeutil import to_utc


logger = logging.getLogger(__name__)


def _is_kktix_test_notification(event: dict) -> bool:
    return event.get("slug") == "event-slug" and event.get("name") == "Event Name"


def handle_notification(notification: dict, channel: str) -> list[str]:
    """Store one KKTIX notification.

    Args:
        notification: Parsed KKTIX notification body.
        channel: Normalized channel name for the event.

    Returns:
        Slugs for events that were added for the first time.
    """
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
            if _add_if_missing(
                conn,
                event_slug,
                Event(
                    event_slug=event_slug,
                    event_name=event_name,
                    channel=channel,
                ),
            ):
                new_slugs.append(event_slug)
            for ticket in tickets:
                _add_if_missing(
                    conn,
                    ticket["id"],
                    Ticket(
                        ticket_id=ticket["id"],
                        ticket_name=ticket["name"],
                        event_slug=event_slug,
                        order_id=order_id,
                        order_state="activated",
                        contact_name=contact.get("name"),
                        contact_email=contact.get("email"),
                        paid_at=to_utc(order.get("paid_at")),
                    ),
                )

    elif type_ == "order_cancelled":
        with get_conn() as conn:
            conn.query(Ticket).filter(Ticket.order_id == order_id).update(
                {
                    Ticket.order_state: "cancelled",
                    Ticket.cancelled_at: to_utc(order.get("cancelled_at")),
                },
                synchronize_session=False,
            )

    return new_slugs


def _add_if_missing(conn, primary_key, instance) -> bool:
    if conn.get(type(instance), primary_key) is not None:
        return False
    try:
        # The savepoint handles two requests that insert the same row.
        with conn.begin_nested():
            conn.add(instance)
            conn.flush()
    except IntegrityError:
        return False
    return True
