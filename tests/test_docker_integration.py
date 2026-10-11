from base64 import b64encode
from collections.abc import Iterator
import json
import os
import socket
import subprocess
import time

from itsdangerous import TimestampSigner
import httpx
import pytest


_SESSION_SECRET = "docker-integration-session-secret"
_WEBHOOK_SECRET = "docker-integration-webhook-secret"
_EMAIL = "integration@example.com"
_APP_ENV = {
    "SESSION_SECRET": _SESSION_SECRET,
    "WEBHOOK_SECRET": _WEBHOOK_SECRET,
    "DISCORD_WEBHOOK_SMOKE": "https://example.com/discord-webhook",
    "ALLOWED_EMAILS": _EMAIL,
    "KKTIX_ORGANIZATION": "",
}
_WEBHOOK_BODY = {
    "notifications": [
        {
            "type": "order_activated_paid",
            "event": {"slug": "smoke-event", "name": "Smoke Event"},
            "order": {"id": 1001, "paid_at": "2026-08-12T10:00:00+08:00"},
            "contact": {
                "name": "Smoke User",
                "email": "smoke@example.com",
            },
            "tickets": [{"id": 501, "name": "General"}],
        }
    ]
}


@pytest.fixture(scope="module")
def argus_image() -> Iterator[str]:
    """Build a clean image and remove it after this module."""
    image = f"argus-integration:{os.getpid()}"
    # Always test a clean image from the current files.
    _run(["docker", "build", "--no-cache", "--tag", image, "."], timeout=300)
    yield image
    _run(["docker", "image", "rm", "--force", image], check=False)


@pytest.fixture(params=["sqlite", "postgresql"])
def api_url(request, argus_image: str) -> Iterator[str]:
    """Start Argus with each supported database and return its URL."""
    database = request.param
    suffix = f"{database}-{os.getpid()}"
    network = f"argus-integration-{suffix}"
    app = f"argus-app-{suffix}"
    db = f"argus-db-{suffix}"
    port = _get_free_port()

    _run(["docker", "network", "create", network])
    try:
        database_url = "sqlite:////data/argus.db"
        if database == "postgresql":
            _start_postgresql(db, network)
            database_url = "postgresql+psycopg://argus:argus@db:5432/argus"

        _run(_app_command(app, network, port, database_url, argus_image))
        base_url = f"http://127.0.0.1:{port}"
        _wait_until_healthy(base_url, app)
        yield base_url
    finally:
        _run(["docker", "rm", "--force", app, db], check=False)
        _run(["docker", "network", "rm", network], check=False)


def test_docker_image_api_flow(api_url: str) -> None:
    """Verify webhook and dashboard APIs through the built image."""
    with httpx.Client(
        base_url=api_url,
        cookies={"session": _session_cookie(_EMAIL)},
        timeout=5,
    ) as client:
        for _ in range(2):
            webhook = client.post(
                "/webhook/kktix/smoke",
                headers={"x-kktix-secret": _WEBHOOK_SECRET},
                json=_WEBHOOK_BODY,
            )
            assert webhook.status_code == 200
            assert webhook.json() == {"ok": True}

        events = client.get("/dashboard/api/events")
        assert events.status_code == 200
        assert events.json()[0]["event_slug"] == "smoke-event"

        timeseries = client.get("/dashboard/api/events/smoke-event/timeseries")
        assert timeseries.status_code == 200
        datasets = timeseries.json()["datasets"]
        assert [dataset["name"] for dataset in datasets] == ["Total", "General"]
        assert all(dataset["data"] for dataset in datasets)
        assert all(count == 1 for dataset in datasets for count in dataset["data"])

        logs = client.get("/dashboard/api/webhook-logs")
        assert logs.status_code == 200
        assert logs.json()["total"] == 2
        assert "smoke@example.com" not in logs.json()["items"][0]["body"]

        deleted = client.delete("/dashboard/api/events/smoke-event")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True, "deleted_slug": "smoke-event"}
        assert client.get("/dashboard/api/events").json() == []


def test_docker_image_serves_frontend_shell(api_url: str) -> None:
    """The built static frontend is served at /dashboard, same-origin.

    `/dashboard` (no trailing slash) 307-redirects to `/dashboard/` — that's
    Starlette's standard `redirect_slashes` behavior for a mount whose static
    export uses Next's `trailingSlash: true`, and any browser follows it
    transparently, so the client here does too.
    """
    with httpx.Client(base_url=api_url, timeout=5, follow_redirects=True) as client:
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def test_docker_image_serves_event_detail_page(api_url: str) -> None:
    """The event-detail page (query-string based) is served at /dashboard/events.

    Unlike `/dashboard` itself, `/dashboard/events` (no trailing slash)
    307-redirects to `/dashboard/events/` via `StaticFiles`' own
    directory-index redirect behavior — it resolves "events" to a directory
    within the mount and redirects to add the trailing slash before serving
    its `index.html`. This is a related but distinct mechanism from `Mount`'s
    `redirect_slashes`, which only applies to the bare mount path itself. The
    client here follows the redirect just as a browser would.
    """
    with httpx.Client(base_url=api_url, timeout=5, follow_redirects=True) as client:
        response = client.get("/dashboard/events", params={"slug": "anything"})
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def test_docker_image_serves_webhook_logs_page(api_url: str) -> None:
    """The webhook-logs page is served at /dashboard/webhook-logs.

    Unlike `/dashboard` itself, `/dashboard/webhook-logs` (no trailing slash)
    307-redirects to `/dashboard/webhook-logs/` via `StaticFiles`' own
    directory-index redirect behavior — it resolves "webhook-logs" to a
    directory within the mount and redirects to add the trailing slash
    before serving its `index.html`. This is a related but distinct
    mechanism from `Mount`'s `redirect_slashes`, which only applies to the
    bare mount path itself. The client here follows the redirect just as a
    browser would.
    """
    with httpx.Client(base_url=api_url, timeout=5, follow_redirects=True) as client:
        response = client.get("/dashboard/webhook-logs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


def _start_postgresql(container: str, network: str) -> None:
    _run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            container,
            "--network",
            network,
            "--network-alias",
            "db",
            "--env",
            "POSTGRES_DB=argus",
            "--env",
            "POSTGRES_USER=argus",
            "--env",
            "POSTGRES_PASSWORD=argus",
            "--health-cmd",
            "pg_isready -U argus -d argus",
            "--health-interval",
            "1s",
            "--health-timeout",
            "5s",
            "--health-retries",
            "30",
            "postgres:17-alpine",
        ]
    )
    _wait_for_container_health(container)


def _app_command(
    container: str,
    network: str,
    port: int,
    database_url: str,
    image: str,
) -> list[str]:
    command = [
        "docker",
        "run",
        "--detach",
        "--name",
        container,
        "--network",
        network,
        "--publish",
        f"{port}:8000",
        "--tmpfs",
        "/data",
        "--env",
        f"DATABASE_URL={database_url}",
    ]
    for key, value in _APP_ENV.items():
        command.extend(["--env", f"{key}={value}"])
    return [*command, image]


def _session_cookie(email: str) -> str:
    data = b64encode(json.dumps({"user": {"email": email}}).encode("utf-8"))
    return TimestampSigner(_SESSION_SECRET).sign(data).decode("utf-8")


def _get_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_healthy(base_url: str, container: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=1)
            if response.status_code == 200:
                assert response.json()["checks"]["database"]["ok"] is True
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    pytest.fail(f"Argus did not become healthy:\n{_container_logs(container)}")


def _wait_for_container_health(container: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = _run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container]
        )
        if result.stdout.strip() == "healthy":
            return
        time.sleep(0.25)
    pytest.fail(f"PostgreSQL did not become healthy:\n{_container_logs(container)}")


def _container_logs(container: str) -> str:
    result = _run(["docker", "logs", container], check=False)
    return result.stdout + result.stderr


def _run(
    command: list[str],
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        pytest.fail(
            f"command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


"""End-to-end API tests for the clean Docker image."""
