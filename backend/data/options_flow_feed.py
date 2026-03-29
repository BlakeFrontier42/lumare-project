"""
options_flow_feed.py - Unusual Whales connector for options flow data.

Provides live options flow, sweep detection, market flow summaries, and
unusual activity detection with rate limiting, caching, retries, and mock data.
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

BASE_URL = "https://api.unusualwhales.com/api"

FLOW_COLUMNS = ["timestamp", "type", "strike", "expiry", "premium", "side", "sentiment"]
SWEEP_COLUMNS = FLOW_COLUMNS  # sweeps share the same schema


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

class TTLCache:
    def __init__(self, default_ttl: int = 30):
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
# Unusual Whales Options Flow Feed
# ---------------------------------------------------------------------------

class OptionsFlowFeed:
    """
    Unusual Whales options flow data feed.

    Parameters
    ----------
    api_key : str | None
        Unusual Whales API token. Falls back to env ``UW_API_KEY``.
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
        cache_ttl: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key or os.getenv("UW_API_KEY", "")
        self.use_mock = use_mock
        self.max_retries = max_retries

        self._cache = TTLCache(default_ttl=cache_ttl)
        self._limiter = RateLimiter(max_calls=5, period=1.0)
        self._client: httpx.AsyncClient | None = None

        if not self.api_key and not self.use_mock:
            logger.warning("No Unusual Whales API key configured -- mock data will be used")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=httpx.Timeout(15.0, connect=5.0),
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
                    wait = float(resp.headers.get("Retry-After", 5))
                    logger.warning("UW 429 -- waiting {}s (attempt {}/{})", wait, attempt, self.max_retries)
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
                logger.warning("UW {} failed (attempt {}/{}): {} -- retrying in {}s",
                               path, attempt, self.max_retries, exc, backoff)
                await asyncio.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Mock data
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_mock_flow(symbol: str, count: int = 50) -> pd.DataFrame:
        np.random.seed(hash(symbol) % 2**31)
        now = datetime.now(timezone.utc)
        base_price = np.random.uniform(50, 500)

        rows = []
        for i in range(count):
            opt_type = np.random.choice(["CALL", "PUT"])
            strike = round(base_price * np.random.uniform(0.85, 1.15), 0)
            days_to_exp = int(np.random.choice([7, 14, 30, 45, 60, 90, 180]))
            expiry = (now + timedelta(days=days_to_exp)).strftime("%Y-%m-%d")
            premium = round(np.random.uniform(5_000, 2_000_000), 2)
            side = np.random.choice(["ASK", "BID", "MID"])
            sentiment = "BULLISH" if (opt_type == "CALL" and side == "ASK") or (opt_type == "PUT" and side == "BID") else "BEARISH"
            ts = now - timedelta(minutes=np.random.randint(0, 480))
            rows.append({
                "timestamp": ts,
                "type": opt_type,
                "strike": strike,
                "expiry": expiry,
                "premium": premium,
                "side": side,
                "sentiment": sentiment,
            })

        df = pd.DataFrame(rows, columns=FLOW_COLUMNS)
        return df.sort_values("timestamp", ascending=False).reset_index(drop=True)

    @staticmethod
    def _generate_mock_sweeps(symbol: str, count: int = 15) -> pd.DataFrame:
        """Sweeps are large, aggressively-priced flow."""
        np.random.seed(hash(symbol) % 2**31 + 10)
        now = datetime.now(timezone.utc)
        base_price = np.random.uniform(50, 500)

        rows = []
        for i in range(count):
            opt_type = np.random.choice(["CALL", "PUT"])
            strike = round(base_price * np.random.uniform(0.9, 1.1), 0)
            days_to_exp = int(np.random.choice([7, 14, 30, 45]))
            expiry = (now + timedelta(days=days_to_exp)).strftime("%Y-%m-%d")
            premium = round(np.random.uniform(200_000, 10_000_000), 2)  # sweeps are large
            side = np.random.choice(["ASK", "BID"])
            sentiment = "BULLISH" if (opt_type == "CALL" and side == "ASK") or (opt_type == "PUT" and side == "BID") else "BEARISH"
            ts = now - timedelta(minutes=np.random.randint(0, 240))
            rows.append({
                "timestamp": ts,
                "type": opt_type,
                "strike": strike,
                "expiry": expiry,
                "premium": premium,
                "side": side,
                "sentiment": sentiment,
            })

        df = pd.DataFrame(rows, columns=FLOW_COLUMNS)
        return df.sort_values("timestamp", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_flow(self, symbol: str, limit: int = 50) -> pd.DataFrame:
        """
        Get recent options flow for a symbol.

        Returns DataFrame with columns:
        ``[timestamp, type, strike, expiry, premium, side, sentiment]``
        """
        if self.use_mock or not self.api_key:
            return self._generate_mock_flow(symbol, count=limit)

        cache_key = f"flow:{symbol}:{limit}"
        try:
            data = await self._request(
                f"/stock/{symbol.upper()}/options-flow",
                params={"limit": str(limit)},
                cache_key=cache_key,
                cache_ttl=15,
            )
            records = data.get("data", [])
            if not records:
                logger.warning("Empty flow data for {}; returning mock", symbol)
                return self._generate_mock_flow(symbol, count=limit)

            df = pd.DataFrame(records)
            rename_map = {
                "executed_at": "timestamp",
                "option_type": "type",
                "strike_price": "strike",
                "expiration_date": "expiry",
                "total_premium": "premium",
                "aggressor": "side",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            # Derive sentiment if not present
            if "sentiment" not in df.columns:
                df["sentiment"] = df.apply(
                    lambda r: "BULLISH" if (r.get("type") == "CALL" and r.get("side") == "ASK")
                              or (r.get("type") == "PUT" and r.get("side") == "BID")
                              else "BEARISH",
                    axis=1,
                )

            for col in FLOW_COLUMNS:
                if col not in df.columns:
                    df[col] = None

            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
            df["premium"] = pd.to_numeric(df["premium"], errors="coerce")

            return df[FLOW_COLUMNS].sort_values("timestamp", ascending=False).reset_index(drop=True)

        except Exception as exc:
            logger.error("Options flow failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_flow(symbol, count=limit)

    async def get_sweeps(self, symbol: str, limit: int = 30) -> pd.DataFrame:
        """Get large sweep orders for a symbol."""
        if self.use_mock or not self.api_key:
            return self._generate_mock_sweeps(symbol, count=limit)

        cache_key = f"sweeps:{symbol}:{limit}"
        try:
            data = await self._request(
                f"/stock/{symbol.upper()}/options-flow",
                params={"limit": str(limit * 3), "is_sweep": "true"},
                cache_key=cache_key,
                cache_ttl=15,
            )
            records = data.get("data", [])
            if not records:
                return self._generate_mock_sweeps(symbol, count=limit)

            df = pd.DataFrame(records)
            rename_map = {
                "executed_at": "timestamp",
                "option_type": "type",
                "strike_price": "strike",
                "expiration_date": "expiry",
                "total_premium": "premium",
                "aggressor": "side",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            if "sentiment" not in df.columns:
                df["sentiment"] = df.apply(
                    lambda r: "BULLISH" if (r.get("type") == "CALL" and r.get("side") == "ASK")
                              or (r.get("type") == "PUT" and r.get("side") == "BID")
                              else "BEARISH",
                    axis=1,
                )

            for col in FLOW_COLUMNS:
                if col not in df.columns:
                    df[col] = None

            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
            df["premium"] = pd.to_numeric(df["premium"], errors="coerce")

            return df[FLOW_COLUMNS].head(limit).sort_values("timestamp", ascending=False).reset_index(drop=True)

        except Exception as exc:
            logger.error("Sweeps fetch failed for {}: {} -- returning mock", symbol, exc)
            return self._generate_mock_sweeps(symbol, count=limit)

    async def get_market_flow_summary(self) -> dict:
        """
        Get overall market options flow summary.

        Returns dict with ``call_volume``, ``put_volume``, ``call_put_ratio``,
        ``total_premium``, ``call_premium``, ``put_premium``.
        """
        if self.use_mock or not self.api_key:
            np.random.seed(int(time.time()) % 2**31)
            call_vol = int(np.random.uniform(5e6, 15e6))
            put_vol = int(np.random.uniform(3e6, 12e6))
            call_prem = round(np.random.uniform(1e9, 5e9), 2)
            put_prem = round(np.random.uniform(0.8e9, 4e9), 2)
            return {
                "call_volume": call_vol,
                "put_volume": put_vol,
                "call_put_ratio": round(call_vol / max(put_vol, 1), 3),
                "total_premium": round(call_prem + put_prem, 2),
                "call_premium": call_prem,
                "put_premium": put_prem,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        try:
            data = await self._request("/market/flow-summary", cache_key="mkt_flow_summary", cache_ttl=60)
            summary = data.get("data", {})
            call_vol = int(summary.get("call_volume", 0))
            put_vol = int(summary.get("put_volume", 0))
            call_prem = float(summary.get("call_premium", 0))
            put_prem = float(summary.get("put_premium", 0))
            return {
                "call_volume": call_vol,
                "put_volume": put_vol,
                "call_put_ratio": round(call_vol / max(put_vol, 1), 3),
                "total_premium": round(call_prem + put_prem, 2),
                "call_premium": call_prem,
                "put_premium": put_prem,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("Market flow summary failed: {}", exc)
            return {"error": str(exc)}

    async def detect_unusual_activity(self, symbol: str) -> dict:
        """
        Detect unusual options activity for a symbol.

        Heuristic:
        - Fetch recent flow and sweeps
        - Flag as unusual if sweep premium > 2x average or call/put ratio is extreme.

        Returns dict with ``is_unusual``, ``direction``, ``confidence``,
        ``total_sweep_premium``, ``dominant_type``.
        """
        flow_df = await self.get_flow(symbol, limit=100)
        sweeps_df = await self.get_sweeps(symbol, limit=50)

        if flow_df.empty:
            return {"is_unusual": False, "direction": "neutral", "confidence": 0.0, "reason": "no_data"}

        total_premium = flow_df["premium"].sum()
        sweep_premium = sweeps_df["premium"].sum() if not sweeps_df.empty else 0.0

        # Call/put premium split
        call_prem = flow_df.loc[flow_df["type"] == "CALL", "premium"].sum()
        put_prem = flow_df.loc[flow_df["type"] == "PUT", "premium"].sum()
        cp_ratio = call_prem / max(put_prem, 1)

        # Sweep intensity: fraction of total premium in sweeps
        sweep_ratio = sweep_premium / max(total_premium, 1)

        # Confidence scoring
        confidence = 0.0
        reasons = []

        if sweep_ratio > 0.5:
            confidence += 0.3
            reasons.append(f"sweep_ratio={sweep_ratio:.2f}")
        if cp_ratio > 3.0:
            confidence += 0.25
            reasons.append(f"heavy_calls cp_ratio={cp_ratio:.2f}")
        elif cp_ratio < 0.33:
            confidence += 0.25
            reasons.append(f"heavy_puts cp_ratio={cp_ratio:.2f}")
        if total_premium > 10_000_000:
            confidence += 0.2
            reasons.append(f"high_volume premium={total_premium:,.0f}")
        if not sweeps_df.empty and len(sweeps_df) > 10:
            confidence += 0.15
            reasons.append(f"many_sweeps n={len(sweeps_df)}")

        confidence = min(confidence, 1.0)
        is_unusual = confidence >= 0.4

        if cp_ratio > 1.5:
            direction = "bullish"
        elif cp_ratio < 0.67:
            direction = "bearish"
        else:
            direction = "neutral"

        dominant = "CALL" if call_prem > put_prem else "PUT"

        result = {
            "is_unusual": is_unusual,
            "direction": direction,
            "confidence": round(confidence, 3),
            "total_premium": round(total_premium, 2),
            "total_sweep_premium": round(sweep_premium, 2),
            "call_put_ratio": round(cp_ratio, 3),
            "dominant_type": dominant,
            "sweep_count": len(sweeps_df),
            "reasons": reasons,
        }
        if is_unusual:
            logger.info("Unusual activity detected for {}: {}", symbol, result)
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("OptionsFlowFeed HTTP client closed")

    async def __aenter__(self) -> "OptionsFlowFeed":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
