import asyncio
import os
import sqlite3
import time

from fastapi.testclient import TestClient


os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

from argus.health import HealthResponse  # noqa: E402
from argus.main import app  # noqa: E402


client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")

    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert isinstance(body["checks"]["database"]["latency_ms"], float)
    assert body["checks"]["database"]["latency_ms"] >= 0
    assert body["checks"]["database"]["error"] is None
    assert body["version"]
    assert isinstance(body["version"], str)


def test_health_db_unreachable(monkeypatch):
    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr("argus.health.sqlite3.connect", _boom)

    resp = client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"]["ok"] is False
    assert body["checks"]["database"]["error"] is not None
    assert "unable to open database file" in body["checks"]["database"]["error"]


def test_health_response_schema_success():
    resp = client.get("/health")
    parsed = HealthResponse.model_validate(resp.json())
    assert parsed.status == "ok"
    assert "database" in parsed.checks


def test_health_response_schema_failure(monkeypatch):
    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("argus.health.sqlite3.connect", _boom)

    resp = client.get("/health")
    parsed = HealthResponse.model_validate(resp.json())
    assert parsed.status == "unhealthy"
    assert parsed.checks["database"].ok is False
    assert parsed.checks["database"].error is not None


def test_health_no_auth_required():
    # Send request with no headers at all — must NOT be blocked by WEBHOOK_SECRET
    resp = client.get("/health")
    assert resp.status_code == 200

    # Also try with a wrong secret header: should be ignored
    resp = client.get("/health", headers={"x-kktix-secret": "wrong"})
    assert resp.status_code == 200


def test_health_does_not_block(monkeypatch):
    # Make _check_database simulate a slow sync call; if handler uses
    # asyncio.to_thread, concurrent requests should overlap and total
    # wall time should be closer to one call than to N sequential calls.
    sleep_s = 0.2
    n = 3

    def slow_check():
        from argus.health import CheckResult

        time.sleep(sleep_s)
        return CheckResult(ok=True, latency_ms=sleep_s * 1000)

    monkeypatch.setattr("argus.health._check_database", slow_check)

    async def _run_all():
        import httpx

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as ac:
            start = time.perf_counter()
            results = await asyncio.gather(*[ac.get("/health") for _ in range(n)])
            elapsed = time.perf_counter() - start
            return results, elapsed

    results, elapsed = asyncio.run(_run_all())
    for r in results:
        assert r.status_code == 200
    # Should be closer to a single sleep than to n * sleep. Allow generous slack.
    assert elapsed < sleep_s * n, (
        f"Handler appears to block event loop: elapsed={elapsed:.3f}s, "
        f"sequential would be {sleep_s * n:.3f}s"
    )


def test_health_latency_is_numeric_and_rounded(monkeypatch):
    resp = client.get("/health")
    body = resp.json()
    latency = body["checks"]["database"]["latency_ms"]
    # round(_, 2) output should have at most 2 decimal places
    assert isinstance(latency, (int, float))
    # Confirm rounding to 2 decimal places
    assert round(latency, 2) == latency


def test_health_error_message_truncated(monkeypatch):
    long_msg = "x" * 500

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError(long_msg)

    monkeypatch.setattr("argus.health.sqlite3.connect", _boom)
    resp = client.get("/health")
    body = resp.json()
    err = body["checks"]["database"]["error"]
    assert err is not None
    assert len(err) <= 200
