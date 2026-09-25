"""
AI Trading Brain — web dashboard server (read-only).

Run:
    python -m web_dashboard.server            # http://localhost:8501

Serves a JSON API under /api/* and the built React app (web_dashboard/frontend/dist).
Only GET endpoints exist; nothing here can change trading state.
"""

from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web_dashboard import data

load_dotenv()

DIST_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

app = FastAPI(title="AI Trading Brain Dashboard", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Liveness probe used by the Dockerfile HEALTHCHECK."""
    return {"ok": True, "frontend_built": os.path.isdir(DIST_DIR)}


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

    port = int(os.getenv("DASHBOARD_PORT", "8501"))
    uvicorn.run(app, host=os.getenv("DASHBOARD_HOST", "0.0.0.0"), port=port, log_level="warning")


if __name__ == "__main__":
    main()
