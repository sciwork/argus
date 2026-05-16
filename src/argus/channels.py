import os
import re


CHANNEL_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
ENV_PREFIX = "DISCORD_WEBHOOK_"


class InvalidChannelError(ValueError):
    """Channel name does not match the allowed pattern."""


class ChannelNotConfiguredError(RuntimeError):
    def __init__(self, channel: str) -> None:
        super().__init__(f"channel not configured: {channel}")
        self.channel = channel


def normalize(channel: str) -> str:
    """Upper-case and validate; raises InvalidChannelError on bad input."""
    up = channel.upper()
    if not CHANNEL_RE.match(up):
        raise InvalidChannelError(channel)
    return up


def resolve_webhook_url(channel: str) -> str:
    """Return Discord webhook URL for channel, or raise ChannelNotConfiguredError.

    Caller should pre-normalize; this function accepts either form and
    normalizes internally for safety.
    """
    up = normalize(channel)
    url = os.getenv(f"{ENV_PREFIX}{up}", "").strip()
    if not url:
        raise ChannelNotConfiguredError(up)
    return url
