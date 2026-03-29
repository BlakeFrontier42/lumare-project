"""
aggregator.py — Unified Data Pipeline
Coordinates all data feeds into a single interface for the engine.
No lookahead bias: all timestamps enforced at query boundary.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import pandas as pd
import numpy as np
from loguru import logger

from backend.config.settings import SETTINGS, Settings
from backend.data.storage import Storage
from backend.data.crypto_feed import CryptoFeed
from backend.data.equities_feed import EquitiesFeed
from backend.data.macro_feed import MacroFeed
from backend.data.options_flow_feed import OptionsFlowFeed
from backend.data.congressional_feed import CongressionalFeed
from backend.data.insider_feed import InsiderFeed


@dataclass
class MarketSnapshot:
    """Complete market data snapshot for a single symbol at a point in time."""
    symbol: str
    asset_type: str  # 'crypto' or 'equity'
    timestamp: datetime
    candles: Dict[str, pd.DataFrame] = field(default_factory=dict)
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume_24h: float = 0.0
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    oi_change_pct: Optional[float] = None
    options_flow: Optional[pd.DataFrame] = None
    congressional_trades: Optional[List[Dict]] = None
    insider_filings: Optional[List[Dict]] = None
    macro: Optional[Dict[str, Any]] = None


@dataclass
class MacroSnapshot:
    """Macro environment data at a point in time."""
    timestamp: datetime
    fed_funds_rate: Optional[float] = None
    m2_yoy_change: Optional[float] = None
    yield_curve_spread: Optional[float] = None
    cpi_yoy: Optional[float] = None
    unemployment: Optional[float] = None
    reverse_repo: Optional[float] = None
    fed_balance_sheet: Optional[float] = None
    liquidity_index: Optional[float] = None
    treasury_2y: Optional[float] = None
    treasury_10y: Optional[float] = None
    treasury_30y: Optional[float] = None


class DataAggregator:
    """
    Unified data pipeline coordinating all feeds.
    Single point of access for the entire engine.
    """

    def __init__(
        self,
        settings: Settings = None,
        storage: Storage = None,
        crypto_feed: CryptoFeed = None,
        equities_feed: EquitiesFeed = None,
        macro_feed: MacroFeed = None,
        options_flow_feed: OptionsFlowFeed = None,
        congressional_feed: CongressionalFeed = None,
        insider_feed: InsiderFeed = None,
    ):
        self.settings = settings or SETTINGS
        self.storage = storage or Storage(self.settings.db_path)
        self.crypto_feed = crypto_feed or CryptoFeed()
        self.equities_feed = equities_feed or EquitiesFeed()
        self.macro_feed = macro_feed or MacroFeed(self.settings)
        self.options_flow_feed = options_flow_feed or OptionsFlowFeed()
        self.congressional_feed = congressional_feed or CongressionalFeed()
        self.insider_feed = insider_feed or InsiderFeed()

        self._macro_cache: Optional[MacroSnapshot] = None
        self._macro_cache_time: Optional[datetime] = None
        self._macro_cache_ttl = timedelta(hours=1)
        self._refresh_task: Optional[asyncio.Task] = None

    # ─── Crypto Data ────────────────────────────────────────

    async def fetch_all_crypto(self, symbol: str) -> MarketSnapshot:
        """Fetch complete crypto data snapshot for a symbol."""
        snapshot = MarketSnapshot(
            symbol=symbol,
            asset_type="crypto",
            timestamp=datetime.now(timezone.utc),
        )
        timeframes = ["1M", "5M", "15M", "1H", "4H", "1D"]

        for tf in timeframes:
            try:
                result = self.crypto_feed.get_ohlcv(symbol, tf, limit=200)
                if asyncio.iscoroutine(result):
                    result = await result
                snapshot.candles[tf] = result
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol} {tf}: {e}")
                snapshot.candles[tf] = pd.DataFrame()

        try:
            ticker = self.crypto_feed.get_ticker(symbol)
            if asyncio.iscoroutine(ticker):
                ticker = await ticker
            if ticker:
                snapshot.last_price = ticker.get("last", 0.0)
                snapshot.volume_24h = ticker.get("volume_24h", 0.0)
        except Exception as e:
            logger.warning(f"Ticker fetch failed for {symbol}: {e}")

        try:
            funding = self.crypto_feed.get_funding_rate(symbol)
            if asyncio.iscoroutine(funding):
                funding = await funding
            if funding:
                snapshot.funding_rate = funding.get("funding_rate", 0.0)
        except Exception as e:
            logger.warning(f"Funding rate fetch failed for {symbol}: {e}")

        try:
            oi = self.crypto_feed.get_open_interest(symbol)
            if asyncio.iscoroutine(oi):
                oi = await oi
            if oi:
                snapshot.open_interest = oi.get("open_interest", 0.0)
                snapshot.oi_change_pct = oi.get("change_pct", 0.0)
        except Exception as e:
            logger.warning(f"OI fetch failed for {symbol}: {e}")

        # Persist candles to storage
        for tf, df in snapshot.candles.items():
            if not df.empty:
                self.storage.store_candles(symbol, tf, df)

        return snapshot

    # ─── Equities Data ──────────────────────────────────────

    async def fetch_all_equities(self, symbol: str) -> MarketSnapshot:
        """Fetch complete equities data snapshot."""
        snapshot = MarketSnapshot(
            symbol=symbol, asset_type="equity",
            timestamp=datetime.now(timezone.utc),
        )
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_1y = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
        start_1w = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        for tf, poly_tf, sd in [("1D", "1day", start_1y), ("1H", "1hour", start_1w),
                                 ("15M", "15min", start_1w), ("5M", "5min", start_1w)]:
            try:
                data = self.equities_feed.get_ohlcv(symbol, poly_tf, sd, end)
                if asyncio.iscoroutine(data):
                    data = await data
                if data is not None:
                    snapshot.candles[tf] = data
            except Exception as e:
                logger.warning(f"Equities {symbol} {tf} failed: {e}")

        try:
            flow = self.options_flow_feed.get_flow(symbol)
            if asyncio.iscoroutine(flow):
                flow = await flow
            snapshot.options_flow = flow
        except Exception:
            pass

        try:
            congress = self.congressional_feed.get_trades_by_ticker(symbol)
            if asyncio.iscoroutine(congress):
                congress = await congress
            if congress is not None and not congress.empty:
                snapshot.congressional_trades = congress.to_dict("records")
        except Exception:
            pass

        try:
            insiders = self.insider_feed.get_filings_by_ticker(symbol)
            if asyncio.iscoroutine(insiders):
                insiders = await insiders
            if insiders is not None and not insiders.empty:
                snapshot.insider_filings = insiders.to_dict("records")
        except Exception:
            pass

        return snapshot

    # ─── Macro Data ─────────────────────────────────────────

    async def fetch_macro_snapshot(self) -> MacroSnapshot:
        """Fetch all macro indicators. Cached with 1-hour TTL."""
        now = datetime.now(timezone.utc)
        if (self._macro_cache and self._macro_cache_time
                and (now - self._macro_cache_time) < self._macro_cache_ttl):
            return self._macro_cache

        snap = MacroSnapshot(timestamp=now)

        try:
            r = self.macro_feed.get_fed_funds_rate()
            snap.fed_funds_rate = (await r) if asyncio.iscoroutine(r) else r
        except Exception:
            pass
        try:
            r = self.macro_feed.get_m2_money_supply()
            m2 = (await r) if asyncio.iscoroutine(r) else r
            if m2 is not None and not m2.empty and len(m2) >= 13:
                snap.m2_yoy_change = (m2.iloc[-1]["value"] - m2.iloc[-13]["value"]) / m2.iloc[-13]["value"]
        except Exception:
            pass
        try:
            r = self.macro_feed.get_yield_curve_spread()
            snap.yield_curve_spread = (await r) if asyncio.iscoroutine(r) else r
        except Exception:
            pass
        try:
            r = self.macro_feed.get_reverse_repo()
            rr = (await r) if asyncio.iscoroutine(r) else r
            if rr is not None and not rr.empty:
                snap.reverse_repo = rr.iloc[-1]["value"]
        except Exception:
            pass
        try:
            r = self.macro_feed.get_fed_balance_sheet()
            fb = (await r) if asyncio.iscoroutine(r) else r
            if fb is not None and not fb.empty:
                snap.fed_balance_sheet = fb.iloc[-1]["value"]
        except Exception:
            pass

        snap.liquidity_index = self._compute_liquidity_index(snap)
        self._macro_cache = snap
        self._macro_cache_time = now
        return snap

    def _compute_liquidity_index(self, macro: MacroSnapshot) -> Optional[float]:
        """
        Composite Liquidity Index (0-100):
        = sigmoid(0.4 * M2_growth_zscore + 0.6 * net_liquidity_zscore)
        Higher = more liquidity = risk-on favorable.
        """
        components = []
        if macro.m2_yoy_change is not None:
            z = (macro.m2_yoy_change - 0.06) / 0.03
            components.append(0.4 * z)
        if macro.reverse_repo is not None and macro.fed_balance_sheet is not None:
            net_liq = macro.fed_balance_sheet - macro.reverse_repo
            z = (net_liq - 4_000_000) / 1_000_000
            components.append(0.6 * z)
        if not components:
            return None
        weighted_z = sum(components) / (0.4 + 0.6 if len(components) == 2 else
                                         0.4 if macro.m2_yoy_change is not None else 0.6)
        return round(float(100.0 / (1.0 + np.exp(-weighted_z))), 2)

    # ─── Full Snapshot ──────────────────────────────────────

    async def fetch_full_snapshot(self, symbol: str, asset_type: str = "crypto") -> MarketSnapshot:
        """Complete data snapshot: market + macro overlay."""
        snapshot = (await self.fetch_all_crypto(symbol) if asset_type == "crypto"
                    else await self.fetch_all_equities(symbol))
        macro = await self.fetch_macro_snapshot()
        snapshot.macro = {
            "fed_funds_rate": macro.fed_funds_rate,
            "m2_yoy_change": macro.m2_yoy_change,
            "yield_curve_spread": macro.yield_curve_spread,
            "liquidity_index": macro.liquidity_index,
            "reverse_repo": macro.reverse_repo,
            "fed_balance_sheet": macro.fed_balance_sheet,
        }
        return snapshot

    # ─── Historical Data (Backtest Safe) ────────────────────

    def get_historical_data(self, symbol: str, timeframe: str,
                            start: datetime, end: datetime) -> pd.DataFrame:
        """Get historical candles. End timestamp is EXCLUSIVE (no lookahead)."""
        return self.storage.get_candles(symbol, timeframe, start.isoformat(), end.isoformat())

    def build_multi_timeframe_data(self, symbol: str, current_time: datetime,
                                    lookback_bars: int = 200) -> Dict[str, pd.DataFrame]:
        """Build multi-timeframe candle dict as of a specific time (backtest safe)."""
        tf_minutes = self.settings.timeframes.timeframe_minutes
        result = {}
        for tf_name, minutes in tf_minutes.items():
            start = current_time - timedelta(minutes=minutes * lookback_bars)
            df = self.get_historical_data(symbol, tf_name, start, current_time)
            if not df.empty:
                result[tf_name] = df
        return result

    # ─── Background Refresh ─────────────────────────────────

    async def schedule_data_refresh(self, interval_minutes: int = 5):
        """Background loop refreshing data for all tracked instruments."""
        logger.info(f"Data refresh loop started: interval={interval_minutes}m")
        while True:
            try:
                for symbol in self.settings.instruments.crypto_pairs:
                    await self.fetch_all_crypto(symbol)
                for symbol in self.settings.instruments.equity_symbols:
                    await self.fetch_all_equities(symbol)
                await self.fetch_macro_snapshot()
            except Exception as e:
                logger.error(f"Data refresh error: {e}")
            await asyncio.sleep(interval_minutes * 60)

    def start_background_refresh(self, interval_minutes: int = 5):
        loop = asyncio.get_event_loop()
        self._refresh_task = loop.create_task(self.schedule_data_refresh(interval_minutes))

    def stop_background_refresh(self):
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None

    def get_data_freshness(self) -> Dict[str, Any]:
        """Report data freshness for all instruments."""
        report = {}
        now = datetime.now(timezone.utc)
        for symbol in self.settings.instruments.crypto_pairs:
            candles = self.storage.get_candles(
                symbol, "5M",
                (now - timedelta(hours=1)).isoformat(),
                now.isoformat(),
            )
            if not candles.empty:
                last = pd.to_datetime(candles["timestamp"].iloc[-1])
                age = (now - last.to_pydatetime().replace(tzinfo=timezone.utc)).total_seconds() / 60
                report[symbol] = {"last_candle": last.isoformat(), "age_minutes": round(age, 1), "fresh": age < 10}
            else:
                report[symbol] = {"last_candle": None, "fresh": False}
        return report
