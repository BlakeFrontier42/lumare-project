"""
ReplayDataAgent — drop-in replacement for DataAgent that replays historical
OHLCV bars onto the spine bus instead of polling live feeds.

Why this exists:

  • SignalAgent's only data source is `bars.update` events (Phase 3 §8 #4
    constraint). That means if we publish *historical* bars on the same
    topic, every downstream agent — Signal, Risk, Execution, Macro — runs
    *unchanged* against the historical tape. No special "backtest mode"
    branches anywhere in the spine.

  • That gives us "free" backtesting: spin up a Spine with ReplayDataAgent
    in place of DataAgent, and the same code path that runs in production
    runs against the past.

  • And it gives us **historical fine-tuning**: tweak strategy params or
    macro weights, run the replay, look at PnL on the resulting closed
    trades. Repeat until the params win.

Bar format:

  The agent expects `historical_bars` in `bot_state` shaped like:

      {
        "AAPL": pd.DataFrame(...),  # cols: open, high, low, close, volume
                                    # index: pandas Datetime
        "SPY":  pd.DataFrame(...),
        ...
      }

  All symbols are advanced together one bar at a time so cross-asset
  signals see a coherent point-in-time slice. The walk-forward window
  is whatever `min_warmup` requires (default 30 bars — same as the price
  ensemble's minimum) up to the end of the longest series.

Speed control:

  • `replay_speed_bars_per_sec` (default 50) — how many ticks per second
    to advance. Higher = faster backtest. Set to a small value (e.g. 1)
    to watch the bot trade in slow motion against history.

  • `replay_loop` (default False) — loop the dataset when finished. Useful
    for stress-testing the spine.
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


_DEFAULT_SPEED = 50  # bars per second
_MIN_WARMUP = 30     # match strategies.compute_signal min length


class ReplayDataAgent(BaseAgent):
    """
    Spine-compatible historical replayer. Same name as DataAgent so
    Spine.health and any consumer that introspects agent names sees a
    drop-in equivalent.
    """

    name = "data"  # intentionally identical so it slots into Spine cleanly

    def __init__(
        self,
        bus: Bus,
        bot_state: dict,
        historical_bars: Optional[dict[str, pd.DataFrame]] = None,
    ) -> None:
        super().__init__(bus, bot_state)
        # Allow callers to either pass bars at construction or stash them in
        # bot_state ahead of time. Construction-time wins if both present.
        if historical_bars is not None:
            bot_state["historical_bars"] = historical_bars
        self._price_cache: dict[str, float] = {}
        self._bars_cache: dict[str, pd.DataFrame] = {}
        # Tracks the current cursor index per symbol so we can advance one
        # bar at a time and surface a strict point-in-time view.
        self._cursors: dict[str, int] = {}

    @property
    def price_cache(self) -> dict[str, float]:
        return self._price_cache

    @property
    def bars_cache(self) -> dict[str, pd.DataFrame]:
        return self._bars_cache

    # ── main loop ────────────────────────────────────────

    async def _run(self) -> None:
        bars = self.bot_state.get("historical_bars") or {}
        if not isinstance(bars, dict) or not bars:
            logger.warning("ReplayDataAgent: no historical_bars in bot_state, exiting")
            return

        speed = max(1, int(self.bot_state.get("replay_speed_bars_per_sec", _DEFAULT_SPEED)))
        loop_when_done = bool(self.bot_state.get("replay_loop", False))
        delay = 1.0 / float(speed)

        # Initialise cursors so every symbol has at least _MIN_WARMUP bars of
        # history available the first time we publish.
        for sym in bars:
            self._cursors[sym] = _MIN_WARMUP
        max_len = max(len(df) for df in bars.values())

        logger.info(
            "ReplayDataAgent started: %d symbols, max_len=%d, speed=%d bars/s",
            len(bars), max_len, speed,
        )
        bot_state_running = self.bot_state.get  # local alias

        while not self._stop.is_set() and bot_state_running("running"):
            advanced = await self._tick(bars)
            if not advanced:
                if loop_when_done:
                    logger.info("ReplayDataAgent: tape exhausted, looping")
                    for sym in bars:
                        self._cursors[sym] = _MIN_WARMUP
                    continue
                logger.info("ReplayDataAgent: tape exhausted, halting")
                break
            await self._sleep(delay)

        logger.info("ReplayDataAgent loop exited")

    async def _tick(self, bars: dict[str, pd.DataFrame]) -> bool:
        """
        Advance every symbol by one bar and publish a `bars.update` event
        carrying the *point-in-time* slice — i.e. only bars up to and
        including the current cursor. Returns False if every symbol is
        already at end-of-tape (caller decides whether to loop or stop).
        """
        any_advanced = False
        now = time.time()
        for sym, full in bars.items():
            cursor = self._cursors.get(sym, _MIN_WARMUP)
            if cursor >= len(full):
                continue
            slice_df = full.iloc[: cursor + 1]
            self._cursors[sym] = cursor + 1
            any_advanced = True

            # Update local caches so anything reading the spine's price_cache
            # property sees the historical "current price" rather than zeros.
            try:
                last_price = float(slice_df["close"].iloc[-1])
                self._price_cache[sym] = last_price
                self._bars_cache[sym] = slice_df
            except Exception:
                continue

            await self.bus.publish(
                "price.tick",
                {"symbol": sym, "price": last_price, "ts": now},
            )
            await self.bus.publish(
                "bars.update",
                {"symbol": sym, "timeframe": "replay", "df": slice_df, "ts": now},
            )
        return any_advanced
