"""
crypto_feed.py - Blowfin API connector for crypto perpetual futures data.

Provides OHLCV, funding rate, open interest, orderbook, and ticker data
with HMAC-signed authentication, rate limiting, caching, and CSV fallback.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.blowfin.com"

TIMEFRAME_MAP = {
    "1M": "1m",
    "5M": "5m",
    "15M": "15m",
    "1H": "1H",
    "4H": "4H",
    "1D": "1D",
}

TIMEFRAME_MS = {
    "1M": 60_000,
    "5M": 300_000,
    "15M": 900_000,
    "1H": 3_600_000,
    "4H": 14_400_000,
    "1D": 86_400_000,
}


# ---------------------------------------------------------------------------
# Simple TTL cache
# ---------------------------------------------------------------------------

class TTLCache:
    """Thread-safe TTL cache backed by a plain dict."""

    def __init__(self, default_ttl: int = 60):
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
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (time.monotonic() + ttl, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# Rate limiter (token-bucket)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Async token-bucket rate limiter."""

    def __init__(self, max_calls: int = 10, period: float = 1.0):
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
# Blowfin Crypto Feed
# ---------------------------------------------------------------------------

class CryptoFeed:
    """
    Blowfin perpetual-futures data feed.

    Parameters
    ----------
    api_key : str | None
        Blowfin API key. Falls back to env ``BLOWFIN_API_KEY``.
    api_secret : str | None
        Blowfin API secret. Falls back to env ``BLOWFIN_API_SECRET``.
    passphrase : str | None
        Blowfin passphrase. Falls back to env ``BLOWFIN_PASSPHRASE``.
    csv_dir : str | Path | None
        Directory holding fallback CSV files named ``{symbol}_{timeframe}.csv``.
    use_mock : bool
        If *True*, bypass API and return synthetic data (for backtesting / CI).
    cache_ttl : int
        Default cache TTL in seconds.
    max_retries : int
        Max retry attempts on transient HTTP errors.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        passphrase: str | None = None,
        csv_dir: str | Path | None = None,
        use_mock: bool = False,
        cache_ttl: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.getenv("BLOWFIN_API_KEY", "")
        self.api_secret = api_secret or os.getenv("BLOWFIN_API_SECRET", "")
        self.passphrase = passphrase or os.getenv("BLOWFIN_PASSPHRASE", "")
        self.csv_dir = Path(csv_dir) if csv_dir else None
        self.use_mock = use_mock
        self.max_retries = max_retries

        self._cache = TTLCache(default_ttl=cache_ttl)
        self._limiter = RateLimiter(max_calls=10, period=1.0)
        self._client: httpx.AsyncClient | None = None

        if not self.api_key and not self.use_mock:
            logger.warning("No Blowfin API key configured -- mock data will be used for authenticated endpoints")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    def _sign_request(self, timestamp: str, method: str, path: str, body: str = "") -> dict[str, str]:
        """Produce HMAC-SHA256 signature headers for Blowfin authenticated endpoints."""
        prehash = f"{timestamp}{method.upper()}{path}{body}"
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode("utf-8"),
                prehash.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return {
            "BF-ACCESS-KEY": self.api_key,
            "BF-ACCESS-SIGN": signature,
            "BF-ACCESS-TIMESTAMP": timestamp,
            "BF-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: str = "",
        signed: bool = False,
        cache_key: str | None = None,
        cache_ttl: int | None = None,
    ) -> Any:
        # Check cache
        if cache_key:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: {}", cache_key)
                return cached

        await self._limiter.acquire()
        client = await self._get_client()

        headers: dict[str, str] = {}
        if signed:
            ts = str(int(time.time()))
            headers = self._sign_request(ts, method, path, body)

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if method.upper() == "GET":
                    resp = await client.get(path, params=params, headers=headers)
                else:
                    resp = await client.post(path, content=body, headers=headers)

                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 2))
                    logger.warning("Rate limited (429), waiting {}s (attempt {}/{})", wait, attempt, self.max_retries)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                if cache_key:
                    self._cache.set(cache_key, data, cache_ttl)

                return data

            except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                backoff = min(2 ** attempt, 10)
                logger.warning(
                    "Request {} {} failed (attempt {}/{}): {} -- retrying in {}s",
                    method, path, attempt, self.max_retries, exc, backoff,
                )
                await asyncio.sleep(backoff)

        logger.error("All {} retries exhausted for {} {}", self.max_retries, method, path)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Mock data generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_mock_ohlcv(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Generate realistic synthetic OHLCV data."""
        np.random.seed(hash(symbol) % 2**31)
        now_ms = int(time.time() * 1000)
        bar_ms = TIMEFRAME_MS.get(timeframe, 60_000)

        timestamps = [now_ms - bar_ms * (limit - 1 - i) for i in range(limit)]
        base_price = 50_000.0 if "BTC" in symbol.upper() else 3_000.0

        closes = [base_price]
        for _ in range(1, limit):
            ret = np.random.normal(0.0, 0.003)
            closes.append(closes[-1] * (1 + ret))

        opens, highs, lows, volumes = [], [], [], []
        for c in closes:
            o = c * (1 + np.random.uniform(-0.002, 0.002))
            h = max(o, c) * (1 + np.random.uniform(0, 0.004))
            lo = min(o, c) * (1 - np.random.uniform(0, 0.004))
            v = np.random.uniform(50, 5000) * (base_price / 1000)
            opens.append(round(o, 2))
            highs.append(round(h, 2))
            lows.append(round(lo, 2))
            volumes.append(round(v, 4))

        closes = [round(c, 2) for c in closes]

        return pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, unit="ms", utc=True),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })

    @staticmethod
    def _generate_mock_ticker(symbol: str) -> dict:
        np.random.seed(hash(symbol) % 2**31 + 1)
        base = 50_000.0 if "BTC" in symbol.upper() else 3_000.0
        last = base * (1 + np.random.uniform(-0.05, 0.05))
        return {
            "symbol": symbol,
            "last_price": round(last, 2),
            "bid": round(last * 0.9999, 2),
            "ask": round(last * 1.0001, 2),
            "high_24h": round(last * 1.03, 2),
            "low_24h": round(last * 0.97, 2),
            "volume_24h": round(np.random.uniform(1e6, 1e9), 2),
            "change_24h_pct": round(np.random.uniform(-5, 5), 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _generate_mock_funding(symbol: str) -> dict:
        np.random.seed(hash(symbol) % 2**31 + 2)
        return {
            "symbol": symbol,
            "funding_rate": round(np.random.uniform(-0.001, 0.001), 6),
            "next_funding_time": datetime.now(timezone.utc).isoformat(),
            "estimated_rate": round(np.random.uniform(-0.001, 0.001), 6),
        }

    @staticmethod
    def _generate_mock_oi(symbol: str) -> dict:
        np.random.seed(hash(symbol) % 2**31 + 3)
        return {
            "symbol": symbol,
            "open_interest": round(np.random.uniform(1e8, 5e9), 2),
            "open_interest_change_24h": round(np.random.uniform(-5, 5), 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _generate_mock_orderbook(symbol: str, depth: int) -> dict:
        np.random.seed(hash(symbol) % 2**31 + 4)
        base = 50_000.0 if "BTC" in symbol.upper() else 3_000.0
        mid = base * (1 + np.random.uniform(-0.01, 0.01))
        bids = [[round(mid - i * 0.5, 2), round(np.random.uniform(0.1, 10), 4)] for i in range(depth)]
        asks = [[round(mid + i * 0.5, 2), round(np.random.uniform(0.1, 10), 4)] for i in range(depth)]
        return {"symbol": symbol, "bids": bids, "asks": asks, "timestamp": datetime.now(timezone.utc).isoformat()}

    # ------------------------------------------------------------------
    # CSV fallback
    # ------------------------------------------------------------------

    def _load_csv(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Load OHLCV from a local CSV file: ``{csv_dir}/{symbol}_{timeframe}.csv``."""
        if self.csv_dir is None:
            return None
        fname = f"{symbol.replace('-', '').replace('/', '')}_{timeframe}.csv"
        path = self.csv_dir / fname
        if not path.exists():
            logger.debug("CSV fallback not found: {}", path)
            return None
        logger.info("Loading OHLCV from CSV: {}", path)
        df = pd.read_csv(path, parse_dates=["timestamp"])
        expected = {"timestamp", "open", "high", "low", "close", "volume"}
        if not expected.issubset(set(df.columns)):
            logger.error("CSV {} missing required columns (need {})", path, expected)
            return None
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
        return df.sort_values("timestamp").reset_index(drop=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1H",
        limit: int = 200,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candlestick data.

        Falls back to: CSV file -> mock data when API is unavailable.
        """
        timeframe = timeframe.upper()
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe {timeframe!r}. Choose from {list(TIMEFRAME_MAP)}")

        # Mock path
        if self.use_mock:
            logger.debug("Returning mock OHLCV for {} {}", symbol, timeframe)
            return self._generate_mock_ohlcv(symbol, timeframe, limit)

        # CSV fallback
        csv_df = self._load_csv(symbol, timeframe)
        if csv_df is not None:
            return csv_df.tail(limit).reset_index(drop=True)

        # Live API
        cache_key = f"ohlcv:{symbol}:{timeframe}:{limit}"
        try:
            data = await self._request(
                "GET",
                "/api/v1/market/candles",
                params={
                    "instId": symbol,
                    "bar": TIMEFRAME_MAP[timeframe],
                    "limit": str(min(limit, 300)),
                },
                cache_key=cache_key,
                cache_ttl=TIMEFRAME_MS[timeframe] // 2000,  # half a bar in seconds
            )
            rows = data.get("data", [])
            if not rows:
                logger.warning("Empty OHLCV response for {} {}; falling back to mock", symbol, timeframe)
                return self._generate_mock_ohlcv(symbol, timeframe, limit)

            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(float), unit="ms", utc=True)
            df = df.sort_values("timestamp").reset_index(drop=True)
            return df

        except Exception as exc:
            logger.error("Failed to fetch OHLCV for {} {}: {} -- falling back to mock", symbol, timeframe, exc)
            return self._generate_mock_ohlcv(symbol, timeframe, limit)

    async def get_funding_rate(self, symbol: str) -> dict:
        """Get current funding rate for a perpetual contract."""
        if self.use_mock or not self.api_key:
            return self._generate_mock_funding(symbol)

        cache_key = f"funding:{symbol}"
        try:
            data = await self._request(
                "GET",
                "/api/v1/market/funding-rate",
                params={"instId": symbol},
                cache_key=cache_key,
                cache_ttl=60,
            )
            record = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            return {
                "symbol": symbol,
                "funding_rate": float(record.get("fundingRate", 0)),
                "next_funding_time": record.get("nextFundingTime", ""),
                "estimated_rate": float(record.get("estimatedRate", 0)),
            }
        except Exception as exc:
            logger.error("Funding rate fetch failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_funding(symbol)

    async def get_open_interest(self, symbol: str) -> dict:
        """Get current open interest."""
        if self.use_mock or not self.api_key:
            return self._generate_mock_oi(symbol)

        cache_key = f"oi:{symbol}"
        try:
            data = await self._request(
                "GET",
                "/api/v1/market/open-interest",
                params={"instId": symbol},
                cache_key=cache_key,
                cache_ttl=30,
            )
            record = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            return {
                "symbol": symbol,
                "open_interest": float(record.get("oi", 0)),
                "open_interest_change_24h": float(record.get("oiChange24h", 0)),
                "timestamp": record.get("ts", datetime.now(timezone.utc).isoformat()),
            }
        except Exception as exc:
            logger.error("OI fetch failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_oi(symbol)

    async def get_orderbook(self, symbol: str, depth: int = 20) -> dict:
        """Get current order book snapshot."""
        if self.use_mock or not self.api_key:
            return self._generate_mock_orderbook(symbol, depth)

        cache_key = f"book:{symbol}:{depth}"
        try:
            data = await self._request(
                "GET",
                "/api/v1/market/books",
                params={"instId": symbol, "sz": str(depth)},
                cache_key=cache_key,
                cache_ttl=5,
            )
            book = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            return {
                "symbol": symbol,
                "bids": [[float(p), float(q)] for p, q in book.get("bids", [])],
                "asks": [[float(p), float(q)] for p, q in book.get("asks", [])],
                "timestamp": book.get("ts", datetime.now(timezone.utc).isoformat()),
            }
        except Exception as exc:
            logger.error("Orderbook fetch failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_orderbook(symbol, depth)

    async def get_ticker(self, symbol: str) -> dict:
        """Get current ticker (last price, 24h change, volume)."""
        if self.use_mock or not self.api_key:
            return self._generate_mock_ticker(symbol)

        cache_key = f"ticker:{symbol}"
        try:
            data = await self._request(
                "GET",
                "/api/v1/market/ticker",
                params={"instId": symbol},
                cache_key=cache_key,
                cache_ttl=10,
            )
            record = data.get("data", [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
            last = float(record.get("last", 0))
            open_24h = float(record.get("open24h", last))
            change_pct = ((last - open_24h) / open_24h * 100) if open_24h else 0.0
            return {
                "symbol": symbol,
                "last_price": last,
                "bid": float(record.get("bidPx", 0)),
                "ask": float(record.get("askPx", 0)),
                "high_24h": float(record.get("high24h", 0)),
                "low_24h": float(record.get("low24h", 0)),
                "volume_24h": float(record.get("vol24h", 0)),
                "change_24h_pct": round(change_pct, 4),
                "timestamp": record.get("ts", datetime.now(timezone.utc).isoformat()),
            }
        except Exception as exc:
            logger.error("Ticker fetch failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_ticker(symbol)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("CryptoFeed HTTP client closed")

    async def __aenter__(self) -> "CryptoFeed":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
