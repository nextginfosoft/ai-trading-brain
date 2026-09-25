"""
Zerodha Kite Connect session management.

Kite access tokens are valid for one trading day: Zerodha expires them at
about 06:00 IST the next morning, and its terms require a manual login each
day (automating the login with stored credentials/TOTP is not allowed). So:

  1. The dashboard's "Connect Zerodha" button asks for a login URL
     (login_url(state)), with a one-time `state` echoed back by Kite via
     `redirect_params`.
  2. Zerodha redirects the browser to <dashboard>/kite/callback with a
     one-time `request_token`.
  3. exchange_request_token() swaps it (plus KITE_API_SECRET) for an access
     token, which save_session() writes to data/broker/kite_session.json
     (mode 600, git-ignored).
  4. The engine calls load_session() whenever it needs the token, so a new
     login takes effect without restarting anything.

Settings: KITE_API_KEY, KITE_API_SECRET (server .env only), optional
KITE_SESSION_DIR (default <repo>/data/broker).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

IST = timezone(timedelta(hours=5, minutes=30))
LOGIN_BASE = "https://kite.zerodha.com/connect/login"
SESSION_FILENAME = "kite_session.json"
TOKEN_EXPIRY_HOUR_IST = 6   # Kite access tokens expire around 06:00 IST the next day

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def session_dir() -> str:
    return os.getenv("KITE_SESSION_DIR") or os.path.join(_ROOT, "data", "broker")


def session_path() -> str:
    return os.path.join(session_dir(), SESSION_FILENAME)


def api_key() -> str:
    return (os.getenv("KITE_API_KEY") or "").strip()


def api_secret() -> str:
    return (os.getenv("KITE_API_SECRET") or "").strip()


def is_configured() -> bool:
    """True when this installation is set up to use Kite (key + secret present)."""
    return bool(api_key() and api_secret())


def login_url(state: str) -> str:
    """Zerodha login page URL; `state` comes back to /kite/callback unchanged."""
    return f"{LOGIN_BASE}?v=3&api_key={quote(api_key())}&redirect_params={quote('state=' + state)}"


def expiry_for(login_at: datetime) -> datetime:
    """Next 06:00 IST strictly after the login time."""
    local = login_at.astimezone(IST)
    expiry = local.replace(hour=TOKEN_EXPIRY_HOUR_IST, minute=0, second=0, microsecond=0)
    if expiry <= local:
        expiry += timedelta(days=1)
    return expiry


def save_session(access_token: str, user_id: str = "", user_name: str = "",
                 now: Optional[datetime] = None) -> dict:
    """Persist the access token atomically with owner-only permissions."""
    now = now or datetime.now(IST)
    record = {
        "access_token": access_token,
        "user_id": user_id,
        "user_name": user_name,
        "login_at": now.astimezone(IST).isoformat(timespec="seconds"),
        "expires_at": expiry_for(now).isoformat(timespec="seconds"),
    }
    os.makedirs(session_dir(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=session_dir(), prefix=".kite_session.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass  # e.g. Windows
        os.replace(tmp, session_path())
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return record


def load_session(now: Optional[datetime] = None) -> Optional[dict]:
    """The saved session if present and not yet expired, else None."""
    try:
        with open(session_path(), encoding="utf-8") as fh:
            record = json.load(fh)
        expires = datetime.fromisoformat(record["expires_at"])
        if not record.get("access_token"):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if (now or datetime.now(IST)) >= expires:
        return None
    return record


def clear_session() -> None:
    try:
        os.remove(session_path())
    except FileNotFoundError:
        pass


def public_status(now: Optional[datetime] = None) -> dict:
    """Connection status without the token — safe to show in the UI."""
    record = load_session(now)
    return {
        "configured": is_configured(),
        "connected": record is not None,
        "user_id": (record or {}).get("user_id", ""),
        "user_name": (record or {}).get("user_name", ""),
        "login_at": (record or {}).get("login_at"),
        "expires_at": (record or {}).get("expires_at"),
    }


def exchange_request_token(request_token: str, client_factory=None) -> dict:
    """Swap Zerodha's one-time request_token for an access token and save it."""
    if not is_configured():
        raise RuntimeError("KITE_API_KEY / KITE_API_SECRET are not set")
    if client_factory is None:
        from kiteconnect import KiteConnect
        client_factory = KiteConnect
    kite = client_factory(api_key=api_key())
    data = kite.generate_session(request_token, api_secret=api_secret())
    return save_session(data["access_token"], data.get("user_id", ""), data.get("user_name", ""))
