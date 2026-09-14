# SQLAlchemy migration validation

The endpoint fixtures were switched to temporary file-backed SQLite before implementation; the initial run failed because `app.database` did not exist. The agent supplied five durability/concurrency tests before the adapter was available. Added an endpoint restart test recreating the FastAPI app to verify authenticated cookies, public receipt replay, guest links, and queue state survive restart.

Final checks: 49 backend tests pass (40 existing and nine new cases); Ruff lint and formatting pass. Two existing upstream TestClient deprecation warnings remain. All seven frontend API client tests pass. Agent review also identified ephemeral SQLite URL hazards; three test cases now verify clear rejection. Concurrent schema creation requires the documented one-time initialization command.

The production default is now persistent SQLite through SQLAlchemy Core, with DATABASE_URL configuration. Tests exercise independent database engines, full transaction rollback, shared rate counters, distinct queue order, stale-version races, idempotent replay, aware timestamps, and restart restoration including undo. No PostgreSQL server was available for integration tests; SQLAlchemy uses portable table types and query expressions.

Transactions use SQLAlchemy context managers for commit/rollback, following the [SQLAlchemy transaction documentation](https://docs.sqlalchemy.org/en/20/core/connections.html#using-transactions).
