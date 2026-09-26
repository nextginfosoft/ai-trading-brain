"""Engine uses Settings-page credentials for Dhan / AngelOne and reconnects when they change."""

import os
import sys
import types

import pytest

# Importing the engine modules load_dotenv()s the developer's .env at import time; restore after.
_env_before = dict(os.environ)
from broker_auth import credentials  # noqa: E402
from data_feeds import angelone_feed as ao_mod  # noqa: E402
from data_feeds import dhan_feed as dhan_mod  # noqa: E402
from data_feeds.data_feed_manager import DataFeedManager  # noqa: E402
from execution_engine import order_manager as om_mod  # noqa: E402
os.environ.clear()
os.environ.update(_env_before)

ALL_ENV = [spec[0] for fields in credentials.BROKERS.values() for spec in fields.values()]


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDENTIALS_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("KITE_SESSION_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("CREDENTIALS_KEY", credentials.generate_key())
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)


# ── Dhan reads Settings first ────────────────────────────────────────────

def test_dhan_credentials_prefer_settings(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "envcid")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "envtok")
    assert dhan_mod._get_credentials() == ("envcid", "envtok")
    credentials.save("dhan", {"access_token": "settok"})
    assert dhan_mod._get_credentials() == ("envcid", "settok")


def test_telegram_token_updates_settings_so_newest_wins(tmp_path, monkeypatch):
    fake_file = tmp_path / "pkg" / "data_feeds" / "dhan_feed.py"       # keeps reload_token's .env write in tmp
    fake_file.parent.mkdir(parents=True)
    monkeypatch.setattr(dhan_mod, "__file__", str(fake_file))
    monkeypatch.setattr(dhan_mod.DhanFeed, "_connect", lambda self: None)
    monkeypatch.setattr(dhan_mod.DhanFeed, "_audit_dhan_coverage", lambda self: None)
    credentials.save("dhan", {"client_id": "1100", "access_token": "OLD-SAVED"})
    feed = dhan_mod.DhanFeed()
    feed.reload_token("NEW-FROM-TELEGRAM")
    assert credentials.get("dhan", "access_token") == "NEW-FROM-TELEGRAM"
    assert credentials.audit_log()[0]["actor"] == "telegram"
    assert (tmp_path / "pkg" / ".env").read_text().strip() == "DHAN_ACCESS_TOKEN=NEW-FROM-TELEGRAM"


# ── AngelOne reads Settings and re-logs in ──────────────────────────────

class FakeSmart:
    logins = []

    def __init__(self, api_key):
        self.api_key = api_key

    def generateSession(self, client_id, password, totp):
        FakeSmart.logins.append((self.api_key, client_id, password))
        return {"status": True, "data": {"feedToken": "ft"}}


def test_angelone_reload_uses_settings(monkeypatch):
    monkeypatch.setitem(sys.modules, "SmartApi", types.SimpleNamespace(SmartConnect=FakeSmart))
    FakeSmart.logins.clear()
    feed = object.__new__(ao_mod.AngelOneFeed)
    import threading
    feed._lock, feed._smart, feed._connected = threading.RLock(), None, False
    feed._session_ts = feed._last_reconnect_attempt = feed._credentials_configured = None

    assert feed.reload_credentials() is False                       # nothing configured yet
    assert FakeSmart.logins == []
    credentials.save("angelone", {"api_key": "AK", "client_id": "C1", "password": "1234",
                                  "totp_secret": "JBSWY3DPEHPK3PXP"})
    assert feed.reload_credentials() is True
    assert FakeSmart.logins == [("AK", "C1", "1234")]


# ── Feed manager hot-reload ─────────────────────────────────────────────

class ReloadCounter:
    def __init__(self):
        self.calls = 0

    def reload_credentials(self):
        self.calls += 1
        return True


def _manager():
    m = object.__new__(DataFeedManager)
    m.dhan, m.angelone = ReloadCounter(), ReloadCounter()
    m._cred_mtime = credentials.store_mtime()
    m._cred_prints = DataFeedManager._credential_fingerprints()
    return m


def _bump_mtime():
    st = os.stat(credentials.store_path())
    os.utime(credentials.store_path(), ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def test_only_the_changed_broker_reconnects():
    m = _manager()
    assert m.check_credential_changes() == []                        # nothing changed
    credentials.save("dhan", {"client_id": "1100", "access_token": "T1"})
    assert m.check_credential_changes() == ["dhan"]
    assert (m.dhan.calls, m.angelone.calls) == (1, 0)
    credentials.save("angelone", {"api_key": "AK"})
    _bump_mtime()
    assert m.check_credential_changes() == ["angelone"]
    assert (m.dhan.calls, m.angelone.calls) == (1, 1)


def test_resaving_identical_values_does_not_reconnect():
    credentials.save("dhan", {"client_id": "1100", "access_token": "T1"})
    m = _manager()
    credentials.save("dhan", {"access_token": "T1"})
    _bump_mtime()
    assert m.check_credential_changes() == []
    assert m.dhan.calls == 0


def test_removing_credentials_reconnects_dhan():
    credentials.save("dhan", {"client_id": "1100", "access_token": "T1"})
    m = _manager()
    credentials.remove("dhan")
    _bump_mtime()
    assert m.check_credential_changes() == ["dhan"]


def test_disabled_angelone_stub_is_skipped():
    m = _manager()
    m.angelone = object()                                           # _DisabledAngelOne has no reload method
    credentials.save("angelone", {"api_key": "AK"})
    assert m.check_credential_changes() == []


# ── Order broker loader reads Settings ──────────────────────────────────

def test_order_broker_uses_saved_dhan_credentials(monkeypatch):
    seen = []

    class FakeDhanBroker:
        def __init__(self, cid, tok):
            seen.append((cid, tok))

    import execution_engine.brokers.dhan_broker as db_mod
    monkeypatch.setattr(db_mod, "DhanBroker", FakeDhanBroker)
    monkeypatch.setattr(om_mod, "ACTIVE_BROKER", "dhan")
    credentials.save("dhan", {"client_id": "1100", "access_token": "SAVED"})
    om_mod.OrderManager._load_broker(object())
    assert seen == [("1100", "SAVED")]
