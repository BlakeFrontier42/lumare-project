"""
RiskAgent — the single point where a trade can be vetoed or resized.

Listens to `signal.candidate` and emits exactly one of:
  • `signal.approved` — the candidate plus a `size_scale` in [0.0, 1.0]
  • `signal.rejected` — the candidate plus a `reason` string

Also keeps an internal portfolio model in sync by listening to
`position.opened` and `position.closed`, so it doesn't have to read
`bot_state["positions"]` (which can be mutated mid-iteration by
ExecutionAgent on a different task).

Rules implemented in PR3 (intentionally pragmatic — sector caps,
correlation, Kelly, and vol-targeting are layered on later without
re-plumbing the rest of the spine):

  1. Hard reject if we already hold a position in this symbol.
  2. Hard reject if open positions ≥ `max_concurrent_positions`.
  3. Hard reject if today's realized loss already exceeds
     `daily_loss_limit_pct` of starting capital (circuit breaker).
  4. Score-based scale factor: signal score 50→0.50, 100→1.00, linear.
  5. Portfolio-heat scale: if adding this position would push total open
     risk past `max_portfolio_heat_pct`, scale it down to fit. If even
     1% of the requested size doesn't fit, reject.

The spec calls for one numeric scale factor per approval; we compute it
once here so ExecutionAgent stays dumb (it just multiplies qty by
size_scale and fires).

`signal.approved` and `signal.rejected` are both lossless so the event
log is the auditable record of every decision the risk layer ever made.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.orchestrator.base import BaseAgent
from backend.orchestrator.bus import Bus

logger = logging.getLogger(__name__)


# Default risk parameters — can be overridden via bot_state["risk_config"].
_DEFAULTS = {
    "daily_loss_limit_pct": 3.0,       # 3% of starting capital
    "max_portfolio_heat_pct": 6.0,     # 6% total open risk across the book
    "stop_distance_pct": 3.0,          # matches ExecutionAgent's 3% SL
    "per_trade_pct": 2.0,              # 2% of capital per trade (notional)
    "min_size_scale": 0.01,            # below this we reject instead
}


class RiskAgent(BaseAgent):
    name = "risk"

    def __init__(self, bus: Bus, bot_state: dict) -> None:
        super().__init__(bus, bot_state)
        self._cand_q = bus.subscribe("signal.candidate", lossy=False, maxsize=256)
        self._open_q = bus.subscribe("position.opened", lossy=False, maxsize=256)
        self._closed_q = bus.subscribe("position.closed", lossy=False, maxsize=256)

        # Internal portfolio model — RiskAgent's own view, kept in sync via
        # position.opened/closed events. We don't read bot_state["positions"]
        # because ExecutionAgent owns it and may mutate it concurrently.
        self._open_positions: dict[str, dict] = {}  # keyed by position id
        self._open_symbols: set[str] = set()
        self._daily_realized: float = 0.0
        self._daily_anchor: float = self._today_start()

        bot_state.setdefault("risk_state", {
            "approvals": 0,
            "rejections": 0,
            "circuit_breaker_tripped": False,
            "portfolio_heat": 0.0,
            "daily_realized_pnl": 0.0,
        })

    # ── lifecycle ────────────────────────────────────────

    async def _run(self) -> None:
        logger.info("RiskAgent loop started")
        cand_loop = asyncio.create_task(self._candidate_loop(), name="risk:candidates")
        open_loop = asyncio.create_task(self._open_loop(), name="risk:opens")
        closed_loop = asyncio.create_task(self._closed_loop(), name="risk:closes")
        try:
            await self._stop.wait()
        finally:
            for t in (cand_loop, open_loop, closed_loop):
                t.cancel()
            for t in (cand_loop, open_loop, closed_loop):
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        logger.info("RiskAgent loop exited")

    # ── inner loops ──────────────────────────────────────

    async def _candidate_loop(self) -> None:
        while not self._stop.is_set():
            try:
                cand = await self._cand_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("RiskAgent failed reading candidate queue")
                continue
            try:
                await self._evaluate(cand)
            except Exception:
                logger.exception("RiskAgent failed evaluating candidate")

    async def _open_loop(self) -> None:
        while not self._stop.is_set():
            try:
                pos = await self._open_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("RiskAgent failed reading position.opened queue")
                continue
            self._open_positions[pos["id"]] = pos
            self._open_symbols.add(pos["symbol"])
            self._refresh_state()

    async def _closed_loop(self) -> None:
        while not self._stop.is_set():
            try:
                closed = await self._closed_q.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("RiskAgent failed reading position.closed queue")
                continue
            pid = closed.get("id")
            if pid in self._open_positions:
                self._open_positions.pop(pid, None)
                # Symbol may still be held by another (future) position; recompute
                self._open_symbols = {p["symbol"] for p in self._open_positions.values()}
            # Roll daily if midnight rolled over while we were running
            if time.time() >= self._daily_anchor + 86400:
                self._daily_realized = 0.0
                self._daily_anchor = self._today_start()
            self._daily_realized += float(closed.get("pnl", 0.0))
            self._refresh_state()

    # ── evaluation ───────────────────────────────────────

    async def _evaluate(self, cand: dict) -> None:
        cfg = self._risk_cfg()
        starting_capital = float(self.bot_state.get("starting_capital", 100_000))
        max_concurrent = int(self.bot_state.get("max_concurrent_positions", 5))

        # Rule 1: one position per symbol
        if cand["symbol"] in self._open_symbols:
            await self._reject(cand, "already_holding_symbol")
            return

        # Rule 2: max concurrent
        if len(self._open_positions) >= max_concurrent:
            await self._reject(cand, "max_concurrent_positions")
            return

        # Rule 3: daily-loss circuit breaker
        daily_loss_limit = starting_capital * (cfg["daily_loss_limit_pct"] / 100.0)
        if self._daily_realized <= -daily_loss_limit:
            self.bot_state["risk_state"]["circuit_breaker_tripped"] = True
            await self._reject(cand, "daily_loss_circuit_breaker")
            return

        # Rule 4: score-based scale (50 → 0.50, 100 → 1.00)
        score = float(cand.get("score", 70.0))
        score_scale = max(0.0, min(1.0, (score - 50.0) / 50.0))

        # Rule 5: portfolio heat — current open risk + this trade's risk
        # must not exceed cap. If it does, scale this trade down to fit.
        max_heat = starting_capital * (cfg["max_portfolio_heat_pct"] / 100.0)
        current_heat = self._compute_open_risk(cfg)

        per_trade_notional = starting_capital * (cfg["per_trade_pct"] / 100.0) * score_scale
        trade_risk = per_trade_notional * (cfg["stop_distance_pct"] / 100.0)

        if trade_risk <= 0:
            await self._reject(cand, "zero_size_after_score_scale")
            return

        heat_remaining = max(0.0, max_heat - current_heat)
        if heat_remaining <= 0:
            await self._reject(cand, "portfolio_heat_exhausted")
            return

        heat_scale = min(1.0, heat_remaining / trade_risk)
        size_scale = score_scale * heat_scale

        if size_scale < cfg["min_size_scale"]:
            await self._reject(cand, "size_scale_below_minimum")
            return

        await self._approve(cand, size_scale)

    async def _approve(self, cand: dict, size_scale: float) -> None:
        approved = {**cand, "size_scale": round(size_scale, 6), "risk_decision": "approved"}
        await self.bus.publish("signal.approved", approved)
        self.bot_state["risk_state"]["approvals"] += 1
        logger.debug(
            "RiskAgent approved %s %s @ scale=%.3f",
            cand["symbol"], cand["direction"], size_scale,
        )

    async def _reject(self, cand: dict, reason: str) -> None:
        rejected = {
            "candidate_id": cand.get("id"),
            "symbol": cand.get("symbol"),
            "reason": reason,
            "candidate": cand,
            "ts": time.time(),
        }
        await self.bus.publish("signal.rejected", rejected)
        self.bot_state["risk_state"]["rejections"] += 1
        logger.debug("RiskAgent rejected %s: %s", cand.get("symbol"), reason)

    # ── helpers ──────────────────────────────────────────

    def _compute_open_risk(self, cfg: dict) -> float:
        """Sum of (entry - stop) * qty across all open positions."""
        total = 0.0
        for pos in self._open_positions.values():
            entry = float(pos.get("entryPrice", 0.0))
            stop = float(pos.get("stopLoss", 0.0))
            qty = float(pos.get("quantity", 0.0))
            if entry <= 0 or stop <= 0 or qty <= 0:
                continue
            total += abs(entry - stop) * qty
        return total

    def _refresh_state(self) -> None:
        cfg = self._risk_cfg()
        starting_capital = float(self.bot_state.get("starting_capital", 100_000))
        heat = self._compute_open_risk(cfg)
        rs = self.bot_state["risk_state"]
        rs["portfolio_heat"] = round(heat, 4)
        rs["portfolio_heat_pct"] = round(
            (heat / starting_capital * 100) if starting_capital else 0.0, 4
        )
        rs["daily_realized_pnl"] = round(self._daily_realized, 4)
        rs["open_position_count"] = len(self._open_positions)

    def _risk_cfg(self) -> dict:
        cfg = dict(_DEFAULTS)
        override = self.bot_state.get("risk_config") or {}
        cfg.update({k: float(v) for k, v in override.items() if k in cfg})
        return cfg

    @staticmethod
    def _today_start() -> float:
        # Midnight UTC anchor; rolling over the day resets daily PnL.
        now = time.time()
        return now - (now % 86400)
