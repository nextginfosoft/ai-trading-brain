"""Broker credential store, connection tests and Settings API. Secrets must never come back out."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from broker_auth import connection_tests, credentials, kite_session
from web_dashboard import auth
from web_dashboard.server import app, reauth_throttle, throttle

PASSWORD = "correct horse battery"
SECRET = "SUPER-SECRET-TOKEN-9876"
ALL_ENV = [spec[0] for fields in credentials.BROKERS.values() for spec in fields.values()]


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KITE_SESSION_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("CREDENTIALS_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("CREDENTIALS_KEY", credentials.generate_key())
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "broker"


# ── Store ────────────────────────────────────────────────────────────────

def test_roundtrip_encrypted_at_rest():
    assert credentials.save("dhan", {"client_id": "1100123", "access_token": SECRET}) == ["access_token", "client_id"]
    assert credentials.get("dhan", "access_token") == SECRET
    with open(credentials.store_path(), "rb") as fh:
        blob = fh.read()
    assert SECRET.encode() not in blob and b"1100123" not in blob


def test_blank_fields_keep_existing_values():
    credentials.save("angelone", {"api_key": "AK1", "client_id": "C1", "password": "1234", "totp_secret": "JBSW"})
    credentials.save("angelone", {"api_key": "AK2", "password": "", "totp_secret": "  "})
    assert credentials.get_all("angelone") == {"api_key": "AK2", "client_id": "C1", "password": "1234",
                                               "totp_secret": "JBSW"}


def test_env_fallback_and_settings_override(monkeypatch):
    monkeypatch.setenv("KITE_API_KEY", "envkey1234")
    assert credentials.get("kite", "api_key") == "envkey1234"
    assert credentials.status()["brokers"]["kite"]["fields"]["api_key"]["source"] == "env"
    credentials.save("kite", {"api_key": "setkey5678"})
    assert credentials.get("kite", "api_key") == "setkey5678" == kite_session.api_key()
    assert credentials.status()["brokers"]["kite"]["fields"]["api_key"]["source"] == "settings"


def test_status_never_contains_secrets():
    credentials.save("dhan", {"client_id": "1100123", "access_token": SECRET})
    status = credentials.status()
    assert SECRET not in json.dumps(status)
    field = status["brokers"]["dhan"]["fields"]["access_token"]
    assert field == {"label": "Access token", "secret": True, "set": True, "source": "settings", "hint": "••••9876", "optional": False}
    assert status["brokers"]["dhan"]["complete"] and not status["brokers"]["angelone"]["complete"]


def test_locked_without_key(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_KEY")
    monkeypatch.setenv("DHAN_CLIENT_ID", "envcid")
    assert credentials.status()["unlocked"] is False
    with pytest.raises(credentials.StoreLocked):
        credentials.save("dhan", {"access_token": SECRET})
    assert credentials.get("dhan", "client_id") == "envcid"


def test_wrong_key_locks_store_but_env_still_works(monkeypatch):
    credentials.save("dhan", {"access_token": SECRET})
    monkeypatch.setenv("CREDENTIALS_KEY", credentials.generate_key())
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "envtoken")
    st = credentials.status()
    assert st["unlocked"] is False and "does not match" in st["lock_reason"]
    assert credentials.get("dhan", "access_token") == "envtoken"
    with pytest.raises(credentials.StoreLocked):
        credentials.save("dhan", {"access_token": "x"})    # never overwrite data it can't read


@pytest.mark.parametrize("broker,values", [
    ("robinhood", {"x": "y"}), ("dhan", {"bogus": "y"}), ("dhan", {"access_token": "a\nb"}),
    ("dhan", {"access_token": "x" * 600}), ("dhan", {"access_token": 123}),
])
def test_invalid_input_rejected(broker, values):
    with pytest.raises(credentials.InvalidInput):
        credentials.save(broker, values)


def test_remove_and_audit_has_no_values():
    credentials.save("dhan", {"client_id": "1100123", "access_token": SECRET})
    assert credentials.remove("dhan") is True
    assert credentials.get("dhan", "access_token") == "" and credentials.remove("dhan") is False
    log = credentials.audit_log()
    assert [e["action"] for e in log] == ["remove", "save"]
    assert log[1]["fields"] == ["access_token", "client_id"]
    with open(credentials.audit_path(), encoding="utf-8") as fh:
        assert SECRET not in fh.read()


def test_mtime_changes_on_save():
    assert credentials.store_mtime() is None
    credentials.save("dhan", {"client_id": "1"})
    first = credentials.store_mtime()
    time.sleep(0.01)
    credentials.save("dhan", {"client_id": "2"})
    assert credentials.store_mtime() != first


# ── Connection tests ────────────────────────────────────────────────────

class FakeDhan:
    def __init__(self, cid, tok):
        self.tok = tok

    def get_fund_limits(self):
        return {"status": "success"} if self.tok == SECRET else {"status": "failure", "remarks": "Invalid token"}


class FakeSmart:
    def __init__(self, api_key):
        self.ended = False

    def generateSession(self, client_id, password, totp):
        return {"status": password == "1234" and totp == "123456", "message": "Invalid credentials"}

    def terminateSession(self, client_id):
        self.ended = True


def test_dhan_test(monkeypatch):
    credentials.save("dhan", {"client_id": "1100123", "access_token": SECRET})
    assert connection_tests.test_dhan(FakeDhan)["ok"] is True
    credentials.save("dhan", {"access_token": "wrong"})
    res = connection_tests.test_dhan(FakeDhan)
    assert res["ok"] is False and "Invalid token" in res["message"]


def test_angelone_test():
    assert connection_tests.test_angelone(FakeSmart, lambda s: "123456")["message"].startswith("Missing")
    credentials.save("angelone", {"api_key": "AK", "client_id": "C1", "password": "1234", "totp_secret": "JBSW"})
    assert connection_tests.test_angelone(FakeSmart, lambda s: "123456")["ok"] is True
    assert connection_tests.test_angelone(FakeSmart, lambda s: "000000")["ok"] is False

    def bad_totp(secret):
        raise ValueError("Non-base32 digit found")
    assert "TOTP secret is not valid" in connection_tests.test_angelone(FakeSmart, bad_totp)["message"]


def test_kite_test_without_login_explains_next_step():
    credentials.save("kite", {"api_key": "k1234", "api_secret": "s5678"})
    res = connection_tests.test_kite()
    assert res["ok"] is True and "Connect Zerodha" in res["message"]


def test_run_test_scrubs_secrets_and_survives_errors(monkeypatch):
    credentials.save("dhan", {"client_id": "1100123", "access_token": SECRET})

    def leaky():
        raise RuntimeError(f"auth failed for token {SECRET}")
    monkeypatch.setitem(connection_tests.TESTS, "dhan", leaky)
    res = connection_tests.run_test("dhan")
    assert res["ok"] is False and SECRET not in res["message"] and "RuntimeError" in res["message"]


def test_run_test_timeout(monkeypatch):
    monkeypatch.setattr(connection_tests, "TIMEOUT_SECONDS", 0.2)
    monkeypatch.setitem(connection_tests.TESTS, "dhan", lambda: time.sleep(2))
    res = connection_tests.run_test("dhan")
    assert res["ok"] is False and "No response" in res["message"]


# ── Settings API ────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", auth.hash_password(PASSWORD, iterations=1_000))
    throttle._failures.clear()
    reauth_throttle._failures.clear()
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    return c


def test_settings_require_login(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", auth.hash_password(PASSWORD, iterations=1_000))
    c = TestClient(app)
    assert c.get("/api/settings/brokers").status_code == 401
    assert c.put("/api/settings/brokers/dhan", json={"password": PASSWORD, "values": {}}).status_code == 401
    assert c.post("/api/settings/brokers/dhan/test").status_code == 401
    assert c.get("/api/settings/audit").status_code == 401


def test_save_requires_password_and_never_echoes_secret(client):
    bad = client.put("/api/settings/brokers/dhan", json={"password": "nope", "values": {"access_token": SECRET}})
    assert bad.status_code == 403 and credentials.get("dhan", "access_token") == ""
    ok = client.put("/api/settings/brokers/dhan",
                    json={"password": PASSWORD, "values": {"client_id": "1100123", "access_token": SECRET}})
    assert ok.status_code == 200 and ok.json()["changed"] == ["access_token", "client_id"]
    assert SECRET not in ok.text and SECRET not in client.get("/api/settings/brokers").text
    assert SECRET not in client.get("/api/settings/audit").text


def test_password_lockout_on_settings_changes(client):
    for _ in range(auth.MAX_FAILURES):
        client.put("/api/settings/brokers/dhan", json={"password": "wrong", "values": {"client_id": "x"}})
    locked = client.put("/api/settings/brokers/dhan", json={"password": PASSWORD, "values": {"client_id": "x"}})
    assert locked.status_code == 429


def test_remove_requires_password(client):
    credentials.save("kite", {"api_key": "k1234", "api_secret": "s5678"})
    assert client.post("/api/settings/brokers/kite/remove", json={"password": "nope"}).status_code == 403
    res = client.post("/api/settings/brokers/kite/remove", json={"password": PASSWORD})
    assert res.status_code == 200 and res.json()["removed"] is True
    assert credentials.get("kite", "api_key") == ""


def test_errors_unknown_broker_invalid_value_and_locked(client, monkeypatch):
    assert client.put("/api/settings/brokers/xyz", json={"password": PASSWORD, "values": {}}).status_code == 404
    bad = client.put("/api/settings/brokers/dhan", json={"password": PASSWORD, "values": {"access_token": "a\nb"}})
    assert bad.status_code == 422
    monkeypatch.delenv("CREDENTIALS_KEY")
    locked = client.put("/api/settings/brokers/dhan", json={"password": PASSWORD, "values": {"client_id": "1"}})
    assert locked.status_code == 503 and client.get("/api/settings/brokers").json()["unlocked"] is False


def test_test_endpoint(client, monkeypatch):
    monkeypatch.setitem(connection_tests.TESTS, "dhan", lambda: {"ok": True, "message": "Connected to Dhan"})
    assert client.post("/api/settings/brokers/dhan/test").json() == {"ok": True, "message": "Connected to Dhan"}
    assert client.post("/api/settings/brokers/nope/test").status_code == 404
