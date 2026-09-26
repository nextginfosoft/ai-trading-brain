"""
"Test connection" checks for each broker, run from the Settings page.

Each test uses the effective credentials (saved settings → .env) and returns
{"ok": bool, "message": str}. Messages never contain credential values: any
occurrence of a configured value is scrubbed before returning. Broker SDK
clients are injectable for tests.
"""

from __future__ import annotations

import concurrent.futures
from typing import Callable, Dict, Optional

from broker_auth import credentials, kite_session

TIMEOUT_SECONDS = 20


def _scrub(message: str, values: Dict[str, str]) -> str:
    for v in values.values():
        if v and len(v) >= 4:
            message = message.replace(v, "••••")
    return message[:300]


def _missing(broker: str, values: Dict[str, str]) -> Optional[dict]:
    optional = credentials.OPTIONAL_FIELDS.get(broker, frozenset())
    missing = [credentials.BROKERS[broker][f][1] for f, v in values.items() if not v and f not in optional]
    if missing:
        return {"ok": False, "message": "Missing: " + ", ".join(missing)}
    return None


def test_kite(client_factory: Optional[Callable] = None) -> dict:
    values = credentials.get_all("kite")
    missing = _missing("kite", values)
    if missing:
        return missing
    session = kite_session.load_session()
    if not session:
        from broker_auth import kite_autologin
        if kite_autologin.is_enabled():
            return {"ok": True, "message": "All set. Not logged in yet today — use Log in now, or wait for the "
                                           "automatic login (from 08:00 IST)."}
        return {"ok": True, "message": "Key and secret saved. Click Connect Zerodha to log in and verify them."}
    if client_factory is None:
        from kiteconnect import KiteConnect
        client_factory = KiteConnect
    kite = client_factory(api_key=values["api_key"])
    kite.set_access_token(session["access_token"])
    profile = kite.profile() or {}
    return {"ok": True, "message": f"Connected to Zerodha as {profile.get('user_id', session.get('user_id', '?'))}."}


def test_dhan(client_factory: Optional[Callable] = None) -> dict:
    values = credentials.get_all("dhan")
    missing = _missing("dhan", values)
    if missing:
        return missing
    if client_factory is None:
        from dhanhq import dhanhq as _DhanHQ
        try:
            from dhanhq import DhanContext
            client_factory = lambda cid, tok: _DhanHQ(DhanContext(cid, tok))   # noqa: E731
        except ImportError:
            client_factory = _DhanHQ
    resp = client_factory(values["client_id"], values["access_token"]).get_fund_limits() or {}
    if resp.get("status") == "success":
        return {"ok": True, "message": "Connected to Dhan: token is valid."}
    remarks = resp.get("remarks") or resp.get("data") or "rejected"
    return {"ok": False, "message": f"Dhan rejected the credentials: {remarks}"}


def test_angelone(client_factory: Optional[Callable] = None, totp_factory: Optional[Callable] = None) -> dict:
    values = credentials.get_all("angelone")
    missing = _missing("angelone", values)
    if missing:
        return missing
    if totp_factory is None:
        import pyotp
        totp_factory = lambda secret: pyotp.TOTP(secret).now()   # noqa: E731
    if client_factory is None:
        from SmartApi import SmartConnect
        client_factory = SmartConnect
    try:
        code = totp_factory(values["totp_secret"])
    except Exception:
        return {"ok": False, "message": "TOTP secret is not valid (it should be the base32 key from AngelOne)."}
    smart = client_factory(api_key=values["api_key"])
    resp = smart.generateSession(values["client_id"], values["password"], code) or {}
    if resp.get("status"):
        try:
            smart.terminateSession(values["client_id"])
        except Exception:
            pass
        return {"ok": True, "message": "Connected to AngelOne: login succeeded."}
    return {"ok": False, "message": f"AngelOne rejected the login: {resp.get('message') or 'unknown error'}"}


TESTS = {"kite": test_kite, "dhan": test_dhan, "angelone": test_angelone}


def run_test(broker: str) -> dict:
    """Run a broker's test with a timeout; never raises, never leaks credential values."""
    if broker not in TESTS:
        return {"ok": False, "message": f"Unknown broker: {broker}"}
    values = credentials.get_all(broker)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        result = pool.submit(TESTS[broker]).result(timeout=TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        result = {"ok": False, "message": f"No response from {credentials.BROKER_LABELS[broker]} "
                                          f"within {TIMEOUT_SECONDS}s."}
    except Exception as exc:
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    finally:
        pool.shutdown(wait=False)
    return {"ok": bool(result.get("ok")), "message": _scrub(str(result.get("message", "")), values)}
