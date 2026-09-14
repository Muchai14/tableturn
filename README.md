# TableTurn

A mobile-friendly restaurant waitlist manager for one restaurant, with a shared staff dashboard and private guest status pages.

## Project specification

Read [_docs/specs.md](_docs/specs.md) for the full MVP requirements, screens, workflows, data model, and acceptance criteria. [AGENTS.md](AGENTS.md) provides guidance for future development.

This repository contains a working frontend in `frontent/` connected to a FastAPI backend with persistent SQLAlchemy storage. All browser API calls are centralized in `frontent/src/api.js`.

## MVP scope

- Guests join at the restaurant by QR code or through a host, providing a name and party size.
- Hosts manage Waiting and Table ready lists, choose seating order, and edit party details.
- Guests see their queue position on a private, view-only page.
- Mark ready starts a five-minute countdown. Overdue parties remain available for staff review.
- Staff can seat, cancel, mark no-show, and undo supported actions.
- Staff manually open or close sign-ups without clearing the active queue.
- A daily summary shows seated parties, no-shows, and average join-to-seat wait.

No texts, phone-number collection, sound alerts, reservations, table maps, multiple locations, or guest editing.

## Architecture

The current backend uses Python, FastAPI, and uv, as requested after the initial specification. A repository interface isolates SQLAlchemy storage. SQLite is the default; DATABASE_URL selects other SQLAlchemy-supported databases. The server owns queue state and timestamps.

## Development status

The API contract is in [openapi.yaml](openapi.yaml). Setup, authentication, endpoint details, and database replacement instructions are in [backend/README.md](backend/README.md).

```sh
cd backend
uv sync --locked
export TABLETURN_STAFF_PASSWORD='choose-a-local-password'
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Run endpoint tests with `uv run pytest -q` from `backend/`. The database persists across restarts. See backend/README.md for DATABASE_URL and initialization details.

Before restaurant launch, configure the restaurant name and timezone, hosting and domain, production staff credentials, database backups, and data retention.

## Start the frontend

In a second terminal, from the repository root (Node.js 20+):

```sh
cd frontent
npm run dev
```

Open [the host desk](http://127.0.0.1:5173/staff) or [guest sign-up](http://127.0.0.1:5173/join). The frontend calls **http://127.0.0.1:8001** directly. Sign in with the backend credentials you configured above. See [frontent/README.md](frontent/README.md) for configuration and tests.
