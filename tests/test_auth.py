from dataclasses import replace
from urllib.parse import urlsplit

from fastapi import FastAPI
from oidc_provider_mock import User, run_server_in_thread
from starlette.middleware.sessions import SessionMiddleware
import httpx
import pytest

from argus import auth, config
from argus.dashboard import router


@pytest.fixture
def dashboard_app(monkeypatch):
    """Create a dashboard app configured to allow Chester's email."""
    monkeypatch.setattr(
        config,
        "settings",
        replace(config.settings, allowed_emails=("chester@example.com",)),
    )
    monkeypatch.setattr(
        config,
        "secrets",
        config.Secrets("", "test-client-id", "test-client-secret", ""),
    )
    monkeypatch.setattr(router.queries, "list_events", lambda: [])

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-session-secret")
    app.include_router(router.router)
    return app


def test_is_email_allowed_matches_allowlist_case_insensitively(monkeypatch):
    """Allow Chester's configured dashboard email regardless of casing."""
    monkeypatch.setattr(
        config,
        "settings",
        replace(config.settings, allowed_emails=("Chester@Example.com",)),
    )

    assert auth.is_email_allowed("chester@example.com") is True
    assert auth.is_email_allowed("steve@example.com") is False
    assert auth.is_email_allowed("") is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "expected_status"),
    [("chester@example.com", 302), ("steve@example.com", 403)],
)
async def test_google_oauth_accepts_only_allowlisted_user(
    dashboard_app, monkeypatch, email, expected_status
):
    """Complete OAuth login with Chester allowed and Steve denied."""
    with run_server_in_thread(
        user_claims=[User(sub=email, claims={"email": email})]
    ) as server:
        provider_url = f"http://localhost:{server.server_port}"
        monkeypatch.setattr(
            auth,
            "_GOOGLE_SERVER_METADATA_URL",
            f"{provider_url}/.well-known/openid-configuration",
        )
        auth.reset_oauth()

        try:
            transport = httpx.ASGITransport(app=dashboard_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                login = await client.get("/dashboard/login", follow_redirects=False)

                # The OIDC mock runs on a loopback HTTP server, outside the ASGI app.
                async with httpx.AsyncClient() as provider_client:
                    authorized = await provider_client.post(
                        login.headers["location"], data={"sub": email}
                    )

                callback = urlsplit(authorized.headers["location"])
                response = await client.get(
                    f"{callback.path}?{callback.query}", follow_redirects=False
                )

                assert response.status_code == expected_status
                if expected_status == 302:
                    assert response.headers["location"] == "/dashboard"
                    assert (
                        await client.get("/dashboard/api/events")
                    ).status_code == 200
        finally:
            auth.reset_oauth()


@pytest.mark.asyncio
async def test_api_me_returns_authenticated_email(dashboard_app, monkeypatch):
    """The frontend can look up who is currently logged in via the session cookie."""
    email = "chester@example.com"
    with run_server_in_thread(
        user_claims=[User(sub=email, claims={"email": email})]
    ) as server:
        provider_url = f"http://localhost:{server.server_port}"
        monkeypatch.setattr(
            auth,
            "_GOOGLE_SERVER_METADATA_URL",
            f"{provider_url}/.well-known/openid-configuration",
        )
        auth.reset_oauth()

        try:
            transport = httpx.ASGITransport(app=dashboard_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                unauthenticated = await client.get("/dashboard/api/me")
                assert unauthenticated.status_code == 401

                login = await client.get("/dashboard/login", follow_redirects=False)

                # The OIDC mock runs on a loopback HTTP server, outside the ASGI app.
                async with httpx.AsyncClient() as provider_client:
                    authorized = await provider_client.post(
                        login.headers["location"], data={"sub": email}
                    )

                callback = urlsplit(authorized.headers["location"])
                await client.get(
                    f"{callback.path}?{callback.query}", follow_redirects=False
                )

                me = await client.get("/dashboard/api/me")
                assert me.status_code == 200
                assert me.json() == {"email": email}
        finally:
            auth.reset_oauth()
