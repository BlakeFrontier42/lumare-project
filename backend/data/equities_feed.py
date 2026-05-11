"""
equities_feed.py - Polygon.io + Yahoo Finance connector for US equities data.

Provides OHLCV aggregates, ticker details, market status, and ticker search
with rate limiting, caching, retries, and yfinance fallback.
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import datetime, date, timedelta, timezone
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
from loguru import logger

try:
    import yfinance as yf
    _HAS_YFINANCE = True
except ImportError:
    _HAS_YFINANCE = False
    logger.warning("yfinance not installed -- equity data will use mock fallback")

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

# Equity symbols that should use yfinance (not crypto)
EQUITY_SYMBOLS = {
    "SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN", "TLT", "BND",
    "GLD", "SLV", "EFA", "VWO", "MSFT", "GOOGL", "META", "AMD",
    "DIA", "IWM",
}

# Map internal timeframe codes to yfinance interval strings
_YF_INTERVAL_MAP = {
    "1min": "1m",   "1M": "1m",
    "5min": "5m",   "5M": "5m",
    "15min": "15m", "15M": "15m",
    "1hour": "1h",  "1H": "1h",
    "4hour": "1h",  "4H": "1h",   # yfinance has no 4h; use 1h and resample
    "1day": "1d",   "1D": "1d",
}

# yfinance max period for each interval (to avoid "period too large" errors)
_YF_MAX_PERIOD = {
    "1m": "7d", "5m": "60d", "15m": "60d",
    "1h": "730d", "1d": "max",
}


# ---------------------------------------------------------------------------
# Standalone helper: get_equity_quote()
# ---------------------------------------------------------------------------

def _yf_fetch_quote_sync(symbol: str) -> dict:
    """
    Synchronous yfinance quote fetch. Returns {price, change_pct, volume}.
    Must be called via asyncio.to_thread() from async code.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = float(info.last_price) if hasattr(info, "last_price") and info.last_price else 0.0
        prev_close = float(info.previous_close) if hasattr(info, "previous_close") and info.previous_close else 0.0
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
        volume = int(info.last_volume) if hasattr(info, "last_volume") and info.last_volume else 0

        # Try to get day high/low from history
        day_high = float(info.day_high) if hasattr(info, "day_high") and info.day_high else 0.0
        day_low = float(info.day_low) if hasattr(info, "day_low") and info.day_low else 0.0

        return {
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "volume": volume,
            "high": round(day_high, 2) if day_high else round(price * 1.005, 2),
            "low": round(day_low, 2) if day_low else round(price * 0.995, 2),
            "prev_close": round(prev_close, 2),
        }
    except Exception as exc:
        logger.warning("yfinance quote fetch failed for {}: {}", symbol, exc)
        raise


async def get_equity_quote(symbol: str) -> dict:
    """
    Async helper to fetch a single equity quote via yfinance.

    Returns
    -------
    dict
        Keys: price, change_pct, volume
    """
    if not _HAS_YFINANCE:
        return {"price": 0.0, "change_pct": 0.0, "volume": 0}
    return await asyncio.to_thread(_yf_fetch_quote_sync, symbol)


def _yf_fetch_ohlcv_sync(
    symbol: str,
    interval: str,
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """
    Synchronous yfinance OHLCV fetch. Returns DataFrame with standard columns.
    Must be called via asyncio.to_thread() from async code.
    """
    ticker = yf.Ticker(symbol)
    kwargs: dict[str, Any] = {"interval": interval}
    if start and end:
        kwargs["start"] = start
        kwargs["end"] = end
    else:
        kwargs["period"] = period or _YF_MAX_PERIOD.get(interval, "30d")

    df = ticker.history(**kwargs)
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = df.reset_index()
    # yfinance uses "Date" for daily, "Datetime" for intraday
    ts_col = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={
        ts_col: "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    # Ensure timezone-aware UTC timestamps
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    else:
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")

    return df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp").reset_index(drop=True)


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
# Polygon + yfinance Equities Feed
# ---------------------------------------------------------------------------

class EquitiesFeed:
    """
    Equities data feed with Polygon.io primary and Yahoo Finance fallback.

    Priority order:
    1. Polygon.io (if API key configured)
    2. Yahoo Finance via yfinance (free, no key needed)
    3. Mock data (last resort)

    Parameters
    ----------
    api_key : str | None
        Polygon API key. Falls back to env ``POLYGON_API_KEY``.
    use_mock : bool
        Force synthetic data instead of hitting any API.
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
        self._yf_cache = TTLCache(default_ttl=30)  # 30s cache for yfinance quotes
        self._limiter = RateLimiter(max_calls=5, period=1.0)
        self._client: httpx.AsyncClient | None = None

        # Per-symbol provenance: "polygon" / "yfinance" / "mock"
        self.last_data_source: dict[str, str] = {}

        if not self.api_key and not self.use_mock:
            if _HAS_YFINANCE:
                logger.info("No Polygon API key -- using Yahoo Finance for equity data")
            else:
                logger.warning("No Polygon API key and yfinance not installed -- mock data will be used")

    # ------------------------------------------------------------------
    # HTTP (Polygon)
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
    # yfinance helpers (async wrappers)
    # ------------------------------------------------------------------

    async def _yfinance_quote(self, symbol: str) -> dict:
        """Fetch quote via yfinance with 30s caching."""
        cache_key = f"yf_quote:{symbol}"
        cached = self._yf_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            result = await asyncio.to_thread(_yf_fetch_quote_sync, symbol)
            self._yf_cache.set(cache_key, result, ttl=30)
            return result
        except Exception as exc:
            logger.warning("yfinance quote failed for {}: {}", symbol, exc)
            # Return last cached value if available (even if expired)
            for key, (_, val) in self._yf_cache._store.items():
                if key == cache_key:
                    return val
            raise

    async def _yfinance_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """Fetch OHLCV via yfinance with caching."""
        yf_interval = _YF_INTERVAL_MAP.get(timeframe, "1d")
        cache_key = f"yf_ohlcv:{symbol}:{yf_interval}:{start_date}:{end_date}:{limit}"

        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Determine period vs start/end
        kwargs: dict[str, Any] = {}
        if start_date and end_date:
            kwargs["start"] = start_date.isoformat()
            kwargs["end"] = end_date.isoformat()
        else:
            # Calculate a sensible period based on interval and limit
            if yf_interval in ("1m", "5m", "15m"):
                kwargs["period"] = "5d" if yf_interval == "1m" else "60d"
            elif yf_interval == "1h":
                kwargs["period"] = "60d"
            else:
                kwargs["period"] = "1y"

        try:
            df = await asyncio.to_thread(
                _yf_fetch_ohlcv_sync, symbol, yf_interval,
                kwargs.get("period"), kwargs.get("start"), kwargs.get("end"),
            )
            if not df.empty:
                df = df.tail(limit).reset_index(drop=True)
                # Cache: shorter TTL for intraday
                ttl = 30 if yf_interval in ("1m", "5m", "15m") else 120
                self._cache.set(cache_key, df, ttl=ttl)
            return df
        except Exception as exc:
            logger.error("yfinance OHLCV failed for {}: {}", symbol, exc)
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    # ------------------------------------------------------------------
    # Mock helpers (last-resort fallback)
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

    _MOCK_PRICES: dict[str, float] = {
        "SPY": 568.42, "QQQ": 487.15, "AAPL": 217.35, "TSLA": 172.80,
        "NVDA": 950.22, "AMZN": 186.74, "MSFT": 425.68, "GOOGL": 158.43,
        "META": 512.30, "AMD": 164.82, "DIA": 432.50, "IWM": 212.67,
        "TLT": 87.50, "BND": 72.30, "GLD": 213.80, "SLV": 25.40,
        "EFA": 79.60, "VWO": 43.20,
    }

    def _generate_mock_quote(self, symbol: str) -> dict:
        """Generate a realistic mock quote with small random drift."""
        base = self._MOCK_PRICES.get(symbol.upper(), 150.00)
        t = time.time()
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
        Fetch OHLCV aggregate bars.

        Priority: Polygon -> yfinance -> mock.

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

        # If forced mock mode, skip everything
        if self.use_mock:
            self.last_data_source[symbol] = "mock"
            return self._generate_mock_ohlcv(symbol, timeframe, _start, _end)

        # Try Polygon first if key is available
        if self.api_key:
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
                if results:
                    df = pd.DataFrame(results)
                    df = df.rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                    df = df[["timestamp", "open", "high", "low", "close", "volume"]].sort_values("timestamp").reset_index(drop=True)
                    self.last_data_source[symbol] = "polygon"
                    return df
                logger.warning("Empty Polygon OHLCV for {}; trying yfinance", symbol)
            except Exception as exc:
                logger.warning("Polygon OHLCV failed for {}: {} -- trying yfinance", symbol, exc)

        # Try yfinance
        if _HAS_YFINANCE:
            try:
                df = await self._yfinance_ohlcv(symbol, timeframe, _start, _end)
                if not df.empty:
                    logger.debug("yfinance OHLCV returned {} bars for {}", len(df), symbol)
                    self.last_data_source[symbol] = "yfinance"
                    return df
            except Exception as exc:
                logger.warning("yfinance OHLCV also failed for {}: {}", symbol, exc)

        # Last resort: mock
        logger.debug("Returning mock OHLCV for {}", symbol)
        self.last_data_source[symbol] = "mock"
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
    # Quote (for prices endpoint + WebSocket streaming)
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> dict | None:
        """
        Get a real-time quote for a single equity ticker.

        Priority: Polygon -> yfinance -> mock.

        Returns dict with: price, change_pct, volume, high, low, prev_close.
        """
        # If forced mock mode, skip APIs
        if self.use_mock:
            return self._generate_mock_quote(symbol)

        # Try Polygon first if key is available
        if self.api_key:
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
                logger.debug("Polygon quote failed for {}: {} -- trying yfinance", symbol, exc)

        # Try yfinance
        if _HAS_YFINANCE:
            try:
                return await self._yfinance_quote(symbol)
            except Exception as exc:
                logger.debug("yfinance quote also failed for {}: {} -- returning mock", symbol, exc)

        # Last resort: mock
        return self._generate_mock_quote(symbol)

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
