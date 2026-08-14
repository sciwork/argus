from dataclasses import replace
import json
import logging

import pytest

from argus import config, database, health


def test_create_db_engine_rounds_postgresql_connect_timeout(monkeypatch):
    """Configure PostgreSQL's integer timeout without opening a connection."""
    captured = {}

    def fake_create_engine(database_url, **kwargs):
        captured["database_url"] = database_url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    database.create_db_engine("postgresql+psycopg://user:pass@db/argus", 1.2)

    assert captured == {
        "database_url": "postgresql+psycopg://user:pass@db/argus",
        "connect_args": {"connect_timeout": 2},
    }


def test_check_database_succeeds_with_sqlite_url(tmp_path, monkeypatch):
    """Connect to the configured SQLAlchemy SQLite database."""
    monkeypatch.setattr(
        config,
        "settings",
        replace(config.settings, database_url=f"sqlite:///{tmp_path / 'health.db'}"),
    )

    result = health._check_database()

    assert result.ok is True
    assert result.latency_ms >= 0
    assert result.error is None


def test_check_database_reports_engine_creation_errors(monkeypatch):
    """Return an unhealthy result when an engine cannot be created."""

    def raise_connection_error(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health, "create_db_engine", raise_connection_error)

    result = health._check_database()

    assert result.ok is False
    assert result.latency_ms >= 0
    assert result.error == "database unavailable"


@pytest.mark.asyncio
async def test_health_returns_ok_for_healthy_database(monkeypatch):
    """Expose a successful database check through the health endpoint."""
    monkeypatch.setattr(
        health,
        "_check_database",
        lambda: health.CheckResult(ok=True, latency_ms=1.25),
    )

    response = await health.health()

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "ok",
        "version": health.__version__,
        "checks": {"database": {"ok": True, "latency_ms": 1.25, "error": None}},
    }


@pytest.mark.asyncio
async def test_health_returns_unhealthy_and_logs_database_error(monkeypatch, caplog):
    """Expose and log a failed database check through the health endpoint."""
    monkeypatch.setattr(
        health,
        "_check_database",
        lambda: health.CheckResult(
            ok=False, latency_ms=1.25, error="database unavailable"
        ),
    )

    with caplog.at_level(logging.WARNING, logger=health.__name__):
        response = await health.health()

    assert response.status_code == 503
    assert json.loads(response.body)["status"] == "unhealthy"
    assert "Health check failed: database: database unavailable" in caplog.messages
