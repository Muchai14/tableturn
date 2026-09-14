# TableTurn FastAPI backend

Implements the root [`openapi.yaml`](../openapi.yaml) contract using FastAPI and a database-agnostic SQLAlchemy repository. Managed with `uv`; all resolved dependencies are recorded in `uv.lock`.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if it is not on your PATH. From the repository root:

```sh
cd backend
uv sync --locked
```

Set a staff password locally; no account password is shipped with the application:

```sh
export TABLETURN_STAFF_USERNAME=host
export TABLETURN_STAFF_PASSWORD='choose-a-local-password'
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

- Interactive API documentation: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)
- OpenAPI JSON: [http://127.0.0.1:8001/openapi.json](http://127.0.0.1:8001/openapi.json)
- Health check: [http://127.0.0.1:8001/health](http://127.0.0.1:8001/health)

Port 8001 keeps this backend separate from the previous Django prototype on port 8000. No frontend is served or changed by this backend. If you omit the password, public endpoints remain usable, while staff login returns a documented 503 until configured.

In the current Codex workspace, uv is installed in `../../../work/venv/bin/uv` relative to `backend/`. You may use that executable if `uv` is not yet on your normal PATH. The generated environment is `backend/.venv/` and is ignored by Git.

## Test and inspect

```sh
uv run pytest -q
uv run ruff check app tests
uv run ruff format --check app tests
```

Tests call the real ASGI endpoints through FastAPI's TestClient, with a fresh temporary SQLite database and deterministic clock. Tests validate response bodies against the hand-authored OpenAPI contract and check route coverage. The test-only password exists only in fixtures.

See [`_docs/backend-validation.md`](../_docs/backend-validation.md) for the test-first baseline and final results.

## Session and CSRF flow

1. Call `GET /api/auth/session` with `credentials: 'include'`. This creates an anonymous HttpOnly cookie and returns `csrf_token`.
2. Send that value as `X-CSRF-Token` on POST/PATCH requests, including public joins.
3. For staff sign-in, call `POST /api/auth/login` with `username` and `password`. Successful login rotates the session and returns a new CSRF token. Use the new token thereafter.
4. Staff routes require the authenticated cookie. `POST /api/auth/logout` invalidates it. Sessions expire after 12 hours.
5. Business mutations also require an `Idempotency-Key` header, typically `crypto.randomUUID()`. Retain the same key and payload for retries of an ambiguous failure. Public-join receipts are scoped to the same browser session.

All failures use `{ "error": { "code": "...", "message": "..." } }`. Invalid bodies or missing/invalid headers return 422; stale versions and invalid transitions return 409. Read current queue state after a conflict. Successful receipt replays return the original response snapshot without repeating the action; refresh the queue for newer changes.

For Swagger UI: execute the session endpoint first, copy its CSRF token into **Authorize → csrfHeader**, then execute login. Cookies are sent by the browser; after login, update csrfHeader to the new token. Browser cookie authentication cannot be set manually through Swagger's cookie input.

## Endpoint overview

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health |
| GET | `/api/auth/session` | Anonymous/authenticated session and CSRF token |
| POST | `/api/auth/login` | Shared staff sign-in |
| POST | `/api/auth/logout` | Invalidate session |
| GET | `/api/public-settings` | Restaurant and sign-up settings |
| POST | `/api/join` | Public join; returns private status URL |
| GET | `/api/status/{token}` | View one guest's position/status |
| GET | `/api/staff/queue` | Waiting, ready, and recently completed parties |
| POST | `/api/staff/parties` | Host adds a party |
| PATCH | `/api/staff/parties/{party_id}` | Version-checked name/size edits |
| POST | `/api/staff/parties/{party_id}/actions` | Ready, seat, no-show, cancel, return, undo |
| PATCH | `/api/staff/settings` | Version-checked public sign-up toggle |
| GET | `/api/staff/summary` | Restaurant-local daily metrics |

## Environment variables

| Variable | Default | Use |
| --- | --- | --- |
| `TABLETURN_STAFF_USERNAME` | `host` | Shared staff username |
| `TABLETURN_STAFF_PASSWORD` | Unset | Required to enable staff login; hashed in memory |
| `RESTAURANT_NAME` | `TableTurn Restaurant` | Display name |
| `RESTAURANT_TIMEZONE` | `America/Los_Angeles` | Valid IANA timezone for daily summaries |
| `CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Explicit allowed frontend origins; wildcard rejected |
| `COOKIE_SECURE` | `0` | Set to `1` behind HTTPS |
| `TABLETURN_LINK_SECRET` | Generated once and stored privately in the database | Optional override of at least 32 characters; preserve across restarts |
| `DATABASE_URL` | SQLite file `backend/tableturn.db` (absolute default path) | SQLAlchemy connection URL |

Use the same hostname consistently for the frontend and backend (for example, both `127.0.0.1`) when testing cookie-based requests. Environment files are not loaded automatically; export variables or use your process manager. Do not put secrets in Git.

## Database storage

`app/database.py` implements the `Repository` / `UnitOfWork` protocols from `app/repository.py` using SQLAlchemy Core. Domain services and API routes remain independent of the SQL dialect. SQLite is the default persistent database; in-memory SQLite URLs are rejected to avoid accidental data loss. settings, parties, event history, idempotency receipts, sessions, rate limits, and the private link secret survive restarts.

Set `DATABASE_URL` to select a different database. For PostgreSQL, install its driver with `uv add "psycopg[binary]"`, then use a URL such as `postgresql+psycopg://user:password@localhost/tableturn`. SQLAlchemy handles the dialect; no service or frontend changes are required. PostgreSQL has not been integration-tested in this workspace. Protect connection credentials as environment configuration.

The initial schema is created automatically on startup with SQLAlchemy metadata. Initialize a new database once with `uv run python -m app.database` before launching multiple workers; concurrent creation of a new schema is not supported. `create_all` creates missing tables but does not upgrade existing columns; future schema changes must ship versioned migrations. Restaurant name/timezone environment variables seed a new database only and do not overwrite saved settings.

Each unit of work uses a transaction, committing on success and rolling back on exceptions. A singleton restaurant-row UPDATE acquires a database lock before reading state, so queue order, receipts, version checks, and rate limits are serialized across independent engines. This intentionally trades throughput for consistent behavior in this single-restaurant MVP. All queries and DDL use SQLAlchemy; there is no raw vendor-specific SQL. Party timestamps are normalized to UTC, including on SQLite; event snapshots preserve aware datetimes using a JSON codec.

Database files are ignored by Git. Back up the database and preserve `TABLETURN_LINK_SECRET` if you override it. The generated default secret is stored in a private database column and never included in public settings. Changing the secret requires a guest-token migration. The old in-memory adapter remains available for explicit injection only; it is no longer the application default. Previous process-local mock data has no automatic migration.

Run the complete backend suite with `uv run pytest -q`. Endpoint tests use temporary database files. Additional tests reopen databases and race separate engines to verify durability, rollback, idempotency, queue ordering, and version conflicts.

Keep access logging disabled or redact `/status/…` and `/api/status/…` at every proxy and monitoring service. All API responses use `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
