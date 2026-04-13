"""
MacroAgent — owns the macro regime view and broadcasts it to the spine.

Cadence: every `interval_seconds_macro` (default 900s = 15 min). Macro
state moves slowly so this is intentionally a much slower beat than the
data/signal cycle.

What it emits:

  • `macro.update` — `{regime, bias, score, vix, signals, ts}`. SignalAgent
    consumes these to apply per-strategy weight adjustments (e.g., haircut
    trend_following confidence in risk-off).

  • `position.flatten` — `{reason, criteria, ts}`. ExecutionAgent honors
    these by closing every open position whose attributes match `criteria`
    (an empty criteria flattens everything). Gated by
    `bot_state["macro_can_flatten"]` — flip that to False to disable
    proactive de-risking entirely without restarting the bot.

How it derives regime: tries `engine.aggregator.macro_feed.get_macro_snapshot()`
if present (FRED + VIX), otherwise emits a `neutral / data_unavailable`
update so downstream consumers always have *something* fresh and don't
assume hostile defaults.

PR4 keeps the regime model simple — three states (bullish / neutral /
risk_off) keyed off VIX + treasury spread. The Macro Compass UI can layer
on richer scoring without changing the event contract.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from backend.orchestrator.base import BaseAgent
from backend.orchestrator.bus import Bus

logger = logging.getLogger(__name__)


_DEFAULT_INTERVAL = 900  # 15 minutes


class MacroAgent(BaseAgent):
    name = "macro"

    def __init__(self, bus: Bus, bot_state: dict, engine: Any) -> None:
        super().__init__(bus, bot_state)
        self.engine = engine
        # Last regime we published — used to detect transitions for flatten.
        self._last_regime: Optional[str] = None
        bot_state.setdefault("macro_can_flatten", True)
        bot_state.setdefault("macro_state", {
            "regime": None,
            "bias": "neutral",
            "score": 50.0,
            "vix": None,
            "ts": None,
            "source": None,
        })

    async def _run(self) -> None:
        logger.info("MacroAgent loop started")
        # Run an immediate refresh so consumers don't have to wait 15 minutes
        # for their first macro state.
        await self._refresh_once()
        interval = max(5, int(self.bot_state.get("interval_seconds_macro", _DEFAULT_INTERVAL)))
        while not self._stop.is_set():
            await self._sleep(interval)
            if self._stop.is_set():
                break
            try:
                await self._refresh_once()
            except Exception:
                logger.exception("MacroAgent refresh failed")
        logger.info("MacroAgent loop exited")

    # ── refresh + publish ────────────────────────────────

    async def _refresh_once(self) -> None:
        snapshot = await self._fetch_snapshot()
        update = self._derive_update(snapshot)
        self.bot_state["macro_state"] = update
        await self.bus.publish("macro.update", update)
        logger.debug(
            "MacroAgent published: regime=%s bias=%s score=%.1f vix=%s",
            update["regime"], update["bias"], update["score"], update.get("vix"),
        )

        # Regime-transition handling: if we just flipped INTO risk_off, and
        # the operator hasn't disabled proactive flattens, fire flatten events
        # for the strategies that perform worst in risk-off (trend_following
        # and breakout — both lean on trends that vol-spikes destroy).
        if (
            self._last_regime is not None
            and self._last_regime != "risk_off"
            and update["regime"] == "risk_off"
            and self.bot_state.get("macro_can_flatten", True)
        ):
            for strat in ("trend_following", "breakout"):
                await self.bus.publish("position.flatten", {
                    "reason": f"macro_regime_risk_off:{strat}",
                    "criteria": {"strategy": strat},
                    "ts": time.time(),
                })
            logger.warning(
                "MacroAgent: regime flipped to risk_off, fired flatten for "
                "trend_following + breakout"
            )
        self._last_regime = update["regime"]

    async def _fetch_snapshot(self) -> Optional[dict]:
        try:
            agg = getattr(self.engine, "aggregator", None)
            if agg is None:
                return None
            feed = getattr(agg, "macro_feed", None)
            if feed is None:
                return None
            snap = await feed.get_macro_snapshot()
            if isinstance(snap, dict):
                return snap
            return None
        except Exception as exc:
            logger.debug("MacroAgent macro_feed fetch failed: %s", exc)
            return None

    @staticmethod
    def _derive_update(snapshot: Optional[dict]) -> dict:
        """
        Translate a raw macro snapshot into the spine-level event shape.

        Logic (deliberately simple — the rich Macro Compass scoring lives
        in `backend/core/macro_engine.py` and feeds the /macro UI; this
        agent's job is to compress that into a regime label the rest of the
        spine can act on):

          risk_off  if VIX > 28 OR 2s10s inverted hard (< -40 bps)
          bullish   if VIX < 16 AND 2s10s > 0
          neutral   otherwise
        """
        ts = time.time()
        if not snapshot:
            return {
                "regime": "neutral",
                "bias": "neutral",
                "score": 50.0,
                "vix": None,
                "signals": ["macro_snapshot_unavailable"],
                "source": "fallback",
                "ts": ts,
            }

        vix = _maybe_float(snapshot.get("vixcls"))
        t10y2y = _maybe_float(snapshot.get("t10y2y"))

        signals: list[str] = []
        regime = "neutral"
        bias = "neutral"
        score = 50.0

        if vix is not None and vix > 28:
            regime = "risk_off"
            bias = "short"
            score = 25.0
            signals.append(f"vix_elevated_{vix:.1f}")
        elif t10y2y is not None and t10y2y < -0.40:
            regime = "risk_off"
            bias = "short"
            score = 30.0
            signals.append(f"yield_curve_inverted_{t10y2y:.2f}")
        elif vix is not None and vix < 16 and (t10y2y is None or t10y2y > 0):
            regime = "bullish"
            bias = "long"
            score = 75.0
            signals.append(f"vix_calm_{vix:.1f}")

        return {
            "regime": regime,
            "bias": bias,
            "score": score,
            "vix": vix,
            "t10y2y": t10y2y,
            "signals": signals,
            "source": "fred",
            "ts": ts,
        }


def _maybe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
