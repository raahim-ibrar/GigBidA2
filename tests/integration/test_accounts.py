from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.security import token_digest
from apps.api.main import create_app
from apps.api.models import User, UserSession, utcnow

CREDS = {"email": "alice@example.org", "password": "A real test password 123!"}
PROFILE = {
    "display_name": "Alice",
    "persona": "ai_ml",
    "hourly_floor": "25.50",
    "weekly_connects_budget": 80,
    "saved_searches": ["Python", "RAG"],
}


def register(client, credentials=None):
    response = client.post("/api/auth/register", json=credentials or CREDS)
    assert response.status_code == 201, response.text
    return response.json()


def test_passwords_and_session_tokens_are_not_stored_in_plaintext(client, account_app):
    account = register(client)
    assert set(account) == {"id", "email", "csrf_token"}
    assert any(cookie.has_nonstandard_attr("HttpOnly") for cookie in client.cookies.jar)
    token = client.cookies.get("gigbid_session")
    with Session(account_app.state.engine) as db:
        user = db.scalar(select(User))
        session = db.scalar(select(UserSession))
        assert user.password_hash.startswith("$argon2id$")
        assert CREDS["password"] not in user.password_hash
        assert session.token_digest == token_digest(token)
        assert session.token_digest != token


def test_login_wrong_password_and_unknown_user_have_same_error(client):
    register(client)
    wrong = client.post("/api/auth/login", json={**CREDS, "password": "Wrong password 123"})
    unknown = client.post("/api/auth/login", json={**CREDS, "email": "unknown@example.org"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_case_normalization_prevents_duplicate_accounts(client):
    register(client)
    duplicate = client.post("/api/auth/register", json={**CREDS, "email": "ALICE@example.org"})
    assert duplicate.status_code == 409


def test_profile_writes_require_csrf_and_trusted_origin(client):
    account = register(client)
    assert client.put("/api/profile/me", json=PROFILE).status_code == 403
    headers = {"X-CSRF-Token": account["csrf_token"], "Origin": "https://attacker.example"}
    assert client.put("/api/profile/me", json=PROFILE, headers=headers).status_code == 403
    headers["Origin"] = "http://localhost:3000"
    assert client.put("/api/profile/me", json=PROFILE, headers=headers).status_code == 200


def test_users_cannot_select_or_overwrite_another_users_profile(account_app):
    with TestClient(account_app) as alice, TestClient(account_app) as bob:
        a = register(alice)
        b = register(bob, {**CREDS, "email": "bob@example.org"})
        assert (
            alice.put(
                "/api/profile/me", json=PROFILE, headers={"X-CSRF-Token": a["csrf_token"]}
            ).status_code
            == 200
        )
        attempted = bob.put(
            "/api/profile/me",
            json={**PROFILE, "user_id": a["id"]},
            headers={"X-CSRF-Token": b["csrf_token"]},
        )
        assert attempted.status_code == 422
        assert bob.get("/api/profile/me").json()["display_name"] == ""
        assert alice.get("/api/profile/me").json()["display_name"] == "Alice"


def test_logout_revokes_token_and_login_rotates_token(client):
    first = register(client)
    old_token = client.cookies.get("gigbid_session")
    logged_in = client.post("/api/auth/login", json=CREDS)
    assert logged_in.status_code == 200
    assert client.cookies.get("gigbid_session") != old_token
    assert (
        client.get("/api/auth/me", headers={"Cookie": f"gigbid_session={old_token}"}).status_code
        == 401
    )
    csrf = logged_in.json()["csrf_token"]
    assert csrf != first["csrf_token"]
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_cannot_be_reused(client, account_app):
    register(client)
    with Session(account_app.state.engine) as db:
        session = db.scalar(select(UserSession))
        session.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_session_and_profile_survive_application_restart(client, account_app):
    user = register(client)
    assert (
        client.put(
            "/api/profile/me", json=PROFILE, headers={"X-CSRF-Token": user["csrf_token"]}
        ).status_code
        == 200
    )
    new_app = create_app(account_app.state.settings)
    with TestClient(new_app) as restarted:
        restarted.cookies.set("gigbid_session", client.cookies.get("gigbid_session"))
        assert restarted.get("/api/auth/me").json()["id"] == user["id"]
        assert restarted.get("/api/profile/me").json()["hourly_floor"] == "25.50"


def test_readiness_requires_migrations(client):
    assert client.get("/health/ready").status_code == 200


def test_invalid_settings_are_rejected(client):
    account = register(client)
    response = client.put(
        "/api/profile/me",
        json={**PROFILE, "hourly_floor": "-1"},
        headers={"X-CSRF-Token": account["csrf_token"]},
    )
    assert response.status_code == 422
