"""Self sign-up, and the gates around it.

An operator account can read every patient record, so the interesting cases
here are the refusals: signup turned off, and signup behind a shared code.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from drscreen.config import Settings
from drscreen.storage import Database
from drscreen.web.app import create_app


@pytest.fixture
def make_client(tmp_path, checkpoint):
    def build(name: str, **overrides) -> TestClient:
        settings = Settings(
            model_path=checkpoint,
            device="cpu",
            database_url=f"sqlite:///{tmp_path / f'{name}.db'}",
            image_store=tmp_path / "images",
            report_dir=tmp_path / "reports",
            sms_enabled=False,
            **overrides,
        )
        Database(settings.database_url).create_schema()
        return TestClient(create_app(settings))

    return build


def test_signup_creates_an_account_and_signs_in(make_client):
    client = make_client("open")
    assert client.get("/api/status").json()["signup_enabled"] is True

    response = client.post("/api/signup", json={"username": "alice", "password": "strongpass1"})
    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    # The session cookie is set by signup, so no separate login is needed.
    assert client.get("/api/me").json()["username"] == "alice"


def test_duplicate_username_is_rejected(make_client):
    client = make_client("dupe")
    client.post("/api/signup", json={"username": "alice", "password": "strongpass1"})
    response = client.post("/api/signup", json={"username": "alice", "password": "otherpass1"})
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("username", "password"),
    [("bob", "short"), ("x", "strongpass1")],
    ids=["password too short", "username too short"],
)
def test_weak_credentials_are_rejected(make_client, username, password):
    client = make_client(f"weak{username}")
    response = client.post("/api/signup", json={"username": username, "password": password})
    assert response.status_code == 400


def test_signup_can_be_disabled(make_client):
    client = make_client("closed", allow_signup=False)
    assert client.get("/api/status").json()["signup_enabled"] is False
    response = client.post("/api/signup", json={"username": "mallory", "password": "strongpass1"})
    assert response.status_code == 403
    assert client.get("/api/me").status_code == 401


def test_signup_code_is_required_when_configured(make_client):
    client = make_client("coded", signup_code="CLINIC-2026")
    status = client.get("/api/status").json()
    assert status["signup_enabled"] and status["signup_requires_code"]

    wrong = client.post(
        "/api/signup",
        json={"username": "carol", "password": "strongpass1", "code": "nope"},
    )
    assert wrong.status_code == 403

    missing = client.post(
        "/api/signup", json={"username": "carol", "password": "strongpass1"}
    )
    assert missing.status_code == 403

    right = client.post(
        "/api/signup",
        json={"username": "carol", "password": "strongpass1", "code": "CLINIC-2026"},
    )
    assert right.status_code == 200
