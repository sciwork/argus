from typing import Literal
import asyncio
import logging
import sqlite3
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from argus import __version__, config


logger = logging.getLogger(__name__)

router = APIRouter()


class CheckResult(BaseModel):
    ok: bool
    latency_ms: float
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "unhealthy"]
    version: str
    checks: dict[str, CheckResult]


def _check_database() -> CheckResult:
    start = time.perf_counter()
    try:
        with sqlite3.connect(
            config.settings.db_path,
            timeout=config.settings.healthcheck_db_timeout,
        ) as conn:
            conn.execute("SELECT 1;").fetchone()
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(ok=True, latency_ms=round(latency_ms, 2))
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return CheckResult(
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=str(e)[:200],
        )


@router.get("/health")
async def health() -> JSONResponse:
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
