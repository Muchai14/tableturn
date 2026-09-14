# Guidance for contributors and coding agents

## Source of truth

Read `_docs/specs.md` before changing product behavior. It defines the TableTurn MVP. Follow explicit user instructions when they change the specification, and update affected documentation to keep it consistent.

This repository contains a FastAPI backend in `backend/` and a connected frontend in `frontent/`. Read `backend/README.md` and the root `openapi.yaml` before API work. The earlier local Django prototype is outside this repository. Inspect the checkout before selecting commands.

## Product constraints

- One restaurant, one shared queue, and one shared staff login.
- On-site QR sign-up or host-added parties; collect only name and party size.
- Guests have private, view-only status pages.
- No texts, phone numbers, sound alerts, email, or push notifications.
- Staff choose seating order. Only Waiting parties count toward parties ahead.
- Mark ready moves a party into Table ready and starts a five-minute server-owned deadline.
- Expiry flags staff review; it must not automatically mark a no-show or remove the party.
- Closing public sign-ups preserves active parties and permits staff operations.
- Respect restaurant-local reporting days and correct metrics after undo.

## Implementation direction

The user has superseded the initial Django plan: use Python/FastAPI with uv and SQLAlchemy for persistent, database-agnostic storage. Preserve the repository boundary and configurable DATABASE_URL. Preserve established project structure and dependency locks when implementation is added. Do not replace the application with a static mockup or a different framework merely for convenience.

Keep state transitions, validation, permission checks, idempotency, and timestamps on the server. Handle concurrent edits explicitly. Never use browser storage as the source of truth for the shared queue.

Use semantic HTML, accessible labels and focus behavior, usable touch controls, and responsive layouts. Keep visible copy useful to hosts and guests.

## Privacy and security

Do not commit credentials, `.env` files, guest databases, private status links, session data, backups, or logs. Use fictional fixtures. Keep private guest tokens out of logs and public responses for other parties.

Require staff authentication for staff pages and APIs, enforce CSRF protection on mutations, validate inputs, and prevent duplicate requests from causing duplicate transitions. Do not disable security checks to make tests pass.

## Verification

For documentation changes, verify relative links and consistency with the specification. Do not invent test results or run application commands when there is no application.

For backend work, write endpoint tests first and run `uv run pytest -q` and `uv run ruff check app tests` from `backend/`. Keep `openapi.yaml` synchronized with request/response behavior. Run meaningful tests covering the changed behavior. Queue changes should cover ordering, five-minute deadlines, manual no-show review, retry idempotency, concurrent edits, undo, and timezone-aware summaries as applicable. UI changes should be checked on phone and desktop layouts.

Keep setup and test commands in README.md accurate. Report what changed, what was verified, and any remaining limitations. Avoid unrelated refactors and scope additions.

## Git workflow

Keep commits focused and descriptive. Inspect staged changes before committing. Do not commit generated runtime files or alter unrelated user changes. Do not force-push, rewrite shared history, or delete remote resources without explicit authorization.

## Frontend integration

Centralize all backend requests in `frontent/src/api.js`. Preserve credentialed sessions, CSRF refresh, idempotency keys across ambiguous retries, and version conflict handling. Run `npm test` and `npm run build` from `frontent/`. The static frontend server runs on 5173 and the API on 8001.
