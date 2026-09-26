"""
Automatic daily Zerodha (Kite) login with the user ID, password and TOTP
secret saved on the Settings page.

Opt-in: it only runs when all five Kite fields are set. Without the user ID /
password / TOTP secret, the daily "Connect Zerodha" button is the only login.

Zerodha has no official API for this. login() drives the same requests the
kite.zerodha.com login page makes (password step, then TOTP step), then
follows the Kite Connect redirect to pick up the one-time request_token and
exchanges it exactly like the manual flow (kite_session.exchange_request_token).
Zerodha can change that page at any time; when it does, this fails with a
clear message and the manual button still works.

Safety:
  • Wrong password / TOTP → no more automatic attempts until the saved
    credentials change (Zerodha locks the account after repeated failures).
  • At most MAX_DAILY_ATTEMPTS automatic attempts per day, RETRY_MINUTES apart.
  • One login at a time across the engine and dashboard (lock file).
  • Credential values never appear in logs or in the status file.

Status of the last attempt: data/broker/kite_autologin.json (see public_status()).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional
from urllib.parse import parse_qs, urljoin, urlparse

from broker_auth import credentials, kite_session
from broker_auth.kite_session import IST

log = logging.getLogger(__name__)

KITE_WEB = "https://kite.zerodha.com"
STATUS_FILENAME = "kite_autologin.json"
LOCK_FILENAME = "kite_autologin.lock"
LOCK_STALE_SECONDS = 120
HTTP_TIMEOUT = 15
MAX_REDIRECTS = 10
MAX_DAILY_ATTEMPTS = 4
RETRY_MINUTES = 15
WINDOW_START = (8, 0)      # IST: first automatic attempt of the day (before the 08:30 reminder)
WINDOW_END = (22, 0)
CHECK_SECONDS = 60
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

LOGIN_FIELDS = ("user_id", "password", "totp_secret")


class AutoLoginError(RuntimeError):
    """Login did not complete; safe to retry later."""


class LoginBusy(AutoLoginError):
    """Another process is logging in right now."""


class BadCredentials(AutoLoginError):
    """Zerodha rejected the user ID, password or TOTP — retrying would risk an account lock."""


# ── Configuration / status ───────────────────────────────────────────────────

def is_enabled() -> bool:
    values = credentials.get_all("kite")
    return all(values.values())


def status_path() -> str:
    return os.path.join(kite_session.session_dir(), STATUS_FILENAME)


def _read_status() -> dict:
    try:
        with open(status_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_status(record: dict) -> None:
    os.makedirs(kite_session.session_dir(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=kite_session.session_dir(), prefix=".kite_autologin.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, status_path())
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def public_status() -> dict:
    """Last attempt, safe for the UI."""
    st = _read_status()
    return {
        "enabled": is_enabled(),
        "last_attempt": st.get("ts"),
        "ok": st.get("ok"),
        "message": st.get("message", ""),
        "actor": st.get("actor"),
        "blocked": bool(st.get("blocked")) and st.get("blocked_mtime") == credentials.store_mtime(),
    }


# ── One login at a time (engine + dashboard share data/broker) ──────────────

class _LoginLock:
    def __init__(self):
        self.path = os.path.join(kite_session.session_dir(), LOCK_FILENAME)
        self.fd: Optional[int] = None

    def acquire(self) -> "_LoginLock":
        os.makedirs(kite_session.session_dir(), exist_ok=True)
        try:
            if time.time() - os.path.getmtime(self.path) > LOCK_STALE_SECONDS:
                os.remove(self.path)
        except OSError:
            pass
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise LoginBusy("Another Zerodha login is already in progress") from None
        return self

    def __enter__(self):
        return self if self.fd is not None else self.acquire()

    def __exit__(self, *exc):
        os.close(self.fd)
        try:
            os.remove(self.path)
        except OSError:
            pass


# ── The login itself ─────────────────────────────────────────────────────────

def _totp_now(secret: str, now_fn: Callable[[], float]) -> str:
    import pyotp
    totp = pyotp.TOTP(secret)
    # A code about to roll over can expire in transit; wait for the next one.
    remaining = totp.interval - (now_fn() % totp.interval)
    if remaining < 3:
        time.sleep(remaining + 0.5)
    return totp.at(now_fn())


def _json(resp, step: str) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise AutoLoginError(f"Zerodha {step} step returned an unexpected page (HTTP {resp.status_code})") from None
    return data if isinstance(data, dict) else {}


def _request_token(http, values: dict, now_fn: Callable[[], float]) -> str:
    """Password + TOTP on kite.zerodha.com, then the Kite Connect redirect → request_token."""
    http.headers.update({"User-Agent": USER_AGENT, "X-Kite-Version": "3"})

    # 1. Open the app's Kite Connect login page: sets cookies and gives the sess_id URL.
    first = http.get(f"{kite_session.LOGIN_BASE}?v=3&api_key={values['api_key']}", timeout=HTTP_TIMEOUT)
    connect_url = first.url

    # 2. Password.
    data = _json(http.post(f"{KITE_WEB}/api/login", timeout=HTTP_TIMEOUT,
                           data={"user_id": values["user_id"], "password": values["password"]}), "password")
    if data.get("status") != "success":
        raise BadCredentials(f"Zerodha rejected the user ID or password: {data.get('message') or 'login failed'}")
    login = data.get("data") or {}
    twofa_type = login.get("twofa_type", "totp")
    if twofa_type != "totp":
        raise BadCredentials(f"This Zerodha account uses '{twofa_type}' 2FA — enable TOTP (external authenticator) "
                             "in Kite → My profile → Password & Security")

    # 3. TOTP.
    data = _json(http.post(f"{KITE_WEB}/api/twofa", timeout=HTTP_TIMEOUT, data={
        "user_id": values["user_id"], "request_id": login.get("request_id", ""),
        "twofa_value": _totp_now(values["totp_secret"], now_fn), "twofa_type": "totp", "skip_totp": "true",
    }), "TOTP")
    if data.get("status") != "success":
        raise BadCredentials(f"Zerodha rejected the TOTP code: {data.get('message') or '2FA failed'}")

    # 4. Back to the Kite Connect page, now logged in: it redirects to the app's
    #    redirect URL with ?request_token=… — read it without visiting that URL.
    url = connect_url + ("&" if "?" in connect_url else "?") + "skip_session=true"
    for _ in range(MAX_REDIRECTS):
        resp = http.get(url, allow_redirects=False, timeout=HTTP_TIMEOUT)
        location = resp.headers.get("Location")
        if not location:
            break
        url = urljoin(url, location)
        query = parse_qs(urlparse(url).query)
        if query.get("request_token"):
            return query["request_token"][0]
        if query.get("status") == ["error"] or "/connect/authorize" in url:
            break
    raise AutoLoginError("Zerodha did not return a request token. If this is the first login for this Kite app, "
                         "use Connect Zerodha once and approve the app, then automatic login will work.")


def login(actor: str = "engine", http_factory: Optional[Callable] = None,
          client_factory: Optional[Callable] = None, now_fn: Callable[[], float] = time.time) -> dict:
    """Log in now. Returns {"ok", "message"} and records the attempt in the status file."""
    values = credentials.get_all("kite")
    missing = [credentials.BROKERS["kite"][f][1] for f, v in values.items() if not v]
    if missing:
        return {"ok": False, "message": "Automatic login needs: " + ", ".join(missing)}

    if http_factory is None:
        import requests
        http_factory = requests.Session
    started = datetime.now(IST)
    blocked = False
    try:
        lock = _LoginLock().acquire()
    except LoginBusy as exc:
        return {"ok": False, "message": str(exc)}
    try:
        with lock:
            http = http_factory()
            try:
                token = _request_token(http, values, now_fn)
            finally:
                close = getattr(http, "close", None)
                if close:
                    close()
            record = kite_session.exchange_request_token(token, client_factory=client_factory)
        ok, message = True, f"Logged in to Zerodha as {record.get('user_id') or values['user_id']}."
    except BadCredentials as exc:
        ok, message, blocked = False, str(exc), True
    except kite_session.WrongAccount as exc:
        ok, message, blocked = False, str(exc), True
    except AutoLoginError as exc:
        ok, message = False, str(exc)
    except Exception as exc:                       # network errors, Zerodha outages, SDK errors
        ok, message = False, f"Automatic login failed: {type(exc).__name__}"
    message = _scrub(message, values)

    prev = _read_status()
    day = started.strftime("%Y-%m-%d")
    attempts = (prev.get("attempts", 0) if prev.get("day") == day else 0) + (1 if actor == "engine" else 0)
    _write_status({
        "ts": started.isoformat(timespec="seconds"), "ok": ok, "message": message, "actor": actor,
        "day": day, "attempts": attempts,
        "blocked": blocked, "blocked_mtime": credentials.store_mtime() if blocked else None,
    })
    (log.info if ok else log.warning)("[KiteAutoLogin] %s (%s)", message, actor)
    return {"ok": ok, "message": message}


def _scrub(message: str, values: dict) -> str:
    for v in values.values():
        if v and len(v) >= 4:
            message = message.replace(v, "••••")
    return message[:300]


# ── Engine scheduler ─────────────────────────────────────────────────────────

def should_attempt(now: datetime, needs_login: bool) -> bool:
    """Whether the engine should try an automatic login right now."""
    if not needs_login or not is_enabled():
        return False
    hm = (now.hour, now.minute)
    if not (WINDOW_START <= hm < WINDOW_END):
        return False
    st = _read_status()
    if st.get("blocked") and st.get("blocked_mtime") == credentials.store_mtime():
        return False                               # wait for new credentials on the Settings page
    if st.get("day") == now.strftime("%Y-%m-%d") and st.get("attempts", 0) >= MAX_DAILY_ATTEMPTS:
        return False
    if st.get("ts") and st.get("actor") == "engine":
        try:
            if now - datetime.fromisoformat(st["ts"]) < timedelta(minutes=RETRY_MINUTES):
                return False
        except ValueError:
            pass
    return True


def start_scheduler(needs_login: Callable[[], bool]) -> threading.Thread:
    """Background thread in the engine: log in automatically whenever Kite isn't live."""
    def loop():
        while True:
            try:
                if should_attempt(datetime.now(IST), needs_login()):
                    login(actor="engine")
            except Exception as exc:
                log.warning("[KiteAutoLogin] scheduler error: %s", type(exc).__name__)
            time.sleep(CHECK_SECONDS)

    thread = threading.Thread(target=loop, daemon=True, name="KiteAutoLogin")
    thread.start()
    return thread
