"""
Read-only data access for the web dashboard.

Reads the telemetry and journal files the trading engine writes:
  - data/control_tower.db       (TelemetryLogger: ct_cycles, ct_decisions, ct_events)
  - data/paper_trades.csv       (OrderManager trade journal)
  - data/paper_trading_daily.json, data/logs/eod_report_*.txt  (EOD outputs)

Never imports trading-brain code and never writes anything.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# DASHBOARD_DATA_DIR lets the UI be previewed against a copy/fixture of data/.
DATA_DIR = os.getenv("DASHBOARD_DATA_DIR") or os.path.join(_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "control_tower.db")
JOURNAL_PATH = os.path.join(DATA_DIR, "paper_trades.csv")

_OPEN_EVENTS = {"OPEN", "REENTRY_OPEN", "AET_CONFIRMED_OPEN"}
_TERMINAL_EVENTS = {"CLOSE", "CANCELLED"}


# ── SQLite helpers (read-only URI mode) ──────────────────────────────────────

def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def _scalar(sql: str, params: tuple = (), default: Any = 0) -> Any:
    rows = _query(sql, params)
    if not rows:
        return default
    val = next(iter(rows[0].values()))
    return default if val is None else val


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── Mode / status ────────────────────────────────────────────────────────────

def trading_mode() -> str:
    """Mirrors OrderManager's live gate: LIVE only when both flags are set."""
    paper = os.getenv("PAPER_TRADING", "true").lower() == "true"
    live_auth = os.getenv("LIVE_TRADING_AUTHORIZED", "").lower() == "true"
    return "LIVE" if (not paper and live_auth) else "PAPER"


def total_capital() -> float:
    return _to_float(os.getenv("TOTAL_CAPITAL")) or 10_000_000.0


def service_status() -> Dict[str, Any]:
    rows = _query("SELECT ts, event_type FROM ct_events ORDER BY id DESC LIMIT 1")
    if not rows:
        return {"status": "UNKNOWN", "last_ts": None, "last_event": "", "age_min": None}
    ts_str, last_event = rows[0]["ts"], rows[0]["event_type"]
    try:
        age = abs((datetime.now() - datetime.fromisoformat(ts_str[:19])).total_seconds() / 60)
    except ValueError:
        return {"status": "UNKNOWN", "last_ts": ts_str, "last_event": last_event, "age_min": None}
    status = "ONLINE" if age < 10 else "IDLE" if age < 60 else "OFFLINE"
    return {"status": status, "last_ts": ts_str[:19], "last_event": last_event, "age_min": round(age, 1)}


# ── Cycles / decisions / events ──────────────────────────────────────────────

def latest_cycle() -> Dict[str, Any]:
    rows = _query("SELECT * FROM ct_cycles ORDER BY started_at DESC LIMIT 1")
    if not rows:
        return {}
    cycle = rows[0]
    cycle["decision_passed"] = _scalar(
        "SELECT COUNT(*) FROM ct_decisions WHERE cycle_id=? AND decision='APPROVED'",
        (cycle.get("cycle_id", ""),),
    )
    if cycle.get("had_error"):
        cycle["status"] = "ERROR"
    elif cycle.get("completed_at"):
        cycle["status"] = "COMPLETE"
    else:
        cycle["status"] = "RUNNING"
    if not cycle.get("cycle_ms") and cycle.get("started_at") and cycle.get("completed_at"):
        try:
            start = datetime.fromisoformat(cycle["started_at"][:19])
            end = datetime.fromisoformat(cycle["completed_at"][:19])
            cycle["cycle_ms"] = int((end - start).total_seconds() * 1000)
        except ValueError:
            pass
    return cycle


def cycle_history(n: int = 50) -> List[Dict[str, Any]]:
    return _query("SELECT * FROM ct_cycles ORDER BY started_at DESC LIMIT ?", (n,))


def decisions(n: int = 200, decision: str = "") -> List[Dict[str, Any]]:
    if decision:
        return _query(
            "SELECT * FROM ct_decisions WHERE decision=? ORDER BY id DESC LIMIT ?",
            (decision.upper(), n),
        )
    return _query("SELECT * FROM ct_decisions ORDER BY id DESC LIMIT ?", (n,))


def rejection_summary() -> List[Dict[str, Any]]:
    return _query(
        "SELECT rejection_reason AS reason, COUNT(*) AS count FROM ct_decisions "
        "WHERE decision='REJECTED' AND rejection_reason != '' "
        "GROUP BY rejection_reason ORDER BY count DESC LIMIT 12"
    )


def strategy_distribution() -> List[Dict[str, Any]]:
    return _query(
        "SELECT strategy, COUNT(*) AS count, AVG(confidence) AS avg_confidence, "
        "SUM(CASE WHEN decision='APPROVED' THEN 1 ELSE 0 END) AS approved "
        "FROM ct_decisions GROUP BY strategy ORDER BY count DESC LIMIT 15"
    )


def funnel_history(n: int = 30) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT cycle_id, started_at, signals_generated, strategies_assigned, "
        "risk_approved, sim_approved, trades_executed FROM ct_cycles "
        "WHERE signals_generated > 0 ORDER BY started_at DESC LIMIT ?",
        (n,),
    )
    return list(reversed(rows))


def recent_events(n: int = 100) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT id, ts, cycle_id, event_type, source_agent, payload "
        "FROM ct_events ORDER BY id DESC LIMIT ?",
        (n,),
    )
    for row in rows:
        try:
            row["payload"] = json.loads(row.get("payload") or "{}")
        except (TypeError, ValueError):
            pass
    return rows


def agent_stats() -> List[Dict[str, Any]]:
    # 'risk.check.failed' / 'trade.rejected' are normal operation, not errors
    return _query(
        "SELECT source_agent AS agent, COUNT(*) AS event_count, "
        "SUM(CASE WHEN (event_type LIKE '%fail%' OR event_type LIKE '%error%') "
        "AND event_type NOT IN ('risk.check.failed','trade.rejected') "
        "THEN 1 ELSE 0 END) AS error_count, MAX(ts) AS last_seen "
        "FROM ct_events WHERE source_agent IS NOT NULL AND source_agent != '' "
        "GROUP BY source_agent ORDER BY event_count DESC"
    )


def today_event_count() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    return int(_scalar("SELECT COUNT(*) FROM ct_events WHERE ts LIKE ?", (today + "%",), 0))


# ── Scheduler ────────────────────────────────────────────────────────────────

_LEGACY_SLOTS = {"market_regime_analysis", "opportunity_scan", "mid_day_review"}
_WEEKEND_ONLY = {"saturday_intelligence": {5}, "sunday_intelligence": {6}}
_WEEKDAY_ONLY = {"premarket_refiner"}


def _read_schedule() -> Dict[str, str]:
    """Parse SCHEDULE from config.py by regex (no import of the trading config needed)."""
    schedule: Dict[str, str] = {}
    try:
        with open(os.path.join(_ROOT, "config.py"), encoding="utf-8") as fh:
            in_block = False
            for line in fh:
                if re.search(r"^SCHEDULE\s*=\s*\{", line):
                    in_block = True
                    continue
                if in_block:
                    if "}" in line:
                        break
                    m = re.search(r'"(\w+)"\s*:\s*"(\d{2}:\d{2})"', line.strip())
                    if m and not line.strip().startswith("#") and m.group(1) not in _LEGACY_SLOTS:
                        schedule[m.group(1)] = m.group(2)
    except OSError:
        pass
    return schedule


def scheduler_status() -> Dict[str, Any]:
    schedule = _read_schedule()
    now = datetime.now()
    today, now_hhmm, weekday = now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), now.weekday()

    done_times = [
        r["started_at"][11:16]
        for r in _query("SELECT started_at FROM ct_cycles WHERE started_at LIKE ?", (today + "%",))
        if len(r.get("started_at") or "") >= 16
    ]
    done_times += [
        r["ts"][11:16]
        for r in _query("SELECT ts FROM ct_events WHERE ts LIKE ?", (today + "%",))
        if len(r.get("ts") or "") >= 16
    ]

    slots = []
    next_slot = None
    for name, hhmm in sorted(schedule.items(), key=lambda x: x[1]):
        label = name.replace("_", " ").capitalize()
        if name in _WEEKEND_ONLY and weekday not in _WEEKEND_ONLY[name]:
            status = "WEEKEND_ONLY"
        elif name in _WEEKDAY_ONLY and weekday >= 5:
            status = "WEEKDAY_ONLY"
        elif any(abs(int(t.replace(":", "")) - int(hhmm.replace(":", ""))) <= 10 for t in done_times):
            status = "DONE"
        elif hhmm <= now_hhmm:
            status = "MISSED"
        else:
            status = "PENDING"
        slots.append({"name": name, "label": label, "time": hhmm, "status": status})
        if next_slot is None and hhmm > now_hhmm:
            h, m = map(int, hhmm.split(":"))
            secs = (now.replace(hour=h, minute=m, second=0, microsecond=0) - now).total_seconds()
            next_slot = {"name": name, "label": label, "time": hhmm, "seconds_until": int(secs)}
    return {"slots": slots, "next": next_slot}


# ── Trade journal (paper_trades.csv) ─────────────────────────────────────────

def _read_journal() -> List[Dict[str, Any]]:
    if not os.path.exists(JOURNAL_PATH):
        return []
    try:
        with open(JOURNAL_PATH, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return []
    for row in rows:
        for key in ("quantity", "entry_price", "stop_loss", "target", "confidence", "rr", "exit_price", "pnl"):
            row[key] = _to_float(row.get(key))
        row["event"] = (row.get("event") or "").strip().upper()
    return rows


def trades_summary() -> Dict[str, Any]:
    """Open positions, closed trades, equity curve and per-strategy / per-day stats."""
    journal = _read_journal()
    capital = total_capital()

    opens: Dict[str, Dict[str, Any]] = {}
    closed: List[Dict[str, Any]] = []
    for row in journal:
        oid = row.get("order_id") or ""
        if row["event"] in _OPEN_EVENTS:
            opens[oid] = row
        elif row["event"] == "CLOSE":
            entry = opens.pop(oid, None)
            trade = dict(entry or row)
            trade.update({
                "opened_at": (entry or {}).get("timestamp"),
                "closed_at": row.get("timestamp"),
                "exit_price": row.get("exit_price"),
                "pnl": row.get("pnl") or 0.0,
                "reason": row.get("reason") or "",
            })
            closed.append(trade)
        elif row["event"] in _TERMINAL_EVENTS:
            opens.pop(oid, None)

    open_positions = [
        {
            "order_id": r.get("order_id"), "symbol": r.get("symbol"), "direction": r.get("direction"),
            "quantity": r.get("quantity"), "entry_price": r.get("entry_price"),
            "stop_loss": r.get("stop_loss"), "target": r.get("target"),
            "strategy": r.get("strategy"), "confidence": r.get("confidence"),
            "opened_at": r.get("timestamp"),
            "exposure": (r.get("quantity") or 0) * (r.get("entry_price") or 0),
        }
        for r in opens.values()
    ]

    closed.sort(key=lambda t: t.get("closed_at") or "")
    equity, running = [], 0.0
    for t in closed:
        running += t["pnl"]
        equity.append({"ts": t["closed_at"], "pnl": round(t["pnl"], 2), "cumulative": round(running, 2),
                       "equity": round(capital + running, 2)})

    by_strategy: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    by_day: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    for t in closed:
        for bucket in (by_strategy[t.get("strategy") or "unknown"], by_day[(t.get("closed_at") or "")[:10]]):
            bucket["trades"] += 1
            bucket["wins"] += 1 if t["pnl"] > 0 else 0
            bucket["pnl"] += t["pnl"]

    wins = [t["pnl"] for t in closed if t["pnl"] > 0]
    losses = [t["pnl"] for t in closed if t["pnl"] < 0]
    today = datetime.now().strftime("%Y-%m-%d")
    realized_today = sum(t["pnl"] for t in closed if (t.get("closed_at") or "").startswith(today))
    peak, max_dd = 0.0, 0.0
    for point in equity:
        peak = max(peak, point["cumulative"])
        max_dd = max(max_dd, peak - point["cumulative"])

    return {
        "capital": capital,
        "open_positions": open_positions,
        "closed_trades": list(reversed(closed))[:500],
        "equity_curve": equity,
        "by_strategy": sorted(
            ({"strategy": k, **v, "pnl": round(v["pnl"], 2),
              "win_rate": v["wins"] / v["trades"] if v["trades"] else 0} for k, v in by_strategy.items()),
            key=lambda x: x["pnl"], reverse=True),
        "by_day": sorted(
            ({"date": k, **v, "pnl": round(v["pnl"], 2)} for k, v in by_day.items() if k),
            key=lambda x: x["date"]),
        "stats": {
            "total_trades": len(closed),
            "win_rate": len(wins) / len(closed) if closed else None,
            "total_pnl": round(sum(t["pnl"] for t in closed), 2),
            "realized_today": round(realized_today, 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses else None,
            "max_drawdown": round(max_dd, 2),
            "open_count": len(open_positions),
            "open_exposure": round(sum(p["exposure"] for p in open_positions), 2),
        },
    }


# ── EOD ──────────────────────────────────────────────────────────────────────

def eod_report() -> Dict[str, Any]:
    daily: Optional[Dict[str, Any]] = None
    path = os.path.join(DATA_DIR, "paper_trading_daily.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                daily = json.load(fh)
        except (OSError, ValueError):
            daily = None
    text = None
    files = sorted(glob.glob(os.path.join(DATA_DIR, "logs", "eod_report_*.txt")), reverse=True)
    if files:
        try:
            with open(files[0], encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = None
    return {"daily": daily, "report_text": text}
