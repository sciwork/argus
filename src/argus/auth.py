from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request, status

from argus import config


# Module-level OAuth instance, lazily configured
_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    """Lazy init so tests can run without the env vars set."""
    global _oauth
    if _oauth is None:
        oauth = OAuth()
        oauth.register(
            name="google",
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id=config.secrets.require_google_oauth_client_id(),
            client_secret=config.secrets.require_google_oauth_client_secret(),
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth


def reset_oauth() -> None:
    """For tests."""
    global _oauth
    _oauth = None


def is_email_allowed(email: str) -> bool:
    if not email:
        return False
    return email.lower() in {e.lower() for e in config.settings.allowed_emails}


async def require_login(request: Request) -> str:
    """FastAPI dependency for API routes. Returns email; raises 401 if not authed."""
    user = request.session.get("user")
    if not user or not user.get("email") or not is_email_allowed(user["email"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="login_required"
        )
    return user["email"]
