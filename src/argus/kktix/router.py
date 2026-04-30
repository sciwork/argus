import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from argus import config
from argus.channels import (
    ChannelNotConfiguredError,
    InvalidChannelError,
    normalize,
    resolve_webhook_url,
)
from argus.database import get_conn
from argus.kktix.handler import handle_notification
from argus.kktix.scraper import enrich_event


logger = logging.getLogger(__name__)
router = APIRouter()

# Headers redacted from webhook_logs to avoid persisting secrets/PII.
# Comparison is case-insensitive.
_SENSITIVE_HEADERS = frozenset(
    {
        "x-kktix-secret",
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
    }
)


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        k: ("***" if k.lower() in _SENSITIVE_HEADERS else v) for k, v in headers.items()
    }


def _redact_body_pii(body: dict) -> dict:
    """Redact contact PII (name/email/mobile) before persisting to webhook_logs.

    The contact details are still written to `tickets` (where they are needed
    for cancellation lookups). The webhook log only needs the structural shape
    for debugging delivery problems, not the personal data.
    """
    if not isinstance(body, dict):
        return body
    redacted = json.loads(json.dumps(body))  # deep copy
    for notification in redacted.get("notifications", []) or []:
        if isinstance(notification, dict) and "contact" in notification:
            contact = notification["contact"]
            if isinstance(contact, dict):
                for key in ("name", "email", "mobile"):
                    if key in contact and contact[key]:
                        contact[key] = "***"
    return redacted


def _verify_secret(x_kktix_secret: str | None) -> None:
    expected = config.secrets.require_webhook_secret()
    # Use constant-time comparison to prevent timing attacks that could
    # allow an attacker to infer the secret one character at a time.
    if x_kktix_secret is None or not hmac.compare_digest(x_kktix_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/webhook/kktix/{channel}")
async def receive_kktix_webhook(
    channel: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_kktix_secret: str | None = Header(default=None),
):
    body = await request.json()
    headers = _redact_headers(dict(request.headers))

    # Pre-validate channel to decide whether to store normalized name in log.
    try:
        normalized = normalize(channel)
    except InvalidChannelError:
        normalized = None  # still log request, with channel = NULL

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO webhook_logs (method, channel, headers, body) VALUES (?, ?, ?, ?)",
            (
                request.method,
                normalized,
                json.dumps(headers),
                json.dumps(_redact_body_pii(body)),
            ),
        )

    if normalized is None:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "invalid_channel"},
        )

    _verify_secret(x_kktix_secret)

    try:
        resolve_webhook_url(normalized)  # ensures channel is configured
    except ChannelNotConfiguredError:
        logger.error("channel_not_configured: %s", normalized)
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "channel_not_configured",
                "channel": normalized,
            },
        )

    for notification in body.get("notifications", []):
        for slug in handle_notification(notification, channel=normalized):
            background_tasks.add_task(enrich_event, slug)

    return {"ok": True}
