"""
macro_feed.py - FRED API connector for macroeconomic data.

Provides access to key macro series (fed funds, M2, treasuries, CPI,
unemployment, reverse repo, fed balance sheet) and computes a composite
liquidity index. Uses the fredapi library for FRED access, with SQLite
caching to minimize redundant API calls, and mock fallback when no key
is configured.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Try to import fredapi; graceful fallback if not installed
# ---------------------------------------------------------------------------

try:
    from fredapi import Fred
    _FREDAPI_AVAILABLE = True
except ImportError:
    Fred = None  # type: ignore[assignment,misc]
    _FREDAPI_AVAILABLE = False
    logger.warning("fredapi not installed -- macro feed will use mock data")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Well-known FRED series IDs
SERIES: Dict[str, str] = {
    "fed_funds":        "FEDFUNDS",
    "m2":               "M2SL",
    "treasury_2y":      "DGS2",
    "treasury_10y":     "DGS10",
    "cpi":              "CPIAUCSL",
    "unemployment":     "UNRATE",
    "reverse_repo":     "RRPONTSYD",
    "fed_balance_sheet": "WALCL",
}

# Cache TTLs per series type (seconds)
# Daily series (treasuries, reverse repo) refresh more often than monthly
_CACHE_TTL: Dict[str, int] = {
    "FEDFUNDS":   86400,      # monthly, 24h cache
    "M2SL":       86400,      # monthly
    "DGS2":       3600,       # daily, 1h cache
    "DGS10":      3600,       # daily
    "CPIAUCSL":   86400,      # monthly
    "UNRATE":     86400,      # monthly
    "RRPONTSYD":  3600,       # daily
    "WALCL":      86400,      # weekly
}

_DEFAULT_CACHE_TTL = 3600  # 1 hour fallback

# SQLite cache database filename
_CACHE_DB_NAME = "macro_cache.db"

# ---------------------------------------------------------------------------
# SQLite Cache Layer
# ---------------------------------------------------------------------------

_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS fred_observations (
    series_id   TEXT    NOT NULL,
    obs_date    TEXT    NOT NULL,
    value       REAL    NOT NULL,
    fetched_at  TEXT    NOT NULL,
    PRIMARY KEY (series_id, obs_date)
);

CREATE TABLE IF NOT EXISTS fred_fetch_log (
    series_id       TEXT    NOT NULL PRIMARY KEY,
    last_fetched_at TEXT    NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 0
);
"""


class _MacroCache:
    """Thread-safe SQLite cache for FRED observations."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._local = threading.local()
        # Initialize schema on first creation
        with self._connect() as conn:
            conn.executescript(_CACHE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """Get a thread-local connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def get_series(
        self,
        series_id: str,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.DataFrame]:
        """
        Return cached observations if the series was fetched recently enough.
        Returns None if cache is stale or empty for this series.
        """
        ttl = _CACHE_TTL.get(series_id, _DEFAULT_CACHE_TTL)
        conn = self._connect()
        row = conn.execute(
            "SELECT last_fetched_at FROM fred_fetch_log WHERE series_id = ?",
            (series_id,),
        ).fetchone()

        if row is None:
            return None

        last_fetched = datetime.fromisoformat(row[0])
        age_seconds = (datetime.now(timezone.utc) - last_fetched).total_seconds()
        if age_seconds > ttl:
            return None

        rows = conn.execute(
            """
            SELECT obs_date, value FROM fred_observations
            WHERE series_id = ? AND obs_date >= ? AND obs_date <= ?
            ORDER BY obs_date
            """,
            (series_id, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

        if not rows:
            return None

        df = pd.DataFrame(rows, columns=["date", "value"])
        df["date"] = pd.to_datetime(df["date"])
        return df

    def store_series(
        self,
        series_id: str,
        df: pd.DataFrame,
    ) -> None:
        """Store observations and update the fetch log."""
        if df is None or df.empty:
            return

        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()

        # Upsert observations
        rows = []
        for _, row in df.iterrows():
            obs_date = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
            rows.append((series_id, obs_date, float(row["value"]), now))

        conn.executemany(
            """
            INSERT OR REPLACE INTO fred_observations (series_id, obs_date, value, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )

        # Update fetch log
        conn.execute(
            """
            INSERT OR REPLACE INTO fred_fetch_log (series_id, last_fetched_at, observation_count)
            VALUES (?, ?, ?)
            """,
            (series_id, now, len(rows)),
        )
        conn.commit()

    def clear(self, series_id: Optional[str] = None) -> None:
        """Clear cache for a specific series, or all if None."""
        conn = self._connect()
        if series_id:
            conn.execute("DELETE FROM fred_observations WHERE series_id = ?", (series_id,))
            conn.execute("DELETE FROM fred_fetch_log WHERE series_id = ?", (series_id,))
        else:
            conn.execute("DELETE FROM fred_observations")
            conn.execute("DELETE FROM fred_fetch_log")
        conn.commit()


# ---------------------------------------------------------------------------
# In-memory TTL cache for hot-path lookups
# ---------------------------------------------------------------------------

class _TTLCache:
    """Simple in-memory TTL cache to avoid hitting SQLite on every call."""

    def __init__(self, default_ttl: int = 300):
        self._store: Dict[str, tuple[float, Any]] = {}
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


# ---------------------------------------------------------------------------
# FRED Macro Feed
# ---------------------------------------------------------------------------

class MacroFeed:
    """
    FRED macroeconomic data feed using the fredapi library.

    Accepts either a Settings object (from backend.config.settings) or
    explicit keyword arguments. When a Settings object is passed, the
    FRED API key is read from settings.api.FRED_KEY.

    Parameters
    ----------
    settings_or_api_key : Settings | str | None
        A Settings dataclass, a raw API key string, or None.
    use_mock : bool
        Return synthetic data instead of hitting the API.
    cache_ttl : int
        Default in-memory cache TTL in seconds.
    db_dir : str | Path | None
        Directory for the SQLite cache file. Defaults to ``data/``.
    """

    def __init__(
        self,
        settings_or_api_key: Any = None,
        use_mock: bool = False,
        cache_ttl: int = 600,
        db_dir: str | Path | None = None,
    ) -> None:
        # Resolve API key from Settings, string, or environment
        self.api_key: str = ""
        self._settings = None

        if settings_or_api_key is not None:
            if isinstance(settings_or_api_key, str):
                self.api_key = settings_or_api_key
            elif hasattr(settings_or_api_key, "api"):
                # It's a Settings object
                self._settings = settings_or_api_key
                self.api_key = getattr(settings_or_api_key.api, "FRED_KEY", "")
            elif hasattr(settings_or_api_key, "FRED_KEY"):
                self.api_key = settings_or_api_key.FRED_KEY

        if not self.api_key:
            self.api_key = os.getenv("FRED_API_KEY", "")

        self.use_mock = use_mock

        # In-memory cache
        self._mem_cache = _TTLCache(default_ttl=cache_ttl)

        # FRED client
        self._fred: Optional[Fred] = None  # type: ignore[assignment]
        if self.api_key and _FREDAPI_AVAILABLE and not self.use_mock:
            try:
                self._fred = Fred(api_key=self.api_key)
                logger.info("FRED API client initialized successfully")
            except Exception as exc:
                logger.error("Failed to initialize FRED client: {}", exc)
                self._fred = None

        if not self._fred and not self.use_mock:
            logger.warning(
                "No FRED API connection available (key={}, fredapi={}). "
                "Mock data will be used.",
                "set" if self.api_key else "missing",
                "installed" if _FREDAPI_AVAILABLE else "missing",
            )

        # SQLite cache
        if db_dir is None:
            db_dir = Path(
                getattr(self._settings, "db_path", "data/lumare.db")
            ).parent if self._settings else Path("data")
        db_dir = Path(db_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        self._cache = _MacroCache(db_dir / _CACHE_DB_NAME)

    # ------------------------------------------------------------------
    # Core series fetcher
    # ------------------------------------------------------------------

    def _fetch_from_fred(
        self,
        series_id: str,
        start_date: date,
        end_date: date,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch a single FRED series via fredapi.
        Returns a DataFrame with [date, value] or None on failure.
        """
        if self._fred is None:
            return None

        try:
            series = self._fred.get_series(
                series_id,
                observation_start=start_date.isoformat(),
                observation_end=end_date.isoformat(),
            )

            if series is None or series.empty:
                logger.warning("FRED returned empty data for {}", series_id)
                return None

            df = series.dropna().reset_index()
            df.columns = ["date", "value"]
            df["date"] = pd.to_datetime(df["date"])
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)

            logger.debug(
                "Fetched {} observations for {} ({} to {})",
                len(df), series_id, start_date, end_date,
            )
            return df

        except Exception as exc:
            logger.error("FRED API error for {}: {}", series_id, exc)
            return None

    async def get_series(
        self,
        series_id: str,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        Fetch a FRED series as a DataFrame with columns [date, value].

        Lookup order:
        1. In-memory TTL cache (hot path)
        2. SQLite cache (warm path)
        3. FRED API via fredapi (cold path, then cached)
        4. Mock data (fallback)
        """
        _end = date.fromisoformat(str(end_date)) if end_date else date.today()
        _start = date.fromisoformat(str(start_date)) if start_date else _end - timedelta(days=365 * 2)

        cache_key = f"fred:{series_id}:{_start}:{_end}"

        # 1. In-memory cache
        cached = self._mem_cache.get(cache_key)
        if cached is not None:
            logger.debug("Memory cache hit for {}", series_id)
            return cached

        # 2. Mock mode shortcut
        if self.use_mock or (not self._fred):
            # Try SQLite cache even without API connection
            sqlite_df = self._cache.get_series(series_id, _start, _end)
            if sqlite_df is not None and not sqlite_df.empty:
                logger.debug("SQLite cache hit for {} (no API)", series_id)
                self._mem_cache.set(cache_key, sqlite_df)
                return sqlite_df

            if not self._fred:
                # No API and no cache -- generate mock
                freq = "MS" if series_id in ("M2SL", "CPIAUCSL", "UNRATE", "FEDFUNDS") else "D"
                mock_df = self._generate_mock_series(series_id, _start, _end, freq=freq)
                self._mem_cache.set(cache_key, mock_df, ttl=300)
                return mock_df

        # 3. SQLite cache check
        sqlite_df = self._cache.get_series(series_id, _start, _end)
        if sqlite_df is not None and not sqlite_df.empty:
            logger.debug("SQLite cache hit for {}", series_id)
            self._mem_cache.set(cache_key, sqlite_df)
            return sqlite_df

        # 4. Fetch from FRED API (run in executor to avoid blocking event loop)
        loop = asyncio.get_event_loop()
        try:
            df = await loop.run_in_executor(
                None, self._fetch_from_fred, series_id, _start, _end
            )
        except Exception as exc:
            logger.error("Executor error fetching {}: {}", series_id, exc)
            df = None

        if df is not None and not df.empty:
            # Persist to SQLite and memory
            try:
                self._cache.store_series(series_id, df)
            except Exception as exc:
                logger.warning("Failed to cache {} in SQLite: {}", series_id, exc)

            ttl = _CACHE_TTL.get(series_id, _DEFAULT_CACHE_TTL)
            self._mem_cache.set(cache_key, df, ttl=ttl)
            return df

        # 5. Fallback to mock
        logger.warning("No data for {} -- returning mock", series_id)
        freq = "MS" if series_id in ("M2SL", "CPIAUCSL", "UNRATE", "FEDFUNDS") else "D"
        mock_df = self._generate_mock_series(series_id, _start, _end, freq=freq)
        self._mem_cache.set(cache_key, mock_df, ttl=300)
        return mock_df

    # ------------------------------------------------------------------
    # Mock data generator
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_mock_series(
        series_id: str, start_date: date, end_date: date, freq: str = "D",
    ) -> pd.DataFrame:
        """Generate realistic synthetic time series for a FRED series."""
        np.random.seed(hash(series_id) % 2**31)
        idx = pd.date_range(start=start_date, end=end_date, freq=freq)
        if len(idx) == 0:
            idx = pd.date_range(start=start_date, periods=30, freq=freq)

        base_map = {
            "FEDFUNDS": 5.25, "DGS2": 4.5, "DGS10": 4.2,
            "M2SL": 21_000, "CPIAUCSL": 310,
            "UNRATE": 3.7, "RRPONTSYD": 500_000, "WALCL": 7_500_000,
        }
        base = base_map.get(series_id, 100.0)

        if series_id in ("FEDFUNDS", "DGS2", "DGS10", "UNRATE"):
            values = base + np.cumsum(np.random.normal(0, 0.01, len(idx)))
            values = np.clip(values, 0, base * 3)
        else:
            trend = np.linspace(0, base * 0.05, len(idx))
            noise = np.cumsum(np.random.normal(0, base * 0.001, len(idx)))
            values = base + trend + noise

        return pd.DataFrame({
            "date": idx,
            "value": np.round(values, 4),
        })

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    async def get_fed_funds_rate(self) -> float:
        """Get the latest effective federal funds rate."""
        df = await self.get_series(SERIES["fed_funds"], start_date=date.today() - timedelta(days=90))
        if df.empty:
            return 0.0
        return float(df["value"].iloc[-1])

    async def get_m2_money_supply(
        self, start_date: str | date | None = None, end_date: str | date | None = None,
    ) -> pd.DataFrame:
        return await self.get_series(SERIES["m2"], start_date, end_date)

    async def get_treasury_yields(
        self,
        maturity: str = "10Y",
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> pd.DataFrame:
        """Fetch treasury yield series. Maturity: ``2Y`` or ``10Y``."""
        key = f"treasury_{maturity.lower()}"
        if key not in SERIES:
            raise ValueError(f"Unsupported maturity {maturity!r}. Use 2Y or 10Y.")
        return await self.get_series(SERIES[key], start_date, end_date)

    async def get_yield_curve_spread(self) -> float:
        """Compute the 10Y-2Y yield curve spread (latest values)."""
        recent = date.today() - timedelta(days=30)
        df_10, df_2 = await asyncio.gather(
            self.get_series(SERIES["treasury_10y"], start_date=recent),
            self.get_series(SERIES["treasury_2y"], start_date=recent),
        )
        y10 = float(df_10["value"].iloc[-1]) if not df_10.empty else 0.0
        y2 = float(df_2["value"].iloc[-1]) if not df_2.empty else 0.0
        spread = round(y10 - y2, 4)
        logger.info("Yield curve spread (10Y-2Y): {}bps", round(spread * 100, 1))
        return spread

    async def get_cpi(
        self, start_date: str | date | None = None, end_date: str | date | None = None,
    ) -> pd.DataFrame:
        return await self.get_series(SERIES["cpi"], start_date, end_date)

    async def get_unemployment(
        self, start_date: str | date | None = None, end_date: str | date | None = None,
    ) -> pd.DataFrame:
        return await self.get_series(SERIES["unemployment"], start_date, end_date)

    async def get_reverse_repo(
        self, start_date: str | date | None = None, end_date: str | date | None = None,
    ) -> pd.DataFrame:
        return await self.get_series(SERIES["reverse_repo"], start_date, end_date)

    async def get_fed_balance_sheet(
        self, start_date: str | date | None = None, end_date: str | date | None = None,
    ) -> pd.DataFrame:
        return await self.get_series(SERIES["fed_balance_sheet"], start_date, end_date)

    # ------------------------------------------------------------------
    # Macro Snapshot — all latest values in one call
    # ------------------------------------------------------------------

    async def get_macro_snapshot(self) -> Dict[str, Any]:
        """
        Return a dictionary of the latest values for all tracked macro series.

        Keys match the SERIES dict keys. Also includes derived values:
        - yield_curve_spread: 10Y - 2Y
        - cpi_yoy: year-over-year CPI change (%)

        Returns empty values (None) for any series that fails, never raises.
        """
        snapshot: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fed_funds": None,
            "m2": None,
            "m2_yoy_change": None,
            "treasury_2y": None,
            "treasury_10y": None,
            "yield_curve_spread": None,
            "cpi": None,
            "cpi_yoy": None,
            "unemployment": None,
            "reverse_repo": None,
            "fed_balance_sheet": None,
        }

        # Fetch all series concurrently
        recent = date.today() - timedelta(days=90)
        two_years = date.today() - timedelta(days=365 * 2)

        tasks = {
            "fed_funds": self.get_series(SERIES["fed_funds"], start_date=recent),
            "m2": self.get_series(SERIES["m2"], start_date=two_years),
            "treasury_2y": self.get_series(SERIES["treasury_2y"], start_date=recent),
            "treasury_10y": self.get_series(SERIES["treasury_10y"], start_date=recent),
            "cpi": self.get_series(SERIES["cpi"], start_date=two_years),
            "unemployment": self.get_series(SERIES["unemployment"], start_date=recent),
            "reverse_repo": self.get_series(SERIES["reverse_repo"], start_date=recent),
            "fed_balance_sheet": self.get_series(SERIES["fed_balance_sheet"], start_date=recent),
        }

        results: Dict[str, pd.DataFrame] = {}
        gathered = await asyncio.gather(
            *tasks.values(), return_exceptions=True,
        )
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.warning("Macro snapshot: {} failed: {}", key, result)
                results[key] = pd.DataFrame()
            else:
                results[key] = result

        # Extract latest values
        def _latest(df: pd.DataFrame) -> Optional[float]:
            if df is None or df.empty:
                return None
            return float(df["value"].iloc[-1])

        snapshot["fed_funds"] = _latest(results["fed_funds"])
        snapshot["m2"] = _latest(results["m2"])
        snapshot["treasury_2y"] = _latest(results["treasury_2y"])
        snapshot["treasury_10y"] = _latest(results["treasury_10y"])
        snapshot["cpi"] = _latest(results["cpi"])
        snapshot["unemployment"] = _latest(results["unemployment"])
        snapshot["reverse_repo"] = _latest(results["reverse_repo"])
        snapshot["fed_balance_sheet"] = _latest(results["fed_balance_sheet"])

        # Derived: yield curve spread
        if snapshot["treasury_10y"] is not None and snapshot["treasury_2y"] is not None:
            snapshot["yield_curve_spread"] = round(
                snapshot["treasury_10y"] - snapshot["treasury_2y"], 4
            )

        # Derived: M2 YoY change
        m2_df = results["m2"]
        if m2_df is not None and not m2_df.empty and len(m2_df) >= 13:
            current = m2_df["value"].iloc[-1]
            year_ago = m2_df["value"].iloc[-13]  # ~12 months prior for monthly data
            if year_ago != 0:
                snapshot["m2_yoy_change"] = round((current - year_ago) / year_ago, 6)

        # Derived: CPI YoY change
        cpi_df = results["cpi"]
        if cpi_df is not None and not cpi_df.empty and len(cpi_df) >= 13:
            current = cpi_df["value"].iloc[-1]
            year_ago = cpi_df["value"].iloc[-13]
            if year_ago != 0:
                snapshot["cpi_yoy"] = round((current - year_ago) / year_ago, 6)

        logger.info(
            "Macro snapshot: fed_funds={}, 10Y={}, 2Y={}, spread={}, CPI_yoy={}, unemp={}",
            snapshot["fed_funds"],
            snapshot["treasury_10y"],
            snapshot["treasury_2y"],
            snapshot["yield_curve_spread"],
            snapshot["cpi_yoy"],
            snapshot["unemployment"],
        )

        return snapshot

    # ------------------------------------------------------------------
    # Derived: Liquidity Index
    # ------------------------------------------------------------------

    async def compute_liquidity_index(
        self,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> pd.DataFrame:
        """
        Composite liquidity index = z(M2_chg) + z(reverse_repo_chg) + z(fed_bs_chg)

        Each component is the rolling 3-period percent change, then z-scored
        and summed into a single index value. Higher = more liquidity.

        Returns DataFrame with columns [date, m2_chg, rrp_chg, bs_chg, liquidity_index].
        """
        _end = date.fromisoformat(str(end_date)) if end_date else date.today()
        _start_ext = (
            date.fromisoformat(str(start_date)) - timedelta(days=180)
            if start_date
            else _end - timedelta(days=365 * 3)
        )
        _start_out = (
            date.fromisoformat(str(start_date))
            if start_date
            else _end - timedelta(days=365 * 2)
        )

        m2_df, rrp_df, bs_df = await asyncio.gather(
            self.get_series(SERIES["m2"], _start_ext, _end),
            self.get_series(SERIES["reverse_repo"], _start_ext, _end),
            self.get_series(SERIES["fed_balance_sheet"], _start_ext, _end),
        )

        def _pct_and_zscore(df: pd.DataFrame, periods: int = 3) -> pd.Series:
            s = df.set_index("date")["value"]
            chg = s.pct_change(periods=periods)
            mu, sigma = chg.mean(), chg.std()
            if sigma == 0 or np.isnan(sigma):
                return chg.fillna(0)
            return (chg - mu) / sigma

        for df in (m2_df, rrp_df, bs_df):
            df["date"] = pd.to_datetime(df["date"])

        m2_z = _pct_and_zscore(m2_df)
        rrp_z = _pct_and_zscore(rrp_df)
        bs_z = _pct_and_zscore(bs_df)

        combined = pd.DataFrame({"m2_chg": m2_z, "rrp_chg": rrp_z, "bs_chg": bs_z})
        combined = combined.sort_index().ffill().dropna()
        combined["liquidity_index"] = combined["m2_chg"] + combined["rrp_chg"] + combined["bs_chg"]
        combined = combined.reset_index().rename(columns={"index": "date"})

        combined = combined[combined["date"] >= pd.Timestamp(_start_out)].reset_index(drop=True)
        logger.info(
            "Liquidity index computed: {} rows, latest={:.3f}",
            len(combined),
            combined["liquidity_index"].iloc[-1] if not combined.empty else float("nan"),
        )
        return combined

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self, series_id: Optional[str] = None) -> None:
        """Clear in-memory and SQLite caches."""
        self._mem_cache.clear()
        self._cache.clear(series_id)
        logger.info("Macro cache cleared{}", f" for {series_id}" if series_id else "")

    def force_refresh(self, series_id: Optional[str] = None) -> None:
        """
        Invalidate cache so the next fetch hits the FRED API.
        If series_id is None, invalidates all series.
        """
        if series_id:
            self._cache.clear(series_id)
        else:
            self._cache.clear()
        self._mem_cache.clear()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Clean up resources."""
        self._mem_cache.clear()
        logger.debug("MacroFeed closed")

    async def __aenter__(self) -> "MacroFeed":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
