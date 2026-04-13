"""
SignalAgent — turns OHLCV bars into trade signals.

Responsibilities:
  • Subscribe to `bars.update` events.
  • For each fresh bar, run the strategy ensemble in
    `backend.orchestrator.strategies.compute_signal`.
  • Filter to strategies enabled in `bot_state["strategies"]`.
  • Dedupe so the same bar can't fire twice for the same symbol.
  • Append the signal to `bot_state["signals"]` (capped at 200 history)
    and emit `signal.candidate` for downstream agents.

Critical design constraint (Phase 3 §8 #4): SignalAgent's ONLY data
source is `bars.update` events. There is NO direct feed access. This
makes backtesting trivial — swap DataAgent for a ReplayDataAgent that
publishes historical bars and SignalAgent runs unchanged.

`signal.candidate` is published as **lossless** so the event log captures
every signal we ever generated, even if no consumer is wired up yet
(e.g., before RiskAgent exists in PR3).
"""
from __future__ import annotations

import asyncio
import logging

from backend.orchestrator.base import BaseAgent
from backend.orchestrator.bus import Bus
from backend.orchestrator.strategies import compute_macro_signal, compute_signal

logger = logging.getLogger(__name__)


class SignalAgent(BaseAgent):
    name = "signal"

    def __init__(self, bus: Bus, bot_state: dict) -> None:
        super().__init__(bus, bot_state)
        # Subscribe BEFORE the agent task starts so we don't miss early bars.
        self._bars_q = bus.subscribe("bars.update", lossy=True, maxsize=512)
        # Macro updates feed strategy-weight adjustments. Lossy is fine — the
        # latest macro snapshot is the only one that matters.
        self._macro_q = bus.subscribe("macro.update", lossy=True, maxsize=32)
        # Track the last bar timestamp processed per symbol so a slow tick
        # delivering the same bar twice doesn't double-fire.
        self._last_bar_ts: dict[str, float] = {}
        # Per-strategy multiplier driven by macro regime; defaults to 1.0.
        self._strategy_weights: dict[str, float] = {}

    async def _run(self) -> None:
        logger.info("SignalAgent loop started")
        bars_loop = asyncio.create_task(self._bars_loop(), name="signal:bars")
        macro_loop = asyncio.create_task(self._macro_loop(), name="signal:macro")
        try:
            await self._stop.wait()
        finally:
            for t in (bars_loop, macro_loop):
                t.cancel()
            for t in (bars_loop, macro_loop):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        logger.info("SignalAgent loop exited")

    async def _bars_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = await self._bars_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("SignalAgent failed reading bars queue")
                continue
            try:
                await self._handle_bars(event)
            except Exception:
                logger.exception("SignalAgent failed handling bars event")

    async def _macro_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = await self._macro_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("SignalAgent failed reading macro queue")
                continue
            self._strategy_weights = self._weights_for_regime(event.get("regime"))
            logger.debug(
                "SignalAgent strategy weights updated for regime %s: %s",
                event.get("regime"), self._strategy_weights,
            )

    @staticmethod
    def _weights_for_regime(regime: str | None) -> dict[str, float]:
        """
        Per-strategy confidence multipliers by macro regime. The score we
        emit is multiplied by the strategy's weight before scoring/sorting,
        so a 0.6 weight means "still legal but capped at 60% of normal
        conviction" — RiskAgent's score-based scale will then size it down.
        """
        if regime == "risk_off":
            return {
                "momentum": 0.7,
                "trend_following": 0.5,   # trends collapse in vol spikes
                "breakout": 0.5,          # false breakouts dominate
                "mean_reversion": 1.1,    # mean rev shines in chop
            }
        if regime == "bullish":
            return {
                "momentum": 1.1,
                "trend_following": 1.1,
                "breakout": 1.05,
                "mean_reversion": 0.9,
            }
        return {}  # neutral / unknown — no adjustment

    async def _handle_bars(self, event: dict) -> None:
        symbol = event.get("symbol")
        df = event.get("df")
        ts = float(event.get("ts", 0.0))
        if not symbol or df is None:
            return

        # Dedupe — only process if bar timestamp moved forward
        if ts and self._last_bar_ts.get(symbol, 0.0) >= ts:
            return
        self._last_bar_ts[symbol] = ts

        # Run both ensembles and pick the higher-scoring signal. The price
        # ensemble is the bread and butter; the macro compass only fires for
        # broad index ETFs in extreme regimes — when it does fire, it's high
        # conviction so we let it compete on equal footing.
        price_sig = compute_signal(df, symbol)
        macro_sig = compute_macro_signal(
            df, symbol, self.bot_state.get("macro_state")
        )
        candidates = [s for s in (price_sig, macro_sig) if s is not None]
        if not candidates:
            return
        sig = max(candidates, key=lambda s: float(s.get("score", 0) or 0))

        enabled = self.bot_state.get("strategies", [])
        if enabled and sig["strategy"] not in enabled:
            return

        # Apply macro-driven weight to the score so RiskAgent's score-based
        # sizing shrinks (or grows) the trade in line with the regime.
        weight = self._strategy_weights.get(sig["strategy"], 1.0)
        if weight != 1.0:
            sig["score"] = round(min(100.0, max(0.0, sig["score"] * weight)), 2)
            sig["macro_weight"] = weight

        # Update the read model the API exposes
        self.bot_state.setdefault("signals", []).append(sig)
        self.bot_state["signals_generated"] = self.bot_state.get("signals_generated", 0) + 1
        if len(self.bot_state["signals"]) > 200:
            self.bot_state["signals"] = self.bot_state["signals"][-200:]

        # Lossless emit so the event log captures every candidate
        await self.bus.publish("signal.candidate", sig)
