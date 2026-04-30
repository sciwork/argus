from datetime import UTC, datetime


_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def to_utc(value: str | None) -> str | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(tzinfo=None, microsecond=0).strftime(_ISO_FORMAT)


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0).strftime(_ISO_FORMAT)
