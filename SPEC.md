# Argus — Project Specification

## Overview

Argus is a small Python service for receiving external events and pushing notifications. The first feature is a KKTIX webhook receiver that tracks event registrations and sends daily summary reports to Discord. The codebase is structured so that future features (different sources / different purposes) can be added as self-contained packages that share common infrastructure.

## Architecture

Argus uses a **vertical slice** layout: each feature owns its full stack (HTTP routing, business logic, persistence access, presentation), and shared infrastructure lives at the package root.

```
┌──────────────── feature packages ────────────────┐
│  kktix/         (future: github_monitor/, ...)   │
│   router · handler · scraper · report            │
└─────────────────────┬────────────────────────────┘
                      │ uses
┌─────────────────────▼────────────────────────────┐
│  shared infrastructure                           │
│  discord (transport)   channels (resolution)     │
│  database              config                    │
│  timeutil              health                    │
└──────────────────────────────────────────────────┘
```

- **`discord.py`** is a thin transport: `post(url, content, embeds)`. It does not understand any feature's data model.
- **`channels.py`** resolves a channel name to a Discord webhook URL via env vars. Source-agnostic.
- **`database.py`** owns SQLite connection and the schema for all features (centralized to keep migrations simple).
- A new feature creates its own package and uses these shared modules; it does **not** modify other features.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Web framework | FastAPI |
| ASGI server | uvicorn |
| Database | SQLite |
| Container image | `python:3.12-slim-bookworm` with `sqlite3` CLI |
| Scheduler | APScheduler |
| HTTP client | httpx |
| HTML parsing | beautifulsoup4 |
| Package manager | Hatch |
| Deploy target | Railway |

---

## API Reference

| Method | Path | Auth | Description | Section |
|--------|------|------|-------------|---------|
| `POST` | `/webhook/kktix/{channel}` | `x-kktix-secret` header | Receive KKTIX registration / cancellation webhook | [KKTIX Webhook](#kktix-webhook) |
| `GET` | `/health` | — | Liveness + DB readiness check | [Health Check](#health-check) |
| `GET` | `/dashboard/login` | — | Start Google OAuth flow | [Dashboard](#dashboard) |
| `GET` | `/dashboard/oauth/callback` | — | OAuth redirect target | [Dashboard](#dashboard) |
| `GET` | `/dashboard/logout` | — | Clear session, redirect to login | [Dashboard](#dashboard) |
| `GET` | `/dashboard` | session (HTML) | Event list page | [Dashboard](#dashboard) |
| `GET` | `/dashboard/events/{slug}` | session (HTML) | Per-event chart page | [Dashboard](#dashboard) |
| `GET` | `/dashboard/webhook-logs` | session (HTML) | Webhook log viewer page | [Dashboard](#dashboard) |
| `GET` | `/dashboard/api/events` | session (401) | JSON: event list | [Dashboard](#dashboard) |
| `GET` | `/dashboard/api/events/{slug}/timeseries` | session (401) | JSON: per-event time series | [Dashboard](#dashboard) |
| `DELETE` | `/dashboard/api/events/{slug}` | session (401) | Permanently delete event + its tickets | [Dashboard](#dashboard) |
| `GET` | `/dashboard/api/webhook-logs` | session (401) | JSON: paginated webhook log entries | [Dashboard](#dashboard) |
| `DELETE` | `/dashboard/api/webhook-logs/{id}` | session (401) | Delete a single webhook log entry | [Dashboard](#dashboard) |
| `DELETE` | `/dashboard/api/webhook-logs` | session (401) | Clear all webhook log entries | [Dashboard](#dashboard) |
| `POST` | `/dashboard/api/report/trigger` | session (401) | Run the daily Discord report immediately | [Dashboard](#dashboard) |

**Auth column legend:**
- `x-kktix-secret header` — request must include header matching `WEBHOOK_SECRET` (constant-time compared)
- `session (HTML)` — protected by signed session cookie; missing/invalid → 302 to `/dashboard/login`
- `session (401)` — same protection but JSON routes return 401 instead of redirecting

---

## Project Structure

```
argus/
├── src/
│   └── argus/
│       ├── __about__.py          # version
│       ├── __init__.py
│       │
│       │   # ── feature packages ──
│       ├── kktix/
│       │   ├── __init__.py
│       │   ├── router.py         # POST /webhook/kktix/{channel}
│       │   ├── handler.py        # webhook payload → DB writes
│       │   ├── scraper.py        # KKTIX page fetch + event enrichment
│       │   └── report.py         # daily report query + Discord payload + send
│       ├── dashboard/
│       │   ├── __init__.py
│       │   ├── router.py         # /dashboard/* routes
│       │   ├── queries.py        # time series queries
│       │   └── templates/
│       │       ├── _base.html    # shared layout
│       │       ├── index.html    # event list
│       │       └── event.html    # per-event chart
│       │
│       │   # ── shared infrastructure ──
│       ├── auth.py               # OAuth client + require_login dependency (reusable)
│       ├── discord.py            # generic Discord webhook client (post-only)
│       ├── channels.py           # channel name validation + URL resolution
│       ├── config.py             # Settings + Secrets dataclasses
│       ├── database.py           # SQLite init + connection (all features' tables)
│       ├── timeutil.py           # UTC datetime helpers
│       │
│       │   # ── system layer ──
│       ├── health.py             # GET /health
│       ├── main.py               # FastAPI app + uvicorn entrypoint
│       └── scheduler.py          # APScheduler; dispatches each feature's scheduled jobs
│
├── tests/
│   ├── conftest.py
│   ├── test_*.py                 # automated tests
│   └── test_discord_format_manual.py  # opt-in test that sends real Discord webhooks
├── .env.example
├── pyproject.toml
├── railway.json
└── README.md
```

### Adding a new feature

1. Create a new package under `src/argus/<feature>/` (e.g. `github_monitor/`).
2. Inside, organize as needed (`router.py`, `handler.py`, `notifier.py`, …) — the feature owns its own structure.
3. Use shared modules: `discord.post()`, `channels.resolve_webhook_url()`, `get_conn()`, `config.settings`.
4. If the feature exposes HTTP endpoints, register its router in `main.py`.
5. If the feature has scheduled work, register its job in `scheduler.py`.
6. If the feature needs new tables, add them to `database.py`'s `_CREATE_TABLES_SQL`.

---

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
| `KKTIX_ORGANIZATION` | — | KKTIX organizer subdomain (e.g. `example` for `example.kktix.cc`) |
| `REPORT_HOUR` | `9` | Daily report hour |
| `REPORT_MINUTE` | `0` | Daily report minute |
| `REPORT_TIMEZONE` | `Asia/Taipei` | Daily report timezone |
| `DB_PATH` | `argus.db` | SQLite file path |
| `HEALTHCHECK_DB_TIMEOUT` | `1.0` | Health check DB timeout in seconds |
| `LOG_LEVEL` | `INFO` | Python application log level |
| `ALLOWED_EMAILS` | — | Comma-separated email allowlist for dashboard access |
| `ARGUS_HTTPS_ONLY` | `0` | Set to `1` to mark session cookies as Secure |

Config is loaded at startup via `Settings.from_env()` and `Secrets.from_env()` in `config.py`. Secret values are masked in `__repr__`.

---

## Database Schema

### events

| Column | Type | Description |
|--------|------|-------------|
| `event_slug` | TEXT, PK | Unique identifier from KKTIX |
| `event_name` | TEXT | Event name |
| `channel` | TEXT | Discord channel (e.g. `SPRINT`) |
| `start_at` | TEXT | Event start time (UTC ISO 8601, no offset) |
| `capacity` | INTEGER | Total attendance cap |
| `created_at` | TEXT | Record creation time (UTC, set by SQLite) |
| `last_reported_at` | TEXT | Timestamp of last successful Discord report (UTC ISO 8601, no offset) |

`start_at` and `capacity` are populated automatically by scraping the KKTIX event page when the event is first created (see [Event Enrichment](#event-enrichment)).

### tickets

| Column | Type | Description |
|--------|------|-------------|
| `ticket_id` | INTEGER, PK | Unique identifier from KKTIX |
| `ticket_name` | TEXT | Ticket type name |
| `event_slug` | TEXT, FK → events | Associated event |
| `order_id` | INTEGER, index | Associated order |
| `order_state` | TEXT | `activated` or `cancelled` |
| `contact_name` | TEXT | Contact person name |
| `contact_email` | TEXT | Contact person email |
| `paid_at` | TEXT | Payment timestamp (UTC ISO 8601, no offset) |
| `cancelled_at` | TEXT | Cancellation timestamp (UTC ISO 8601, no offset) |

Indexes: `event_slug`, `order_id`, `ticket_name`.

### webhook_logs

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER, PK | Auto-increment |
| `method` | TEXT | HTTP method |
| `channel` | TEXT | Normalized channel name (NULL if invalid) |
| `headers` | TEXT (JSON) | All request headers |
| `body` | TEXT (JSON) | Request body |
| `created_at` | TEXT | Record creation time (UTC, set by SQLite) |

All incoming webhook requests are logged before auth verification, including rejected ones.

### Datetime Storage

All application-written timestamps (`paid_at`, `cancelled_at`, `last_reported_at`) are stored as UTC ISO 8601 strings without timezone offset or microseconds: `YYYY-MM-DDTHH:MM:SS`. Conversion is handled by `timeutil.to_utc()` and `timeutil.utcnow_iso()`.

---

## KKTIX Webhook

### Authentication

| Field | Value |
|-------|-------|
| Auth header name | `x-kktix-secret` |
| Auth header value | value of `WEBHOOK_SECRET` |

Secret comparison uses `hmac.compare_digest` to prevent timing attacks.

### Endpoint

```
POST /webhook/kktix/{channel}
```

The `channel` path segment maps to a Discord channel. It is case-insensitive and normalized to uppercase. The corresponding `DISCORD_WEBHOOK_<CHANNEL>` env var must be set.

**Error responses:**

| Condition | Status |
|-----------|--------|
| Invalid channel name format | 400 `invalid_channel` |
| Auth failure | 401 `Unauthorized` |
| Channel env var not configured | 503 `channel_not_configured` |

All requests are logged to `webhook_logs` before any validation.

### Payload — Registration (`order_activated_paid`)

```json
{
  "batch_id": "0000000000000001",
  "notifications": [
    {
      "type": "order_activated_paid",
      "event": {
        "name": "Example Event",
        "slug": "abcd1234"
      },
      "order": {
        "id": 100000001,
        "state": "activated",
        "paid_at": "2026-04-18T14:00:54.442+08:00"
      },
      "contact": {
        "name": "Test User",
        "email": "test@example.com",
        "mobile": ""
      },
      "tickets": [
        { "id": 200000001, "name": "一般票", "price_cents": 0, "price_currency": "TWD" },
        { "id": 200000002, "name": "早鳥票", "price_cents": 0, "price_currency": "TWD" }
      ]
    }
  ]
}
```

### Payload — Cancellation (`order_cancelled`)

```json
{
  "batch_id": "0000000000000002",
  "notifications": [
    {
      "type": "order_cancelled",
      "event": {
        "name": "Example Event",
        "slug": "abcd1234"
      },
      "order": {
        "id": 100000001,
        "state": "cancelled",
        "cancelled_at": "2026-04-18T14:03:50.949+08:00"
      }
    }
  ]
}
```

### Processing Logic

- `order_activated_paid`:
  - Upsert event into `events` with channel (`ON CONFLICT DO NOTHING`)
  - Insert each ticket into `tickets` with `order_state = 'activated'` (`ON CONFLICT DO NOTHING`)
  - If the event is newly inserted (first time seen), schedule [Event Enrichment](#event-enrichment) as a background task
- `order_cancelled`:
  - Update all tickets matching `order_id` to `order_state = 'cancelled'`, set `cancelled_at`
- One order may contain multiple tickets
- One webhook payload may contain multiple notifications
- All timestamps converted to UTC before storage

---

## Event Enrichment

When a new event is first inserted, a background task fetches `start_at` and `capacity` from the KKTIX event page.

**URL:** `https://{KKTIX_ORGANIZATION}.kktix.cc/events/{slug}`

**Parsing:**
- `start_at`: extracted from JSON-LD structured data (`"startDate"` field), converted to UTC
- `capacity`: extracted from `<i class="fa fa-male"></i>{registered} / {capacity}` pattern

The task is skipped if `start_at` is already populated. All exceptions are swallowed and logged; failures do not affect the webhook response.

---

## Daily Discord Report

Implemented in `kktix/report.py`. Uses the shared `discord.post()` transport.

### Schedule

Configured via `REPORT_HOUR`, `REPORT_MINUTE`, `REPORT_TIMEZONE`. Defaults to 09:00 Asia/Taipei.

### Channel Selection

`send_report()` queries the DB for channels with active events:

```sql
SELECT DISTINCT channel FROM events
WHERE channel IS NOT NULL
  AND (start_at IS NULL OR start_at > <now_utc>)
```

Only these channels receive a report. Channels with no active events are skipped entirely. Events with `start_at IS NULL` (not yet enriched) are included.

### Report Content

One Discord message per channel, containing one embed per event:

```
📊 Argus Daily Registration Summary  2026-04-29 09:00 (Asia/Taipei)

🎟️ Event Name
一般票　3　(+2)
早鳥票　2　(+0)
─────────────
**Total　5　(+2)**
```

- First report for an event (no `last_reported_at`): counts shown without delta
- Subsequent reports: delta shown as `(+N)` or `(-N)` compared to last report
- Embed border color: green (`0x1D9E75`) for net increase, red (`0xE24B4A`) for net decrease, grey (`0x888780`) for no change or first report
- Multiple events in the same channel appear as separate embeds in a single Discord message (Discord limit: 10 embeds per message)
- Discord failure: log status code and response body (up to 500 chars), do not update `last_reported_at`, do not raise exception

### Delta Calculation

Delta is computed from the `tickets` table using `events.last_reported_at` as the reference point — no separate snapshot table is maintained.

```sql
-- Current count (now)
SELECT ticket_name, COUNT(*) AS cnt
FROM tickets
WHERE event_slug = ? AND order_state = 'activated'
GROUP BY ticket_name;

-- Count at last report time
SELECT ticket_name, COUNT(*) AS cnt
FROM tickets
WHERE event_slug = ?
  AND paid_at IS NOT NULL AND paid_at <= <last_reported_at>
  AND (cancelled_at IS NULL OR cancelled_at > <last_reported_at>)
GROUP BY ticket_name;
```

After each successful send, `events.last_reported_at` is updated to the current UTC time for all events in that channel.

---

## Dashboard

A web UI that visualizes registration trends per event over time. Implemented as a separate feature package `dashboard/`. Protected by Google OAuth.

### Routes

See [API Reference](#api-reference) for the canonical list. All routes under `/dashboard/*` (except `login` and `oauth/callback`) require an authenticated session. HTML routes redirect to `/dashboard/login` on failure; JSON API routes return `401`.

### Authentication

Server-side OAuth 2.0 with Google as the identity provider. After successful OAuth, the user's email is checked against `ALLOWED_EMAILS`. If allowed, a signed session cookie is set.

**Flow:**

1. Visit `/dashboard` (or any protected route) without session → 302 to `/dashboard/login`
2. `/dashboard/login` → 302 to Google consent screen
3. Google → `/dashboard/oauth/callback?code=...`
4. Backend exchanges code for `id_token`, verifies email is in `ALLOWED_EMAILS`
5. On success: session cookie written, 302 to original destination (or `/dashboard`)
6. On rejection: 403 page

Session is signed using `SESSION_SECRET` via Starlette's `SessionMiddleware`.

### Time Series Computation

No new DB table. Time series is derived from existing `tickets` data using the same logic as report delta calculation.

For each day `D` in range:

```sql
SELECT ticket_name, COUNT(*) AS cnt
FROM tickets
WHERE event_slug = ?
  AND paid_at IS NOT NULL AND paid_at <= ?    -- end of day D in UTC
  AND (cancelled_at IS NULL OR cancelled_at > ?)
GROUP BY ticket_name;
```

A ticket counts on day `D` if it was paid by end of `D` and either not cancelled or cancelled after `D`. This naturally reflects historical state.

**Range:** from `date(min(paid_at))` through `min(today, date(events.start_at))` in the configured display timezone. The chart never extends into the future — if `start_at` is upcoming, the chart stops at today and the `start_marker_label` field is `null` so the frontend suppresses the "Event start" annotation. Once `start_at` is reached, the chart extends to that date and the marker appears at the right edge.

### JSON Response Shape

`GET /dashboard/api/events`:

```json
[
  {
    "event_slug": "test-event",
    "event_name": "Test Event",
    "channel": "SPRINT",
    "start_at": "2026-04-25T01:00:00",
    "capacity": 30
  }
]
```

`GET /dashboard/api/events/{slug}/timeseries`:

```json
{
  "event": {
    "event_slug": "test-event",
    "event_name": "Test Event",
    "channel": "SPRINT",
    "start_at": "2026-04-25T01:00:00",
    "capacity": 30
  },
  "labels": ["2026-04-15", "2026-04-16", "..."],
  "datasets": [
    { "name": "Total",  "data": [1, 3, 5, ...] },
    { "name": "一般票", "data": [1, 2, 3, ...] },
    { "name": "早鳥票", "data": [0, 1, 2, ...] }
  ],
  "start_marker_label": "2026-04-25"
}
```

`start_marker_label` is `null` when `start_at` is unset or still in the future.

### Frontend

Single Jinja2 template per page; charts rendered client-side with Chart.js (CDN, no build step).

**Per-event chart features:**
- One line per ticket type, plus a "Total" line
- Horizontal dashed line at `capacity` (when set)
- Vertical dashed line at `start_at`
- Daily granularity on X axis

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_OAUTH_CLIENT_ID` | Yes | Google OAuth 2.0 client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Yes | Google OAuth 2.0 client secret |
| `SESSION_SECRET` | Yes | Random ≥32-byte hex string for signing session cookies |
| `ALLOWED_EMAILS` | Yes | Comma-separated allowlist, e.g. `alice@example.com,bob@example.com` |

Google OAuth redirect URI to register in Google Cloud Console:
`https://<your-domain>/dashboard/oauth/callback`

### Dependencies (additions)

- `authlib` — OAuth 2.0 client integration with Google
- `jinja2` — HTML templating
- `itsdangerous` — session cookie signing (transitive via Starlette)

---

## Health Check

```
GET /health
```

Returns DB connectivity status and app version.

```json
{
  "status": "ok",
  "version": "0.1.0",
  "checks": {
    "database": { "ok": true, "latency_ms": 0.42 }
  }
}
```

HTTP 200 when healthy, 503 when unhealthy.

---

## Development

```bash
# Source env vars
set -a && source .env && set +a

hatch run serve   # start server
hatch run test    # run automated tests
hatch run lint    # ruff check
hatch run fmt     # ruff format

# Visual inspection of Discord report (opt-in, sends a real webhook)
ARGUS_MANUAL_TEST=1 hatch run pytest tests/test_discord_format_manual.py -v -s
```

---

## Deployment (Railway)

1. Push repo to GitHub
2. Create new Railway project → Deploy from GitHub repo
3. Add a Volume, mount at `/data`, set `DB_PATH=/data/argus.db`
4. Set all required environment variables in Railway dashboard
5. Railway builds `Dockerfile`, installs the package and SQLite CLI, then starts the installed `argus` console command

```json
{
  "deploy": {
    "startCommand": "argus"
  }
}
```

Subsequent deploys trigger automatically on `git push`.
