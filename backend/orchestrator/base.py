"""
Base class for spine agents.

Every agent owns one asyncio task, has a stable name for logging/health, and
follows the same start/stop contract. The Spine never knows the internals of
an agent — only `start`, `stop`, `name`, and `is_running`.

Crash policy lives here: if `_run` raises, we log it and the agent's
`is_running` flips to False. The Spine's supervisor (see spine.py) is
responsible for deciding whether to restart it.
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from backend.orchestrator.bus import Bus

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    name: str = "agent"

    def __init__(self, bus: Bus, bot_state: dict) -> None:
        self.bus = bus
        self.bot_state = bot_state
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            logger.warning("Agent %s start() called while already running", self.name)
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._wrapped_run(), name=f"agent:{self.name}")
        logger.info("Agent %s started", self.name)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Agent %s did not stop in 5s, cancelling", self.name)
                self._task.cancel()
            except Exception:
                # Already crashed; nothing to do.
                pass
            self._task = None
        logger.info("Agent %s stopped", self.name)

    async def _wrapped_run(self) -> None:
        try:
            await self._run()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Agent %s crashed", self.name)
            raise

    async def _sleep(self, seconds: float) -> None:
        """Sleep that aborts immediately when stop is requested."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    @abstractmethod
    async def _run(self) -> None:
        """Subclass main loop. Should poll `self._stop.is_set()` regularly."""
        ...
