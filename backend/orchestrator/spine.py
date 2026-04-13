"""
Spine — owns the lifecycle of all spine agents.

The Spine is intentionally tiny: construct a Bus, construct each agent, start
them, supervise them, stop them. It does not know what any agent does.

Supervisor policy:
  • If an agent's task ends with an exception, log it and restart that one
    agent after a short backoff. The other agents keep running.
  • If `stop()` is called, every agent is stopped in reverse construction
    order so producers shut down before consumers.
  • The supervisor task itself only exits when `stop()` is called.

PR4 scope: Data + Signal + Risk + Execution + Macro are all wired in.
MacroAgent runs on a 15-minute cadence, emits `macro.update` for SignalAgent
to weight strategies, and `position.flatten` for ExecutionAgent to
proactively de-risk on regime flips (gated by `bot_state["macro_can_flatten"]`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.orchestrator.agents.data import DataAgent
from backend.orchestrator.agents.execution import ExecutionAgent
from backend.orchestrator.agents.macro import MacroAgent
from backend.orchestrator.agents.replay import ReplayDataAgent
from backend.orchestrator.agents.risk import RiskAgent
from backend.orchestrator.agents.signal import SignalAgent
from backend.orchestrator.base import BaseAgent
from backend.orchestrator.bus import Bus

logger = logging.getLogger(__name__)

_RESTART_BACKOFF_SECONDS = 5


class Spine:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.bus = Bus()
        self._agents: list[BaseAgent] = []
        self._supervisor: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._data_agent: DataAgent | None = None

    # ── lifecycle ────────────────────────────────────────

    async def start(self, bot_state: dict) -> None:
        if self._supervisor is not None and not self._supervisor.done():
            logger.warning("Spine.start() called but supervisor already running")
            return

        self._stop.clear()
        self.bus = Bus()

        # Construct subscribers BEFORE the producer so their bus.subscribe()
        # calls register their queues before DataAgent ever publishes.
        # If `bot_state["historical_bars"]` is set, swap DataAgent for the
        # ReplayDataAgent so the same spine code path runs against historical
        # tape (Phase 4 backtesting / fine-tuning entry point).
        if bot_state.get("historical_bars"):
            self._data_agent = ReplayDataAgent(self.bus, bot_state)  # type: ignore[assignment]
        else:
            self._data_agent = DataAgent(self.bus, bot_state, self.engine)
        signal_agent = SignalAgent(self.bus, bot_state)
        risk_agent = RiskAgent(self.bus, bot_state)
        execution_agent = ExecutionAgent(self.bus, bot_state)
        macro_agent = MacroAgent(self.bus, bot_state, self.engine)

        # Order in this list governs both startup and reverse-shutdown:
        # consumers start first, producer last; producer stops first, consumers
        # last (reverse order in `stop()`). MacroAgent is a producer too but
        # its cadence is so slow it doesn't matter where it sits.
        self._agents = [
            signal_agent,
            risk_agent,
            execution_agent,
            macro_agent,
            self._data_agent,
        ]

        for a in self._agents:
            await a.start()

        self._supervisor = asyncio.create_task(self._supervise(bot_state), name="spine:supervisor")
        logger.info("Spine started with %d agents", len(self._agents))

    async def stop(self) -> None:
        self._stop.set()
        # Stop agents in reverse so producers go before consumers
        for a in reversed(self._agents):
            try:
                await a.stop()
            except Exception:
                logger.exception("Error stopping agent %s", a.name)
        if self._supervisor is not None:
            try:
                await asyncio.wait_for(self._supervisor, timeout=5)
            except asyncio.TimeoutError:
                self._supervisor.cancel()
            except Exception:
                pass
            self._supervisor = None
        self._agents = []
        logger.info("Spine stopped")

    @property
    def is_running(self) -> bool:
        return self._supervisor is not None and not self._supervisor.done()

    @property
    def health(self) -> dict[str, bool]:
        return {a.name: a.is_running for a in self._agents}

    @property
    def price_cache(self) -> dict[str, float]:
        """Backwards-compat shim — exposes DataAgent's price cache."""
        return self._data_agent.price_cache if self._data_agent else {}

    @property
    def bars_cache(self):
        return self._data_agent.bars_cache if self._data_agent else {}

    # ── supervisor ───────────────────────────────────────

    async def _supervise(self, bot_state: dict) -> None:
        """
        Watch every agent. If one dies while bot_state["running"] is still
        True, restart it after a short backoff.
        """
        try:
            while not self._stop.is_set() and bot_state.get("running"):
                for a in self._agents:
                    if not a.is_running and not self._stop.is_set():
                        logger.warning(
                            "Spine: agent %s not running, restarting in %ds",
                            a.name,
                            _RESTART_BACKOFF_SECONDS,
                        )
                        try:
                            await asyncio.wait_for(
                                self._stop.wait(),
                                timeout=_RESTART_BACKOFF_SECONDS,
                            )
                            return  # stop requested during backoff
                        except asyncio.TimeoutError:
                            pass
                        try:
                            await a.start()
                        except Exception:
                            logger.exception("Failed to restart agent %s", a.name)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Spine supervisor crashed")
