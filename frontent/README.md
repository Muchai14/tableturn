# TableTurn frontend

Interactive, responsive staff and guest pages backed by the FastAPI API. No frontend queue mock remains; browser storage remembers only a private guest link on this device. The backend uses persistent SQLAlchemy storage, defaulting to SQLite.

## Run

Start the backend using its README, then from this directory with Node.js 20+:

```sh
npm run dev
```

No npm dependencies need installing. Open http://127.0.0.1:5173/staff or http://127.0.0.1:5173/join. Staff credentials are configured on the backend.

## API connection

All HTTP requests live in `src/api.js`. The default API origin is `http://<frontend-hostname>:8001`, so opening the frontend at `127.0.0.1:5173` uses **http://127.0.0.1:8001**. Requests include session cookies, CSRF tokens, mutation idempotency keys, and record versions. Queue and guest pages poll every five seconds.

Override the origin when starting the development server or building:

```sh
TABLETURN_API_BASE_URL=http://127.0.0.1:8001 npm run dev
```

Use matching hostnames for frontend and backend in local development so cookies work. Configure the backend CORS origins to allow the frontend origin. For a static deployment, set `public/runtime-config.js` before building or provide the environment variable at build time. Private status links open on the frontend origin.

## Checks and build

```sh
npm test
npm run build
```

The build outputs static files in `dist/`. Serve the generated route directories and rewrite `/status/*` to `/guest.html`; `_redirects` includes that rule for compatible static hosts. Runtime configuration must point to the deployed API.

Features include staff login/logout, host additions and editing, ready/seat/return/cancel/no-show/undo actions, public sign-up control, daily summary, guest joining, private status pages, and locally generated QR codes. No texts or phone numbers are used.
