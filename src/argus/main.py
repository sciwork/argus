from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from argus import config
from argus.dashboard.router import router as dashboard_router
from argus.database import init_db
from argus.health import router as health_router
from argus.kktix.router import router as kktix_router
from argus.scheduler import start_scheduler


logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s:%(name)s:%(message)s",
    )


_configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Argus",
    description="KKTIX webhook receiver with daily Discord reports and analytics dashboard",
    lifespan=lifespan,
)

# Session middleware is global (cookies are I/O only); auth enforcement happens
# per-route via argus.auth.require_login or in-route session checks.
# SESSION_SECRET must be explicitly set — there is no fallback because a known
# fallback key would let anyone forge dashboard sessions. Tests set this via
# fixture; deploys must set it via env. See README → Dashboard.
_session_secret = config.secrets.require_session_secret()

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    same_site="lax",
    https_only=os.getenv("ARGUS_HTTPS_ONLY", "0") == "1",
)

app.include_router(kktix_router)
app.include_router(dashboard_router)
app.include_router(health_router)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)
