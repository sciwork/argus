from sqlalchemy import select

from argus.database import Event, Ticket
from argus.kktix.handler import handle_notification


def test_paid_notification_inserts_event_and_tickets_once(session):
    notification = {
        "type": "order_activated_paid",
        "event": {"slug": "event-1", "name": "Event One"},
        "order": {"id": 1001, "paid_at": "2026-06-01T10:00:00+08:00"},
        "contact": {"name": "Ada", "email": "ada@example.com"},
        "tickets": [
            {"id": 501, "name": "General"},
            {"id": 502, "name": "VIP"},
        ],
    }

    assert handle_notification(notification, channel="OPS") == ["event-1"]
    assert handle_notification(notification, channel="OPS") == []

    event = session.get(Event, "event-1")
    assert event is not None
    assert (event.event_slug, event.event_name, event.channel) == (
        "event-1",
        "Event One",
        "OPS",
    )

    tickets = session.scalars(select(Ticket).order_by(Ticket.ticket_id)).all()
    assert [
        (
            ticket.ticket_id,
            ticket.ticket_name,
            ticket.event_slug,
            ticket.order_id,
            ticket.order_state,
            ticket.contact_name,
            ticket.contact_email,
            ticket.paid_at,
        )
        for ticket in tickets
    ] == [
        (
            501,
            "General",
            "event-1",
            1001,
            "activated",
            "Ada",
            "ada@example.com",
            "2026-06-01T02:00:00",
        ),
        (
            502,
            "VIP",
            "event-1",
            1001,
            "activated",
            "Ada",
            "ada@example.com",
            "2026-06-01T02:00:00",
        ),
    ]


def test_cancelled_notification_marks_order_tickets_cancelled(session):
    paid_notification = {
        "type": "order_activated_paid",
        "event": {"slug": "event-1", "name": "Event One"},
        "order": {"id": 1001, "paid_at": "2026-06-01T10:00:00+08:00"},
        "contact": {},
        "tickets": [{"id": 501, "name": "General"}],
    }
    cancel_notification = {
        "type": "order_cancelled",
        "event": {"slug": "event-1", "name": "Event One"},
        "order": {"id": 1001, "cancelled_at": "2026-06-02T12:30:00+08:00"},
    }

    handle_notification(paid_notification, channel="OPS")
    assert handle_notification(cancel_notification, channel="OPS") == []

    ticket = session.get(Ticket, 501)
    assert ticket is not None
    assert (ticket.order_state, ticket.cancelled_at) == (
        "cancelled",
        "2026-06-02T04:30:00",
    )
