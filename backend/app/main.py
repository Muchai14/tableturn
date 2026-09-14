"""FastAPI transport for the contract in the repository root's openapi.yaml."""

import hmac
import os
import secrets
from copy import deepcopy
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml
from fastapi import Depends, FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .repository import Repository
from .database import SQLAlchemyRepository
from .schemas import ActionInput, LoginInput, PartyEdit, PartyInput, SettingsInput
from .services import ApiError, SessionService, WaitlistService

COOKIE = "tableturn_session"
RequestKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=80)]
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"


def create_app(
    *,
    repository: Repository | None = None,
    database_url: str | None = None,
    clock=None,
    staff_username=None,
    staff_password=None,
    restaurant_name=None,
    restaurant_timezone=None,
    secure_cookie=None,
    allowed_origins=None,
    join_limit=120,
    login_limit=20,
):
    clock = clock or (lambda: datetime.now(timezone.utc))
    restaurant_timezone = restaurant_timezone or os.getenv(
        "RESTAURANT_TIMEZONE", "America/Los_Angeles"
    )
    ZoneInfo(restaurant_timezone)
    owns_repository = repository is None
    repository = repository or SQLAlchemyRepository(
        database_url
        or os.getenv(
            "DATABASE_URL", "sqlite:///" + str(Path(__file__).resolve().parents[1] / "tableturn.db")
        ),
        restaurant_name or os.getenv("RESTAURANT_NAME", "TableTurn Restaurant"),
        restaurant_timezone,
    )
    sessions = SessionService(
        repository,
        clock,
        staff_username or os.getenv("TABLETURN_STAFF_USERNAME", "host"),
        staff_password if staff_password is not None else os.getenv("TABLETURN_STAFF_PASSWORD"),
        secure_cookie if secure_cookie is not None else os.getenv("COOKIE_SECURE") == "1",
    )
    link_secret = os.getenv("TABLETURN_LINK_SECRET")
    if link_secret is not None and len(link_secret) < 32:
        raise ValueError("TABLETURN_LINK_SECRET must contain at least 32 characters.")
    service = WaitlistService(
        repository,
        clock,
        link_secret.encode()
        if link_secret
        else (
            repository.link_secret()
            if isinstance(repository, SQLAlchemyRepository)
            else secrets.token_bytes(32)
        ),
    )
    origins = (
        allowed_origins
        if allowed_origins is not None
        else [
            s.strip()
            for s in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(
                ","
            )
            if s.strip()
        ]
    )
    if "*" in origins:
        raise ValueError("Use explicit CORS origins with cookie authentication.")

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owns_repository:
                repository.close()

    app = FastAPI(title="TableTurn API", version="1.0.0", redirect_slashes=False, lifespan=lifespan)
    app.state.repository = repository
    contract = yaml.safe_load(CONTRACT_PATH.read_text())
    app.openapi = lambda: deepcopy(contract)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def private_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
            }
        )
        return response

    @app.exception_handler(ApiError)
    async def domain_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
            headers={"Retry-After": "600"} if exc.status == 429 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never include the input values (possibly credentials) in error responses.
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request fields or headers. Check the API specification.",
                }
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {"error": {"code": "http_error", "message": str(exc.detail)}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    def guard(request: Request, staff=False, csrf=False):
        session = sessions.lookup(request.cookies.get(COOKIE))
        if staff and (session is None or not session["username"]):
            raise ApiError(401, "authentication_required", "Please sign in to continue.")
        if csrf:
            origin = request.headers.get("origin")
            if origin and origin not in [*origins, str(request.base_url).rstrip("/")]:
                raise ApiError(403, "origin_rejected", "This request origin is not allowed.")
            provided = request.headers.get("x-csrf-token", "")
            if session is None or not hmac.compare_digest(
                provided.encode(), session["csrf_token"].encode()
            ):
                raise ApiError(403, "csrf_rejected", "A valid session and CSRF token are required.")
        return session

    def staff_read(request: Request):
        return guard(request, staff=True)

    def staff_write(request: Request):
        return guard(request, staff=True, csrf=True)

    def public_write(request: Request):
        return guard(request, csrf=True)

    def cookie(response, token):
        response.set_cookie(
            COOKIE,
            token,
            max_age=43200,
            httponly=True,
            secure=sessions.secure_cookie,
            samesite="lax",
            path="/",
        )

    def session_view(session):
        return {
            "authenticated": bool(session["username"]),
            "username": session["username"],
            "csrf_token": session["csrf_token"],
        }

    def peer(request):
        # The mock does not trust arbitrary forwarded IP headers.
        return request.client.host if request.client else "unknown"

    @app.get("/health", operation_id="health")
    def health():
        return {"status": "ok", "storage": getattr(repository, "storage", "memory")}

    @app.get("/api/auth/session", operation_id="getSession")
    def get_session(request: Request, response: Response):
        session = sessions.lookup(request.cookies.get(COOKIE))
        if session is None:
            token, session = sessions.create()
            cookie(response, token)
        return session_view(session)

    @app.post("/api/auth/login", operation_id="login")
    def login(
        request: Request, response: Response, data: LoginInput, session=Depends(public_write)
    ):
        sessions.rate("login", peer(request), login_limit)
        sessions.authenticate(data.username, data.password)
        token, session = sessions.create(sessions.username, old_token=request.cookies.get(COOKIE))
        cookie(response, token)
        return session_view(session)

    @app.post("/api/auth/logout", operation_id="logout")
    def logout(request: Request, response: Response, session=Depends(staff_write)):
        sessions.delete(request.cookies[COOKIE])
        response.delete_cookie(
            COOKIE, path="/", secure=sessions.secure_cookie, httponly=True, samesite="lax"
        )
        return {"ok": True}

    @app.get("/api/public-settings", operation_id="publicSettings")
    def public_settings():
        return service.settings()

    @app.post("/api/join", operation_id="join", status_code=201)
    def join(request: Request, data: PartyInput, key: RequestKey, session=Depends(public_write)):
        sessions.rate("join", peer(request), join_limit)
        body = data.model_dump()
        # Bind public retry receipts to the browser session to prevent receipt lookup by other guests.
        scope = "join:" + session["csrf_token"]
        return service.mutate(scope, key, body, lambda tx: service.add(tx, body, True, "guest"))

    @app.get("/api/status/{token}", operation_id="guestStatus")
    def guest_status(token: str):
        return service.guest_status(token)

    @app.get("/api/staff/queue", operation_id="staffQueue")
    def staff_queue(session=Depends(staff_read)):
        return service.queue()

    @app.post("/api/staff/parties", operation_id="addParty", status_code=201)
    def add_party(data: PartyInput, key: RequestKey, session=Depends(staff_write)):
        body = data.model_dump()
        return service.mutate(
            "staff:add", key, body, lambda tx: service.add(tx, body, False, session["username"])
        )

    @app.patch("/api/staff/parties/{party_id}", operation_id="editParty")
    def edit_party(party_id: UUID, data: PartyEdit, key: RequestKey, session=Depends(staff_write)):
        body = data.model_dump()
        return service.mutate(
            "party:edit:" + str(party_id),
            key,
            body,
            lambda tx: service.change(tx, str(party_id), body, session["username"], True),
        )

    @app.post("/api/staff/parties/{party_id}/actions", operation_id="partyAction")
    def party_action(
        party_id: UUID, data: ActionInput, key: RequestKey, session=Depends(staff_write)
    ):
        body = data.model_dump()
        return service.mutate(
            "party:action:" + str(party_id),
            key,
            body,
            lambda tx: service.change(tx, str(party_id), body, session["username"]),
        )

    @app.patch("/api/staff/settings", operation_id="updateSettings")
    def update_settings(data: SettingsInput, key: RequestKey, session=Depends(staff_write)):
        body = data.model_dump()
        return service.mutate("settings", key, body, lambda tx: service.update_settings(tx, body))

    @app.get("/api/staff/summary", operation_id="dailySummary")
    def daily_summary(session=Depends(staff_read)):
        return service.summary()

    return app


app = create_app()
