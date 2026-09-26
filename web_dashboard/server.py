"""
TradeSense AI — web dashboard server (read-only).

Run:
    python -m web_dashboard.server            # http://localhost:8501

Serves a JSON API under /api/* and the built React app (web_dashboard/frontend/dist).
Data endpoints are GET-only; nothing here can place, change or cancel trades.
Every /api/* route except /api/auth/* requires a password login (see auth.py).
The only writes are broker access: the Zerodha (Kite) daily login session
(/api/kite/*, /kite/callback) and broker credentials on the Settings page
(/api/settings/brokers/*, encrypted; saving or removing requires the dashboard
password again). Secret values are never sent back to the browser.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from datetime import datetime
from typing import Dict
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from broker_auth import connection_tests, credentials, kite_session
from web_dashboard import auth, data

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env() -> None:
    """Load .env.local then .env (load_dotenv never overwrites, so .env.local wins).
    Called at server start, not import, so importing the app has no side effects."""
    load_dotenv(os.path.join(_ROOT, ".env.local"))
    load_dotenv(os.path.join(_ROOT, ".env"))


DIST_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

app = FastAPI(title="TradeSense AI Dashboard", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1024)
throttle = auth.LoginThrottle()


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    return auth.client_ip(peer, request.headers.get("x-forwarded-for"))


def _is_authenticated(request: Request) -> bool:
    return auth.verify_token(request.cookies.get(auth.COOKIE_NAME), auth.configured_hash())


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/auth/") and not _is_authenticated(request):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Liveness probe used by the Dockerfile HEALTHCHECK (no data exposed)."""
    return {"ok": True, "frontend_built": os.path.isdir(DIST_DIR)}


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    password: str


@app.get("/api/auth/session")
def session(request: Request) -> dict:
    return {"authenticated": _is_authenticated(request), "configured": bool(auth.configured_hash())}


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request) -> JSONResponse:
    pw_hash = auth.configured_hash()
    if not pw_hash:
        return JSONResponse(
            {"detail": "No dashboard password is set. Run: python -m web_dashboard.set_password"},
            status_code=503,
        )
    ip = _client_ip(request)
    wait = throttle.retry_after(ip)
    if wait:
        return JSONResponse(
            {"detail": f"Too many failed attempts. Try again in {max(1, wait // 60)} min."},
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    if not auth.verify_password(body.password, pw_hash):
        throttle.record_failure(ip)
        return JSONResponse({"detail": "Incorrect password"}, status_code=401)

    throttle.reset(ip)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_token(pw_hash),
        max_age=int(auth.session_hours() * 3600),
        httponly=True,
        samesite="strict",
        secure=auth.cookie_secure(),
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(auth.COOKIE_NAME, path="/", samesite="strict", httponly=True, secure=auth.cookie_secure())
    return response


# ── Data (login required) ────────────────────────────────────────────────────


@app.get("/api/overview")
def overview() -> dict:
    trades = data.trades_summary()
    return {
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "mode": data.trading_mode(),
        "service": data.service_status(),
        "today_events": data.today_event_count(),
        "capital": trades["capital"],
        "stats": trades["stats"],
        "open_positions": trades["open_positions"],
        "equity_curve": trades["equity_curve"],
        "cycle": data.latest_cycle(),
        "scheduler": data.scheduler_status(),
        "latest_approved": (data.decisions(1, "APPROVED") or [None])[0],
        "recent_decisions": data.decisions(12),
    }


@app.get("/api/trades")
def trades() -> dict:
    return data.trades_summary()


@app.get("/api/decisions")
def decisions(limit: int = Query(200, ge=1, le=2000), decision: str = "") -> dict:
    return {
        "decisions": data.decisions(limit, decision),
        "rejections": data.rejection_summary(),
        "strategies": data.strategy_distribution(),
        "funnel_history": data.funnel_history(),
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "service": data.service_status(),
        "scheduler": data.scheduler_status(),
        "cycles": data.cycle_history(50),
        "agents": data.agent_stats(),
        "events": data.recent_events(150),
    }


@app.get("/api/eod")
def eod() -> dict:
    return data.eod_report()


# ── Zerodha (Kite) daily login ───────────────────────────────────────────────

class _KiteStateStore:
    """One-time `state` values for the Kite login round-trip (10-minute TTL).

    /kite/callback is reached by a cross-site redirect from kite.zerodha.com, so
    the SameSite=Strict session cookie is not sent. Only a logged-in dashboard
    user can obtain a state (via /api/kite/login), and each one works once.
    """

    TTL_SECONDS = 600

    def __init__(self) -> None:
        self._states: Dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self) -> str:
        state = secrets.token_urlsafe(24)
        with self._lock:
            now = time.monotonic()
            self._states = {s: t for s, t in self._states.items() if now - t < self.TTL_SECONDS}
            self._states[state] = now
        return state

    def consume(self, state: str) -> bool:
        with self._lock:
            issued = self._states.pop(state, None)
        return issued is not None and time.monotonic() - issued < self.TTL_SECONDS


kite_states = _KiteStateStore()


def _kite_redirect(outcome: str, reason: str = "") -> RedirectResponse:
    query = {"kite": outcome, **({"reason": reason} if reason else {})}
    return RedirectResponse(f"/?{urlencode(query)}", status_code=303)


@app.get("/api/kite/status")
def kite_status() -> dict:
    return kite_session.public_status()


@app.post("/api/kite/login")
def kite_login() -> JSONResponse:
    if not kite_session.is_configured():
        return JSONResponse({"detail": "KITE_API_KEY / KITE_API_SECRET are not set on the server"},
                            status_code=503)
    return JSONResponse({"url": kite_session.login_url(kite_states.issue())})


@app.post("/api/kite/disconnect")
def kite_disconnect() -> dict:
    kite_session.clear_session()
    return kite_session.public_status()


@app.get("/kite/callback", include_in_schema=False)
def kite_callback(request_token: str = "", status: str = "", state: str = "") -> RedirectResponse:
    """Zerodha redirects here after login (register this URL in the Kite developer console)."""
    if not kite_states.consume(state):
        return _kite_redirect("error", "Login link expired or invalid — click Connect Zerodha again")
    if status != "success" or not request_token:
        return _kite_redirect("error", "Zerodha login was cancelled or failed")
    try:
        kite_session.exchange_request_token(request_token)
    except Exception as exc:  # network / invalid token / wrong secret
        return _kite_redirect("error", f"Token exchange failed: {type(exc).__name__}")
    return _kite_redirect("connected")


# ── Settings: broker credentials ─────────────────────────────────────────────

reauth_throttle = auth.LoginThrottle()


class CredentialsBody(BaseModel):
    password: str
    values: Dict[str, str] = {}


class ConfirmBody(BaseModel):
    password: str


def _confirm_password(password: str, request: Request):
    """Re-check the dashboard password before changing credentials. Returns an error response or None."""
    ip = _client_ip(request)
    wait = reauth_throttle.retry_after(ip)
    if wait:
        return JSONResponse({"detail": f"Too many wrong passwords. Try again in {max(1, wait // 60)} min."},
                            status_code=429, headers={"Retry-After": str(wait)})
    if not auth.verify_password(password or "", auth.configured_hash()):
        reauth_throttle.record_failure(ip)
        return JSONResponse({"detail": "Incorrect dashboard password"}, status_code=403)
    reauth_throttle.reset(ip)
    return None


def _broker_or_404(broker: str):
    if broker not in credentials.BROKERS:
        return JSONResponse({"detail": f"Unknown broker: {broker}"}, status_code=404)
    return None


@app.get("/api/settings/brokers")
def settings_brokers() -> dict:
    return credentials.status()


@app.put("/api/settings/brokers/{broker}")
def settings_save(broker: str, body: CredentialsBody, request: Request) -> JSONResponse:
    err = _broker_or_404(broker) or _confirm_password(body.password, request)
    if err:
        return err
    try:
        changed = credentials.save(broker, body.values)
    except credentials.InvalidInput as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    except credentials.StoreLocked as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    return JSONResponse({"changed": changed, "status": credentials.status()})


@app.post("/api/settings/brokers/{broker}/remove")
def settings_remove(broker: str, body: ConfirmBody, request: Request) -> JSONResponse:
    err = _broker_or_404(broker) or _confirm_password(body.password, request)
    if err:
        return err
    try:
        removed = credentials.remove(broker)
    except credentials.StoreLocked as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    return JSONResponse({"removed": removed, "status": credentials.status()})


@app.post("/api/settings/brokers/{broker}/test")
def settings_test(broker: str) -> JSONResponse:
    err = _broker_or_404(broker)
    if err:
        return err
    return JSONResponse(connection_tests.run_test(broker))


@app.get("/api/settings/audit")
def settings_audit() -> dict:
    return {"entries": credentials.audit_log(50)}


if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Serve the React single-page app; client-side routes fall back to index.html."""
        candidate = os.path.realpath(os.path.join(DIST_DIR, path))
        if path and candidate.startswith(os.path.realpath(DIST_DIR) + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(DIST_DIR, "index.html"))


def main() -> None:
    import uvicorn

    load_env()
    port = int(os.getenv("DASHBOARD_PORT", "8501"))
    uvicorn.run(app, host=os.getenv("DASHBOARD_HOST", "0.0.0.0"), port=port, log_level="warning")


if __name__ == "__main__":
    main()
