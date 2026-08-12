import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from argus import database


@pytest.fixture
def db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(database, "_SessionLocal", session_local)

    database.init_db()
    raw_conn = engine.raw_connection()
    driver_conn = raw_conn.driver_connection
    assert isinstance(driver_conn, sqlite3.Connection)
    driver_conn.row_factory = sqlite3.Row
    try:
        yield driver_conn
    finally:
        raw_conn.close()


@pytest.fixture
def session(db):
    """Provide an ORM session backed by the isolated test database."""
    del db
    session_local = database._SessionLocal
    assert session_local is not None
    session = session_local()
    try:
        yield session
    finally:
        session.close()
