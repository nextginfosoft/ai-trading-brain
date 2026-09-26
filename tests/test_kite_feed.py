"""Kite (Zerodha) data feed and its place in the data routing chains. No network: fake Kite client."""

import os
from datetime import datetime, timedelta

import pytest

# Importing data_feeds pulls in modules that load_dotenv() the developer's .env at
# import time; snapshot/restore so nothing leaks into other tests.
_env_before = dict(os.environ)
from broker_auth import kite_session  # noqa: E402
from broker_auth.kite_session import IST  # noqa: E402
from data_feeds.base_feed import TickerQuote, is_live_broker_source  # noqa: E402
from data_feeds.data_feed_manager import DataFeedManager, _FeedCycleStats, FeedTruthLevel  # noqa: E402
from data_feeds.fallback_contamination_audit import get_trust_multiplier, is_contaminated  # noqa: E402
from data_feeds.kite_feed import KiteFeed  # noqa: E402
from data_feeds.market_data_router import MarketDataRouter  # noqa: E402
from opportunity_engine.invalidation_tracker import InvalidationTracker, FEED_LIVE  # noqa: E402
os.environ.clear()
os.environ.update(_env_before)


class TokenException(Exception):
    """Same class name kiteconnect raises for an expired/invalid token."""


class FakeKite:
    instances = []

    def __init__(self, api_key):
        self.api_key = api_key
        self.token = None
        self.quote_calls = []
        self.hist_calls = []
        self.fail_with = None
        FakeKite.instances.append(self)

    def set_access_token(self, token):
        self.token = token

    def quote(self, keys):
        self.quote_calls.append(list(keys))
        if self.fail_with:
            raise self.fail_with
        prices = {"NSE:SBIN": 800.0, "NSE:NIFTY 50": 25000.0, "NSE:INDIA VIX": 12.5}
        return {k: {"last_price": prices.get(k, 100.0), "volume": 1234, "net_change": 0,
                    "ohlc": {"open": 790.0, "high": 805.0, "low": 785.0, "close": 780.0},
                    "depth": {"buy": [{"price": 799.9}], "sell": [{"price": 800.1}]}}
                for k in keys if not k.startswith("NSE:UNKNOWN")}

    def instruments(self, exchange):
        return [{"tradingsymbol": "SBIN", "instrument_token": 779521}] if exchange == "NSE" else []

    def historical_data(self, token, start, end, interval):
        self.hist_calls.append((token, start, end, interval))
        out, day = [], start.replace(hour=9, minute=15, second=0, microsecond=0)
        while day <= end:
            out.append({"date": day.replace(tzinfo=IST), "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                        "volume": 10})
            day += timedelta(days=1)
        return out


@pytest.fixture(autouse=True)
def kite_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KITE_SESSION_DIR", str(tmp_path / "broker"))
    monkeypatch.setenv("KITE_API_KEY", "k")
    monkeypatch.setenv("KITE_API_SECRET", "s")
    FakeKite.instances.clear()


def login(token="TOK1"):
    kite_session.save_session(token, "AB1234")


@pytest.fixture
def feed():
    return KiteFeed(client_factory=FakeKite)


# ── KiteFeed ─────────────────────────────────────────────────────────────

def test_not_live_without_login_and_returns_nothing(feed):
    assert feed.is_live is False
    assert feed.get_multiple_quotes(["SBIN"]) == {}
    assert feed.get_history("SBIN", 10) == []
    assert FakeKite.instances == []


def test_symbol_mapping():
    m = KiteFeed.to_kite_symbol
    assert m("SBIN") == m("sbin.ns") == "NSE:SBIN"
    assert m("RELIANCE.BO") == "BSE:RELIANCE"
    assert m("NIFTY") == m("^NSEI") == "NSE:NIFTY 50"
    assert m("INDIAVIX") == "NSE:INDIA VIX"
    assert m("^GSPC") is None and m("USDINR=X") is None


def test_quotes_are_live_kite_quotes_keyed_by_requested_symbol(feed):
    login()
    res = feed.get_multiple_quotes(["SBIN", "SBIN.NS", "NIFTY", "^GSPC", "UNKNOWN"])
    assert set(res) == {"SBIN", "SBIN.NS", "NIFTY"}
    q = res["SBIN.NS"]
    assert q.symbol == "SBIN.NS" and q.feed_source == "KITE"
    assert q.ltp == 800.0 and q.close == 780.0 and round(q.change_pct, 2) == 2.56
    assert (q.bid, q.ask, q.volume) == (799.9, 800.1, 1234)
    assert FakeKite.instances[-1].token == "TOK1"


def test_quote_batches_respect_limit(feed, monkeypatch):
    monkeypatch.setattr("data_feeds.kite_feed.QUOTE_MIN_INTERVAL", 0)
    login()
    feed.get_multiple_quotes([f"S{i}" for i in range(600)])
    assert [len(c) for c in FakeKite.instances[-1].quote_calls] == [250, 250, 100]


def test_expired_token_switches_off_until_next_login(feed):
    login("OLD")
    feed.get_multiple_quotes(["SBIN"])
    FakeKite.instances[-1].fail_with = TokenException("Incorrect `api_key` or `access_token`.")
    assert feed.get_multiple_quotes(["SBIN"]) == {}
    assert feed.is_live is False                          # rejected token is not retried
    login("NEW")                                          # user clicks Connect Zerodha again
    assert feed.is_live is True
    assert feed.get_multiple_quotes(["SBIN"])["SBIN"].ltp == 800.0
    assert FakeKite.instances[-1].token == "NEW"


def test_network_error_falls_back_without_disabling(feed):
    login()
    feed.get_multiple_quotes(["SBIN"])
    FakeKite.instances[-1].fail_with = ConnectionError("timeout")
    assert feed.get_multiple_quotes(["SBIN"]) == {}
    assert feed.is_live is True


def test_session_expiry_at_6am(feed):
    kite_session.save_session("T", now=datetime.now(IST) - timedelta(days=2))
    assert feed.is_live is False


def test_history_chunks_by_interval_limit_and_strips_tz(feed, monkeypatch):
    monkeypatch.setattr("data_feeds.kite_feed.HIST_MIN_INTERVAL", 0)
    login()
    bars = feed.get_history("SBIN", days=150, interval="1m")
    calls = FakeKite.instances[-1].hist_calls
    assert len(calls) == 3 and all(c[0] == 779521 and c[3] == "minute" for c in calls)
    assert all((c[2] - c[1]).days <= 60 for c in calls)
    assert bars and bars[0].timestamp.tzinfo is None
    assert [b.timestamp for b in bars] == sorted({b.timestamp for b in bars})   # sorted, no duplicates
    assert feed.get_history("UNLISTED", 5) == [] and feed.get_history("SBIN", 5, "7m") == []


class PermissionException(Exception):
    """Same class name kiteconnect raises when the app lacks an API permission."""


def test_history_permission_error_disables_history_for_the_day_only(feed, monkeypatch):
    monkeypatch.setattr("data_feeds.kite_feed.HIST_MIN_INTERVAL", 0)
    login()
    feed.get_multiple_quotes(["SBIN"])
    client = FakeKite.instances[-1]
    client.historical_data = lambda *a: (_ for _ in ()).throw(PermissionException("Insufficient permission"))
    assert feed.get_history("SBIN", 10) == []
    calls_before = len(client.hist_calls)
    assert feed.get_history("SBIN", 10) == []            # not retried today
    assert len(client.hist_calls) == calls_before
    assert feed.is_live and feed.get_multiple_quotes(["SBIN"])["SBIN"].feed_source == "KITE"


# ── Routing: DataFeedManager ─────────────────────────────────────────────

class StubFeed:
    def __init__(self, live, source, prices=None):
        self.is_live, self.source, self.prices, self.requested = live, source, prices or {}, []

    def get_multiple_quotes(self, symbols):
        self.requested.append(list(symbols))
        return {s: _q(s, self.prices[s], self.source) for s in symbols if s in self.prices}

    def get_quote(self, s):
        return self.get_multiple_quotes([s]).get(s)

    def get_history(self, *a, **k):
        return []


def _q(sym, ltp, src):
    return TickerQuote(symbol=sym, timestamp=datetime.now(), ltp=ltp, open=ltp, high=ltp, low=ltp,
                       close=ltp, change=0, change_pct=0, volume=0, feed_source=src)


def _manager(kite, dhan, yahoo):
    m = object.__new__(DataFeedManager)
    m.kite, m.dhan, m.yahoo = kite, dhan, yahoo
    m.angelone = StubFeed(False, "ANGELONE")
    m._stats = _FeedCycleStats()
    m._last_yahoo_refresh = None
    return m


def test_manager_uses_kite_first_then_falls_back():
    kite = StubFeed(True, "KITE", {"SBIN.NS": 800.0})
    yahoo = StubFeed(True, "YAHOO", {"TCS.NS": 3000.0, "SP500": 5000.0})
    m = _manager(kite, StubFeed(False, "DHAN"), yahoo)
    res = m.get_multiple_quotes(["SBIN.NS", "TCS.NS", "SP500"])
    assert res["SBIN.NS"].feed_source == "KITE" and res["TCS.NS"].feed_source == "YAHOO"
    assert kite.requested == [["SBIN.NS", "TCS.NS"]]          # global symbols never sent to Kite
    assert sorted(yahoo.requested[0]) == ["SP500", "TCS.NS"]  # only what Kite missed + globals
    assert m._stats.kite_hits == 1 and m._stats.truth_level() == FeedTruthLevel.LIVE


def test_manager_unchanged_when_kite_not_connected():
    yahoo = StubFeed(True, "YAHOO", {"SBIN.NS": 801.0})
    m = _manager(StubFeed(False, "KITE"), StubFeed(False, "DHAN"), yahoo)
    assert m.get_multiple_quotes(["SBIN.NS"])["SBIN.NS"].feed_source == "YAHOO"
    assert m.get_quote("SBIN.NS").feed_source == "YAHOO"


# ── Routing: MarketDataRouter (stop-loss / target pricing) ──────────────

def test_router_prefers_kite_and_reports_it():
    r = object.__new__(MarketDataRouter)
    kite = StubFeed(True, "KITE", {"SBIN": 800.0})
    dhan = StubFeed(False, "DHAN")
    yahoo = StubFeed(True, "YAHOO", {"TCS.NS": 3000.0})
    r._kite, r._dhan, r._yahoo = kite, dhan, yahoo
    r._ltp_cache = {}
    for attr in ("_kite_success", "_kite_fail", "_dhan_success", "_dhan_fail", "_yahoo_success",
                 "_yahoo_fail", "_cache_served", "_degraded_count", "_divergence_count", "_total_calls"):
        setattr(r, attr, 0)
    res = r.get_live_prices(["SBIN", "TCS"])
    assert res["SBIN"].feed_source == "KITE" and res["TCS"].feed_source == "YAHOO"
    assert r.get_symbol_sources() == {"SBIN": "KITE", "TCS": "YAHOO"}
    stats = r.get_router_stats()
    assert stats["kite_live"] is True and stats["kite_success"] == 1
    assert "Kite=" in r.get_source_report()


# ── Kite counts as live broker data everywhere ──────────────────────────

def test_kite_is_trusted_like_dhan():
    assert is_live_broker_source("KITE") and is_live_broker_source("dhan")
    assert not is_live_broker_source("YAHOO")
    assert get_trust_multiplier("KITE") == 1.0 and not is_contaminated("KITE")
    assert InvalidationTracker.classify_feed_source("SBIN", 1000.0, 812.0, "KITE") == FEED_LIVE
