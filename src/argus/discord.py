import logging

import httpx


logger = logging.getLogger(__name__)


def post(
    url: str, content: str | None = None, embeds: list[dict] | None = None
) -> bool:
    """POST a message payload to a Discord webhook URL.

    Returns True on success (2xx), False otherwise (logs status + body).
    Caller decides how to react to failure.
    """
    payload: dict = {}
    if content is not None:
        payload["content"] = content
    if embeds is not None:
        payload["embeds"] = embeds

    with httpx.Client() as client:
        resp = client.post(url, json=payload)

    if not resp.is_success:
        logger.error(
            "discord: %s returned %s: %s",
            url,
            resp.status_code,
            resp.text[:500],
        )
        return False
    return True
