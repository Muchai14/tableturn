# TableTurn

A mobile-friendly restaurant waitlist manager for one restaurant, with a shared staff dashboard and private guest status pages.

## Project specification

Read [_docs/specs.md](_docs/specs.md) for the full MVP requirements, screens, workflows, data model, and acceptance criteria. [AGENTS.md](AGENTS.md) provides guidance for future development.

This repository starts with project documentation. The existing local application implementation is not included in this initial commit.

## MVP scope

- Guests join at the restaurant by QR code or through a host, providing a name and party size.
- Hosts manage Waiting and Table ready lists, choose seating order, and edit party details.
- Guests see their queue position on a private, view-only page.
- Mark ready starts a five-minute countdown. Overdue parties remain available for staff review.
- Staff can seat, cancel, mark no-show, and undo supported actions.
- Staff manually open or close sign-ups without clearing the active queue.
- A daily summary shows seated parties, no-shows, and average join-to-seat wait.

No texts, phone-number collection, sound alerts, reservations, table maps, multiple locations, or guest editing.

## Planned architecture

Python and Django, PostgreSQL, and responsive server-rendered pages with lightweight JavaScript. The server owns queue state and timestamps; visible pages refresh periodically.

## Development status

The specification is ready for implementation planning. This documentation-only repository has no runnable application or test commands yet. Add accurate setup and verification instructions when implementation is imported.

Before restaurant launch, configure the restaurant name and timezone, hosting and domain, production staff credentials, database backups, and data retention.
