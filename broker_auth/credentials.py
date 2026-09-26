"""
Encrypted broker credential store (Zerodha Kite, Dhan, AngelOne).

Credentials entered on the dashboard's Settings page live in
data/broker/credentials.enc (git-ignored, mode 600), encrypted with Fernet.
The key is CREDENTIALS_KEY from the server .env — deliberately NOT stored next
to the ciphertext, so a copy of data/ (backup, log bundle) reveals nothing.
Without a key the store is locked: nothing can be saved and only .env
values are used.

Lookup order for every field: saved setting → environment variable (.env).
Secrets are never returned in status output — only whether a field is set,
where it came from, and a masked hint (last 4 characters).

Generate a key (on the server, once):
    python -m broker_auth.credentials --generate-key     # prints CREDENTIALS_KEY=...
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))
STORE_FILENAME = "credentials.enc"
AUDIT_FILENAME = "credentials_audit.jsonl"
MAX_VALUE_LENGTH = 512

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCK = threading.Lock()

# broker → field → (env var fallback, label, is_secret)
BROKERS: Dict[str, Dict[str, tuple]] = {
    "kite": {
        "user_id": ("KITE_USER_ID", "Zerodha user ID", False),
        "password": ("KITE_PASSWORD", "Zerodha login password", True),
        "api_key": ("KITE_API_KEY", "Kite Connect API key", False),
        "api_secret": ("KITE_API_SECRET", "Kite Connect API secret", True),
        "totp_secret": ("KITE_TOTP_SECRET", "TOTP secret key", True),
    },
    "dhan": {
        "client_id": ("DHAN_CLIENT_ID", "Client ID", False),
        "access_token": ("DHAN_ACCESS_TOKEN", "Access token", True),
    },
    "angelone": {
        "api_key": ("ANGELONE_API_KEY", "API key", False),
        "client_id": ("ANGELONE_CLIENT_ID", "Client ID", False),
        "password": ("ANGELONE_PASSWORD", "PIN / password", True),
        "totp_secret": ("ANGELONE_TOTP_SECRET", "TOTP secret", True),
    },
}
# Fields a broker works without (Kite: user ID / password / TOTP only enable the automatic daily login).
OPTIONAL_FIELDS: Dict[str, frozenset] = {"kite": frozenset({"user_id", "password", "totp_secret"})}
BROKER_LABELS = {"kite": "Zerodha (Kite)", "dhan": "Dhan", "angelone": "AngelOne"}


class StoreLocked(RuntimeError):
    """CREDENTIALS_KEY is missing or wrong — the encrypted store can't be used."""


class InvalidInput(ValueError):
    pass


# ── Paths / key ──────────────────────────────────────────────────────────────

def store_dir() -> str:
    return os.getenv("CREDENTIALS_DIR") or os.getenv("KITE_SESSION_DIR") or os.path.join(_ROOT, "data", "broker")


def store_path() -> str:
    return os.path.join(store_dir(), STORE_FILENAME)


def audit_path() -> str:
    return os.path.join(store_dir(), AUDIT_FILENAME)


def _fernet():
    key = (os.getenv("CREDENTIALS_KEY") or "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        return None


def is_unlocked() -> bool:
    return _fernet() is not None


def generate_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


# ── Read / write ─────────────────────────────────────────────────────────────

def _read_store() -> Dict[str, Dict[str, str]]:
    """Decrypted saved settings ({} if none). Raises StoreLocked if the key can't decrypt."""
    try:
        with open(store_path(), "rb") as fh:
            blob = fh.read()
    except FileNotFoundError:
        return {}
    f = _fernet()
    if f is None:
        raise StoreLocked("CREDENTIALS_KEY is not set")
    from cryptography.fernet import InvalidToken
    try:
        data = json.loads(f.decrypt(blob).decode())
    except InvalidToken as exc:
        raise StoreLocked("CREDENTIALS_KEY does not match the saved credentials") from exc
    return data if isinstance(data, dict) else {}


def _write_store(data: Dict[str, Dict[str, str]]) -> None:
    f = _fernet()
    if f is None:
        raise StoreLocked("CREDENTIALS_KEY is not set — cannot save credentials")
    os.makedirs(store_dir(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=store_dir(), prefix=".credentials.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(f.encrypt(json.dumps(data).encode()))
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, store_path())
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _saved() -> Dict[str, Dict[str, str]]:
    """Saved settings, or {} when the store is locked/unreadable (env fallback still applies)."""
    try:
        return _read_store()
    except StoreLocked:
        return {}


def get(broker: str, field: str) -> str:
    """Effective value: saved setting first, then the .env variable."""
    env_name = BROKERS[broker][field][0]
    value = (_saved().get(broker) or {}).get(field)
    return value if value else (os.getenv(env_name) or "").strip()


def get_all(broker: str) -> Dict[str, str]:
    saved = _saved().get(broker) or {}
    return {f: (saved.get(f) or (os.getenv(spec[0]) or "").strip()) for f, spec in BROKERS[broker].items()}


def is_complete(broker: str) -> bool:
    """All required fields set (optional ones don't count)."""
    optional = OPTIONAL_FIELDS.get(broker, frozenset())
    return all(v for f, v in get_all(broker).items() if f not in optional)


def store_mtime() -> Optional[int]:
    """Changes whenever saved credentials change — lets the engine hot-reload."""
    try:
        return os.stat(store_path()).st_mtime_ns
    except OSError:
        return None


def _hint(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 4 else "••••"


def status() -> dict:
    """Per-broker, per-field status. Never contains secret values."""
    try:
        saved, locked_error = _read_store(), None
    except StoreLocked as exc:
        saved, locked_error = {}, str(exc)
    brokers = {}
    for broker, fields in BROKERS.items():
        out_fields = {}
        for field, (env_name, label, secret) in fields.items():
            s_val = (saved.get(broker) or {}).get(field) or ""
            e_val = (os.getenv(env_name) or "").strip()
            value, source = (s_val, "settings") if s_val else ((e_val, "env") if e_val else ("", None))
            out_fields[field] = {"label": label, "secret": secret, "set": bool(value), "source": source,
                                 "hint": _hint(value) if value else "",
                                 "optional": field in OPTIONAL_FIELDS.get(broker, frozenset())}
        brokers[broker] = {"label": BROKER_LABELS[broker], "fields": out_fields,
                           "complete": all(v["set"] for v in out_fields.values() if not v["optional"]),
                           "updated_at": (saved.get("_meta") or {}).get(broker)}
    return {"unlocked": locked_error is None and is_unlocked(), "lock_reason": locked_error
            or (None if is_unlocked() else "CREDENTIALS_KEY is not set on the server"), "brokers": brokers}


def _clean(broker: str, values: Dict[str, str]) -> Dict[str, str]:
    if broker not in BROKERS:
        raise InvalidInput(f"Unknown broker: {broker}")
    cleaned = {}
    for field, value in (values or {}).items():
        if field not in BROKERS[broker]:
            raise InvalidInput(f"Unknown field for {broker}: {field}")
        if value is None:
            continue
        if not isinstance(value, str):
            raise InvalidInput(f"{field} must be text")
        value = value.strip()
        if not value:
            continue                      # blank = keep the current value
        if len(value) > MAX_VALUE_LENGTH or any(c in value for c in "\r\n\x00"):
            raise InvalidInput(f"{field} is not a valid value")
        cleaned[field] = value
    return cleaned


def _clean_kite_field(field: str, value: str) -> str:
    label = BROKERS["kite"][field][1]
    if field == "user_id":
        value = value.upper()
        if not (value.isalnum() and 4 <= len(value) <= 12):
            raise InvalidInput(f"{label} should look like AB1234")
    elif field == "totp_secret":
        import base64
        import binascii
        value = value.replace(" ", "").upper()
        try:
            base64.b32decode(value + "=" * (-len(value) % 8))
        except (binascii.Error, ValueError):
            raise InvalidInput(f"{label} is not valid — paste the key shown under 'Can't scan the QR code?'")
        if len(value) < 16:
            raise InvalidInput(f"{label} looks too short — paste the full key, not a 6-digit code")
    return value


def save(broker: str, values: Dict[str, str], actor: str = "dashboard") -> List[str]:
    """Update only the non-blank fields given. Returns the field names changed."""
    cleaned = _clean(broker, values)
    if not cleaned:
        return []
    with _LOCK:
        data = _read_store()
        data.setdefault(broker, {}).update(cleaned)
        data.setdefault("_meta", {})[broker] = datetime.now(IST).isoformat(timespec="seconds")
        _write_store(data)
    _audit("save", broker, sorted(cleaned), actor)
    return sorted(cleaned)


def remove(broker: str, actor: str = "dashboard") -> bool:
    """Delete all saved fields for a broker (.env values, if any, still apply)."""
    if broker not in BROKERS:
        raise InvalidInput(f"Unknown broker: {broker}")
    with _LOCK:
        data = _read_store()
        existed = bool(data.pop(broker, None))
        (data.get("_meta") or {}).pop(broker, None)
        if existed:
            _write_store(data)
    if existed:
        _audit("remove", broker, [], actor)
    return existed


def _audit(action: str, broker: str, fields: List[str], actor: str) -> None:
    """Append-only change log: when, what, which fields — never values."""
    entry = {"ts": datetime.now(IST).isoformat(timespec="seconds"), "action": action, "broker": broker,
             "fields": fields, "actor": actor}
    try:
        os.makedirs(store_dir(), exist_ok=True)
        with open(audit_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def audit_log(limit: int = 50) -> List[dict]:
    try:
        with open(audit_path(), encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


if __name__ == "__main__":
    if "--generate-key" in sys.argv:
        print(f"CREDENTIALS_KEY={generate_key()}")
    else:
        print(__doc__)
