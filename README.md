# Argus

KKTIX webhook receiver with daily Discord reports and a Google-OAuth-protected dashboard for visualizing registration trends.

## Installation

```bash
git clone https://github.com/sciwork/argus
cd argus
uv sync
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
| `DATABASE_URL` | `sqlite:///argus.db` | SQLAlchemy SQLite database URL |
| `HEALTHCHECK_DB_TIMEOUT` | `1.0` | `/health` endpoint DB connect timeout in seconds |
| `LOG_LEVEL` | `INFO` | Python application log level |
| `ALLOWED_EMAILS` | — | Comma-separated email allowlist for dashboard access |
| `ARGUS_HTTPS_ONLY` | `0` | Set to `1` to mark session cookies as Secure |

## Usage

```bash
uv run uvicorn argus.main:app --host 0.0.0.0 --port 8000
```

### Docker Compose

Docker Compose uses SQLite persisted in the `argus-data` volume:

```bash
docker compose up -d
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

> **Testing against a real KKTIX event:** if the event is tagged with the
> "測試" (Test) category, KKTIX omits the JSON-LD (`application/ld+json`)
> block from the event page — the same block `argus.kktix.scraper` parses
> for `start_at`. Remove that category tag (leaving only real categories
> like "線上活動") or `start_at` will silently stay `null` for that event,
> even though the webhook and `capacity` scraping both work fine.

## Dashboard

A Google-OAuth-protected web UI for viewing per-event registration time series.

- **Event list:** `/dashboard`
- **Per-event chart:** `/dashboard/events?slug=<slug>` — line chart of Total + each ticket type, with capacity (horizontal dashed) and event start (vertical dashed) reference lines.

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

The dashboard UI is a Next.js app (`frontend/`) built to static files and served same-origin by the backend. `uvicorn` alone won't serve it in a fresh checkout — build the frontend first (or use the `next dev` proxy workflow), see [Development](#development) below.

```bash
set -a && source .env && set +a
cd frontend && pnpm install && pnpm build && cd ..   # one-time (or after frontend changes)
uv run uvicorn argus.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/dashboard
```

You will be redirected to Google to sign in. Only emails in `ALLOWED_EMAILS` are granted access.

## Production / Deployment

When deploying (e.g. to Railway):

- **Railway builds the Dockerfile** using `python:3.12-slim-bookworm`, installs the package with `pip install .`, and starts uvicorn via `railway.json` `startCommand`. Railway injects `$PORT` and the start command binds to it.
- **The frontend build is automatic** — the Dockerfile's first stage builds `frontend/` (`pnpm install && pnpm build`) and copies its static export into `src/argus/dashboard/frontend/` before the Python stage installs the package. No manual frontend build step is needed for Docker/Railway deploys.
- **For SQLite, mount a persistent volume** at `/data` and set `DATABASE_URL=sqlite:////data/argus.db`. SQLite written to the container's local filesystem will be wiped on every redeploy.
- **`SESSION_SECRET` is required** — the app refuses to boot without it. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`.
- **Port:** the Dockerfile's `CMD` binds to a fixed port 8000. Railway overrides this via `railway.json`'s `startCommand`, which substitutes its injected `$PORT`. To change the port in non-Railway environments, override the container command (e.g. `docker run … argus-image uvicorn argus.main:app --host 0.0.0.0 --port 9000`).
- **`ARGUS_HTTPS_ONLY=1`** — set this once the deploy URL is HTTPS-only, to add the `Secure` flag to session cookies.
- **Google OAuth redirect URI** must be added in Cloud Console: `https://<your-domain>/dashboard/oauth/callback`.

See [SPEC.md → Deployment](SPEC.md#deployment-railway) for the full Railway walkthrough.

## Development

Copy `.env.example` to `.env` and fill in the values, then source it before running any command:

```bash
uv sync --group dev               # create .venv and install all dependencies
set -a && source .env && set +a

uv run uvicorn argus.main:app --host 0.0.0.0 --port 8000  # start server
uv run pytest tests/              # run tests, including clean Docker builds
uv run ruff check src tests       # lint
uv run ruff format src tests      # format

# Visual inspection of Discord report (sends a real webhook):
ARGUS_MANUAL_TEST=1 uv run pytest tests/test_discord_format_manual.py -v -s
```

### Frontend (`frontend/`)

The dashboard UI lives in `frontend/` — a Next.js app using `pnpm` (not `npm`), statically exported (`next build`) into `src/argus/dashboard/frontend/`, and served same-origin by the backend under `/dashboard` (no separate frontend server or CORS setup in production). This copy step happens automatically in Docker's multi-stage build; locally you have two options:

1. **Build once, run `uvicorn` normally** — full same-origin experience, matches production:
   ```bash
   cd frontend && pnpm install && pnpm build && cd ..
   uv run uvicorn argus.main:app --host 0.0.0.0 --port 8000
   # open http://localhost:8000/dashboard
   ```
   Re-run `pnpm build` after frontend changes to see them.

2. **`next dev` + dev proxy** — for active frontend development with hot reload, run both processes side by side:
   ```bash
   # terminal 1
   uv run uvicorn argus.main:app --host 0.0.0.0 --port 8000
   # terminal 2
   cd frontend && pnpm install && pnpm dev
   # open http://localhost:3000/dashboard
   ```
   `frontend/next.config.ts` proxies `/dashboard/api/*` calls from the `next dev` server (port 3000) to `uvicorn` (port 8000), so no CORS configuration is needed.

Other frontend commands (run from `frontend/`): `pnpm lint`, `pnpm test` (vitest unit/component tests), `pnpm exec tsc --noEmit`.
