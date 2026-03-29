"""
equities_feed.py - Polygon.io connector for US equities data.

Provides OHLCV aggregates, ticker details, market status, and ticker search
with rate limiting, caching, retries, and mock fallback.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.polygon.io"

# Polygon multiplier/timespan pairs
TIMEFRAME_MAP = {
    "1min":  (1, "minute"),
    "5min":  (5, "minute"),
    "15min": (15, "minute"),
    "1hour": (1, "hour"),
    "1day":  (1, "day"),
}


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

class TTLCache:
    def __init__(self, default_ttl: int = 120):
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
    """Async token-bucket rate limiter."""
    def __init__(self, max_calls: int = 5, period: float = 1.0):
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
# Polygon Equities Feed
# ---------------------------------------------------------------------------

class EquitiesFeed:
    """
    Polygon.io equities data feed.

    Parameters
    ----------
    api_key : str | None
        Polygon API key. Falls back to env ``POLYGON_API_KEY``.
    use_mock : bool
        Return synthetic data instead of hitting the API.
    cache_ttl : int
        Default cache TTL in seconds.
    max_retries : int
        Max retry attempts on transient errors.
    """

    def __init__(
        self,
        api_key: str | None = None,
        use_mock: bool = False,
        cache_ttl: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        self.use_mock = use_mock
        self.max_retries = max_retries

        self._cache = TTLCache(default_ttl=cache_ttl)
        self._limiter = RateLimiter(max_calls=5, period=1.0)
        self._client: httpx.AsyncClient | None = None

        if not self.api_key and not self.use_mock:
            logger.warning("No Polygon API key configured -- mock data will be used")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(20.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def _request(
        self,
        path: str,
        params: dict | None = None,
        cache_key: str | None = None,
        cache_ttl: int | None = None,
    ) -> Any:
        if cache_key:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        await self._limiter.acquire()
        client = await self._get_client()
        params = dict(params or {})
        params["apiKey"] = self.api_key

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.get(path, params=params)

                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 12))
                    logger.warning("Polygon 429 -- waiting {}s (attempt {}/{})", wait, attempt, self.max_retries)
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
                logger.warning("Polygon request {} failed (attempt {}/{}): {} -- retrying in {}s",
                               path, attempt, self.max_retries, exc, backoff)
                await asyncio.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Mock helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_mock_ohlcv(symbol: str, timeframe: str, start_date: date, end_date: date) -> pd.DataFrame:
        np.random.seed(hash(symbol) % 2**31)
        mult, span = TIMEFRAME_MAP.get(timeframe, (1, "day"))

        if span == "minute":
            freq = f"{mult}min"
            total_bars = min(int((end_date - start_date).total_seconds() / (mult * 60)), 5000)
        elif span == "hour":
            freq = f"{mult}h"
            total_bars = min(int((end_date - start_date).total_seconds() / (mult * 3600)), 5000)
        else:
            freq = "1D"
            total_bars = min((end_date - start_date).days, 5000)

        total_bars = max(total_bars, 50)
        ts = pd.date_range(start=start_date, periods=total_bars, freq=freq, tz="US/Eastern")

        base = np.random.uniform(20, 500)
        returns = np.random.normal(0.0002, 0.015, size=total_bars)
        closes = base * np.cumprod(1 + returns)

        opens = closes * (1 + np.random.uniform(-0.005, 0.005, total_bars))
        highs = np.maximum(opens, closes) * (1 + np.random.uniform(0, 0.01, total_bars))
        lows = np.minimum(opens, closes) * (1 - np.random.uniform(0, 0.01, total_bars))
        vols = np.random.uniform(1e5, 5e6, total_bars)

        return pd.DataFrame({
            "timestamp": ts,
            "open": np.round(opens, 2),
            "high": np.round(highs, 2),
            "low": np.round(lows, 2),
            "close": np.round(closes, 2),
            "volume": np.round(vols, 0).astype(int),
        })

    @staticmethod
    def _generate_mock_ticker_details(symbol: str) -> dict:
        return {
            "ticker": symbol.upper(),
            "name": f"{symbol.upper()} Inc.",
            "market": "stocks",
            "locale": "us",
            "primary_exchange": "XNYS",
            "type": "CS",
            "currency_name": "usd",
            "market_cap": round(np.random.uniform(1e9, 2e12), 0),
            "description": f"Mock description for {symbol.upper()}.",
            "sic_code": "7372",
            "homepage_url": f"https://{symbol.lower()}.example.com",
            "total_employees": int(np.random.uniform(100, 200000)),
            "list_date": "2005-01-01",
            "share_class_shares_outstanding": int(np.random.uniform(1e8, 5e9)),
            "weighted_shares_outstanding": int(np.random.uniform(1e8, 5e9)),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1day",
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV aggregate bars from Polygon.

        Parameters
        ----------
        symbol : str
            Ticker (e.g. ``"AAPL"``).
        timeframe : str
            One of ``1min``, ``5min``, ``15min``, ``1hour``, ``1day``.
        start_date, end_date : str | date | None
            Date range. Defaults to last 30 days.
        """
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe {timeframe!r}. Choose from {list(TIMEFRAME_MAP)}")

        _end = date.fromisoformat(str(end_date)) if end_date else date.today()
        _start = date.fromisoformat(str(start_date)) if start_date else _end - timedelta(days=30)

        if self.use_mock or not self.api_key:
            logger.debug("Returning mock OHLCV for {}", symbol)
            return self._generate_mock_ohlcv(symbol, timeframe, _start, _end)

        mult, span = TIMEFRAME_MAP[timeframe]
        path = f"/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/{_start.isoformat()}/{_end.isoformat()}"
        cache_key = f"eq_ohlcv:{symbol}:{timeframe}:{_start}:{_end}"

        try:
            data = await self._request(
                path,
                params={"adjusted": "true", "sort": "asc", "limit": "50000"},
                cache_key=cache_key,
                cache_ttl=300 if span == "day" else 60,
            )
            results = data.get("results", [])
            if not results:
                logger.warning("Empty Polygon OHLCV for {}; returning mock", symbol)
                return self._generate_mock_ohlcv(symbol, timeframe, _start, _end)

            df = pd.DataFrame(results)
            df = df.rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp").reset_index(drop=True)
            return df

        except Exception as exc:
            logger.error("Polygon OHLCV failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_ohlcv(symbol, timeframe, _start, _end)

    async def get_ticker_details(self, symbol: str) -> dict:
        """Get detailed information about a ticker."""
        if self.use_mock or not self.api_key:
            return self._generate_mock_ticker_details(symbol)

        cache_key = f"eq_details:{symbol}"
        try:
            data = await self._request(f"/v3/reference/tickers/{symbol.upper()}", cache_key=cache_key, cache_ttl=3600)
            return data.get("results", {})
        except Exception as exc:
            logger.error("Ticker details failed for {}: {}", symbol, exc)
            return self._generate_mock_ticker_details(symbol)

    async def get_market_status(self) -> dict:
        """Get current market status (open/closed/early hours)."""
        if self.use_mock or not self.api_key:
            now = datetime.now(timezone.utc)
            hour = now.hour
            is_open = 13 <= hour <= 21 and now.weekday() < 5
            return {
                "market": "open" if is_open else "closed",
                "serverTime": now.isoformat(),
                "exchanges": {"nyse": "open" if is_open else "closed", "nasdaq": "open" if is_open else "closed"},
            }

        try:
            data = await self._request("/v1/marketstatus/now", cache_key="market_status", cache_ttl=60)
            return data
        except Exception as exc:
            logger.error("Market status failed: {}", exc)
            return {"market": "unknown", "error": str(exc)}

    async def search_tickers(self, query: str, limit: int = 20) -> list[dict]:
        """Search for tickers matching a query string."""
        if self.use_mock or not self.api_key:
            return [
                {"ticker": query.upper(), "name": f"{query.upper()} Inc.", "market": "stocks", "type": "CS"},
                {"ticker": f"{query.upper()}X", "name": f"{query.upper()}X Corp.", "market": "stocks", "type": "CS"},
            ]

        cache_key = f"eq_search:{query}:{limit}"
        try:
            data = await self._request(
                "/v3/reference/tickers",
                params={"search": query, "active": "true", "limit": str(limit), "market": "stocks"},
                cache_key=cache_key,
                cache_ttl=600,
            )
            return data.get("results", [])
        except Exception as exc:
            logger.error("Ticker search failed for {!r}: {}", query, exc)
            return []

    # ------------------------------------------------------------------
    # Quote (for WebSocket streaming)
    # ------------------------------------------------------------------

    # Realistic base prices for mock quotes
    _MOCK_PRICES: dict[str, float] = {
        "SPY": 568.42, "QQQ": 487.15, "AAPL": 217.35, "TSLA": 172.80,
        "NVDA": 950.22, "AMZN": 186.74, "MSFT": 425.68, "GOOGL": 158.43,
        "META": 512.30, "AMD": 164.82, "DIA": 432.50, "IWM": 212.67,
    }

    async def get_quote(self, symbol: str) -> dict | None:
        """
        Get a real-time quote for a single equity ticker.

        Returns dict with: price, change_pct, volume, high, low, prev_close.
        Uses Polygon snapshot endpoint when key available, mock otherwise.
        """
        if self.use_mock or not self.api_key:
            return self._generate_mock_quote(symbol)

        cache_key = f"eq_quote:{symbol}"
        try:
            data = await self._request(
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}",
                cache_key=cache_key,
                cache_ttl=15,
            )
            ticker = data.get("ticker", {})
            day = ticker.get("day", {})
            prev = ticker.get("prevDay", {})
            last = ticker.get("lastTrade", {})

            price = float(last.get("p", day.get("c", 0)))
            prev_close = float(prev.get("c", price))
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

            return {
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(day.get("v", 0)),
                "high": float(day.get("h", 0)),
                "low": float(day.get("l", 0)),
                "prev_close": round(prev_close, 2),
            }
        except Exception as exc:
            logger.debug("Quote failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_quote(symbol)

    def _generate_mock_quote(self, symbol: str) -> dict:
        """Generate a realistic mock quote with small random drift."""
        base = self._MOCK_PRICES.get(symbol.upper(), 150.00)
        # Deterministic but slowly drifting price based on time
        import math
        t = time.time()
        # Small sinusoidal drift + noise so it looks alive
        drift = math.sin(t / 120) * 0.003 + math.sin(t / 37) * 0.001
        price = round(base * (1 + drift), 2)
        change_pct = round(drift * 100, 2)
        return {
            "price": price,
            "change_pct": change_pct,
            "volume": int(np.random.uniform(5e6, 80e6)),
            "high": round(price * 1.008, 2),
            "low": round(price * 0.992, 2),
            "prev_close": round(base, 2),
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("EquitiesFeed HTTP client closed")

    async def __aenter__(self) -> "EquitiesFeed":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
