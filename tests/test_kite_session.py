"""Zerodha (Kite) daily-login session handling: broker_auth.kite_session + dashboard endpoints."""

import os
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from broker_auth import kite_session
from broker_auth.kite_session import IST
from web_dashboard import auth
from web_dashboard.server import app, kite_states, throttle

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def kite_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KITE_SESSION_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("KITE_API_KEY", "testkey")
    monkeypatch.setenv("KITE_API_SECRET", "testsecret")
    return tmp_path / "broker"


class FakeKite:
    calls = []

    def __init__(self, api_key):
        self.api_key = api_key

    def generate_session(self, request_token, api_secret):
        FakeKite.calls.append((self.api_key, request_token, api_secret))
        if request_token == "bad":
            raise ValueError("Token is invalid or has expired.")
        return {"access_token": "ACCESS-123", "user_id": "AB1234", "user_name": "Tester"}


# ── Session storage ─────────────────────────────────────────────────────────

def test_expiry_is_next_6am_ist():
    assert kite_session.expiry_for(datetime(2026, 9, 28, 8, 30, tzinfo=IST)) == datetime(2026, 9, 29, 6, 0, tzinfo=IST)
    assert kite_session.expiry_for(datetime(2026, 9, 28, 5, 30, tzinfo=IST)) == datetime(2026, 9, 28, 6, 0, tzinfo=IST)


def test_save_load_and_expire(kite_env):
    login = datetime(2026, 9, 28, 8, 30, tzinfo=IST)
    kite_session.save_session("TOKEN", "AB1234", "Tester", now=login)
    assert kite_session.load_session(now=datetime(2026, 9, 28, 15, 0, tzinfo=IST))["access_token"] == "TOKEN"
    assert kite_session.load_session(now=datetime(2026, 9, 29, 6, 0, tzinfo=IST)) is None  # expired
    if os.name != "nt":
        assert oct(os.stat(kite_session.session_path()).st_mode & 0o777) == "0o600"


def test_public_status_never_contains_token(kite_env):
    kite_session.save_session("SECRET-TOKEN", "AB1234")
    status = kite_session.public_status()
    assert status["connected"] is True and status["user_id"] == "AB1234"
    assert "SECRET-TOKEN" not in str(status)


def test_corrupt_or_missing_file_is_not_connected(kite_env):
    assert kite_session.load_session() is None
    os.makedirs(kite_env, exist_ok=True)
    with open(kite_session.session_path(), "w") as fh:
        fh.write("{not json")
    assert kite_session.load_session() is None


def test_login_url_carries_state():
    url = kite_session.login_url("abc123")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://kite.zerodha.com/connect/login")
    assert q["api_key"] == ["testkey"] and q["v"] == ["3"]
    assert parse_qs(q["redirect_params"][0]) == {"state": ["abc123"]}


def test_exchange_saves_session(kite_env):
    FakeKite.calls.clear()
    record = kite_session.exchange_request_token("REQ", client_factory=FakeKite)
    assert FakeKite.calls == [("testkey", "REQ", "testsecret")]
    assert record["access_token"] == "ACCESS-123"
    assert kite_session.load_session()["user_id"] == "AB1234"


# ── Dashboard endpoints ────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", auth.hash_password(PASSWORD, iterations=1_000))
    throttle._failures.clear()
    return TestClient(app)


def login(client):
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200


def test_kite_endpoints_require_dashboard_login(client):
    assert client.get("/api/kite/status").status_code == 401
    assert client.post("/api/kite/login").status_code == 401
    assert client.post("/api/kite/disconnect").status_code == 401


def test_full_login_round_trip(client, monkeypatch):
    monkeypatch.setattr(kite_session, "exchange_request_token",
                        lambda token: kite_session.save_session("ACCESS-XYZ", "AB1234", "Tester"))
    login(client)
    url = client.post("/api/kite/login").json()["url"]
    state = parse_qs(parse_qs(urlparse(url).query)["redirect_params"][0])["state"][0]

    res = client.get("/kite/callback", params={"request_token": "REQ", "status": "success", "state": state},
                     follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"] == "/?kite=connected"
    assert client.get("/api/kite/status").json()["connected"] is True

    # the same state cannot be replayed
    again = client.get("/kite/callback", params={"request_token": "REQ", "status": "success", "state": state},
                       follow_redirects=False)
    assert "kite=error" in again.headers["location"]


def test_callback_rejects_unknown_state(client):
    res = client.get("/kite/callback", params={"request_token": "REQ", "status": "success", "state": "forged"},
                     follow_redirects=False)
    assert "kite=error" in res.headers["location"]
    assert kite_session.load_session() is None


def test_callback_handles_cancel_and_exchange_failure(client, monkeypatch):
    def boom(token):
        raise ValueError("secret-ish detail must not leak")
    monkeypatch.setattr(kite_session, "exchange_request_token", boom)
    for params in ({"status": "cancelled"}, {"status": "success", "request_token": "bad"}):
        params["state"] = kite_states.issue()
        loc = client.get("/kite/callback", params=params, follow_redirects=False).headers["location"]
        assert "kite=error" in loc and "secret-ish" not in loc


def test_login_unavailable_without_credentials(client, monkeypatch):
    monkeypatch.delenv("KITE_API_SECRET")
    login(client)
    assert client.post("/api/kite/login").status_code == 503
    assert client.get("/api/kite/status").json()["configured"] is False


def test_disconnect_clears_session(client):
    kite_session.save_session("T", "AB1234")
    login(client)
    assert client.post("/api/kite/disconnect").json()["connected"] is False
    assert kite_session.load_session() is None
