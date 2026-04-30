import os


# These env vars are read at import time by argus.config / argus.main.
# Set them BEFORE importing argus.* so the singletons are populated.
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")

import pytest  # noqa: E402

from argus.config import Settings  # noqa: E402
from argus.database import init_db  # noqa: E402
import argus.config  # noqa: E402


@pytest.fixture(autouse=True)
def use_tmp_db(tmp_path, monkeypatch):
    # Clear any DISCORD_WEBHOOK_* vars that may have leaked from other test modules.
    for k in list(os.environ):
        if k.startswith("DISCORD_WEBHOOK_"):
            monkeypatch.delenv(k, raising=False)

    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    new_settings = Settings(
        report_hour=argus.config.settings.report_hour,
        report_minute=argus.config.settings.report_minute,
        report_timezone=argus.config.settings.report_timezone,
        db_path=tmp_path / "test.db",
        healthcheck_db_timeout=argus.config.settings.healthcheck_db_timeout,
        kktix_organization=argus.config.settings.kktix_organization,
        allowed_emails=argus.config.settings.allowed_emails,
    )
    # Patching argus.config.settings is sufficient; all modules now read via
    # `config.settings.<x>` rather than holding a stale local reference.
    monkeypatch.setattr(argus.config, "settings", new_settings)

    init_db()
