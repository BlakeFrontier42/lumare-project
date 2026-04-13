"""
Lumare Orchestrator — thin shim around the agent Spine.

After PR2 of the agent-spine refactor (see docs/agent-spine-spec.md):

  • DataAgent owns market data refresh.
  • SignalAgent owns signal generation off `bars.update`.
  • ExecutionAgent owns position open/close off `signal.candidate` + `price.tick`.

This file used to contain a 374-line trading loop. That logic now lives in
the agents under `backend/orchestrator/agents/`. The Orchestrator class is
kept as a thin lifecycle adapter so `backend/api/app.py` keeps importing
`Orchestrator` without changes.

The legacy `_compute_signal` symbol is re-exported from `strategies.py` so
any out-of-tree caller (tests, notebooks) keeps working.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.orchestrator.spine import Spine
from backend.orchestrator.strategies import compute_signal as _compute_signal  # noqa: F401

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Lumare orchestrator — owns the agent spine that runs the bot.

    Construction is cheap and side-effect-free. Calling `start(bot_state)`
    spins up the spine (Data + Signal + Execution agents). Everything is
    event-driven: there is no per-tick loop in this class anymore.
    """

    def __init__(self, engine: Any, settings: Any | None = None) -> None:
        self.engine = engine
        self.settings = settings
        self._spine = Spine(engine)
        self._running = False

    # ── lifecycle ────────────────────────────────────────

    async def start(self, bot_state: dict) -> None:
        if self._running:
            logger.warning("Orchestrator.start() called but already running")
            return
        await self._spine.start(bot_state)
        self._running = True
        logger.info("Orchestrator started (spine + agents up)")

    async def stop(self) -> None:
        await self._spine.stop()
        self._running = False
        logger.info("Orchestrator stopped (spine down)")

    @property
    def is_running(self) -> bool:
        return self._running and self._spine.is_running

    @property
    def price_cache(self) -> dict[str, float]:
        """Last-known prices keyed by symbol — sourced from DataAgent."""
        return self._spine.price_cache

    @property
    def health(self) -> dict[str, bool]:
        return self._spine.health
