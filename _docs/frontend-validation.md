# Frontend integration verification

Verified the frontend on port 5173 against FastAPI on port 8001.

Browser checks passed: staff sign-in, adding and editing a fictional party, private guest position, marking ready with automatic guest countdown update, and seating with guest confirmation and daily summary update. The narrow staff layout provides Waiting and Table ready tabs.

Seven API client tests pass, covering origin/cookies, CSRF bootstrap and rotation, ambiguous retry idempotency, CSRF recovery, authentication, simultaneous bootstrap, and timeouts. Static build succeeds. Backend review reports 40 endpoint tests passing. No-show expiry is covered by endpoint tests rather than a five-minute browser wait.

The backend mock database resets on restart. Browser verification used fictional data.
