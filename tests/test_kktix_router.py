import json

from fastapi import FastAPI
from sqlalchemy import select
import httpx
import pytest

from argus import config
from argus.database import WebhookLog
from argus.kktix import router


@pytest.fixture
def webhook_app():
    """Create an app exposing only the KKTIX webhook router."""
    app = FastAPI()
    app.include_router(router.router)
    return app


async def _post_webhook(app, channel, payload, headers=None):
    """Post a JSON webhook request without starting the production lifespan."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            f"/webhook/kktix/{channel}", json=payload, headers=headers
        )


def _payload():
    """Return one representative KKTIX notification payload."""
    return {
        "notifications": [
            {
                "type": "order_activated_paid",
                "event": {"slug": "event-1", "name": "Event One"},
                "order": {"id": 1001, "paid_at": "2026-08-12T09:00:00+08:00"},
                "contact": {
                    "name": "Ada",
                    "email": "ada@example.com",
                    "mobile": "12345678",
                },
                "tickets": [{"id": 501, "name": "General"}],
            }
        ]
    }


@pytest.mark.asyncio
async def test_webhook_logs_redacted_request_and_enriches_new_event(
    webhook_app, session, monkeypatch
):
    monkeypatch.setattr(config, "secrets", config.Secrets("shared-secret", "", "", ""))
    monkeypatch.setenv("DISCORD_WEBHOOK_OPS", "https://example.com/webhook")
    handled = []
    enriched = []

    def fake_handle_notification(notification, channel):
        handled.append((notification, channel))
        return ["event-1"]

    async def fake_enrich_event(slug):
        enriched.append(slug)

    monkeypatch.setattr(router, "handle_notification", fake_handle_notification)
    monkeypatch.setattr(router, "enrich_event", fake_enrich_event)
    payload = _payload()

    response = await _post_webhook(
        webhook_app,
        "ops",
        payload,
        headers={"X-KKTIX-Secret": "shared-secret", "Authorization": "Bearer token"},
    )

    assert response.json() == {"ok": True}
    assert handled == [(payload["notifications"][0], "OPS")]
    assert enriched == ["event-1"]
    log = session.scalar(select(WebhookLog))
    assert log is not None
    assert log.method == "POST"
    assert log.channel == "OPS"
    headers = json.loads(log.headers)
    assert headers["authorization"] == "***"
    assert headers["x-kktix-secret"] == "***"
    contact = json.loads(log.body)["notifications"][0]["contact"]
    assert contact == {"name": "***", "email": "***", "mobile": "***"}


@pytest.mark.asyncio
async def test_webhook_logs_invalid_channel_before_rejecting(webhook_app, session):
    response = await _post_webhook(webhook_app, "invalid-channel", _payload())

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_channel"}
    log = session.scalar(select(WebhookLog))
    assert log is not None
    assert log.channel is None


@pytest.mark.asyncio
async def test_webhook_logs_request_before_rejecting_invalid_secret(
    webhook_app, session, monkeypatch
):
    monkeypatch.setattr(config, "secrets", config.Secrets("shared-secret", "", "", ""))

    response = await _post_webhook(webhook_app, "ops", _payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    log = session.scalar(select(WebhookLog))
    assert log is not None
    assert log.channel == "OPS"


@pytest.mark.asyncio
async def test_webhook_rejects_unconfigured_channel_after_logging(
    webhook_app, session, monkeypatch
):
    monkeypatch.setattr(config, "secrets", config.Secrets("shared-secret", "", "", ""))
    monkeypatch.delenv("DISCORD_WEBHOOK_OPS", raising=False)

    response = await _post_webhook(
        webhook_app,
        "ops",
        _payload(),
        headers={"X-KKTIX-Secret": "shared-secret"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "ok": False,
        "error": "channel_not_configured",
        "channel": "OPS",
    }
    log = session.scalar(select(WebhookLog))
    assert log is not None
    assert log.channel == "OPS"
