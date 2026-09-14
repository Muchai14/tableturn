from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
import pytest
import yaml

from app.main import create_app
from conftest import bootstrap, sign_in

CONTRACT = yaml.safe_load((Path(__file__).parents[2] / "openapi.yaml").read_text())


def check(response, path, method="get", status=200):
    assert response.status_code == status, response.text
    schema = CONTRACT["paths"][path][method]["responses"][str(status)]["content"][
        "application/json"
    ]["schema"]
    Draft202012Validator({**schema, "components": CONTRACT["components"]}).validate(response.json())
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def mutation(client, path, data, method="post", key=None):
    return getattr(client, method)(
        path, json=data, headers={"Idempotency-Key": key or str(uuid4())}
    )


def add(host, name="Alex", size=2):
    return check(
        mutation(host, "/api/staff/parties", {"name": name, "size": size}),
        "/api/staff/parties",
        "post",
        201,
    )["party"]


def action(host, party, value, key=None, status=200):
    r = mutation(
        host,
        f"/api/staff/parties/{party['id']}/actions",
        {"action": value, "version": party["version"]},
        key=key,
    )
    d = check(r, "/api/staff/parties/{party_id}/actions", "post", status)
    return d["party"] if status == 200 else d


def queue(host):
    return check(host.get("/api/staff/queue"), "/api/staff/queue")


def summary(host):
    return check(host.get("/api/staff/summary"), "/api/staff/summary")


def test_contract_is_valid_openapi():
    validate(CONTRACT)


def test_health_and_public_settings(client):
    assert check(client.get("/health"), "/health") == {"status": "ok", "storage": "sqlalchemy"}
    d = check(client.get("/api/public-settings"), "/api/public-settings")
    assert d["is_open"] is True
    assert d["grace_seconds"] == 300


def test_session_login_rotation_logout(client):
    first = check(bootstrap(client), "/api/auth/session")
    old_cookie = client.cookies["tableturn_session"]
    assert not first["authenticated"]
    sign_in(client)
    assert client.cookies["tableturn_session"] != old_cookie
    assert check(client.get("/api/auth/session"), "/api/auth/session")["authenticated"]
    check(client.post("/api/auth/logout"), "/api/auth/logout", "post")
    assert client.get("/api/staff/queue").status_code == 401


def test_wrong_password_and_csrf_are_rejected(client):
    bootstrap(client)
    r = client.post("/api/auth/login", json={"username": "host", "password": "wrong"})
    check(r, "/api/auth/login", "post", 401)
    r = client.post(
        "/api/auth/login",
        json={"username": "host", "password": "test-only-password"},
        headers={"X-CSRF-Token": "wrong"},
    )
    check(r, "/api/auth/login", "post", 403)


def test_public_join_requires_csrf(client):
    check(mutation(client, "/api/join", {"name": "A", "size": 2}), "/api/join", "post", 403)


def test_join_idempotency_and_private_status(client):
    bootstrap(client)
    payload = {"name": "  Alex  ", "size": 2}
    a = check(mutation(client, "/api/join", payload, key="repeat-key-1"), "/api/join", "post", 201)
    b = check(mutation(client, "/api/join", payload, key="repeat-key-1"), "/api/join", "post", 201)
    assert a == b
    status = check(client.get("/api" + a["status_url"]), "/api/status/{token}")
    assert status["party"]["name"] == "Alex"
    assert status["party"]["ahead"] == 0
    assert "status_url" not in status["party"]
    assert "can_undo" not in status["party"]
    assert status["party"]["state"] == "waiting"


def test_duplicate_key_with_changed_payload_conflicts(client):
    bootstrap(client)
    mutation(client, "/api/join", {"name": "Alex", "size": 2}, key="same-request")
    check(
        mutation(client, "/api/join", {"name": "Alex", "size": 3}, key="same-request"),
        "/api/join",
        "post",
        409,
    )


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "size": 2},
        {"name": "   ", "size": 2},
        {"name": "A" * 81, "size": 2},
        {"name": "A", "size": 0},
        {"name": "A", "size": 31},
        {"name": "A", "size": 2.5},
        {"name": "A", "size": True},
        {"name": "A", "size": "2"},
        {"name": "A"},
        {"name": "A", "size": 2, "phone": "123"},
    ],
)
def test_join_validation(client, body):
    bootstrap(client)
    check(mutation(client, "/api/join", body), "/api/join", "post", 422)


def test_missing_idempotency_key(client):
    bootstrap(client)
    check(client.post("/api/join", json={"name": "A", "size": 2}), "/api/join", "post", 422)


def test_private_status_is_read_only_and_isolated(host):
    a = add(host, "Alex")
    add(host, "Someone else")
    with TestClient(host.app) as guest:
        d = check(guest.get("/api" + a["status_url"]), "/api/status/{token}")
        assert "Someone else" not in str(d)
        assert guest.post("/api" + a["status_url"], json={"state": "seated"}).status_code == 405
        check(guest.get("/api/status/invalid-token"), "/api/status/{token}", status=404)


def test_every_staff_endpoint_requires_login(client):
    assert client.get("/api/staff/queue").status_code == 401
    assert client.get("/api/staff/summary").status_code == 401
    assert mutation(client, "/api/staff/parties", {"name": "A", "size": 2}).status_code == 401
    assert (
        mutation(
            client, "/api/staff/settings", {"is_open": False, "version": 1}, method="patch"
        ).status_code
        == 401
    )
    unknown = str(uuid4())
    assert (
        mutation(
            client,
            "/api/staff/parties/" + unknown,
            {"name": "A", "size": 2, "version": 1},
            method="patch",
        ).status_code
        == 401
    )
    assert (
        mutation(
            client, "/api/staff/parties/" + unknown + "/actions", {"action": "ready", "version": 1}
        ).status_code
        == 401
    )


def test_staff_mutations_require_csrf_and_trusted_origin(host):
    r = host.post(
        "/api/staff/parties",
        json={"name": "A", "size": 2},
        headers={"Idempotency-Key": "request-key", "X-CSRF-Token": "wrong"},
    )
    check(r, "/api/staff/parties", "post", 403)
    r = host.post(
        "/api/staff/parties",
        json={"name": "A", "size": 2},
        headers={"Idempotency-Key": "request-key", "Origin": "https://attacker.example"},
    )
    check(r, "/api/staff/parties", "post", 403)


def test_close_preserves_parties_blocks_public_and_allows_staff(host):
    a = add(host)
    d = check(
        mutation(host, "/api/staff/settings", {"is_open": False, "version": 1}, method="patch"),
        "/api/staff/settings",
        "patch",
    )
    assert not d["is_open"]
    check(mutation(host, "/api/join", {"name": "Guest", "size": 2}), "/api/join", "post", 409)
    add(host, "Host-added")
    assert queue(host)["waiting"][0]["id"] == a["id"]
    check(
        mutation(host, "/api/staff/settings", {"is_open": True, "version": 1}, method="patch"),
        "/api/staff/settings",
        "patch",
        409,
    )


def test_queue_order_ready_timer_and_return(host, clock):
    a, b, c = [add(host, n) for n in ["A", "B", "C"]]
    ready = action(host, b, "ready", key="ready-request")
    assert datetime.fromisoformat(ready["deadline"]) - clock.value == __import__(
        "datetime"
    ).timedelta(seconds=300)
    clock.advance(seconds=20)
    assert action(host, b, "ready", key="ready-request") == ready
    q = queue(host)
    assert [p["name"] for p in q["waiting"]] == ["A", "C"]
    assert q["waiting"][1]["ahead"] == 1
    action(host, ready, "return")
    q = queue(host)
    assert [p["name"] for p in q["waiting"]] == ["A", "B", "C"]
    assert q["waiting"][1]["deadline"] is None
    assert q["waiting"][1]["joined_at"] == b["joined_at"]


def test_expiry_is_review_not_automatic_no_show(host, clock):
    p = action(host, add(host), "ready")
    action(host, p, "no_show", status=409)
    clock.advance(seconds=300)
    q = queue(host)
    assert len(q["ready"]) == 1
    assert q["ready"][0]["overdue"]
    assert q["ready"][0]["state"] == "ready"
    p = action(host, p, "no_show")
    assert p["state"] == "no_show"
    assert summary(host)["no_shows"] == 1


def test_edit_preserves_timer_and_stale_version_is_rejected(host):
    p = action(host, add(host), "ready")
    data = {"name": "Updated", "size": 4, "version": p["version"]}
    r = mutation(host, "/api/staff/parties/" + p["id"], data, method="patch")
    updated = check(r, "/api/staff/parties/{party_id}", "patch")["party"]
    assert updated["deadline"] == p["deadline"]
    assert updated["joined_at"] == p["joined_at"]
    assert updated["version"] == p["version"] + 1
    action(host, p, "seat", status=409)


def test_seating_undo_and_summary(host, clock):
    p = add(host)
    clock.advance(minutes=12)
    p = action(host, p, "ready")
    original_deadline = p["deadline"]
    clock.advance(minutes=3)
    p = action(host, p, "seat")
    assert summary(host)["average_wait"] == 15
    assert summary(host)["seated"] == 1
    clock.advance(minutes=3)
    p = action(host, p, "undo")
    assert p["state"] == "ready"
    assert p["deadline"] == original_deadline and p["overdue"]
    assert p["seated_at"] is None
    assert summary(host)["seated"] == 0 and summary(host)["average_wait"] is None
    action(host, p, "undo", status=409)


def test_cancel_undo_and_invalid_transitions(host):
    p = add(host)
    action(host, p, "seat", status=409)
    p = action(host, p, "cancel")
    assert queue(host)["recent"][0]["state"] == "cancelled"
    p = action(host, p, "undo")
    assert p["state"] == "waiting" and p["cancelled_at"] is None


def test_unknown_party_and_action(host):
    r = mutation(
        host, "/api/staff/parties/" + str(uuid4()) + "/actions", {"action": "ready", "version": 1}
    )
    check(r, "/api/staff/parties/{party_id}/actions", "post", 404)
    p = add(host)
    r = mutation(
        host, "/api/staff/parties/" + p["id"] + "/actions", {"action": "delete", "version": 1}
    )
    check(r, "/api/staff/parties/{party_id}/actions", "post", 422)


def test_summary_cross_midnight_and_excludes_cancelled(host, clock):
    clock.value = datetime(2026, 9, 14, 6, 50, tzinfo=timezone.utc)  # Sep 13 23:50 LA
    p = action(host, add(host), "ready")
    action(host, add(host, "Cancelled"), "cancel")
    clock.advance(minutes=20)
    action(host, p, "seat")
    d = summary(host)
    assert d == {
        "seated": 1,
        "no_shows": 0,
        "average_wait": 20,
        "date": "2026-09-14",
        "timezone": "America/Los_Angeles",
    }
    clock.advance(days=1)
    sign_in(host)
    assert summary(host)["seated"] == 0


def test_recent_is_limited_to_twenty_and_twenty_four_hours(host, clock):
    for i in range(22):
        action(host, add(host, f"Party {i}"), "cancel")
        clock.advance(seconds=1)
    recent = queue(host)["recent"]
    assert len(recent) == 20 and recent[0]["name"] == "Party 21"
    clock.advance(hours=25)
    sign_in(host)
    assert queue(host)["recent"] == []


def test_expired_session_is_rejected(host, clock):
    clock.advance(hours=13)
    assert host.get("/api/staff/queue").status_code == 401
    assert not check(bootstrap(host), "/api/auth/session")["authenticated"]


def test_separate_databases_are_isolated(host, clock, tmp_path):
    add(host)
    with TestClient(
        create_app(
            database_url=f"sqlite:///{tmp_path / 'other.db'}",
            clock=clock,
            staff_username="host",
            staff_password="test-only-password",
        )
    ) as other:
        sign_in(other)
        assert queue(other)["waiting"] == []


def test_rate_limits(clock, tmp_path):
    application = create_app(
        clock=clock,
        staff_username="host",
        staff_password="test-only-password",
        database_url=f"sqlite:///{tmp_path / 'rate.db'}",
        join_limit=1,
        login_limit=1,
    )
    with TestClient(application) as c:
        bootstrap(c)
        check(mutation(c, "/api/join", {"name": "A", "size": 2}), "/api/join", "post", 201)
        check(mutation(c, "/api/join", {"name": "B", "size": 2}), "/api/join", "post", 429)
        bad = {"username": "host", "password": "wrong"}
        assert c.post("/api/auth/login", json=bad).status_code == 401
        check(c.post("/api/auth/login", json=bad), "/api/auth/login", "post", 429)


def test_concurrent_replay_creates_only_one_party(host, application):
    cookies = dict(host.cookies)
    csrf = host.headers["X-CSRF-Token"]

    def work(_):
        with TestClient(application) as c:
            c.cookies.update(cookies)
            c.headers["X-CSRF-Token"] = csrf
            return check(
                mutation(c, "/api/staff/parties", {"name": "A", "size": 2}, key="concurrent-key"),
                "/api/staff/parties",
                "post",
                201,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(work, range(2)))
    assert results[0] == results[1]
    assert len(queue(host)["waiting"]) == 1


def test_concurrent_version_changes_have_one_winner(host, application):
    p = add(host)
    cookies = dict(host.cookies)
    csrf = host.headers["X-CSRF-Token"]

    def work(value):
        with TestClient(application) as c:
            c.cookies.update(cookies)
            c.headers["X-CSRF-Token"] = csrf
            return mutation(
                c, "/api/staff/parties/" + p["id"] + "/actions", {"action": value, "version": 1}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(work, ["ready", "cancel"]))
    assert sorted(results) == [200, 409]


def test_served_contract_and_route_coverage(client):
    assert client.get("/openapi.json").json() == CONTRACT
    actual = {
        (r.path, m.lower())
        for r in client.app.routes
        for m in getattr(r, "methods", [])
        if r.path.startswith("/api/") or r.path == "/health"
    }
    expected = {(p, m) for p, methods in CONTRACT["paths"].items() for m in methods}
    assert actual == expected


def test_retry_receipts_do_not_store_private_links(host, application):
    p = check(
        mutation(host, "/api/staff/parties", {"name": "A", "size": 2}, key="privacy-test"),
        "/api/staff/parties",
        "post",
        201,
    )["party"]
    with application.state.repository.atomic() as tx:
        receipt = tx.receipt("staff:add:privacy-test")
        assert p["status_url"] not in str(receipt)
        stored = tx.party(p["id"])
        assert p["status_url"].split("/")[-1] not in str(stored)


def test_cookie_flags_and_rotated_session_cannot_be_reused(client, application):
    response = bootstrap(client)
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header and "samesite=lax" in cookie_header
    old = client.cookies["tableturn_session"]
    sign_in(client)
    with TestClient(application) as stale:
        stale.cookies.set("tableturn_session", old)
        assert not stale.get("/api/auth/session").json()["authenticated"]


def test_dst_fall_back_summary_uses_local_calendar_date(host, clock):
    clock.value = datetime(2026, 11, 1, 8, 30, tzinfo=timezone.utc)  # 01:30 PDT
    sign_in(host)
    p = action(host, add(host), "ready")
    clock.advance(hours=1)  # 01:30 PST, still Nov 1
    action(host, p, "seat")
    assert summary(host)["date"] == "2026-11-01"
    assert summary(host)["average_wait"] == 60


def test_no_show_undo_updates_no_show_count(host, clock):
    p = action(host, add(host), "ready")
    clock.advance(minutes=5)
    p = action(host, p, "no_show")
    assert summary(host)["no_shows"] == 1
    p = action(host, p, "undo")
    assert p["state"] == "ready" and p["overdue"]
    assert summary(host)["no_shows"] == 0
