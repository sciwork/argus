import pytest

from argus.channels import (
    ChannelNotConfiguredError,
    InvalidChannelError,
    normalize,
    resolve_webhook_url,
)


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------


def test_normalize_upper():
    assert normalize("sprint") == "SPRINT"


def test_normalize_mixed_case():
    assert normalize("Sprint") == "SPRINT"


def test_normalize_already_upper():
    assert normalize("SPRINT") == "SPRINT"


def test_normalize_rejects_empty():
    with pytest.raises(InvalidChannelError):
        normalize("")


def test_normalize_rejects_special_chars():
    for bad in ("a-b", "a.b", "../x", "1abc"):
        with pytest.raises(InvalidChannelError):
            normalize(bad)


def test_normalize_rejects_too_long():
    # 33 upper-case chars (A + 32 more) exceeds {0,31} => total length 33 > 32
    with pytest.raises(InvalidChannelError):
        normalize("A" * 33)


def test_normalize_accepts_max_length():
    # exactly 32 chars is the maximum (A + 31 more)
    assert normalize("A" * 32) == "A" * 32


# ---------------------------------------------------------------------------
# resolve_webhook_url()
# ---------------------------------------------------------------------------


def test_resolve_webhook_url_hit(monkeypatch):
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_SPRINT", "https://discord.com/api/webhooks/test"
    )
    assert resolve_webhook_url("SPRINT") == "https://discord.com/api/webhooks/test"


def test_resolve_webhook_url_missing(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_SPRINT", raising=False)
    with pytest.raises(ChannelNotConfiguredError) as exc_info:
        resolve_webhook_url("SPRINT")
    assert exc_info.value.channel == "SPRINT"


def test_resolve_webhook_url_empty_string(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_SPRINT", "   ")
    with pytest.raises(ChannelNotConfiguredError):
        resolve_webhook_url("SPRINT")
