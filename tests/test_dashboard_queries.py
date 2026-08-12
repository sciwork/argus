from argus.dashboard import queries


def test_list_and_get_event(db):
    db.execute(
        """INSERT INTO events (event_slug, event_name, channel, start_at, capacity)
           VALUES (?, ?, ?, ?, ?)""",
        ("past", "Past Event", "OPS", "2026-06-01T02:00:00", 100),
    )
    db.execute(
        """INSERT INTO events (event_slug, event_name, channel, start_at, capacity)
           VALUES (?, ?, ?, ?, ?)""",
        ("future", "Future Event", "OPS", "2026-06-03T02:00:00", 200),
    )
    db.execute(
        """INSERT INTO events (event_slug, event_name, channel, start_at, capacity)
           VALUES (?, ?, ?, ?, ?)""",
        ("hidden", "Hidden Event", None, "2026-06-04T02:00:00", 300),
    )
    db.commit()

    assert queries.get_event("past") == {
        "event_slug": "past",
        "event_name": "Past Event",
        "channel": "OPS",
        "start_at": "2026-06-01T02:00:00",
        "capacity": 100,
    }
    assert queries.get_event("missing") is None
    assert [e["event_slug"] for e in queries.list_events()] == ["future", "past"]


def test_webhook_log_queries(db):
    db.execute(
        "INSERT INTO webhook_logs (method, channel, headers, body) VALUES (?, ?, ?, ?)",
        ("POST", "OPS", "{}", '{"ok": true}'),
    )
    db.execute(
        "INSERT INTO webhook_logs (method, channel, headers, body) VALUES (?, ?, ?, ?)",
        ("POST", "SALES", "{}", '{"ok": false}'),
    )
    db.commit()

    assert queries.count_webhook_logs() == 2
    logs = queries.list_webhook_logs(limit=1)
    assert len(logs) == 1
    assert logs[0]["channel"] == "SALES"

    assert queries.delete_webhook_log(logs[0]["id"]) is True
    assert queries.delete_webhook_log(logs[0]["id"]) is False
    assert queries.count_webhook_logs() == 1
    assert queries.clear_webhook_logs() == 1
    assert queries.count_webhook_logs() == 0


def test_delete_event_removes_tickets_atomically(db):
    db.execute(
        "INSERT INTO events (event_slug, event_name, channel) VALUES (?, ?, ?)",
        ("event-1", "Event One", "OPS"),
    )
    db.execute(
        """INSERT INTO tickets
           (ticket_id, ticket_name, event_slug, order_id, order_state)
           VALUES (?, ?, ?, ?, ?)""",
        (501, "General", "event-1", 1001, "activated"),
    )
    db.commit()

    assert queries.delete_event("missing") is False
    assert queries.delete_event("event-1") is True

    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0


def test_get_timeseries_counts_active_tickets_by_local_day(db):
    db.execute(
        """INSERT INTO events (event_slug, event_name, channel, start_at, capacity)
           VALUES (?, ?, ?, ?, ?)""",
        ("event-1", "Event One", "OPS", "2026-06-03T01:00:00", 100),
    )
    db.executemany(
        """INSERT INTO tickets
           (ticket_id, ticket_name, event_slug, order_id, order_state, paid_at,
            cancelled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                501,
                "General",
                "event-1",
                1001,
                "activated",
                "2026-06-01T02:00:00",
                None,
            ),
            (
                502,
                "VIP",
                "event-1",
                1002,
                "activated",
                "2026-06-02T02:00:00",
                None,
            ),
            (
                503,
                "General",
                "event-1",
                1003,
                "cancelled",
                "2026-06-01T03:00:00",
                "2026-06-01T12:00:00",
            ),
        ],
    )
    db.commit()

    result = queries.get_timeseries("event-1")

    assert result["event"]["event_slug"] == "event-1"
    assert result["labels"] == ["2026-06-01", "2026-06-02", "2026-06-03"]
    assert result["start_marker_label"] == "2026-06-03"
    assert result["datasets"] == [
        {"name": "Total", "data": [1, 2, 2]},
        {"name": "General", "data": [1, 1, 1]},
        {"name": "VIP", "data": [0, 1, 1]},
    ]


def test_get_timeseries_returns_empty_datasets_when_event_has_no_tickets(db):
    db.execute(
        "INSERT INTO events (event_slug, event_name, channel) VALUES (?, ?, ?)",
        ("event-1", "Event One", "OPS"),
    )
    db.commit()

    assert queries.get_timeseries("event-1") == {
        "event": {
            "event_slug": "event-1",
            "event_name": "Event One",
            "channel": "OPS",
            "start_at": None,
            "capacity": None,
        },
        "labels": [],
        "datasets": [],
        "start_marker_label": None,
    }
    assert queries.get_timeseries("missing") is None
