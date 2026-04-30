# Argus

KKTIX webhook receiver with daily Discord reports and a Google-OAuth-protected dashboard for visualizing registration trends.

## Installation

```bash
pip install git+https://github.com/yourname/argus.git
```

## Environment Variables

### Secrets

| Variable | Required | Description |
|----------|----------|-------------|
| `WEBHOOK_SECRET` | Yes | KKTIX auth header value |
| `DISCORD_WEBHOOK_<CHANNEL>` | Yes (≥1) | Discord webhook URL per channel, e.g. `DISCORD_WEBHOOK_SPRINT` |
| `GOOGLE_OAUTH_CLIENT_ID` | Yes | Google OAuth 2.0 client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes | Google OAuth 2.0 client secret |
| `SESSION_SECRET` | Yes | Random ≥32-byte hex string for signing session cookies |

### Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `KKTIX_ORGANIZATION` | — | KKTIX organizer subdomain, e.g. `example` for `example.kktix.cc`; required to auto-fetch event start time and capacity |
| `REPORT_HOUR` | `9` | Report hour |
| `REPORT_MINUTE` | `0` | Report minute |
| `REPORT_TIMEZONE` | `Asia/Taipei` | Report timezone |
| `DB_PATH` | `argus.db` | SQLite database path |
| `HEALTHCHECK_DB_TIMEOUT` | `1.0` | `/health` endpoint DB connect timeout in seconds |
| `LOG_LEVEL` | `INFO` | Python application log level |
| `ALLOWED_EMAILS` | — | Comma-separated email allowlist for dashboard access |
| `ARGUS_HTTPS_ONLY` | `0` | Set to `1` to mark session cookies as Secure |

## Usage

```bash
argus
```

## KKTIX Webhook Setup

Configure one endpoint per channel. The channel name (case-insensitive) maps to a `DISCORD_WEBHOOK_<CHANNEL>` env var.

| Field | Value |
|-------|-------|
| URL | `https://your-domain/webhook/kktix/<channel>` |
| Auth header name | `x-kktix-secret` |
| Auth header value | value of `WEBHOOK_SECRET` |

Example: sending to the `sprint` channel →
URL: `https://your-domain/webhook/kktix/sprint`, env var: `DISCORD_WEBHOOK_SPRINT`

## Dashboard

A Google-OAuth-protected web UI for viewing per-event registration time series.

- **Event list:** `/dashboard`
- **Per-event chart:** `/dashboard/events/{slug}` — line chart of Total + each ticket type, with capacity (horizontal dashed) and event start (vertical dashed) reference lines.

### One-time Google OAuth setup

1. Open [Google Cloud Console — Credentials](https://console.cloud.google.com/apis/credentials).
2. Create an **OAuth 2.0 Client ID** (Application type: **Web application**).
3. Under **Authorized redirect URIs**, add:
   - `http://localhost:8000/dashboard/oauth/callback` (for local dev)
   - `https://<your-deploy-domain>/dashboard/oauth/callback` (for production)
4. Copy the **Client ID** and **Client secret** into `.env` as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.
5. Generate a session secret:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Put the output into `.env` as `SESSION_SECRET`.
6. List allowed users in `.env` as `ALLOWED_EMAILS=alice@example.com,bob@example.com`.

### Try it locally

```bash
set -a && source .env && set +a
hatch run serve
# open http://localhost:8000/dashboard
```

You will be redirected to Google to sign in. Only emails in `ALLOWED_EMAILS` are granted access.

## Production / Deployment

When deploying (e.g. to Railway):

- **Railway builds the Dockerfile** using `python:3.12-slim-bookworm`, installs `sqlite3` for SSH database inspection, installs the package with `pip install .`, and starts the `argus` console command. `argus` reads Railway's injected `PORT` environment variable at runtime.
- **Mount a persistent volume** at `/data` (or wherever) and set `DB_PATH=/data/argus.db`. SQLite written to the container's local filesystem will be wiped on every redeploy.
- **`SESSION_SECRET` is required** — the app refuses to boot without it. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- **`PORT` is read from env** automatically (Railway and most container platforms inject it). No code change needed.
- **`ARGUS_HTTPS_ONLY=1`** — set this once the deploy URL is HTTPS-only, to add the `Secure` flag to session cookies.
- **Google OAuth redirect URI** must be added in Cloud Console: `https://<your-domain>/dashboard/oauth/callback`.

See [SPEC.md → Deployment](SPEC.md#deployment-railway) for the full Railway walkthrough.

## Development

Copy `.env.example` to `.env` and fill in the values, then source it before running any command:

```bash
set -a && source .env && set +a
hatch run serve   # start server
hatch run test    # run automated tests
hatch run lint    # lint
hatch run fmt     # format

# Visual inspection of Discord report (sends a real webhook):
ARGUS_MANUAL_TEST=1 hatch run pytest tests/test_discord_format_manual.py -v -s
```
