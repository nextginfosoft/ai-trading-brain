"""
Unit tests for broker_auth/kite_autologin.py
"""

import pytest
from datetime import datetime
import pytz

from broker_auth import credentials, kite_autologin, kite_session

ALL_ENV = [spec[0] for fields in credentials.BROKERS.values() for spec in fields.values()]

@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KITE_SESSION_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("CREDENTIALS_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("CREDENTIALS_KEY", credentials.generate_key())
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "broker"


def test_is_enabled():
    assert not kite_autologin.is_enabled()

    credentials.save("kite", {
        "api_key": "kkey",
        "api_secret": "ksec",
        "user_id": "AB1234",
        "password": "mypassword",
        "totp_secret": "JBSWY3DPEHPK3PXP"
    })
    assert kite_autologin.is_enabled()


def test_should_attempt():
    ist = pytz.timezone("Asia/Kolkata")
    dt_now = datetime(2026, 9, 26, 9, 0, 0, tzinfo=ist)

    # Not enabled -> False
    assert not kite_autologin.should_attempt(dt_now, needs_login=True)

    # Save credentials
    credentials.save("kite", {
        "api_key": "kkey",
        "api_secret": "ksec",
        "user_id": "AB1234",
        "password": "mypassword",
        "totp_secret": "JBSWY3DPEHPK3PXP"
    })

    # Needs login True -> True
    assert kite_autologin.should_attempt(dt_now, needs_login=True)

    # Outside window (e.g. 05:00 IST) -> False
    dt_early = datetime(2026, 9, 26, 5, 0, 0, tzinfo=ist)
    assert not kite_autologin.should_attempt(dt_early, needs_login=True)


def test_login_missing_credentials():
    res = kite_autologin.login()
    assert res["ok"] is False
    assert "Automatic login needs" in res["message"]
