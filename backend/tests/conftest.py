from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from app.database import SQLAlchemyRepository


class Clock:
    def __init__(self):
        self.value = datetime(2026, 9, 14, 6, 30, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


def bootstrap(client):
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


def sign_in(client):
    bootstrap(client)
    response = client.post(
        "/api/auth/login", json={"username": "host", "password": "test-only-password"}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def application(clock, tmp_path):
    repository = SQLAlchemyRepository(f"sqlite:///{tmp_path / 'test.db'}")
    yield create_app(
        repository=repository,
        clock=clock,
        staff_username="host",
        staff_password="test-only-password",
    )
    repository.close()


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


@pytest.fixture
def host(client):
    return sign_in(client)
