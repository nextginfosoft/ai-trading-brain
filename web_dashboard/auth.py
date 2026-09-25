"""
Password login for the web dashboard.

- The password is never stored in plain text: DASHBOARD_PASSWORD_HASH holds a
  salted PBKDF2-SHA256 hash (create it with `python -m web_dashboard.set_password`).
- Sessions are stateless signed tokens in an HttpOnly, SameSite=Strict cookie.
  The signing key is derived from the password hash, so changing the password
  logs every existing session out.
- Fails closed: with no hash configured, nobody can log in.
- Repeated failures lock the client IP out for a while.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Dict, List, Optional

PBKDF2_ITERATIONS = 600_000
COOKIE_NAME = "atb_session"
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ── Password hashing ─────────────────────────────────────────────────────────
# Format uses ':' separators (not '$') so the value is safe in .env files.

def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256:{iterations}:{_b64(salt)}:{_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split(":")
        if algo != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(iterations))
        return hmac.compare_digest(candidate, _unb64(digest))
    except (ValueError, TypeError):
        return False


def configured_hash() -> str:
    return (os.getenv("DASHBOARD_PASSWORD_HASH") or "").strip()


def session_hours() -> float:
    try:
        return max(0.25, float(os.getenv("DASHBOARD_SESSION_HOURS", "12")))
    except ValueError:
        return 12.0


def cookie_secure() -> bool:
    """Set DASHBOARD_COOKIE_SECURE=true once the dashboard is served over HTTPS."""
    return os.getenv("DASHBOARD_COOKIE_SECURE", "").lower() == "true"


# ── Session tokens ───────────────────────────────────────────────────────────

def _signing_key(pw_hash: str) -> bytes:
    return hmac.new(pw_hash.encode(), b"atb-dashboard-session-v1", hashlib.sha256).digest()


def issue_token(pw_hash: str, now: Optional[float] = None) -> str:
    expires = int((now or time.time()) + session_hours() * 3600)
    body = f"{expires}.{secrets.token_urlsafe(12)}"
    sig = hmac.new(_signing_key(pw_hash), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def verify_token(token: Optional[str], pw_hash: str, now: Optional[float] = None) -> bool:
    if not token or not pw_hash:
        return False
    try:
        expires, nonce, sig = token.split(".")
        expected = hmac.new(_signing_key(pw_hash), f"{expires}.{nonce}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            return False
        return int(expires) > (now or time.time())
    except (ValueError, TypeError):
        return False


# ── Brute-force lockout (in-memory, per client IP) ───────────────────────────

class LoginThrottle:
    def __init__(self, max_failures: int = MAX_FAILURES, lockout_seconds: int = LOCKOUT_SECONDS):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> int:
        """Seconds until this IP may try again (0 = allowed)."""
        now = time.time()
        with self._lock:
            recent = [t for t in self._failures.get(ip, []) if now - t < self.lockout_seconds]
            self._failures[ip] = recent
            if len(recent) >= self.max_failures:
                return int(self.lockout_seconds - (now - recent[-self.max_failures])) + 1
            return 0

    def record_failure(self, ip: str) -> None:
        with self._lock:
            self._failures.setdefault(ip, []).append(time.time())

    def reset(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
