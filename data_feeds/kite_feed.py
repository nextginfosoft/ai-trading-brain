"""
Zerodha Kite Connect data feed
==============================
Real-time quotes and historical candles for NSE equities and indices, using the
daily access token saved by the dashboard's "Connect Zerodha" login
(broker_auth.kite_session). Data only: no order placement here.

Design rules:
  • Never fabricates prices. When Kite is unavailable (no login today, token
    expired, network error) it returns nothing, so DataFeedManager /
    MarketDataRouter fall through to the next source (Dhan → AngelOne → Yahoo).
  • Picks up a new login automatically (the session file is re-read when it
    changes); an expired/invalid token switches the feed off until then.
  • Respects Kite rate limits: quote ≈1 req/s, historical ≈3 req/s.

Symbols accepted: bare NSE symbols ("SBIN"), ".NS"/".BO" suffixes, index
aliases ("NIFTY", "BANKNIFTY", "INDIAVIX", ...) and Yahoo index tickers
("^NSEI"). Returned dicts are keyed by the symbol string that was requested.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from broker_auth import kite_session
from utils import get_logger

from .base_feed import BaseFeed, PriceBar, TickerQuote

log = get_logger(__name__)

# Index aliases used across the codebase → Kite "EXCHANGE:TRADINGSYMBOL"
INDEX_MAP: Dict[str, str] = {
    "NIFTY": "NSE:NIFTY 50",
    "NIFTY50": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "FINNIFTY": "NSE:NIFTY FIN SERVICE",
    "MIDCAPNIFTY": "NSE:NIFTY MID SELECT",
    "INDIAVIX": "NSE:INDIA VIX",
    "SENSEX": "BSE:SENSEX",
}
YAHOO_INDEX_ALIASES = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY", "^INDIAVIX": "INDIAVIX", "^BSESN": "SENSEX"}

# Kite candle intervals and the maximum calendar days per historical request
INTERVAL_MAP: Dict[str, Tuple[str, int]] = {
    "1m": ("minute", 60), "3m": ("3minute", 100), "5m": ("5minute", 100), "10m": ("10minute", 100),
    "15m": ("15minute", 200), "30m": ("30minute", 200), "60m": ("60minute", 400), "1h": ("60minute", 400),
    "1d": ("day", 2000),
}

QUOTE_BATCH = 250            # Kite allows up to 500 instruments per quote call
QUOTE_MIN_INTERVAL = 1.05    # seconds between quote calls (limit ≈1/s)
HIST_MIN_INTERVAL = 0.35     # seconds between historical calls (limit ≈3/s)
INSTRUMENT_EXCHANGES = ("NSE", "BSE")


class KiteFeed(BaseFeed):
    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory
        self._client = None
        self._client_token: Optional[str] = None
        self._bad_token: Optional[str] = None       # token Kite rejected; ignored until a new login
        self._lock = threading.Lock()
        self._last_call: Dict[str, float] = {}
        self._tokens: Dict[str, int] = {}           # "NSE:SBIN" → instrument_token
        self._tokens_day: Optional[date] = None
        self._announced_live = False
        self._session_mtime: Optional[int] = None
        self._session: Optional[dict] = None
        self._history_off_day: Optional[date] = None   # set when the plan has no historical-data access

    # ── Identity / state ──────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "KITE" if self.is_live else "KITE(OFF)"

    def _current_token(self) -> Optional[str]:
        """Today's access token, re-reading the session file only when it changes."""
        if not kite_session.api_key():
            return None
        try:
            mtime = os.stat(kite_session.session_path()).st_mtime_ns
        except OSError:
            return None
        if self._session_mtime != mtime:
            self._session_mtime = mtime
            self._session = kite_session.load_session()
        session = self._session
        if not session:
            return None
        # load_session() checks expiry; re-check here because the cached record can age past 06:00
        if datetime.now(kite_session.IST) >= datetime.fromisoformat(session["expires_at"]):
            return None
        token = session.get("access_token")
        if not token or token == self._bad_token:
            return None
        return token

    @property
    def is_live(self) -> bool:
        return self._current_token() is not None

    def _kite(self):
        """Kite client bound to today's token (rebuilt after a new login), or None."""
        token = self._current_token()
        if token is None:
            return None
        with self._lock:
            if self._client is None or self._client_token != token:
                factory = self._client_factory
                if factory is None:
                    try:
                        from kiteconnect import KiteConnect
                    except ImportError:
                        log.warning("[KiteFeed] kiteconnect not installed — Kite data disabled.")
                        return None
                    factory = KiteConnect
                client = factory(api_key=kite_session.api_key())
                client.set_access_token(token)
                self._client, self._client_token = client, token
                if not self._announced_live:
                    log.info("[KiteFeed] Zerodha session active — Kite is the primary Indian data source.")
                    self._announced_live = True
            return self._client

    def _throttle(self, kind: str, min_interval: float) -> None:
        with self._lock:
            wait = self._last_call.get(kind, 0.0) + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call[kind] = time.monotonic()

    def _handle_error(self, where: str, exc: Exception) -> None:
        kind = type(exc).__name__
        if kind == "TokenException":
            # Expired or revoked: stop using this token until the next dashboard login.
            self._bad_token = self._client_token
            self._client = None
            log.warning("[KiteFeed] %s: Zerodha session invalid (%s) — Kite off until next login.", where, exc)
        else:
            log.warning("[KiteFeed] %s failed: %s: %s — falling back to other feeds.", where, kind, exc)

    # ── Symbol mapping ────────────────────────────────────────────────────

    @staticmethod
    def to_kite_symbol(symbol: str) -> Optional[str]:
        """'SBIN' / 'SBIN.NS' → 'NSE:SBIN', 'X.BO' → 'BSE:X', 'NIFTY' / '^NSEI' → 'NSE:NIFTY 50'."""
        s = (symbol or "").strip().upper()
        if not s:
            return None
        s = YAHOO_INDEX_ALIASES.get(s, s)
        if s in INDEX_MAP:
            return INDEX_MAP[s]
        if s.startswith("^") or "=" in s:
            return None                     # other Yahoo tickers (global indices, FX) — not on Kite
        if s.endswith(".BO"):
            return f"BSE:{s[:-3]}"
        return f"NSE:{s[:-3] if s.endswith('.NS') else s}"

    # ── Quotes ────────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Optional[TickerQuote]:
        return self.get_multiple_quotes([symbol]).get(symbol)

    def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, TickerQuote]:
        kite = self._kite()
        if kite is None or not symbols:
            return {}
        wanted: Dict[str, List[str]] = {}          # kite symbol → requested strings
        for s in symbols:
            k = self.to_kite_symbol(s)
            if k:
                wanted.setdefault(k, []).append(s)
        out: Dict[str, TickerQuote] = {}
        keys = list(wanted)
        for i in range(0, len(keys), QUOTE_BATCH):
            batch = keys[i:i + QUOTE_BATCH]
            try:
                self._throttle("quote", QUOTE_MIN_INTERVAL)
                data = kite.quote(batch) or {}
            except Exception as exc:
                self._handle_error("quote", exc)
                return out
            now = datetime.now()
            for k, row in data.items():
                q = self._to_quote(row, now)
                if q is None:
                    continue
                for requested in wanted.get(k, []):
                    out[requested] = TickerQuote(**{**q.__dict__, "symbol": requested})
        return out

    @staticmethod
    def _to_quote(row: dict, now: datetime) -> Optional[TickerQuote]:
        ltp = float(row.get("last_price") or 0)
        if ltp <= 0:
            return None
        ohlc = row.get("ohlc") or {}
        prev = float(ohlc.get("close") or 0)   # Kite's ohlc.close is the previous session close
        change = ltp - prev if prev else float(row.get("net_change") or 0)
        depth = row.get("depth") or {}
        bid = float(((depth.get("buy") or [{}])[0] or {}).get("price") or 0)
        ask = float(((depth.get("sell") or [{}])[0] or {}).get("price") or 0)
        return TickerQuote(
            symbol="",
            timestamp=now,
            ltp=ltp,
            open=float(ohlc.get("open") or 0),
            high=float(ohlc.get("high") or 0),
            low=float(ohlc.get("low") or 0),
            close=prev,
            change=round(change, 4),
            change_pct=round(change / prev * 100, 4) if prev else 0.0,
            volume=float(row.get("volume") or row.get("volume_traded") or 0),
            bid=bid,
            ask=ask,
            oi=float(row.get("oi") or 0),
            feed_source="KITE",
        )

    # ── Instruments (for historical data) ────────────────────────────────

    def _instrument_token(self, kite, kite_symbol: str) -> Optional[int]:
        if self._tokens_day != date.today() or not self._tokens:
            tokens: Dict[str, int] = {}
            for exch in INSTRUMENT_EXCHANGES:
                try:
                    for inst in kite.instruments(exch) or []:
                        tokens[f"{exch}:{inst['tradingsymbol']}"] = int(inst["instrument_token"])
                except Exception as exc:
                    self._handle_error(f"instruments({exch})", exc)
            if tokens:
                self._tokens, self._tokens_day = tokens, date.today()
                log.info("[KiteFeed] Loaded %d instrument tokens.", len(tokens))
        return self._tokens.get(kite_symbol)

    # ── History ───────────────────────────────────────────────────────────

    def get_history(self, symbol: str, days: int = 30, interval: str = "1d") -> List[PriceBar]:
        if self._history_off_day == date.today():
            return []
        kite = self._kite()
        kite_symbol = self.to_kite_symbol(symbol)
        if kite is None or kite_symbol is None or interval not in INTERVAL_MAP:
            return []
        token = self._instrument_token(kite, kite_symbol)
        if token is None:
            return []
        kite_interval, max_days = INTERVAL_MAP[interval]
        end = datetime.now()
        start = end - timedelta(days=days + (5 if interval == "1d" else 0))   # weekend buffer, like DhanFeed
        bars: List[PriceBar] = []
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=max_days), end)
            try:
                self._throttle("hist", HIST_MIN_INTERVAL)
                candles = kite.historical_data(token, chunk_start, chunk_end, kite_interval) or []
            except Exception as exc:
                if type(exc).__name__ == "PermissionException":
                    # Plan without the historical-data API: stop asking for today; quotes stay on Kite.
                    self._history_off_day = date.today()
                    log.warning("[KiteFeed] Historical data not permitted for this Kite app (%s) — "
                                "candles come from fallback feeds today.", exc)
                else:
                    self._handle_error(f"historical_data({kite_symbol})", exc)
                return []
            for c in candles:
                ts = c["date"]
                if isinstance(ts, datetime) and ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)        # Kite returns IST; other feeds use naive local time
                bars.append(PriceBar(symbol=symbol, timestamp=ts, open=float(c["open"]), high=float(c["high"]),
                                     low=float(c["low"]), close=float(c["close"]),
                                     volume=float(c.get("volume") or 0), interval=interval))
            chunk_start = chunk_end + timedelta(seconds=1)
        # de-duplicate chunk boundaries, oldest first
        seen, unique = set(), []
        for b in sorted(bars, key=lambda b: b.timestamp):
            if b.timestamp not in seen:
                seen.add(b.timestamp)
                unique.append(b)
        return unique
