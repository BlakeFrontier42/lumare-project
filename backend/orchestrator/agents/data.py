"""
DataAgent — owns market data refresh.

Responsibilities:
  • Periodically fetch the latest spot price for every symbol in
    bot_state["symbols"].
  • Periodically fetch fresh OHLCV bars for those same symbols.
  • Maintain a shared `price_cache` dict that other components (the
    inline orchestrator loop in PR1, future SignalAgent / RiskAgent in
    PR2) can read directly without going back to the feeds.
  • Publish two events on every cycle:
      - "price.tick"  → {symbol, price, ts}             (lossy)
      - "bars.update" → {symbol, timeframe, df}         (lossy)

Lossy delivery is the right call here: if a downstream consumer is too
slow to keep up, the latest tick is the one that matters. We log dropped
counts via the bus.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import pandas as pd

from backend.orchestrator.base import BaseAgent
from backend.orchestrator.bus import Bus

logger = logging.getLogger(__name__)


_CRYPTO_HINTS = ("BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "DOGE", "LINK", "DOT", "MATIC")


def _is_crypto(symbol: str) -> bool:
    s = symbol.upper()
    if s.endswith("USDT") or s.endswith("USD") or s.endswith("PERP"):
        return True
    return any(s.startswith(h) for h in _CRYPTO_HINTS)


class DataAgent(BaseAgent):
    name = "data"

    def __init__(self, bus: Bus, bot_state: dict, engine: Any) -> None:
        super().__init__(bus, bot_state)
        self.engine = engine
        self._price_cache: dict[str, float] = {}
        self._bars_cache: dict[str, pd.DataFrame] = {}

    @property
    def price_cache(self) -> dict[str, float]:
        return self._price_cache

    @property
    def bars_cache(self) -> dict[str, pd.DataFrame]:
        return self._bars_cache

    # ── data fetching ────────────────────────────────────

    async def _fetch_price(self, symbol: str) -> Optional[float]:
        """
        Fetch a single live price. When `bot_state["live_only"]` is True
        (the default for production), reject any quote whose `source`
        field is `"mock"` so the bot never trades on synthetic data.
        """
        live_only = bool(self.bot_state.get("live_only", True))
        try:
            if _is_crypto(symbol):
                feed = getattr(self.engine, "crypto_feed", None)
                if feed is None:
                    return None
                tk = await feed.get_ticker(symbol)
                if live_only and isinstance(tk, dict) and tk.get("source") == "mock":
                    return None
                return float(tk.get("last_price") or 0) or None
            feed = getattr(self.engine, "equities_feed", None)
            if feed is None:
                return None
            q = await feed.get_quote(symbol)
            if live_only and isinstance(q, dict) and q.get("source") == "mock":
                return None
            return float(q.get("price") or 0) or None
        except Exception as exc:
            logger.debug("DataAgent price fetch failed for %s: %s", symbol, exc)
            return None

    async def _fetch_ohlcv(self, symbol: str) -> Optional[pd.DataFrame]:
        try:
            if _is_crypto(symbol):
                feed = getattr(self.engine, "crypto_feed", None)
                if feed is None:
                    return None
                return await feed.get_ohlcv(symbol, timeframe="1H", limit=120)
            feed = getattr(self.engine, "equities_feed", None)
            if feed is None:
                return None
            return await feed.get_ohlcv(symbol, timeframe="1hour")
        except Exception as exc:
            logger.warning("DataAgent OHLCV fetch failed for %s: %s", symbol, exc)
            return None

    # ── main loop ────────────────────────────────────────

    async def _run(self) -> None:
        """
        Run two parallel inner loops, one per asset class:
          • equities at `interval_seconds_equities` (default 60s)
          • crypto   at `interval_seconds_crypto`   (default 10s)

        Crypto trades 24/7 and benefits from a tighter cadence; equities
        don't, so polling them every 10s burns the rate-limit budget for
        no gain. Splitting the loops keeps each asset class independent —
        a slow equities feed never delays the next crypto refresh.

        Both intervals fall back to legacy `interval_seconds` if the new
        keys aren't present in `bot_state`.
        """
        logger.info("DataAgent loop started")
        legacy = max(5, int(self.bot_state.get("interval_seconds", 60)))
        eq_interval = max(5, int(self.bot_state.get("interval_seconds_equities", legacy)))
        cr_interval = max(5, int(self.bot_state.get("interval_seconds_crypto", min(legacy, 10))))
        eq_loop = asyncio.create_task(self._cadence_loop("equities", eq_interval))
        cr_loop = asyncio.create_task(self._cadence_loop("crypto", cr_interval))
        try:
            await self._stop.wait()
        finally:
            for t in (eq_loop, cr_loop):
                t.cancel()
            for t in (eq_loop, cr_loop):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        logger.info("DataAgent loop exited")

    async def _cadence_loop(self, asset_class: str, interval: int) -> None:
        """One inner loop scoped to a single asset class."""
        while not self._stop.is_set() and self.bot_state.get("running"):
            try:
                await self._tick(asset_class)
            except Exception:
                logger.exception("DataAgent %s tick failed", asset_class)
            await self._sleep(interval)

    async def _tick(self, asset_class: str) -> None:
        all_symbols = list(self.bot_state.get("symbols", []))
        if not all_symbols:
            return
        if asset_class == "crypto":
            symbols = [s for s in all_symbols if _is_crypto(s)]
        else:
            symbols = [s for s in all_symbols if not _is_crypto(s)]
        if not symbols:
            return

        now = time.time()

        # 1. Prices in parallel
        price_results = await asyncio.gather(
            *[self._fetch_price(s) for s in symbols],
            return_exceptions=True,
        )
        live = 0
        for sym, price in zip(symbols, price_results):
            if isinstance(price, (int, float)) and price > 0:
                self._price_cache[sym] = float(price)
                live += 1
                await self.bus.publish(
                    "price.tick",
                    {"symbol": sym, "price": float(price), "ts": now},
                )

        # 2. OHLCV bars in parallel
        bar_results = await asyncio.gather(
            *[self._fetch_ohlcv(s) for s in symbols],
            return_exceptions=True,
        )
        for sym, df in zip(symbols, bar_results):
            if isinstance(df, Exception) or df is None:
                continue
            self._bars_cache[sym] = df
            await self.bus.publish(
                "bars.update",
                {"symbol": sym, "timeframe": "1H", "df": df, "ts": now},
            )

        logger.debug(
            "DataAgent %s tick: %d/%d prices live", asset_class, live, len(symbols)
        )
