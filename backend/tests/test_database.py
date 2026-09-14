"""Durability and cross-connection behavior for the SQLAlchemy adapter."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from app.database import SQLAlchemyRepository
from app.services import ApiError, SessionService, WaitlistService

NOW = datetime(2026, 9, 14, 6, 30, tzinfo=timezone.utc)


def service(repository):
    return WaitlistService(repository, lambda: NOW, repository.link_secret())


def add(waitlist, key="add-party"):
    body = {"name": "Sample party", "size": 3}
    return waitlist.mutate("host", key, body, lambda tx: waitlist.add(tx, body, False, "host"))


@pytest.fixture
def database_url(tmp_path):
    return "sqlite:///" + str(tmp_path / "tableturn.sqlite3")


def test_reopen_preserves_queue_links_sessions_receipts_and_undo(database_url):
    repository = SQLAlchemyRepository(database_url)
    waitlist = service(repository)
    joined = add(waitlist)
    party = joined["party"]
    secret = repository.link_secret()
    sessions = SessionService(repository, lambda: NOW, "host", "test-password")
    cookie, session = sessions.create("host")
    with repository.atomic() as tx:
        settings = tx.settings()
        settings.update(is_open=False, version=2)
        tx.save_settings(settings)
    ready = {"action": "ready", "version": 1}
    waitlist.mutate(
        "host", "ready", ready, lambda tx: waitlist.change(tx, party["id"], ready, "host")
    )
    seat = {"action": "seat", "version": 2}
    waitlist.mutate("host", "seat", seat, lambda tx: waitlist.change(tx, party["id"], seat, "host"))
    repository.close()

    reopened = SQLAlchemyRepository(database_url)
    try:
        restored = service(reopened)
        assert reopened.link_secret() == secret
        assert not restored.settings()["is_open"]
        assert restored.settings()["version"] == 2
        assert add(restored) == joined
        token = party["status_url"].rsplit("/", 1)[-1]
        assert restored.guest_status(token)["party"]["state"] == "seated"
        assert restored.summary()["seated"] == 1
        assert (
            SessionService(reopened, lambda: NOW, "host", "test-password").lookup(cookie) == session
        )
        with reopened.atomic() as tx:
            saved = tx.party(party["id"])
            assert saved["joined_at"] == NOW
            assert saved["joined_at"].tzinfo is not None
            assert [event["action"] for event in tx.events(party["id"])] == [
                "join",
                "ready",
                "seat",
            ]
        undo = {"action": "undo", "version": 3}
        restored.mutate(
            "host", "undo", undo, lambda tx: restored.change(tx, party["id"], undo, "host")
        )
        assert restored.queue()["ready"][0]["can_undo"] is False
        assert restored.summary()["seated"] == 0
    finally:
        reopened.close()


def test_failed_transaction_rolls_back_all_writes(database_url):
    repository = SQLAlchemyRepository(database_url)
    try:
        waitlist = service(repository)
        with pytest.raises(RuntimeError, match="injected failure"):
            with repository.atomic() as tx:
                rolled_back = waitlist.add(tx, {"name": "Rollback", "size": 2}, False, "host")[
                    "party"
                ]["id"]
                settings = tx.settings()
                settings["is_open"] = False
                tx.save_settings(settings)
                tx.save_receipt("rolled-back", {"fingerprint": "abc", "result": {}})
                tx.save_session(
                    "rolled-back", {"username": "host", "csrf_token": "test", "expires_at": NOW}
                )
                tx.increment_rate("rolled-back", 1)
                raise RuntimeError("injected failure")
        with repository.atomic() as tx:
            assert tx.parties() == []
            assert tx.events(rolled_back) == []
            assert tx.settings()["is_open"] is True
            assert tx.receipt("rolled-back") is None
            assert tx.session("rolled-back") is None
            assert tx.increment_rate("rolled-back", 1) == 1
            assert tx.next_order() == 1
    finally:
        repository.close()


def race(functions):
    barrier = Barrier(len(functions))

    def run(function):
        barrier.wait(timeout=10)
        return function()

    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(run, functions))


def test_independent_engines_replay_same_key_once(database_url):
    first, second = SQLAlchemyRepository(database_url), SQLAlchemyRepository(database_url)
    try:
        services = [service(first), service(second)]
        results = race([lambda s=s: add(s) for s in services])
        assert results[0] == results[1]
        with first.atomic() as tx:
            assert len(tx.parties()) == 1
            assert len(tx.events(results[0]["party"]["id"])) == 1
    finally:
        first.close()
        second.close()


def test_independent_engines_version_race_has_one_winner(database_url):
    first, second = SQLAlchemyRepository(database_url), SQLAlchemyRepository(database_url)
    try:
        services = [service(first), service(second)]
        party = add(services[0])["party"]

        def change(waitlist, key):
            data = {"action": "ready", "version": 1}
            try:
                waitlist.mutate(
                    "host", key, data, lambda tx: waitlist.change(tx, party["id"], data, "host")
                )
                return "success"
            except ApiError as error:
                assert error.status == 409
                return error.code

        results = race(
            [lambda: change(services[0], "first"), lambda: change(services[1], "second")]
        )
        assert sorted(results) == ["success", "version_conflict"]
        with first.atomic() as tx:
            assert tx.party(party["id"])["version"] == 2
            assert len(tx.events(party["id"])) == 2
    finally:
        first.close()
        second.close()


def test_independent_engines_share_rates_and_unique_queue_order(database_url):
    first, second = SQLAlchemyRepository(database_url), SQLAlchemyRepository(database_url)
    try:
        services = [service(first), service(second)]
        race([lambda: add(services[0], "one"), lambda: add(services[1], "two")])
        with first.atomic() as tx:
            assert sorted(p["order"] for p in tx.parties()) == [1, 2]

        def increment(repository):
            with repository.atomic() as tx:
                return tx.increment_rate("shared", 100)

        assert sorted(race([lambda: increment(first), lambda: increment(second)])) == [1, 2]
        with second.atomic() as tx:
            assert tx.increment_rate("shared", 101) == 1
    finally:
        first.close()
        second.close()


def test_app_restart_preserves_guest_link_session_and_idempotency(database_url, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from conftest import sign_in

    monkeypatch.delenv("TABLETURN_LINK_SECRET", raising=False)

    def application():
        return create_app(database_url=database_url, staff_password="test-only-password")

    with TestClient(application()) as first:
        sign_in(first)
        headers = {"X-CSRF-Token": first.headers["X-CSRF-Token"], "Idempotency-Key": "restart-join"}
        body = {"name": "Durable guest", "size": 2}
        response = first.post("/api/join", json=body, headers=headers)
        assert response.status_code == 201
        original = response.json()
        cookies = dict(first.cookies)
    with TestClient(application()) as second:
        second.cookies.update(cookies)
        assert second.get("/health").json()["storage"] == "sqlalchemy"
        assert second.get("/api/auth/session").json()["authenticated"]
        assert second.post("/api/join", json=body, headers=headers).json() == original
        assert second.get("/api" + original["status_url"]).json()["party"]["name"] == body["name"]
        assert len(second.get("/api/staff/queue").json()["waiting"]) == 1


@pytest.mark.parametrize(
    "url", ["sqlite://", "sqlite:///:memory:", "sqlite:///file:test?mode=memory&uri=true"]
)
def test_durable_adapter_rejects_ephemeral_database(url):
    with pytest.raises(ValueError, match="persistent"):
        SQLAlchemyRepository(url)
