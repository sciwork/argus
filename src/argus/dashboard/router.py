from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from argus import auth, config
from argus.dashboard import queries
from argus.kktix.report import send_report


_TEMPLATES_DIR = Path(__file__).parent / "templates"
_UTC = ZoneInfo("UTC")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _format_start_at_local(utc_iso: str | None) -> str | None:
    """Render a stored UTC ISO 8601 timestamp in the configured display timezone."""
    if not utc_iso:
        return None
    tz = ZoneInfo(config.settings.report_timezone)
    dt = datetime.fromisoformat(utc_iso).replace(tzinfo=_UTC).astimezone(tz)
    return dt.strftime(f"%Y-%m-%d %H:%M ({config.settings.report_timezone})")


def _session_email_or_redirect(request: Request) -> str | RedirectResponse:
    """Returns the authenticated email, or a RedirectResponse to /dashboard/login."""
    user = request.session.get("user")
    if not user or not user.get("email") or not auth.is_email_allowed(user["email"]):
        return RedirectResponse(
            url="/dashboard/login", status_code=status.HTTP_302_FOUND
        )
    return user["email"]


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard/login")
async def login(request: Request):
    redirect_uri = request.url_for("oauth_callback")
    return await auth.get_oauth().google.authorize_redirect(request, str(redirect_uri))


@router.get("/dashboard/oauth/callback", name="oauth_callback")
async def oauth_callback(request: Request):
    try:
        token = await auth.get_oauth().google.authorize_access_token(request)
    except Exception as e:
        logger.exception("oauth: token exchange failed")
        raise HTTPException(status_code=400, detail="oauth_exchange_failed") from e

    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="no_email_in_token")

    if not auth.is_email_allowed(email):
        logger.warning("oauth: rejected email %s", email)
        return HTMLResponse(
            "<h1>Access denied</h1>"
            "<p>This account is not authorized to view the dashboard.</p>",
            status_code=403,
        )

    request.session["user"] = {"email": email}
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/dashboard/login", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard")
async def dashboard_home(request: Request):
    result = _session_email_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"events": queries.list_events(), "user_email": result},
    )


@router.get("/dashboard/events/{slug}")
async def dashboard_event(slug: str, request: Request):
    result = _session_email_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result
    event = queries.get_event(slug)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return templates.TemplateResponse(
        request=request,
        name="event.html",
        context={
            "user_email": result,
            "slug": slug,
            "event_name": event["event_name"],
            "channel": event["channel"],
            "start_at": _format_start_at_local(event["start_at"]),
            "capacity": event["capacity"],
        },
    )


# ── JSON API ────────────────────────────────────────────────────────────────
# Protected by `Depends(auth.require_login)`. Returns 401 if not authenticated.


@router.get("/dashboard/api/events")
async def api_events(_email: str = Depends(auth.require_login)):
    return queries.list_events()


@router.get("/dashboard/api/events/{slug}/timeseries")
async def api_event_timeseries(slug: str, _email: str = Depends(auth.require_login)):
    result = queries.get_timeseries(slug)
    if result is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return result


@router.get("/dashboard/webhook-logs")
async def dashboard_webhook_logs(request: Request):
    result = _session_email_or_redirect(request)
    if isinstance(result, RedirectResponse):
        return result
    return templates.TemplateResponse(
        request=request,
        name="webhook_logs.html",
        context={
            "user_email": result,
            "total": queries.count_webhook_logs(),
        },
    )


@router.get("/dashboard/api/webhook-logs")
async def api_webhook_logs(
    limit: int = 100,
    offset: int = 0,
    _email: str = Depends(auth.require_login),
):
    # Cap limit defensively to avoid accidentally streaming huge tables.
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return {
        "items": queries.list_webhook_logs(limit=limit, offset=offset),
        "total": queries.count_webhook_logs(),
        "limit": limit,
        "offset": offset,
    }


@router.delete("/dashboard/api/webhook-logs/{log_id}")
async def api_delete_webhook_log(log_id: int, email: str = Depends(auth.require_login)):
    logger.info("Delete webhook log id=%s by %s", log_id, email)
    if not queries.delete_webhook_log(log_id):
        raise HTTPException(status_code=404, detail="webhook_log_not_found")
    return {"ok": True, "deleted_id": log_id}


@router.delete("/dashboard/api/webhook-logs")
async def api_clear_webhook_logs(email: str = Depends(auth.require_login)):
    deleted = queries.clear_webhook_logs()
    logger.info("Clear webhook_logs by %s: removed %s rows", email, deleted)
    return {"ok": True, "deleted_count": deleted}


@router.delete("/dashboard/api/events/{slug}")
async def api_delete_event(slug: str, email: str = Depends(auth.require_login)):
    """Delete an event and all of its tickets. Idempotent-ish: 404 if already gone."""
    logger.info("Manual event delete by %s: slug=%s", email, slug)
    deleted = queries.delete_event(slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="event_not_found")
    return {"ok": True, "deleted_slug": slug}


@router.post("/dashboard/api/report/trigger")
async def api_trigger_report(email: str = Depends(auth.require_login)):
    """Run the daily Discord report immediately, bypassing the scheduler.

    Per-channel failures are isolated inside `send_report` and logged there;
    this endpoint succeeds as long as the dispatch itself doesn't crash.
    """
    logger.info("Manual report trigger by %s", email)
    try:
        # send_report does sync SQLite + httpx work; offload to a thread so it
        # doesn't block the asyncio event loop.
        await asyncio.to_thread(send_report)
    except Exception as e:
        logger.exception("Manual report trigger failed")
        raise HTTPException(status_code=500, detail="report_failed") from e
    return {"ok": True, "message": "Report dispatched"}
