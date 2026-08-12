from typing import Literal
import asyncio
import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from argus import __version__, config
from argus.database import create_db_engine


logger = logging.getLogger(__name__)

router = APIRouter()


class CheckResult(BaseModel):
    """Result of one health check."""

    ok: bool
    latency_ms: float
    error: str | None = None


class HealthResponse(BaseModel):
    """Response body for the health endpoint."""

    status: Literal["ok", "unhealthy"]
    version: str
    checks: dict[str, CheckResult]


def _check_database() -> CheckResult:
    """Check that the configured database accepts a simple query."""
    start = time.perf_counter()
    engine = None
    try:
        engine = create_db_engine(
            config.settings.database_url,
            connect_timeout=config.settings.healthcheck_db_timeout,
        )
        with engine.connect() as conn:
            conn.execute(select(1)).scalar()
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(ok=True, latency_ms=round(latency_ms, 2))
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=str(e)[:200],
        )
    finally:
        if engine is not None:
            engine.dispose()


@router.get("/health")
async def health() -> JSONResponse:
    """Return application and database health."""
    db_check = await asyncio.to_thread(_check_database)

    checks: dict[str, CheckResult] = {"database": db_check}
    all_ok = all(c.ok for c in checks.values())
    status: Literal["ok", "unhealthy"] = "ok" if all_ok else "unhealthy"

    response = HealthResponse(
        status=status,
        version=__version__,
        checks=checks,
    )

    if not all_ok:
        for name, result in checks.items():
            if not result.ok:
                logger.warning("Health check failed: %s: %s", name, result.error)

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content=response.model_dump(),
    )
