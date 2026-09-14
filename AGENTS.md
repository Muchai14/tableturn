# Guidance for contributors and coding agents

## Source of truth

Read `_docs/specs.md` before changing product behavior. It defines the TableTurn MVP. Follow explicit user instructions when they change the specification, and update affected documentation to keep it consistent.

This repository initially contains documentation only. Do not assume the local prototype or its dependencies are present. Inspect the checkout before selecting commands.

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

Use the specified Python/Django and PostgreSQL architecture unless the user requests a change. Preserve established project structure and dependency locks when implementation is added. Do not replace the application with a static mockup or a different framework merely for convenience.

Keep state transitions, validation, permission checks, idempotency, and timestamps on the server. Handle concurrent edits explicitly. Never use browser storage as the source of truth for the shared queue.

Use semantic HTML, accessible labels and focus behavior, usable touch controls, and responsive layouts. Keep visible copy useful to hosts and guests.

## Privacy and security

Do not commit credentials, `.env` files, guest databases, private status links, session data, backups, or logs. Use fictional fixtures. Keep private guest tokens out of logs and public responses for other parties.

Require staff authentication for staff pages and APIs, enforce CSRF protection on mutations, validate inputs, and prevent duplicate requests from causing duplicate transitions. Do not disable security checks to make tests pass.

## Verification

For documentation changes, verify relative links and consistency with the specification. Do not invent test results or run application commands when there is no application.

When implementation is present, run meaningful tests covering the changed behavior. Queue changes should cover ordering, five-minute deadlines, manual no-show review, retry idempotency, concurrent edits, undo, and timezone-aware summaries as applicable. UI changes should be checked on phone and desktop layouts.

Keep setup and test commands in README.md accurate. Report what changed, what was verified, and any remaining limitations. Avoid unrelated refactors and scope additions.

## Git workflow

Keep commits focused and descriptive. Inspect staged changes before committing. Do not commit generated runtime files or alter unrelated user changes. Do not force-push, rewrite shared history, or delete remote resources without explicit authorization.
