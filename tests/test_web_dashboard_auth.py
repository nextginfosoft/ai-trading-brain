"""Password login for the read-only web dashboard (web_dashboard/)."""

import pytest
from fastapi.testclient import TestClient

from web_dashboard import auth
from web_dashboard.server import app, throttle

PASSWORD = "correct horse battery"


@pytest.fixture
def client(monkeypatch):
    # Low iteration count keeps the test fast; format and verification are identical.
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", auth.hash_password(PASSWORD, iterations=1_000))
    throttle._failures.clear()
    return TestClient(app)


def test_hash_roundtrip_and_no_plaintext():
    stored = auth.hash_password(PASSWORD, iterations=1_000)
    assert PASSWORD not in stored
    assert "$" not in stored  # safe inside .env files
    assert auth.verify_password(PASSWORD, stored)
    assert not auth.verify_password("wrong password", stored)
    assert not auth.verify_password(PASSWORD, "garbage")


def test_token_rejects_tampering_expiry_and_password_change():
    pw_hash = auth.hash_password(PASSWORD, iterations=1_000)
    token = auth.issue_token(pw_hash)
    assert auth.verify_token(token, pw_hash)
    assert not auth.verify_token(token[:-2] + "xx", pw_hash)
    assert not auth.verify_token(token, pw_hash, now=10**12)
    assert not auth.verify_token(token, auth.hash_password("another password", iterations=1_000))


def test_data_endpoints_require_login(client):
    for path in ["/api/overview", "/api/trades", "/api/decisions", "/api/health", "/api/eod", "/api/docs"]:
        assert client.get(path).status_code == 401, path
    assert client.get("/healthz").status_code == 200
    assert client.get("/api/auth/session").json() == {"authenticated": False, "configured": True}


def test_login_logout_flow(client):
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401

    res = client.post("/api/auth/login", json={"password": PASSWORD})
    assert res.status_code == 200
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie

    assert client.get("/api/overview").status_code == 200
    assert client.get("/api/auth/session").json()["authenticated"] is True

    client.post("/api/auth/logout")
    assert client.get("/api/overview").status_code == 401


def test_lockout_after_repeated_failures(client):
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    locked = client.post("/api/auth/login", json={"password": PASSWORD})
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_fails_closed_without_configured_password(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD_HASH", raising=False)
    c = TestClient(app)
    assert c.get("/api/overview").status_code == 401
    assert c.post("/api/auth/login", json={"password": "anything"}).status_code == 503
    assert c.get("/api/auth/session").json() == {"authenticated": False, "configured": False}
