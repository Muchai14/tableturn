# Backend validation

## Test-first sequence

1. Created `openapi.yaml` from the product specification before endpoint implementation.
2. Wrote endpoint and response-contract tests against a route-free FastAPI scaffold.
3. Ran the initial suite: **20 failed, 15 fixture errors, 1 passed**. The contract-validation test passed; endpoint tests failed with missing routes (404).
4. Implemented the FastAPI routes, domain services, sessions, and in-memory repository. The original **36 tests passed**.
5. Added privacy, cookie rotation, DST reporting, and no-show undo tests. Ran the private-link receipt test before its fix and observed the expected failure.
6. Removed private links from stored receipt snapshots and reran the complete suite: **40 passed**.

## Coverage

- OpenAPI 3.1 document validation, response JSON schemas, and route/method coverage.
- Public settings, anonymous session bootstrap, staff login/logout, session rotation and expiry.
- CSRF and origin checks, staff-only endpoints, login/join rate limiting.
- Name/size validation, missing headers, invalid routes/transitions, and stale versions.
- Public and host joins, idempotency conflicts and exact replays, private read-only status.
- Closing public sign-ups without clearing parties or blocking staff additions.
- Waiting order, ready deadlines, expiry as review, return to original order.
- Seating, cancellation, no-show review, and supported undo behavior.
- Daily averages, midnight boundaries, DST fall-back, and metrics after undo.
- Recent-party count/time limits and isolated mock database instances.
- Simultaneous duplicate creation and competing versioned transitions.
- No raw private links/tokens in party records or stored mutation receipts.

## Additional checks

- `uv run ruff check app tests`: passed.
- `uv run ruff format --check app tests`: passed.
- `git diff --check`: passed.
- The lockfile was generated and dependencies installed with uv.
- Two upstream deprecation warnings are emitted by the installed Starlette/httpx/AnyIO test tooling; all tests pass. No warnings are suppressed.

## Scope and limits

This is a local backend using an intentionally ephemeral, process-local mock repository. It has not been connected to the unfinished frontend, deployed, or validated against a durable database. Run a single worker. Queue and session data disappear on restart. Database replacement and public hosting remain separate work.
