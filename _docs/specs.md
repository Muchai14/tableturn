# TableTurn — MVP Project Specification

Version: 1.0

Date: September 13, 2026

Status: Ready for implementation planning

## 1. Product definition

TableTurn is a responsive restaurant waitlist website for one restaurant. Hosts manage one shared queue on a tablet or computer. Guests join through an on-site QR code or a host and check a private status page on their phones.

The application uses visual updates only. It does not collect phone numbers or send texts, sounds, emails, or push notifications.

This specification preserves the agreed scope. Specific technical limits, refresh intervals, mobile layout, and recovery behavior below are implementation defaults selected to make the project buildable, rather than additional user-requested features.

## 2. Objectives

- Let guests join quickly with a name and party size.
- Let hosts scan the waiting list and choose which party to call next.
- Give each guest a private view of their current queue position and table-ready status.
- Flag overdue parties without automatically removing them.
- Provide a simple daily service summary.

Success means the complete join → ready → seated/no-show workflow works across multiple browsers without duplicate parties, lost changes, or inconsistent queue positions.

## 3. Users and permissions

| User | Allowed actions |
| --- | --- |
| Guest | Join while sign-ups are open; view their own status through a private link |
| Staff | Shared login; open/close sign-ups; add/edit parties; mark ready, seat, cancel, mark no-show, undo; view daily summary |

Guests cannot view other parties, edit their details, cancel their entry, or change any status. Staff accounts are shared; event records identify the shared account, not the individual host.

## 4. Core workflows

### 4.1 Guest joins through the restaurant QR code

1. Guest scans the restaurant’s QR code and opens `/join`.
2. If sign-ups are open, the page shows restaurant name, name, party size, and Join waitlist.
3. Submission validates the fields and immediately creates a Waiting party.
4. The guest is redirected to `/status/<private-token>`.
5. The status page shows the number of waiting parties ahead and party details.

If closed, replace the form with: **“The waitlist is currently closed. Please see the host.”** The server rechecks this setting at submission, including when a form was opened before closing.

### 4.2 Host adds a party

1. Staff select Add party.
2. A side panel collects name and party size.
3. Saving creates a Waiting party and shows its private status QR code and copy-link action.
4. The guest scans the code to follow their status.

Default: staff may add parties while public sign-ups are closed. The toggle controls public sign-ups; existing entries and staff operations stay available.

### 4.3 Staff mark a table ready

1. Staff select Mark ready on any Waiting row.
2. The action takes effect immediately, without confirmation.
3. The party moves to Table ready, and its five-minute deadline is recorded.
4. Remaining waiting positions update.
5. The guest page displays **“Your table is ready—please return to the host”** with a countdown.

No external notification is sent. Guests must check the status page.

### 4.4 Staff resolve the party

- Select Seat when the party returns: remove it from active lists and record seating time.
- At the deadline, retain the party in Table ready and show Review. Staff decide whether to seat it or mark No-show.
- Staff may cancel a Waiting or Table ready party through its side panel.
- Terminal entries appear in a compact Recently completed section below the dashboard, limited to the latest 20 transitions from the past 24 hours, to support undo.

### 4.5 Staff close sign-ups

Closing prevents new public submissions immediately. It does not clear, cancel, or otherwise change active parties. There is no automatic midnight reset.

## 5. Screens and layout

### 5.1 Staff login — `/staff/login`

Username and password, sign-in action, and clear authentication errors. Provide logout on authenticated screens. Provision and reset the shared account through an operator procedure; guest registration and self-service staff registration are out of scope.

### 5.2 Dashboard — `/staff`

- Header: TableTurn, restaurant name, Dashboard/Summary navigation, sign-up status toggle, Add party, logout.
- Tablet/desktop: Waiting on the left and Table ready on the right.
- Below 768 CSS pixels: Waiting and Table ready tabs with counts; maintain access to overdue count from either tab.
- Empty Waiting message: “No parties waiting.”
- Empty Table ready message: “No tables awaiting guests.”

| Waiting row | Table ready row |
| --- | --- |
| Position, name, party size, elapsed wait, Mark ready | Name, party size, countdown, Seat |
| Tap row to open details | At expiry: Review label and No-show action |

Overdue entries remain visible. Sort Waiting by original join order and Table ready by readiness time, oldest first. Mark ready and Seat buttons must not accidentally open the row panel.

### 5.3 Party side panel

- Add mode: name, party size, Save, Cancel.
- Edit mode: editable name and party size, status, relevant timestamps, Save, private-link QR code, and permitted actions.
- Editing does not change join order, timestamps, or an existing ready deadline.
- Cancellation and no-show require a short confirmation identifying the party.
- On mobile the side panel may occupy the full viewport.

### 5.4 Summary — `/staff/summary`

Show today’s seated parties, no-shows, and average wait. Display the date and restaurant timezone. No charts, exports, or historical date picker in the MVP.

### 5.5 Guest join — `/join`

One short form with visible labels and inline errors. No account creation. Disable submission while a request is pending and preserve entered values after errors.

### 5.6 Guest status — `/status/<private-token>`

| State | Primary content |
| --- | --- |
| Waiting, multiple ahead | “3 parties ahead” with correct singular/plural |
| Waiting, none ahead | “No parties ahead” |
| Table ready before deadline | “Your table is ready—please return to the host” and `MM:SS` countdown |
| Table ready at/after deadline | “Please check with the host” |
| Seated | “You’re seated. Enjoy your meal!” |
| No-show | “Your party was marked as a no-show. Please see the host.” |
| Cancelled | “Your waitlist entry has been cancelled. Please see the host if you need help.” |
| Invalid/unavailable link | “This waitlist link is unavailable. Please see the host.” |

Waiting content includes name, party size, “Keep this page open and check back for your table,” and “Seating order may vary by party size.” No guest mutation controls or list of other guests.

## 6. Business rules

### 6.1 Input validation

- Name: required, trimmed, 1–80 characters; support Unicode; escape rendered content.
- Party size: required integer from 1–30. This is a configurable implementation limit; larger parties should ask the host.
- Do not deduplicate on name: unrelated parties can share a name.
- Public submissions require the server’s current open setting.

### 6.2 Queue order

Assign a stable, server-generated order when a party joins. Queue position and parties-ahead counts include only parties currently Waiting. Staff can mark any waiting party ready; manual drag-to-reorder is out of scope.

Undoing readiness restores the original order relative to parties still waiting. It does not move already ready or seated parties back into the queue.

### 6.3 State transitions

| From | Action | To | Effect |
| --- | --- | --- | --- |
| Waiting | Mark ready | Table ready | Set ready timestamp and deadline = ready time + 300 seconds |
| Waiting | Cancel | Cancelled | Record terminal timestamp |
| Table ready | Seat | Seated | Record seating timestamp |
| Table ready | Mark no-show | No-show | Record no-show timestamp; default available after expiry |
| Table ready | Cancel | Cancelled | Record cancellation timestamp |
| Table ready | Return to waiting | Waiting | Restore original order; clear current ready timestamp/deadline |
| Terminal state | Undo latest transition | Previous active state | Restore prior active state and timestamps |

Undo is a new recorded event, not deletion of history. It is permitted only if no later change has superseded the target transition. Restoring Table ready preserves its former deadline and may immediately show Review. Summary totals must reflect the restored current state. A later Mark ready after a return to Waiting starts a new five-minute period.

### 6.4 Time and reporting

- Store timestamps in UTC; use the configured restaurant timezone for daily boundaries.
- Today means local midnight through the next local midnight, including daylight-saving changes.
- Seated count: parties currently Seated whose seating timestamp falls today.
- No-show count: parties currently No-show whose no-show timestamp falls today.
- Average wait: mean of `seated_at - joined_at` for parties included in today’s seated count, rounded to the nearest whole minute for display.
- Exclude cancellations, no-shows, and active parties from average wait.
- With no seated parties, display “—” for average wait; counts display zero.
- A party joining before midnight and seated after midnight contributes to the seating day.

### 6.5 Duplicate submissions and guest recovery

- Use an idempotency key for each join attempt so retries and double taps create only one party.
- Retain the current private link in the same browser. Revisiting Join in that browser with an active entry shows a View your entry link instead of a second form.
- Do not claim to prevent duplicates across browsers or devices; staff resolve these manually.
- If a guest loses access, the host can display that party’s private QR code again.
- The on-site QR link can be shared remotely. Location enforcement is outside this MVP.

## 7. Reliability and accessibility

- Poll visible staff and guest pages every five seconds, refresh immediately on page focus, and use the response from successful actions to update the acting staff screen immediately.
- Target other active browsers reflecting a change within six seconds under normal connectivity. Mobile background tabs may update only when reopened.
- Calculate countdowns using the server’s time and deadline; clamp at zero. Expiry is derived from time and requires no scheduled job.
- After a failed refresh, show “Connection lost—status may be out of date,” retain the last known display, and retry. Show when data was last updated.
- Never claim an action succeeded until the server confirms it. Ambiguous request failures can be retried safely using the same idempotency key.
- Use transactions and record versions to reject conflicting staff edits. Show the refreshed state with “This party was updated elsewhere. Please review.”
- Provide visible focus, keyboard operation, readable contrast, and touch targets of at least 44 × 44 CSS pixels for primary actions.
- Label overdue/error states with text as well as color. Expose meaningful status changes accessibly without announcing each countdown second; the application emits no audio.

## 8. Visual direction

Warm white surfaces, charcoal text, teal primary actions, amber review indicators, and red error states. Use clear typography, generous touch spacing, and minimal decoration. Prioritize scanning on staff screens and a large status message on guest screens.

## 9. Technical architecture

- Python/Django application with responsive server-rendered templates and lightweight JavaScript.
- PostgreSQL for persistent data and transactional updates.
- Same-origin endpoints for dashboard actions and periodic status refreshes.
- Framework-managed staff password hashing, sessions, and CSRF protection.
- HTTPS deployment with application server and managed database; hosting provider selected at implementation time.
- Pin supported dependency versions during setup. This specification does not prescribe version numbers.
- No SMS service, audio service, native app, or separate frontend application required.

### 9.1 Data model

| Entity | Fields |
| --- | --- |
| RestaurantSettings | name, timezone, public_signups_open, max_party_size (default 30), grace_seconds (300) |
| Party | UUID, name, party_size, state, stable_queue_order, guest_token_digest, joined_at, ready_at, ready_deadline, seated_at, no_show_at, cancelled_at, version, updated_at |
| PartyEvent | UUID, party_id, action, previous/next state, before/after values needed for undo, timestamp, shared staff account or guest origin, idempotency key |
| Staff account | Django-managed credentials and session data |
| Mutation receipt | unique idempotency key and operation scope, request fingerprint, result reference, creation time |

Terminal timestamps not relevant to the current state are cleared on restoration; the event history retains prior values. Add indexes for active-state ordering and summary timestamps. Validate state-dependent fields server-side.

### 9.2 Endpoint responsibilities

| Endpoint | Purpose |
| --- | --- |
| `POST /api/join` | Validate public sign-up, create party idempotently, return private link |
| `GET /api/status/<token>` | Return only that party’s display data, position, deadline, server time |
| `GET /api/staff/queue` | Return active lists and recent completed entries |
| `POST /api/staff/parties` | Host adds a party |
| `PATCH /api/staff/parties/<id>` | Update name/size with expected version |
| `POST /api/staff/parties/<id>/actions` | Mark ready, seat, no-show, cancel, return, or undo |
| `PATCH /api/staff/settings` | Open/close public sign-ups |
| `GET /api/staff/summary` | Return today’s metrics and timezone |

All staff endpoints require authentication. Mutation endpoints enforce validation, CSRF protection, expected versions where applicable, and idempotency for repeatable requests.

### 9.3 Privacy and operations

- Private links use cryptographically random tokens with at least 128 bits of entropy; store token digests and redact raw tokens from logs.
- Guest pages and status responses use no-store caching and a no-referrer policy; omit third-party analytics from these pages.
- Never expose other guests’ names, private links, or staff-only history in public responses.
- Rate-limit public joins and login attempts using configurable limits suitable for guests sharing restaurant Wi-Fi.
- Keep secrets outside source control. Back up the database and document restore steps.
- Before production, choose and document retention periods for party names, history, completed links, logs, and backups; indefinite retention is not a product requirement.

## 10. Acceptance criteria

1. A valid QR sign-up creates one Waiting entry and opens its private status page without host approval.
2. Repeating the same submission key creates no additional entry.
3. Closing sign-ups rejects a submission from an already-open form and preserves active parties.
4. Staff can add a party while public sign-ups are closed and show its private QR code.
5. If A, B, C are waiting and staff mark B ready, Waiting becomes A, C; C sees one party ahead and B sees the ready message.
6. Mark ready requires no confirmation and starts one server-recorded 300-second deadline; retrying the action does not restart it.
7. At expiry, staff see Review; the party remains Table ready and the guest sees the check-with-host message.
8. Seat and No-show remove the party from active lists and produce the appropriate terminal guest page.
9. Returning B to Waiting restores A, B, C when A and C still wait, without changing their join times.
10. Undoing seating restores the previous ready deadline, removes that party from seated metrics, and preserves audit history.
11. Two concurrent changes cannot silently overwrite one another; the losing request receives current state and a conflict message.
12. Guest pages contain no editing controls and public requests cannot mutate existing parties.
13. Summary calculations handle no data, cancellation exclusion, undo, and seating across midnight correctly.
14. Network loss is visibly indicated; reconnecting refreshes current state without duplicate actions.
15. The main workflow works on phone, tablet, and desktop layouts with keyboard-accessible controls.
16. No screen collects phone numbers or promises text/sound notifications; no messaging service is called.

## 11. Delivery sequence

1. **Interface prototype:** dashboard, side panel, summary, join page, and all guest states using sample data.
2. **Core application:** authentication, database, state transitions, queue ordering, and public/private access.
3. **Operational behavior:** polling, timers, concurrency, undo, closed sign-ups, and summary calculations.
4. **Verification and handoff:** workflow tests, responsive review, deployment configuration, account setup, and backup/restore instructions.

## 12. Out of scope

Reservations; supported remote-join marketing/workflow; table inventory or floor plans; estimated wait times; seating preferences; guest edits/cancellation; phone-based deduplication; texts, sounds, emails, and push notifications; multiple restaurants/locations; individual host accounts or role hierarchies; native apps; advanced analytics and report exports.

## 13. Remaining launch configuration

Implementation can proceed with sample values. Before production, supply the restaurant display name, timezone, hosting/domain, staff credentials, and retention policy. Confirm the default maximum party size against restaurant operations. No further product-scope decision is required to begin prototyping.
