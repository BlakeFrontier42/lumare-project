"""
ExecutionAgent — owns the paper trading book.

Responsibilities:
  • Listen for `signal.approved` (post-PR3: RiskAgent has already vetoed
    or scaled the trade and attached a `size_scale` factor in [0,1]).
  • Open paper positions sized by `size_scale * per_trade_capital`.
  • Listen for `price.tick` events and run SL/TP exit checks against
    open positions on every fresh price.
  • Emit lossless `position.opened` and `position.closed` events so the
    event log is the authoritative trade history.

Concurrency limits, per-symbol dedup, and the daily-loss circuit breaker
all live in RiskAgent now — ExecutionAgent trusts the approved signal
and just fires it. This is the spec's "single point of veto" rule.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from backend.orchestrator.base import BaseAgent
from backend.orchestrator.bus import Bus

logger = logging.getLogger(__name__)


def _matches(pos: dict, criteria: dict) -> bool:
    """
    Position matches a flatten criteria dict iff every key in criteria
    matches the corresponding field on the position. Empty criteria matches
    everything (full flatten).
    """
    if not criteria:
        return True
    for k, v in criteria.items():
        if pos.get(k) != v:
            return False
    return True


class ExecutionAgent(BaseAgent):
    name = "execution"

    def __init__(self, bus: Bus, bot_state: dict) -> None:
        super().__init__(bus, bot_state)
        # Post-PR3: RiskAgent sits between SignalAgent and us. We only
        # see candidates that have already been approved and sized.
        self._sig_q = bus.subscribe("signal.approved", lossy=False, maxsize=256)
        self._tick_q = bus.subscribe("price.tick", lossy=True, maxsize=1024)
        # PR4: MacroAgent can ask us to flatten matching positions on a
        # regime flip. Lossless because losing a flatten could leave a hot
        # position open against the operator's intent.
        self._flat_q = bus.subscribe("position.flatten", lossy=False, maxsize=64)

    async def _run(self) -> None:
        logger.info("ExecutionAgent loop started")
        sig_loop = asyncio.create_task(self._signal_loop(), name="exec:signals")
        tick_loop = asyncio.create_task(self._price_loop(), name="exec:ticks")
        flat_loop = asyncio.create_task(self._flatten_loop(), name="exec:flatten")
        try:
            await self._stop.wait()
        finally:
            for t in (sig_loop, tick_loop, flat_loop):
                t.cancel()
            for t in (sig_loop, tick_loop, flat_loop):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        logger.info("ExecutionAgent loop exited")

    # ── signal handling ──────────────────────────────────

    async def _signal_loop(self) -> None:
        while not self._stop.is_set():
            try:
                signal = await self._sig_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ExecutionAgent failed reading signal queue")
                continue
            try:
                await self._handle_signal(signal)
            except Exception:
                logger.exception("ExecutionAgent failed handling signal")

    async def _handle_signal(self, signal: dict) -> None:
        opened = self._open_position(signal)
        if opened is None:
            return
        await self.bus.publish("position.opened", opened)

        # Mirror the legacy bot_log so the /api/bot/state log shows opens
        try:
            from backend.api import app as _app
            _app._bot_log(
                "opened",
                symbol=opened["symbol"],
                detail=(
                    f"{opened['direction']} {opened['quantity']} @ "
                    f"{opened['entryPrice']:.2f} ({signal.get('strategy', '?')})"
                ),
            )
        except Exception:
            logger.debug("ExecutionAgent could not append bot_log for open", exc_info=True)

    def _open_position(self, signal: dict) -> dict | None:
        bot_state = self.bot_state
        # Belt-and-suspenders: RiskAgent has already filtered, but if for any
        # reason a duplicate slipped through (e.g. two approvals racing), we
        # still refuse to double-up on a symbol we already hold.
        if any(p["symbol"] == signal["symbol"] for p in bot_state.get("positions", [])):
            return None

        starting_capital = float(bot_state.get("starting_capital", 100_000))
        size_scale = float(signal.get("size_scale", 1.0))
        per_trade = starting_capital * 0.02 * size_scale
        price = float(signal["price"])
        if per_trade <= 0 or price <= 0:
            return None
        qty = round(per_trade / max(price, 1e-6), 6)

        pos = {
            "id": str(uuid.uuid4())[:8],
            "symbol": signal["symbol"],
            "direction": signal["direction"],
            "strategy": signal.get("strategy", "unknown"),
            "entryPrice": price,
            "currentPrice": price,
            "quantity": qty,
            "stopLoss": price * (0.97 if signal["direction"] == "LONG" else 1.03),
            "takeProfit": price * (1.06 if signal["direction"] == "LONG" else 0.94),
            "entryTime": time.time(),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
        }
        bot_state.setdefault("positions", []).append(pos)
        bot_state["trades_placed"] = bot_state.get("trades_placed", 0) + 1
        return pos

    # ── flatten handling ─────────────────────────────────

    async def _flatten_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = await self._flat_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ExecutionAgent failed reading flatten queue")
                continue
            try:
                await self._handle_flatten(event)
            except Exception:
                logger.exception("ExecutionAgent failed handling flatten")

    async def _handle_flatten(self, event: dict) -> None:
        criteria = event.get("criteria") or {}
        reason = event.get("reason", "macro_flatten")
        bot_state = self.bot_state
        positions = bot_state.get("positions", [])
        if not positions:
            return

        survivors: list[dict] = []
        closed: list[dict] = []
        for pos in positions:
            if not _matches(pos, criteria):
                survivors.append(pos)
                continue
            entry = pos["entryPrice"]
            qty = pos["quantity"]
            price = float(pos.get("currentPrice", entry))
            if pos["direction"] == "LONG":
                pnl = (price - entry) * qty
            else:
                pnl = (entry - price) * qty
            cost = entry * qty
            closed.append({
                **pos,
                "exitPrice": price,
                "exitTime": time.time(),
                "pnl": round(pnl, 4),
                "pnl_pct": round((pnl / cost * 100) if cost else 0.0, 4),
                "exit_reason": reason,
            })

        if not closed:
            return

        bot_state["positions"] = survivors
        bot_state.setdefault("closed_trades", []).extend(closed)
        if len(bot_state["closed_trades"]) > 1000:
            bot_state["closed_trades"] = bot_state["closed_trades"][-1000:]
        for c in closed:
            await self.bus.publish("position.closed", c)
            try:
                from backend.api import app as _app
                _app._bot_log(
                    "flattened",
                    symbol=c["symbol"],
                    detail=f"{reason} pnl={c['pnl']:+.2f}",
                )
            except Exception:
                logger.debug("ExecutionAgent could not append bot_log for flatten", exc_info=True)
        logger.warning("ExecutionAgent flattened %d positions (%s)", len(closed), reason)

    # ── price-tick / exit handling ───────────────────────

    async def _price_loop(self) -> None:
        while not self._stop.is_set():
            try:
                tick = await self._tick_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ExecutionAgent failed reading tick queue")
                continue
            try:
                await self._apply_tick(tick)
            except Exception:
                logger.exception("ExecutionAgent failed applying tick")

    async def _apply_tick(self, tick: dict) -> None:
        sym = tick.get("symbol")
        price = tick.get("price")
        if not sym or not isinstance(price, (int, float)) or price <= 0:
            return

        bot_state = self.bot_state
        positions = bot_state.get("positions", [])
        if not positions:
            return

        survivors: list[dict] = []
        closed: list[dict] = []
        for pos in positions:
            if pos["symbol"] != sym:
                survivors.append(pos)
                continue

            pos["currentPrice"] = float(price)
            entry = pos["entryPrice"]
            qty = pos["quantity"]
            if pos["direction"] == "LONG":
                pnl = (price - entry) * qty
                hit_sl = price <= pos["stopLoss"]
                hit_tp = price >= pos["takeProfit"]
            else:
                pnl = (entry - price) * qty
                hit_sl = price >= pos["stopLoss"]
                hit_tp = price <= pos["takeProfit"]

            cost = entry * qty
            pos["unrealized_pnl"] = round(pnl, 4)
            pos["unrealized_pnl_pct"] = round((pnl / cost * 100) if cost else 0.0, 4)

            if hit_sl or hit_tp:
                exit_event = {
                    **pos,
                    "exitPrice": float(price),
                    "exitTime": time.time(),
                    "pnl": round(pnl, 4),
                    "pnl_pct": pos["unrealized_pnl_pct"],
                    "exit_reason": "take_profit" if hit_tp else "stop_loss",
                }
                closed.append(exit_event)
            else:
                survivors.append(pos)

        bot_state["positions"] = survivors
        if closed:
            bot_state.setdefault("closed_trades", []).extend(closed)
            if len(bot_state["closed_trades"]) > 1000:
                bot_state["closed_trades"] = bot_state["closed_trades"][-1000:]
            for c in closed:
                await self.bus.publish("position.closed", c)
                try:
                    from backend.api import app as _app
                    _app._bot_log(
                        "closed",
                        symbol=c["symbol"],
                        detail=f"{c['exit_reason']} pnl={c['pnl']:+.2f}",
                    )
                except Exception:
                    logger.debug("ExecutionAgent could not append bot_log for close", exc_info=True)
