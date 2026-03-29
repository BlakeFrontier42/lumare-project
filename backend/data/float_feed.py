"""
float_feed.py - Stock float data provider for Lumare.

Provides float analysis including:
- Shares outstanding vs. float (freely tradeable shares)
- Float classification (low/mid/high float)
- Short interest as % of float
- Institutional ownership as % of float
- Float turnover ratio (volume / float)
- Squeeze potential detection (low float + high short interest)

Data sources:
1. Polygon.io ticker details (primary - shares outstanding)
2. Financial Modeling Prep (FMP) API (float, institutional holdings)
3. SEC EDGAR (13F filings for institutional ownership)
4. Fallback: cached/mock data

Float Categories:
- Nano Float:   < 1M shares    (extreme volatility, penny stocks)
- Low Float:    1M - 10M       (high volatility, momentum plays)
- Mid Float:    10M - 100M     (moderate volatility)
- High Float:   100M - 1B      (liquid, stable)
- Mega Float:   > 1B           (ultra-liquid, index constituents)
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
from loguru import logger


# ─── Float Classification ────────────────────────────────────

class FloatCategory(str, Enum):
    NANO = "NANO"        # < 1M
    LOW = "LOW"          # 1M - 10M
    MID = "MID"          # 10M - 100M
    HIGH = "HIGH"        # 100M - 1B
    MEGA = "MEGA"        # > 1B

    @classmethod
    def classify(cls, float_shares: float) -> "FloatCategory":
        if float_shares < 1_000_000:
            return cls.NANO
        elif float_shares < 10_000_000:
            return cls.LOW
        elif float_shares < 100_000_000:
            return cls.MID
        elif float_shares < 1_000_000_000:
            return cls.HIGH
        else:
            return cls.MEGA


@dataclass
class FloatProfile:
    """Complete float analysis for a single ticker."""
    symbol: str
    shares_outstanding: Optional[float] = None
    float_shares: Optional[float] = None
    restricted_shares: Optional[float] = None
    float_category: Optional[str] = None

    # Ownership breakdown
    insider_ownership_pct: Optional[float] = None
    institutional_ownership_pct: Optional[float] = None
    public_float_pct: Optional[float] = None

    # Short interest
    short_interest: Optional[float] = None        # shares shorted
    short_pct_of_float: Optional[float] = None     # short interest / float
    days_to_cover: Optional[float] = None          # short interest / avg daily volume

    # Volume metrics
    avg_daily_volume: Optional[float] = None
    float_turnover_ratio: Optional[float] = None   # avg daily volume / float
    relative_volume: Optional[float] = None        # today's vol / avg vol

    # Derived signals
    squeeze_potential: Optional[float] = None      # 0-100 score
    liquidity_score: Optional[float] = None        # 0-100 score
    volatility_multiplier: Optional[float] = None  # expected vol vs market

    # Metadata
    market_cap: Optional[float] = None
    last_updated: Optional[str] = None
    data_source: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ─── SQLite Cache ─────────────────────────────────────────────

class _FloatDBCache:
    """Persistent SQLite cache for float data."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, timeout=10)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS float_data (
                symbol        TEXT PRIMARY KEY,
                profile_json  TEXT NOT NULL,
                fetched_at    TEXT NOT NULL,
                source        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_float_fetched
                ON float_data(fetched_at);
        """)
        conn.commit()

    def get(self, symbol: str, max_age_hours: int = 24) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT profile_json, fetched_at FROM float_data WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
        if row is None:
            return None
        fetched = datetime.fromisoformat(row["fetched_at"])
        if (datetime.now(timezone.utc) - fetched).total_seconds() > max_age_hours * 3600:
            return None
        return json.loads(row["profile_json"])

    def put(self, symbol: str, profile: dict, source: str = "api"):
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO float_data (symbol, profile_json, fetched_at, source)
               VALUES (?, ?, ?, ?)""",
            (
                symbol.upper(),
                json.dumps(profile),
                datetime.now(timezone.utc).isoformat(),
                source,
            ),
        )
        conn.commit()

    def get_all(self, max_age_hours: int = 24) -> list[dict]:
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        rows = conn.execute(
            "SELECT profile_json FROM float_data WHERE fetched_at > ?",
            (cutoff,),
        ).fetchall()
        return [json.loads(r["profile_json"]) for r in rows]


# ─── In-Memory TTL Cache ──────────────────────────────────────

class _TTLCache:
    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        exp, val = entry
        if time.monotonic() > exp:
            del self._store[key]
            return None
        return val

    def set(self, key: str, val: Any, ttl: int | None = None):
        self._store[key] = (time.monotonic() + (ttl or self._ttl), val)


# ─── Rate Limiter ─────────────────────────────────────────────

class _RateLimiter:
    def __init__(self, max_calls: int = 5, period: float = 1.0):
        self._max = max_calls
        self._period = period
        self._tokens = float(max_calls)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
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


# ─── Float Feed ───────────────────────────────────────────────

class FloatFeed:
    """
    Multi-source stock float data provider.

    Fetches float data from Polygon.io (primary) and Financial Modeling Prep
    (secondary), computes derived metrics (squeeze potential, liquidity score),
    and caches results in SQLite for fast retrieval.

    Usage:
        feed = FloatFeed(polygon_key="...", fmp_key="...")
        profile = await feed.get_float_profile("AAPL")
        low_floats = await feed.scan_low_float(symbols=["GME", "AMC", "BBBY"])
    """

    def __init__(
        self,
        polygon_key: str | None = None,
        fmp_key: str | None = None,
        db_path: str | None = None,
        cache_ttl_hours: int = 12,
    ):
        self._polygon_key = polygon_key or os.getenv("POLYGON_API_KEY", "")
        self._fmp_key = fmp_key or os.getenv("FMP_API_KEY", "")
        self._cache_ttl = cache_ttl_hours

        _db = db_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "lumare.db",
        )
        self._db_cache = _FloatDBCache(_db)
        self._mem_cache = _TTLCache(default_ttl=cache_ttl_hours * 3600)
        self._limiter = _RateLimiter(max_calls=5, period=1.0)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    # ─── Data Fetching ────────────────────────────────────────

    async def _fetch_polygon_details(self, symbol: str) -> dict:
        """Fetch ticker details from Polygon.io (includes shares outstanding)."""
        if not self._polygon_key:
            return {}

        await self._limiter.acquire()
        client = await self._get_client()
        try:
            resp = await client.get(
                f"https://api.polygon.io/v3/reference/tickers/{symbol.upper()}",
                params={"apiKey": self._polygon_key},
            )
            resp.raise_for_status()
            return resp.json().get("results", {})
        except Exception as exc:
            logger.warning("Polygon details failed for {}: {}", symbol, exc)
            return {}

    async def _fetch_fmp_float(self, symbol: str) -> dict:
        """Fetch float data from Financial Modeling Prep."""
        if not self._fmp_key:
            return {}

        await self._limiter.acquire()
        client = await self._get_client()
        try:
            # FMP shares float endpoint
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v4/shares_float",
                params={"symbol": symbol.upper(), "apikey": self._fmp_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if isinstance(data, list) and data else {}
        except Exception as exc:
            logger.warning("FMP float failed for {}: {}", symbol, exc)
            return {}

    async def _fetch_fmp_quote(self, symbol: str) -> dict:
        """Fetch quote data from FMP (volume, market cap)."""
        if not self._fmp_key:
            return {}

        await self._limiter.acquire()
        client = await self._get_client()
        try:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v3/quote/{symbol.upper()}",
                params={"apikey": self._fmp_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if isinstance(data, list) and data else {}
        except Exception as exc:
            logger.warning("FMP quote failed for {}: {}", symbol, exc)
            return {}

    async def _fetch_fmp_short_interest(self, symbol: str) -> dict:
        """Fetch short interest from FMP."""
        if not self._fmp_key:
            return {}

        await self._limiter.acquire()
        client = await self._get_client()
        try:
            resp = await client.get(
                f"https://financialmodelingprep.com/api/v4/short-interest",
                params={"symbol": symbol.upper(), "apikey": self._fmp_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if isinstance(data, list) and data else {}
        except Exception as exc:
            logger.debug("FMP short interest unavailable for {}: {}", symbol, exc)
            return {}

    # ─── Profile Construction ─────────────────────────────────

    async def get_float_profile(self, symbol: str, force_refresh: bool = False) -> FloatProfile:
        """
        Get complete float profile for a symbol.

        Three-tier lookup: memory cache -> SQLite cache -> API fetch -> mock.
        """
        sym = symbol.upper()

        # Tier 1: Memory cache
        if not force_refresh:
            cached = self._mem_cache.get(f"float:{sym}")
            if cached is not None:
                return FloatProfile(**cached)

        # Tier 2: SQLite cache
        if not force_refresh:
            db_cached = self._db_cache.get(sym, max_age_hours=self._cache_ttl)
            if db_cached is not None:
                self._mem_cache.set(f"float:{sym}", db_cached)
                return FloatProfile(**db_cached)

        # Tier 3: API fetch
        try:
            profile = await self._build_profile(sym)
        except Exception as exc:
            logger.error("Float profile build failed for {}: {}", sym, exc)
            profile = self._mock_profile(sym)

        # Cache result
        profile_dict = profile.to_dict()
        self._mem_cache.set(f"float:{sym}", profile_dict)
        self._db_cache.put(sym, profile_dict, source=profile.data_source or "api")

        return profile

    async def _build_profile(self, symbol: str) -> FloatProfile:
        """Build a float profile from multiple API sources."""
        # Fetch from all sources concurrently
        polygon_data, fmp_float, fmp_quote, fmp_short = await asyncio.gather(
            self._fetch_polygon_details(symbol),
            self._fetch_fmp_float(symbol),
            self._fetch_fmp_quote(symbol),
            self._fetch_fmp_short_interest(symbol),
            return_exceptions=True,
        )

        # Handle exceptions gracefully
        if isinstance(polygon_data, Exception):
            polygon_data = {}
        if isinstance(fmp_float, Exception):
            fmp_float = {}
        if isinstance(fmp_quote, Exception):
            fmp_quote = {}
        if isinstance(fmp_short, Exception):
            fmp_short = {}

        # If no data from any source, return mock
        if not polygon_data and not fmp_float and not fmp_quote:
            logger.info("No float data available for {} - using mock", symbol)
            return self._mock_profile(symbol)

        # ─── Extract raw values ───────────────────────────────

        # Shares outstanding (Polygon primary, FMP fallback)
        outstanding = (
            polygon_data.get("share_class_shares_outstanding")
            or polygon_data.get("weighted_shares_outstanding")
            or fmp_float.get("outstandingShares")
            or fmp_quote.get("sharesOutstanding")
        )

        # Float shares (FMP primary - they have explicit float data)
        float_shares = (
            fmp_float.get("freeFloat")
            or fmp_float.get("floatShares")
        )

        # If we have outstanding but not float, estimate from ownership
        insider_pct = None
        institutional_pct = None

        if fmp_quote:
            # FMP sometimes includes these in quote data
            pass

        # Compute float from outstanding if not directly available
        if float_shares is None and outstanding is not None:
            # Default estimate: ~80% of outstanding is float
            # Refined if we have insider/institutional data
            estimated_restricted_pct = 0.20
            float_shares = outstanding * (1.0 - estimated_restricted_pct)
            logger.debug("Estimated float for {} from outstanding: {:.0f}", symbol, float_shares)

        # Restricted shares
        restricted = None
        if outstanding and float_shares:
            restricted = max(0, outstanding - float_shares)
            if outstanding > 0:
                insider_pct = (restricted / outstanding) * 100

        # Float category
        category = None
        if float_shares and float_shares > 0:
            category = FloatCategory.classify(float_shares).value

        # Short interest
        short_interest = None
        short_pct_float = None
        days_cover = None
        if fmp_short:
            short_interest = fmp_short.get("shortInterest")
            if short_interest and float_shares and float_shares > 0:
                short_pct_float = (short_interest / float_shares) * 100

        # Volume metrics
        avg_volume = fmp_quote.get("avgVolume") or fmp_quote.get("volume")
        current_volume = fmp_quote.get("volume")
        market_cap = (
            polygon_data.get("market_cap")
            or fmp_quote.get("marketCap")
        )

        # Float turnover ratio
        turnover_ratio = None
        if avg_volume and float_shares and float_shares > 0:
            turnover_ratio = avg_volume / float_shares

        # Days to cover
        if short_interest and avg_volume and avg_volume > 0:
            days_cover = short_interest / avg_volume

        # Relative volume
        rel_vol = None
        if current_volume and avg_volume and avg_volume > 0:
            rel_vol = current_volume / avg_volume

        # ─── Derived Signals ──────────────────────────────────

        # Squeeze potential: 0-100 (higher = more squeeze-prone)
        squeeze = self._compute_squeeze_potential(
            float_shares=float_shares,
            short_pct_float=short_pct_float,
            turnover_ratio=turnover_ratio,
            days_to_cover=days_cover,
        )

        # Liquidity score: 0-100 (higher = more liquid)
        liquidity = self._compute_liquidity_score(
            float_shares=float_shares,
            avg_volume=avg_volume,
            market_cap=market_cap,
        )

        # Volatility multiplier: expected vol relative to market
        vol_mult = self._compute_volatility_multiplier(
            float_shares=float_shares,
            avg_volume=avg_volume,
            turnover_ratio=turnover_ratio,
        )

        # Determine data source
        sources = []
        if polygon_data:
            sources.append("polygon")
        if fmp_float:
            sources.append("fmp_float")
        if fmp_quote:
            sources.append("fmp_quote")
        if fmp_short:
            sources.append("fmp_short")

        return FloatProfile(
            symbol=symbol,
            shares_outstanding=_safe_float(outstanding),
            float_shares=_safe_float(float_shares),
            restricted_shares=_safe_float(restricted),
            float_category=category,
            insider_ownership_pct=_safe_float(insider_pct),
            institutional_ownership_pct=_safe_float(institutional_pct),
            public_float_pct=_safe_float((float_shares / outstanding * 100) if outstanding and float_shares else None),
            short_interest=_safe_float(short_interest),
            short_pct_of_float=_safe_float(short_pct_float),
            days_to_cover=_safe_float(days_cover),
            avg_daily_volume=_safe_float(avg_volume),
            float_turnover_ratio=_safe_float(turnover_ratio),
            relative_volume=_safe_float(rel_vol),
            squeeze_potential=squeeze,
            liquidity_score=liquidity,
            volatility_multiplier=vol_mult,
            market_cap=_safe_float(market_cap),
            last_updated=datetime.now(timezone.utc).isoformat(),
            data_source="+".join(sources) if sources else "mock",
        )

    # ─── Signal Computation ───────────────────────────────────

    @staticmethod
    def _compute_squeeze_potential(
        float_shares: Optional[float],
        short_pct_float: Optional[float],
        turnover_ratio: Optional[float],
        days_to_cover: Optional[float],
    ) -> Optional[float]:
        """
        Squeeze potential score (0-100).

        High scores indicate conditions favorable for a short squeeze:
        - Low float (small supply)
        - High short interest as % of float
        - High float turnover (active trading relative to supply)
        - High days to cover (shorts can't easily exit)
        """
        if float_shares is None:
            return None

        score = 0.0
        components = 0

        # Float size component (lower float = higher squeeze potential)
        if float_shares > 0:
            # Log scale: 1M float = 80, 10M = 60, 100M = 40, 1B = 20
            float_score = max(0, 100 - 20 * np.log10(max(float_shares, 100_000) / 100_000))
            score += float_score * 0.25
            components += 0.25

        # Short interest component
        if short_pct_float is not None and short_pct_float > 0:
            # >20% SI = max score, linear below
            si_score = min(100, short_pct_float * 5)
            score += si_score * 0.35
            components += 0.35

        # Turnover component (high turnover + low float = momentum potential)
        if turnover_ratio is not None and turnover_ratio > 0:
            turnover_score = min(100, turnover_ratio * 200)
            score += turnover_score * 0.20
            components += 0.20

        # Days to cover component
        if days_to_cover is not None and days_to_cover > 0:
            # >5 days = high, >10 = very high
            dtc_score = min(100, days_to_cover * 10)
            score += dtc_score * 0.20
            components += 0.20

        if components == 0:
            return None

        return round(score / components, 1)

    @staticmethod
    def _compute_liquidity_score(
        float_shares: Optional[float],
        avg_volume: Optional[float],
        market_cap: Optional[float],
    ) -> Optional[float]:
        """
        Liquidity score (0-100). Higher = more liquid / easier to trade.

        Considers float size, average volume, and market cap.
        """
        if float_shares is None and avg_volume is None:
            return None

        score = 0.0
        components = 0

        # Float size (bigger = more liquid)
        if float_shares and float_shares > 0:
            float_score = min(100, 20 * np.log10(max(float_shares, 1) / 1_000_000) + 50)
            float_score = max(0, float_score)
            score += float_score * 0.35
            components += 0.35

        # Volume (higher = more liquid)
        if avg_volume and avg_volume > 0:
            vol_score = min(100, 20 * np.log10(max(avg_volume, 1) / 100_000) + 40)
            vol_score = max(0, vol_score)
            score += vol_score * 0.40
            components += 0.40

        # Market cap
        if market_cap and market_cap > 0:
            cap_score = min(100, 15 * np.log10(max(market_cap, 1) / 1_000_000_000) + 60)
            cap_score = max(0, cap_score)
            score += cap_score * 0.25
            components += 0.25

        if components == 0:
            return None

        return round(score / components, 1)

    @staticmethod
    def _compute_volatility_multiplier(
        float_shares: Optional[float],
        avg_volume: Optional[float],
        turnover_ratio: Optional[float],
    ) -> Optional[float]:
        """
        Expected volatility multiplier relative to market (SPY = 1.0).

        Low float + high turnover = higher expected volatility.
        """
        if float_shares is None:
            return None

        base = 1.0

        # Float size effect
        if float_shares < 1_000_000:
            base *= 3.5
        elif float_shares < 5_000_000:
            base *= 2.5
        elif float_shares < 10_000_000:
            base *= 2.0
        elif float_shares < 50_000_000:
            base *= 1.5
        elif float_shares < 100_000_000:
            base *= 1.2
        elif float_shares < 500_000_000:
            base *= 1.0
        else:
            base *= 0.8

        # Turnover amplification
        if turnover_ratio is not None:
            if turnover_ratio > 0.5:
                base *= 1.3
            elif turnover_ratio > 0.2:
                base *= 1.1

        return round(base, 2)

    # ─── Batch Operations ─────────────────────────────────────

    async def scan_low_float(
        self,
        symbols: list[str],
        max_float: float = 10_000_000,
    ) -> list[FloatProfile]:
        """Scan a list of symbols and return only low-float stocks."""
        profiles = await asyncio.gather(
            *[self.get_float_profile(s) for s in symbols],
            return_exceptions=True,
        )

        results = []
        for p in profiles:
            if isinstance(p, Exception):
                continue
            if p.float_shares is not None and p.float_shares <= max_float:
                results.append(p)

        # Sort by float (lowest first)
        results.sort(key=lambda x: x.float_shares or float("inf"))
        return results

    async def get_squeeze_candidates(
        self,
        symbols: list[str],
        min_squeeze_score: float = 60.0,
    ) -> list[FloatProfile]:
        """Find stocks with high squeeze potential."""
        profiles = await asyncio.gather(
            *[self.get_float_profile(s) for s in symbols],
            return_exceptions=True,
        )

        results = []
        for p in profiles:
            if isinstance(p, Exception):
                continue
            if p.squeeze_potential is not None and p.squeeze_potential >= min_squeeze_score:
                results.append(p)

        results.sort(key=lambda x: x.squeeze_potential or 0, reverse=True)
        return results

    async def get_float_summary(self, symbols: list[str]) -> pd.DataFrame:
        """Get a summary DataFrame of float data for multiple symbols."""
        profiles = await asyncio.gather(
            *[self.get_float_profile(s) for s in symbols],
            return_exceptions=True,
        )

        rows = []
        for p in profiles:
            if isinstance(p, Exception):
                continue
            rows.append({
                "symbol": p.symbol,
                "float_shares": p.float_shares,
                "float_category": p.float_category,
                "short_pct_float": p.short_pct_of_float,
                "avg_volume": p.avg_daily_volume,
                "turnover_ratio": p.float_turnover_ratio,
                "squeeze_score": p.squeeze_potential,
                "liquidity_score": p.liquidity_score,
                "vol_multiplier": p.volatility_multiplier,
                "market_cap": p.market_cap,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df.sort_values("float_shares", ascending=True).reset_index(drop=True)

    # ─── Scoring Engine Integration ───────────────────────────

    def get_position_size_adjustment(self, profile: FloatProfile) -> float:
        """
        Returns a position size multiplier based on float characteristics.

        - Low float stocks get smaller positions (higher volatility risk)
        - High float stocks can take full positions
        - Squeeze candidates get reduced positions

        Returns: multiplier (0.25 to 1.0)
        """
        multiplier = 1.0

        if profile.float_category:
            cat = FloatCategory(profile.float_category)
            if cat == FloatCategory.NANO:
                multiplier *= 0.25
            elif cat == FloatCategory.LOW:
                multiplier *= 0.50
            elif cat == FloatCategory.MID:
                multiplier *= 0.75
            elif cat == FloatCategory.HIGH:
                multiplier *= 1.0
            elif cat == FloatCategory.MEGA:
                multiplier *= 1.0

        # Reduce size for high squeeze potential (unpredictable moves)
        if profile.squeeze_potential is not None and profile.squeeze_potential > 70:
            multiplier *= 0.60

        # Reduce size for low liquidity
        if profile.liquidity_score is not None and profile.liquidity_score < 30:
            multiplier *= 0.50

        return max(0.10, round(multiplier, 2))

    def get_stop_loss_adjustment(self, profile: FloatProfile) -> float:
        """
        Returns a stop-loss width multiplier based on float volatility.

        Low float = wider stops (higher noise).
        Returns: multiplier (1.0 to 3.0)
        """
        if profile.volatility_multiplier is not None:
            return min(3.0, max(1.0, profile.volatility_multiplier))
        return 1.0

    # ─── Mock Data ────────────────────────────────────────────

    @staticmethod
    def _mock_profile(symbol: str) -> FloatProfile:
        """Generate realistic mock float data."""
        np.random.seed(hash(symbol) % 2**31)

        outstanding = np.random.lognormal(mean=20, sigma=2)
        float_pct = np.random.uniform(0.60, 0.95)
        float_shares = outstanding * float_pct
        short_pct = np.random.uniform(1, 25)
        avg_vol = float_shares * np.random.uniform(0.01, 0.15)
        price = np.random.lognormal(mean=3.5, sigma=1.0)
        mcap = outstanding * price

        profile = FloatProfile(
            symbol=symbol.upper(),
            shares_outstanding=round(outstanding),
            float_shares=round(float_shares),
            restricted_shares=round(outstanding - float_shares),
            float_category=FloatCategory.classify(float_shares).value,
            insider_ownership_pct=round((1 - float_pct) * 100, 1),
            public_float_pct=round(float_pct * 100, 1),
            short_interest=round(float_shares * short_pct / 100),
            short_pct_of_float=round(short_pct, 1),
            days_to_cover=round(float_shares * short_pct / 100 / max(avg_vol, 1), 1),
            avg_daily_volume=round(avg_vol),
            float_turnover_ratio=round(avg_vol / max(float_shares, 1), 4),
            market_cap=round(mcap),
            last_updated=datetime.now(timezone.utc).isoformat(),
            data_source="mock",
        )

        # Compute derived scores using the static methods
        profile.squeeze_potential = FloatFeed._compute_squeeze_potential(
            float_shares=profile.float_shares,
            short_pct_float=profile.short_pct_of_float,
            turnover_ratio=profile.float_turnover_ratio,
            days_to_cover=profile.days_to_cover,
        )
        profile.liquidity_score = FloatFeed._compute_liquidity_score(
            float_shares=profile.float_shares,
            avg_volume=profile.avg_daily_volume,
            market_cap=profile.market_cap,
        )
        profile.volatility_multiplier = FloatFeed._compute_volatility_multiplier(
            float_shares=profile.float_shares,
            avg_volume=profile.avg_daily_volume,
            turnover_ratio=profile.float_turnover_ratio,
        )

        return profile

    # ─── Lifecycle ────────────────────────────────────────────

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "FloatFeed":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()


# ─── Helpers ──────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if not (np.isnan(f) or np.isinf(f)) else None
    except (ValueError, TypeError):
        return None
