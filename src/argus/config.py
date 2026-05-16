from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True, slots=True)
class Settings:
    report_hour: int
    report_minute: int
    report_timezone: str
    db_path: Path
    healthcheck_db_timeout: float
    kktix_organization: str
    allowed_emails: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            report_hour=int(os.getenv("REPORT_HOUR", "9")),
            report_minute=int(os.getenv("REPORT_MINUTE", "0")),
            report_timezone=os.getenv("REPORT_TIMEZONE", "Asia/Taipei"),
            db_path=Path(os.getenv("DB_PATH", "argus.db")),
            healthcheck_db_timeout=float(os.getenv("HEALTHCHECK_DB_TIMEOUT", "1.0")),
            kktix_organization=os.getenv("KKTIX_ORGANIZATION", ""),
            allowed_emails=tuple(
                e.strip()
                for e in os.getenv("ALLOWED_EMAILS", "").split(",")
                if e.strip()
            ),
        )


@dataclass(frozen=True, slots=True)
class Secrets:
    webhook_secret: str
    google_oauth_client_id: str
    google_oauth_client_secret: str
    session_secret: str

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            google_oauth_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            google_oauth_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            session_secret=os.getenv("SESSION_SECRET", ""),
        )

    def __repr__(self) -> str:
        return (
            "Secrets(webhook_secret=***, google_oauth_client_id=***, "
            "google_oauth_client_secret=***, session_secret=***)"
        )

    def require_webhook_secret(self) -> str:
        if not self.webhook_secret:
            raise RuntimeError("WEBHOOK_SECRET env var is not set")
        return self.webhook_secret

    def require_google_oauth_client_id(self) -> str:
        if not self.google_oauth_client_id:
            raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID env var is not set")
        return self.google_oauth_client_id

    def require_google_oauth_client_secret(self) -> str:
        if not self.google_oauth_client_secret:
            raise RuntimeError("GOOGLE_OAUTH_CLIENT_SECRET env var is not set")
        return self.google_oauth_client_secret

    def require_session_secret(self) -> str:
        if not self.session_secret:
            raise RuntimeError("SESSION_SECRET env var is not set")
        return self.session_secret


settings = Settings.from_env()
secrets = Secrets.from_env()


def reload() -> None:
    global settings, secrets
    settings = Settings.from_env()
    secrets = Secrets.from_env()
