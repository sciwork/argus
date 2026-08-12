"""Database models, engine setup, and transaction handling."""

from collections.abc import Iterator
from contextlib import contextmanager
import math

from sqlalchemy import ForeignKey, Integer, String, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from argus import config


class Base(DeclarativeBase):
    """Base class for database models."""

    pass


class Event(Base):
    """KKTIX event stored by its slug."""

    __tablename__ = "events"

    event_slug: Mapped[str] = mapped_column(String, primary_key=True)
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str | None] = mapped_column(String)
    start_at: Mapped[str | None] = mapped_column(String)
    capacity: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("CAST(CURRENT_TIMESTAMP AS VARCHAR)"),
    )
    last_reported_at: Mapped[str | None] = mapped_column(String)


class Ticket(Base):
    """Ticket received from a KKTIX order notification."""

    __tablename__ = "tickets"

    ticket_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_slug: Mapped[str] = mapped_column(
        ForeignKey("events.event_slug"), nullable=False, index=True
    )
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    order_state: Mapped[str] = mapped_column(String, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String)
    contact_email: Mapped[str | None] = mapped_column(String)
    paid_at: Mapped[str | None] = mapped_column(String)
    cancelled_at: Mapped[str | None] = mapped_column(String)


class WebhookLog(Base):
    """Redacted record of an incoming webhook request."""

    __tablename__ = "webhook_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str | None] = mapped_column(String)
    headers: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("CAST(CURRENT_TIMESTAMP AS VARCHAR)"),
    )


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def create_db_engine(database_url: str, connect_timeout: float | None = None) -> Engine:
    """Create a SQLAlchemy engine for a supported database.

    Args:
        database_url: SQLAlchemy database URL.
        connect_timeout: Optional connection timeout in seconds.

    Returns:
        A configured SQLAlchemy engine.
    """
    connect_args = {}
    if connect_timeout is not None:
        backend = make_url(database_url).get_backend_name()
        if backend == "sqlite":
            connect_args["timeout"] = connect_timeout
        elif backend == "postgresql":
            connect_args["connect_timeout"] = max(1, math.ceil(connect_timeout))
    return create_engine(database_url, connect_args=connect_args)


def _get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_db_engine(config.settings.database_url)
        _SessionLocal = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """Create all missing database tables and indexes."""
    Base.metadata.create_all(_get_engine())


@contextmanager
def get_conn() -> Iterator[Session]:
    """Provide a database session with commit and rollback handling.

    Yields:
        A SQLAlchemy session.
    """
    if _SessionLocal is None:
        _get_engine()
    session_local = _SessionLocal
    assert session_local is not None
    conn = session_local()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
