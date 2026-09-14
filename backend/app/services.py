"""Queue rules. No FastAPI or concrete database adapter dependencies."""

import hashlib
import hmac
import json
import math
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from .repository import Repository, UnitOfWork

ACTIVE = ("waiting", "ready")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


class WaitlistService:
    def __init__(self, repository: Repository, clock: Callable[[], datetime], link_secret: bytes):
        self.repository, self.clock, self.link_secret = repository, clock, link_secret

    def now(self):
        return self.clock().astimezone(timezone.utc)

    def token(self, party):
        # A stable keyed digest gives each party a 256-bit opaque token,
        # regenerable by staff and unchanged across database restarts.
        import base64

        raw = hmac.new(self.link_secret, party["id"].encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def settings(self):
        with self.repository.atomic() as tx:
            return tx.settings()

    def party_view(self, tx: UnitOfWork, party, staff=False):
        now = self.now()
        view = {k: party[k] for k in ["id", "name", "size", "state", "version"]}
        view.update(
            joined_at=party["joined_at"].isoformat(),
            deadline=party["deadline"].isoformat() if party["deadline"] else None,
            overdue=party["state"] == "ready" and party["deadline"] <= now,
            ahead=sum(p["state"] == "waiting" and p["order"] < party["order"] for p in tx.parties())
            if party["state"] == "waiting"
            else None,
        )
        if staff:
            for key in ["ready_at", "seated_at", "no_show_at", "cancelled_at", "updated_at"]:
                view[key] = party[key].isoformat() if party[key] else None
            events = tx.events(party["id"])
            view["can_undo"] = bool(
                events and events[-1]["action"] in ["seat", "no_show", "cancel"]
            )
            view["status_url"] = "/status/" + self.token(party)
        return view

    def queue(self):
        with self.repository.atomic() as tx:
            parties = tx.parties()
            waiting = sorted(
                (p for p in parties if p["state"] == "waiting"), key=lambda p: p["order"]
            )
            ready = sorted(
                (p for p in parties if p["state"] == "ready"), key=lambda p: p["ready_at"]
            )
            recent = sorted(
                (
                    p
                    for p in parties
                    if p["state"] not in ACTIVE
                    and p["updated_at"] >= self.now() - timedelta(hours=24)
                ),
                key=lambda p: (p["updated_at"], p["order"]),
                reverse=True,
            )[:20]
            return {
                "waiting": [self.party_view(tx, p, True) for p in waiting],
                "ready": [self.party_view(tx, p, True) for p in ready],
                "recent": [self.party_view(tx, p, True) for p in recent],
                "settings": tx.settings(),
                "server_time": self.now().isoformat(),
            }

    def guest_status(self, token):
        hashed = digest(token)
        with self.repository.atomic() as tx:
            party = next(
                (p for p in tx.parties() if hmac.compare_digest(p["token_digest"], hashed)), None
            )
            if party is None:
                raise ApiError(
                    404, "not_found", "This waitlist link is unavailable. Please see the host."
                )
            return {"party": self.party_view(tx, party), "server_time": self.now().isoformat()}

    def mutate(self, scope, key, body, operation):
        fingerprint = digest(json.dumps(body, sort_keys=True, ensure_ascii=False))
        with self.repository.atomic() as tx:
            receipt_key = scope + ":" + key
            existing = tx.receipt(receipt_key)
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise ApiError(
                        409,
                        "idempotency_conflict",
                        "This request key was already used for different details.",
                    )
                return self.restore_receipt(existing["result"])
            result = operation(tx)
            tx.save_receipt(
                receipt_key, {"fingerprint": fingerprint, "result": self.encode_receipt(tx, result)}
            )
            return result

    def encode_receipt(self, tx, result):
        encoded = deepcopy(result)
        if "status_url" in encoded:
            token_hash = digest(encoded["status_url"].rsplit("/", 1)[-1])
            party = next(p for p in tx.parties() if p["token_digest"] == token_hash)
            return {"join_party_id": party["id"]}
        if "party" in encoded:
            encoded["party"].pop("status_url", None)
        return encoded

    def restore_receipt(self, encoded):
        result = deepcopy(encoded)
        if "join_party_id" in result:
            return {"status_url": "/status/" + self.token({"id": result["join_party_id"]})}
        if "party" in result:
            result["party"]["status_url"] = "/status/" + self.token(result["party"])
        return result

    def add(self, tx, data, public, actor):
        settings = tx.settings()
        if public and not settings["is_open"]:
            raise ApiError(
                409, "waitlist_closed", "The waitlist is currently closed. Please see the host."
            )
        if data["size"] > settings["max_party_size"]:
            raise ApiError(422, "validation_error", "Party size exceeds the restaurant limit.")
        now = self.now()
        party = {
            "id": str(uuid4()),
            "name": data["name"],
            "size": data["size"],
            "state": "waiting",
            "order": tx.next_order(),
            "version": 1,
            "joined_at": now,
            "updated_at": now,
            "ready_at": None,
            "deadline": None,
            "seated_at": None,
            "no_show_at": None,
            "cancelled_at": None,
        }
        party["token_digest"] = digest(self.token(party))
        tx.save_party(party)
        tx.append_event(
            party["id"],
            {"action": "join", "before": None, "after": deepcopy(party), "at": now, "actor": actor},
        )
        return (
            {"status_url": "/status/" + self.token(party)}
            if public
            else {"party": self.party_view(tx, party, True)}
        )

    def change(self, tx, party_id, data, actor, edit=False):
        party = tx.party(party_id)
        if party is None:
            raise ApiError(404, "not_found", "This party is unavailable.")
        if data["version"] != party["version"]:
            raise ApiError(
                409, "version_conflict", "This party was updated elsewhere. Please review."
            )
        before, now = deepcopy(party), self.now()
        action = "edit" if edit else data["action"]
        if edit and party["state"] in ACTIVE:
            party.update(name=data["name"], size=data["size"])
        elif action == "ready" and party["state"] == "waiting":
            party.update(state="ready", ready_at=now, deadline=now + timedelta(seconds=300))
        elif action == "seat" and party["state"] == "ready":
            party.update(state="seated", seated_at=now)
        elif action == "no_show" and party["state"] == "ready" and now >= party["deadline"]:
            party.update(state="no_show", no_show_at=now)
        elif action == "cancel" and party["state"] in ACTIVE:
            party.update(state="cancelled", cancelled_at=now)
        elif action == "return" and party["state"] == "ready":
            party.update(state="waiting", ready_at=None, deadline=None)
        elif action == "undo" and party["state"] not in ACTIVE:
            events = tx.events(party_id)
            if not events or events[-1]["action"] not in ["seat", "no_show", "cancel"]:
                raise ApiError(409, "invalid_transition", "This action can no longer be undone.")
            party = deepcopy(events[-1]["before"])
        else:
            raise ApiError(
                409,
                "invalid_transition",
                "This action is not available for the party’s current status.",
            )
        party.update(version=before["version"] + 1, updated_at=now)
        tx.save_party(party)
        tx.append_event(
            party_id,
            {
                "action": action,
                "before": before,
                "after": deepcopy(party),
                "at": now,
                "actor": actor,
            },
        )
        return {"party": self.party_view(tx, party, True)}

    def update_settings(self, tx, data):
        settings = tx.settings()
        if data["version"] != settings["version"]:
            raise ApiError(
                409, "version_conflict", "Sign-up settings changed elsewhere. Please review."
            )
        settings.update(is_open=data["is_open"], version=settings["version"] + 1)
        tx.save_settings(settings)
        return settings

    def summary(self):
        with self.repository.atomic() as tx:
            settings = tx.settings()
            zone = ZoneInfo(settings["timezone"])
            today = self.now().astimezone(zone).date()
            parties = tx.parties()
            seated = [
                p
                for p in parties
                if p["state"] == "seated" and p["seated_at"].astimezone(zone).date() == today
            ]
            no_shows = [
                p
                for p in parties
                if p["state"] == "no_show" and p["no_show_at"].astimezone(zone).date() == today
            ]
            average = (
                math.floor(
                    sum((p["seated_at"] - p["joined_at"]).total_seconds() / 60 for p in seated)
                    / len(seated)
                    + 0.5
                )
                if seated
                else None
            )
            return {
                "seated": len(seated),
                "no_shows": len(no_shows),
                "average_wait": average,
                "date": today.isoformat(),
                "timezone": settings["timezone"],
            }


class SessionService:
    def __init__(self, repository, clock, username, password, secure_cookie=False):
        self.repository, self.clock, self.username = repository, clock, username
        self.salt = secrets.token_bytes(16)
        self.password_hash = self.hash_password(password) if password else None
        self.secure_cookie = secure_cookie

    def hash_password(self, password):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), self.salt, 200_000)

    def lookup(self, token):
        if not token:
            return None
        with self.repository.atomic() as tx:
            tx.prune_sessions(self.clock())
            return tx.session(digest(token))

    def create(self, username=None, old_token=None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session = {
            "username": username,
            "csrf_token": csrf,
            "expires_at": self.clock() + timedelta(hours=12),
        }
        with self.repository.atomic() as tx:
            tx.prune_sessions(self.clock())
            if old_token:
                tx.delete_session(digest(old_token))
            tx.save_session(digest(token), session)
        return token, session

    def delete(self, token):
        with self.repository.atomic() as tx:
            tx.delete_session(digest(token))

    def authenticate(self, username, password):
        if self.password_hash is None:
            raise ApiError(
                503,
                "credentials_not_configured",
                "Configure TABLETURN_STAFF_PASSWORD before staff sign-in.",
            )
        valid = hmac.compare_digest(self.hash_password(password), self.password_hash)
        if not valid or not hmac.compare_digest(username.encode(), self.username.encode()):
            raise ApiError(401, "invalid_credentials", "The username or password is incorrect.")

    def rate(self, category, peer, limit):
        window = int(self.clock().timestamp() // 600)
        with self.repository.atomic() as tx:
            count = tx.increment_rate(digest(category + ":" + peer), window)
        if count > limit:
            raise ApiError(
                429, "rate_limited", "Too many attempts. Please try again in a few minutes."
            )
