from contextlib import contextmanager
import sqlite3

from argus import config


_CREATE_TABLES_SQL = """
    CREATE TABLE IF NOT EXISTS events (
        event_slug       TEXT PRIMARY KEY,
        event_name       TEXT NOT NULL,
        channel          TEXT,
        start_at         TEXT,
        capacity         INTEGER,
        created_at       TEXT NOT NULL DEFAULT (datetime('now')),
        last_reported_at TEXT
    );

    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id     INTEGER PRIMARY KEY,
        ticket_name   TEXT NOT NULL,
        event_slug    TEXT NOT NULL REFERENCES events(event_slug),
        order_id      INTEGER NOT NULL,
        order_state   TEXT NOT NULL,
        contact_name  TEXT,
        contact_email TEXT,
        paid_at       TEXT,
        cancelled_at  TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_tickets_event_slug
        ON tickets (event_slug);
    CREATE INDEX IF NOT EXISTS idx_tickets_order_id
        ON tickets (order_id);
    CREATE INDEX IF NOT EXISTS idx_tickets_ticket_name
        ON tickets (ticket_name);

    CREATE TABLE IF NOT EXISTS webhook_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        method     TEXT NOT NULL,
        channel    TEXT,
        headers    TEXT NOT NULL,
        body       TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_CREATE_TABLES_SQL)


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
