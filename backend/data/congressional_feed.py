"""
congressional_feed.py - Quiver Quant connector for congressional trading data.

Provides recent congressional trades, per-ticker lookups, cluster detection,
and politician performance tracking with caching, rate limiting, retries,
SQLite persistence, and mock fallback.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
import threading
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.quiverquant.com/beta"

TRADE_COLUMNS = ["politician", "ticker", "type", "date", "amount_range"]

# SQLite schema for congressional trade cache
_CONGRESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS congressional_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    politician      TEXT    NOT NULL,
    ticker          TEXT    NOT NULL,
    type            TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    amount_range    TEXT,
    fetched_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_congress_ticker ON congressional_trades(ticker);
CREATE INDEX IF NOT EXISTS idx_congress_date ON congressional_trades(date);
CREATE INDEX IF NOT EXISTS idx_congress_politician ON congressional_trades(politician);
CREATE INDEX IF NOT EXISTS idx_congress_fetched ON congressional_trades(fetched_at);
"""


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

class TTLCache:
    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.monotonic() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._store[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    def clear(self) -> None:
        self._store.clear()


class RateLimiter:
    def __init__(self, max_calls: int = 3, period: float = 1.0):
        self._max = max_calls
        self._period = period
        self._tokens = float(max_calls)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._max, self._tokens + elapsed * (self._max / self._period))
            self._last = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) * (self._period / self._max)
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# ---------------------------------------------------------------------------
# SQLite cache layer
# ---------------------------------------------------------------------------

class _CongressDBCache:
    """Thread-safe SQLite cache for congressional trades."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.executescript(_CONGRESS_SCHEMA)
        conn.commit()

    def get_cached_trades(self, max_age_seconds: int = 600) -> pd.DataFrame | None:
        """Return cached trades if fresh enough, else None."""
        conn = self._conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        row = conn.execute(
            "SELECT MAX(fetched_at) as latest FROM congressional_trades"
        ).fetchone()
        if row is None or row["latest"] is None or row["latest"] < cutoff:
            return None

        rows = conn.execute(
            "SELECT politician, ticker, type, date, amount_range FROM congressional_trades"
        ).fetchall()
        if not rows:
            return None

        df = pd.DataFrame([dict(r) for r in rows], columns=TRADE_COLUMNS)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.sort_values("date", ascending=False).reset_index(drop=True)

    def get_cached_by_ticker(self, ticker: str, max_age_seconds: int = 600) -> pd.DataFrame | None:
        """Return cached trades for a specific ticker if fresh enough."""
        conn = self._conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        row = conn.execute(
            "SELECT MAX(fetched_at) as latest FROM congressional_trades WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        if row is None or row["latest"] is None or row["latest"] < cutoff:
            return None

        rows = conn.execute(
            "SELECT politician, ticker, type, date, amount_range FROM congressional_trades WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchall()
        if not rows:
            return None

        df = pd.DataFrame([dict(r) for r in rows], columns=TRADE_COLUMNS)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.sort_values("date", ascending=False).reset_index(drop=True)

    def store_trades(self, df: pd.DataFrame) -> None:
        """Replace cached trades with fresh data."""
        if df.empty:
            return
        conn = self._conn()
        conn.execute("DELETE FROM congressional_trades")
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for _, row in df.iterrows():
            dt = row["date"]
            if pd.notna(dt):
                date_str = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
            else:
                date_str = ""
            rows.append((
                str(row.get("politician", "")),
                str(row.get("ticker", "")),
                str(row.get("type", "")),
                date_str,
                str(row.get("amount_range", "")),
                now,
            ))
        conn.executemany(
            "INSERT INTO congressional_trades (politician, ticker, type, date, amount_range, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        logger.debug("Cached {} congressional trades in SQLite", len(rows))

    def store_ticker_trades(self, ticker: str, df: pd.DataFrame) -> None:
        """Replace cached trades for a specific ticker."""
        if df.empty:
            return
        conn = self._conn()
        conn.execute("DELETE FROM congressional_trades WHERE ticker = ?", (ticker.upper(),))
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for _, row in df.iterrows():
            dt = row["date"]
            if pd.notna(dt):
                date_str = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
            else:
                date_str = ""
            rows.append((
                str(row.get("politician", "")),
                str(row.get("ticker", "")),
                str(row.get("type", "")),
                date_str,
                str(row.get("amount_range", "")),
                now,
            ))
        conn.executemany(
            "INSERT INTO congressional_trades (politician, ticker, type, date, amount_range, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        logger.debug("Cached {} trades for ticker {} in SQLite", len(rows), ticker)


# ---------------------------------------------------------------------------
# Congressional Feed
# ---------------------------------------------------------------------------

MOCK_POLITICIANS = [
    "Nancy Pelosi", "Dan Crenshaw", "Tommy Tuberville", "Mark Green",
    "Josh Gottheimer", "Michael McCaul", "Ro Khanna", "Pat Fallon",
    "Virginia Foxx", "Marjorie Taylor Greene", "John Curtis", "Earl Blumenauer",
]

MOCK_TICKERS = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "AMD", "CRM", "PLTR", "COIN", "JPM"]

AMOUNT_RANGES = [
    "$1,001 - $15,000",
    "$15,001 - $50,000",
    "$50,001 - $100,000",
    "$100,001 - $250,000",
    "$250,001 - $500,000",
    "$500,001 - $1,000,000",
    "$1,000,001 - $5,000,000",
]


class CongressionalFeed:
    """
    Quiver Quant congressional trading data feed.

    Parameters
    ----------
    api_key : str | None
        Quiver Quant API token. Falls back to env ``QUIVER_API_KEY``
        or ``QUIVER_QUANT_KEY``.
    use_mock : bool
        Return synthetic data.
    cache_ttl : int
        Default in-memory cache TTL in seconds.
    db_path : str | None
        Path for SQLite cache. If None, uses ``data/congressional_cache.db``.
    max_retries : int
        Max retry attempts.
    """

    def __init__(
        self,
        api_key: str | None = None,
        use_mock: bool = False,
        cache_ttl: int = 300,
        db_path: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.getenv("QUIVER_API_KEY") or os.getenv("QUIVER_QUANT_KEY", "")
        self.use_mock = use_mock
        self.max_retries = max_retries

        self._cache = TTLCache(default_ttl=cache_ttl)
        self._limiter = RateLimiter(max_calls=3, period=1.0)
        self._client: httpx.AsyncClient | None = None

        # SQLite persistent cache
        _db = db_path or os.path.join("data", "congressional_cache.db")
        self._db = _CongressDBCache(_db)

        if not self.api_key and not self.use_mock:
            logger.warning("No Quiver Quant API key configured -- mock data will be used")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(20.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
            )
        return self._client

    async def _request(
        self,
        path: str,
        params: dict | None = None,
        cache_key: str | None = None,
        cache_ttl: int | None = None,
    ) -> Any:
        # In-memory TTL cache first
        if cache_key:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        await self._limiter.acquire()
        client = await self._get_client()

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.get(path, params=params)
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 10))
                    logger.warning("Quiver 429 -- waiting {}s", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if cache_key:
                    self._cache.set(cache_key, data, cache_ttl)
                return data
            except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                backoff = min(2 ** attempt, 15)
                logger.warning("Quiver {} failed (attempt {}/{}): {}", path, attempt, self.max_retries, exc)
                await asyncio.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Response normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_api_response(data: list[dict], days: int | None = None) -> pd.DataFrame:
        """Convert Quiver Quant API response into a normalized DataFrame."""
        if not data:
            return pd.DataFrame(columns=TRADE_COLUMNS)

        df = pd.DataFrame(data)
        rename = {
            "Representative": "politician",
            "Ticker": "ticker",
            "Transaction": "type",
            "TransactionDate": "date",
            "Range": "amount_range",
            "ReportDate": "_report_date",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        if days is not None:
            cutoff = pd.Timestamp(date.today() - timedelta(days=days), tz=None)
            df = df[df["date"] >= cutoff]

        for col in TRADE_COLUMNS:
            if col not in df.columns:
                df[col] = None

        return df[TRADE_COLUMNS].sort_values("date", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_mock_trades(days: int = 30, count: int = 80) -> pd.DataFrame:
        np.random.seed(42)
        now = date.today()
        rows = []
        for _ in range(count):
            politician = np.random.choice(MOCK_POLITICIANS)
            ticker = np.random.choice(MOCK_TICKERS)
            trade_type = np.random.choice(["Purchase", "Sale"])
            trade_date = now - timedelta(days=int(np.random.uniform(0, days)))
            amount = np.random.choice(AMOUNT_RANGES)
            rows.append({
                "politician": politician,
                "ticker": ticker,
                "type": trade_type,
                "date": trade_date.isoformat(),
                "amount_range": amount,
            })
        df = pd.DataFrame(rows, columns=TRADE_COLUMNS)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_recent_trades(self, days: int = 30) -> pd.DataFrame:
        """
        Get recent congressional trades.

        Returns DataFrame: ``[politician, ticker, type, date, amount_range]``

        Checks in order: in-memory cache -> SQLite cache -> Quiver API -> mock fallback.
        """
        if self.use_mock or not self.api_key:
            return self._generate_mock_trades(days=days)

        # Check in-memory cache
        mem_key = f"congress_recent:{days}"
        cached = self._cache.get(mem_key)
        if cached is not None:
            return cached

        # Check SQLite persistent cache
        db_cached = self._db.get_cached_trades(max_age_seconds=600)
        if db_cached is not None:
            cutoff = pd.Timestamp(date.today() - timedelta(days=days), tz=None)
            filtered = db_cached[db_cached["date"] >= cutoff].reset_index(drop=True)
            if not filtered.empty:
                self._cache.set(mem_key, filtered, 600)
                logger.debug("Served {} congressional trades from SQLite cache", len(filtered))
                return filtered

        # Fetch from API
        try:
            data = await self._request("/bulk/congresstrading", cache_key=None, cache_ttl=600)
            if not data:
                return self._generate_mock_trades(days=days)

            df = self._normalize_api_response(data, days=days)

            # Persist full result set to SQLite (unfiltered by days for reuse)
            full_df = self._normalize_api_response(data, days=None)
            self._db.store_trades(full_df)

            # Memory cache the filtered result
            self._cache.set(mem_key, df, 600)
            logger.info("Fetched {} congressional trades from Quiver API (last {} days)", len(df), days)
            return df

        except Exception as exc:
            logger.error("Congressional trades failed: {} -- returning mock", exc)
            return self._generate_mock_trades(days=days)

    async def get_trades_by_ticker(self, symbol: str) -> pd.DataFrame:
        """Get all recent congressional trades for a specific ticker."""
        ticker = symbol.upper()

        if self.use_mock or not self.api_key:
            mock = self._generate_mock_trades(days=90, count=120)
            return mock[mock["ticker"] == ticker].reset_index(drop=True)

        # Check in-memory cache
        mem_key = f"congress_ticker:{ticker}"
        cached = self._cache.get(mem_key)
        if cached is not None:
            return cached

        # Check SQLite persistent cache
        db_cached = self._db.get_cached_by_ticker(ticker, max_age_seconds=600)
        if db_cached is not None and not db_cached.empty:
            self._cache.set(mem_key, db_cached, 600)
            logger.debug("Served {} trades for {} from SQLite cache", len(db_cached), ticker)
            return db_cached

        # Fetch from API
        try:
            data = await self._request(
                f"/historical/congresstrading/{ticker}",
                cache_key=None,
                cache_ttl=600,
            )
            if not data:
                mock = self._generate_mock_trades(days=90, count=120)
                return mock[mock["ticker"] == ticker].reset_index(drop=True)

            df = self._normalize_api_response(data, days=None)

            # Persist to SQLite
            self._db.store_ticker_trades(ticker, df)

            # Memory cache
            self._cache.set(mem_key, df, 600)
            logger.info("Fetched {} congressional trades for {} from Quiver API", len(df), ticker)
            return df

        except Exception as exc:
            logger.error("Congressional trades by ticker failed for {}: {}", ticker, exc)
            return pd.DataFrame(columns=TRADE_COLUMNS)

    async def detect_clusters(
        self,
        min_politicians: int = 3,
        days: int = 14,
    ) -> list[dict]:
        """
        Detect cluster buying/selling: multiple politicians trading the same
        ticker in the same direction within a window.

        Returns list of dicts: ``{ticker, count, direction, politicians, date_range}``.
        """
        trades = await self.get_recent_trades(days=days)
        if trades.empty:
            return []

        clusters: list[dict] = []

        # Group by ticker + direction
        for direction in ["Purchase", "Sale"]:
            subset = trades[trades["type"] == direction]
            grouped = subset.groupby("ticker")

            for ticker, group in grouped:
                unique_politicians = group["politician"].nunique()
                if unique_politicians >= min_politicians:
                    clusters.append({
                        "ticker": ticker,
                        "count": unique_politicians,
                        "direction": "buy" if direction == "Purchase" else "sell",
                        "politicians": sorted(group["politician"].unique().tolist()),
                        "date_range": {
                            "start": group["date"].min().isoformat() if not group["date"].isna().all() else None,
                            "end": group["date"].max().isoformat() if not group["date"].isna().all() else None,
                        },
                        "total_trades": len(group),
                    })

        clusters.sort(key=lambda x: x["count"], reverse=True)
        if clusters:
            logger.info("Detected {} congressional clusters (min_politicians={}, days={})",
                        len(clusters), min_politicians, days)
        return clusters

    async def get_politician_performance(self, name: str) -> dict:
        """
        Get a summary of a politician's trading activity.

        Returns dict with trade counts, tickers traded, buy/sell ratio, etc.
        """
        trades = await self.get_recent_trades(days=365)
        politician_trades = trades[trades["politician"].str.contains(name, case=False, na=False)]

        if politician_trades.empty:
            return {
                "politician": name,
                "total_trades": 0,
                "found": False,
            }

        buys = politician_trades[politician_trades["type"] == "Purchase"]
        sells = politician_trades[politician_trades["type"] == "Sale"]
        tickers = politician_trades["ticker"].unique().tolist()

        # Estimate trade frequency
        if len(politician_trades) > 1:
            dates = politician_trades["date"].dropna().sort_values()
            if len(dates) > 1:
                avg_gap = (dates.iloc[-1] - dates.iloc[0]).days / max(len(dates) - 1, 1)
            else:
                avg_gap = 0
        else:
            avg_gap = 0

        return {
            "politician": name,
            "found": True,
            "total_trades": len(politician_trades),
            "buys": len(buys),
            "sells": len(sells),
            "buy_sell_ratio": round(len(buys) / max(len(sells), 1), 2),
            "unique_tickers": len(tickers),
            "top_tickers": tickers[:10],
            "avg_days_between_trades": round(avg_gap, 1),
            "most_recent_trade": politician_trades["date"].max().isoformat() if not politician_trades["date"].isna().all() else None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("CongressionalFeed HTTP client closed")

    async def __aenter__(self) -> "CongressionalFeed":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
