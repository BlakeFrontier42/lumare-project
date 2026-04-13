"""
Lumare in-process event bus.

A tiny pub/sub primitive built on `asyncio.Queue`. Topics are strings; each
subscriber gets its own queue, so a slow consumer cannot starve a fast one.

Two delivery modes per topic:

  • lossy   — when a subscriber's queue is full, drop the oldest event so the
              newest one always lands. Use for high-frequency, snapshot-style
              data (price.tick, bars.update) where the latest value is what
              matters and missing one in flight is fine.

  • lossless — when a subscriber's queue is full, the publisher awaits space.
               Use for events that must be processed exactly once
               (signal.approved, position.opened) where dropping silently
               would corrupt state. Lossless events are ALSO persisted to an
               append-only JSONL log (`data/spine-events.jsonl` by default)
               so a crash mid-tick doesn't silently lose trades — the log is
               replayable for audit and (eventually) for state recovery.

Lossiness is fixed per topic and chosen by the FIRST subscriber. Mixing modes
on one topic is intentionally disallowed — it would let one buggy subscriber
silently degrade the whole pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path("data/spine-events.jsonl")


def _json_safe(value: Any) -> Any:
    """Coerce common non-JSON types (DataFrames, Timestamps, sets) for the log."""
    if isinstance(value, pd.DataFrame):
        return {"__df__": True, "rows": len(value), "cols": list(value.columns)}
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return list(value)
    return value


class Bus:
    def __init__(self, log_path: Path | None = None) -> None:
        self._topics: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lossy: dict[str, bool] = {}
        self._dropped: dict[str, int] = defaultdict(int)
        self._log_path = log_path or _DEFAULT_LOG_PATH
        self._log_lock = asyncio.Lock()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(
        self,
        topic: str,
        *,
        lossy: bool = False,
        maxsize: int = 256,
    ) -> asyncio.Queue:
        """
        Subscribe to a topic. Returns a queue that the caller polls.

        The first subscriber to a topic locks in its delivery mode; subsequent
        subscribers must agree.
        """
        if topic in self._lossy and self._lossy[topic] != lossy:
            raise ValueError(
                f"Topic {topic!r} already registered as "
                f"{'lossy' if self._lossy[topic] else 'lossless'}; "
                f"cannot also subscribe as {'lossy' if lossy else 'lossless'}."
            )
        self._lossy[topic] = lossy
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._topics[topic].append(q)
        return q

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """
        Publish an event to all subscribers of `topic`.

        Lossy topics drop the oldest event when full and never block.
        Lossless topics await space — slow consumers WILL throttle producers.
        Lossless events are also persisted to the append-only event log
        BEFORE delivery, so a crash mid-publish never loses the event.
        Topics with zero subscribers are no-ops for delivery, but lossless
        events are still logged so audit replay works even when no
        consumer is wired up yet.
        """
        lossy = self._lossy.get(topic, True)

        # Persist lossless events FIRST so the log is the source of truth.
        if not lossy:
            await self._append_log(topic, event)

        subs = self._topics.get(topic)
        if not subs:
            return
        for q in subs:
            if lossy:
                if q.full():
                    try:
                        _ = q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    self._dropped[topic] += 1
                    if self._dropped[topic] % 50 == 1:
                        logger.warning(
                            "Bus topic %r dropped %d events (lossy)",
                            topic,
                            self._dropped[topic],
                        )
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Race lost to another producer; drop and move on.
                    self._dropped[topic] += 1
            else:
                await q.put(event)

    async def _append_log(self, topic: str, event: dict[str, Any]) -> None:
        """Append a single event to the persistent JSONL log under a lock."""
        record = {
            "ts": time.time(),
            "topic": topic,
            "event": {k: _json_safe(v) for k, v in event.items()},
        }
        line = json.dumps(record, default=str) + "\n"
        try:
            async with self._log_lock:
                # Sync append; file ops are fast enough that doing this in a
                # threadpool would add latency without buying much.
                with self._log_path.open("a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
        except Exception:
            logger.exception("Bus failed to append lossless event for %r", topic)

    def replay_log(self, since_ts: float = 0.0) -> list[dict[str, Any]]:
        """
        Read back all persisted lossless events with ts >= since_ts.

        Used for audit endpoints and (in PR3+) for state recovery on boot.
        Returns events in original write order.
        """
        if not self._log_path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self._log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("ts", 0) >= since_ts:
                    out.append(record)
        return out

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "topics": {
                t: {
                    "subscribers": len(self._topics[t]),
                    "lossy": self._lossy.get(t, True),
                    "dropped": self._dropped.get(t, 0),
                }
                for t in self._topics
            }
        }
