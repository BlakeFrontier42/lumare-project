# Lumare Agent Spine — Phase 3 Spec (Draft for Review)

> **Status:** Draft, not implemented. Read top-to-bottom, push back on
> anything you disagree with, then I'll build it.
>
> **Author:** Claude (drafted 2026-04-06)
> **Audience:** Blake (review + sign-off)
> **Goal:** Replace the single-loop orchestrator (`backend/orchestrator/router.py`)
> with a coordinated set of specialist agents that share state through one
> bus, so that signal generation, risk, execution, and macro context can
> evolve independently without one piece blocking the others.

---

## 1. Why a spine, not a bigger loop

Today's `Orchestrator._run()` is a single asyncio task that does five jobs in
sequence on every tick: refresh prices, run exits, generate signals, open
positions, log. That works for ~20 symbols and one strategy family. It will
not survive what we want next:

1. **Macro Compass as a strategy** — needs its own cadence (15-min news +
   AI synthesis) that is much slower than the 60-second tick.
2. **Historical fine-tuning** — needs to backtest while the live loop runs,
   without contending for the same universe state.
3. **Risk overlay** — should be able to *veto* a trade after the signal
   agent says "buy" but before the execution agent fires, with its own
   logic on portfolio heat / correlation / sector caps.
4. **Multiple execution venues** — equities, crypto, options each have
   different latency, fill semantics, and rate limits. One blocking call
   to a slow broker should not stall the whole loop.

The spine pattern: each concern is an agent (an `asyncio.Task`) that
subscribes to events on a shared in-process bus, does its job, and emits
its own events. The spine itself owns lifecycle (start/stop/health) and
the shared `bot_state` snapshot. Nothing else.

---

## 2. The five agents

```
                   ┌───────────────────────────────┐
                   │         Spine (lifecycle)     │
                   └───────────────┬───────────────┘
                                   │ start/stop/health
       ┌───────────┬───────────────┼───────────────┬───────────┐
       │           │               │               │           │
   ┌───▼───┐  ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐ ┌───▼───┐
   │ Data  │  │ Signal  │    │   Risk    │   │ Execution │ │ Macro │
   │ Agent │  │ Agent   │    │   Agent   │   │   Agent   │ │ Agent │
   └───┬───┘  └────┬────┘    └─────┬─────┘   └─────┬─────┘ └───┬───┘
       │           │               │               │           │
       └───────────┴───────┬───────┴───────────────┴───────────┘
                           │
                       ┌───▼───┐
                       │  Bus  │  (asyncio.Queue per topic)
                       └───────┘
```

### 2.1 Data Agent
- **Owns:** equities_feed + crypto_feed clients, OHLCV cache, last-price cache.
- **Cadence:** ticks once per `interval_seconds` (default 60s for equities,
  10s for crypto when crypto is in the universe).
- **Emits:**
  - `price.tick` — `{symbol, price, ts}` for each refreshed symbol.
  - `bars.update` — `{symbol, timeframe, df}` when fresh OHLCV is fetched.
- **Listens:** none. It's a pure producer.
- **Failure mode:** per-symbol failures get logged and skipped, identical to
  today. The agent itself is restarted by the spine if it crashes.

### 2.2 Signal Agent
- **Owns:** the strategy ensemble (`_compute_signal` and successors), one
  per strategy family.
- **Cadence:** triggered by `bars.update`. Stateless between bars except
  for a small "last-signal-per-symbol" dedupe map (so one bar can't fire
  the same signal twice).
- **Emits:**
  - `signal.candidate` — `{id, symbol, direction, strategy, score, price, reason, ts}`.
- **Listens:**
  - `bars.update` — runs strategies on the new bars.
  - `macro.update` — adjusts strategy weights when the regime flips
    (e.g., trend-following gets a confidence haircut in risk-off regimes).

### 2.3 Risk Agent
- **Owns:** portfolio heat math, sector caps, correlation matrix, max
  concurrent positions, daily loss circuit breaker.
- **Cadence:** event-driven. Reacts to every `signal.candidate` with one
  of two outcomes.
- **Emits:**
  - `signal.approved` — pass-through with optional size adjustment.
  - `signal.rejected` — `{candidate_id, reason}`. Logged but not traded.
- **Listens:**
  - `signal.candidate`
  - `position.opened` / `position.closed` (to keep its own portfolio model
    in sync without re-querying state).

This is the **single point** where a trade can be vetoed. Today this
logic is inlined in `_open_position`; pulling it out makes it testable
in isolation and lets us layer on smarter rules (Kelly sizing, vol
targeting) without touching the rest of the loop.

### 2.4 Execution Agent
- **Owns:** the paper-trading book + (eventually) live broker adapters.
- **Cadence:** event-driven on `signal.approved`; also runs an SL/TP
  sweep on every `price.tick` for open positions.
- **Emits:**
  - `position.opened`
  - `position.closed` — `{position, exit_reason, pnl}`
  - `execution.failed` — when a broker rejects or times out (paper mode
    will never emit this; live mode will).
- **Listens:**
  - `signal.approved`
  - `price.tick`

### 2.5 Macro Agent
- **Owns:** the existing Macro Compass pipeline (Perplexity calls + the
  composite scoring). This is the agent that replaces the manual
  refresh on `/macro`.
- **Cadence:** every 15 minutes, plus on-demand when the API is hit.
- **Emits:**
  - `macro.update` — `{regime, bias, vix, breadth, ts}`. Both the
    Signal Agent and the frontend `/macro` page consume this.
- **Listens:** none.

---

## 3. The Bus

In-process, no external broker. Every topic is an `asyncio.Queue` with a
bounded size (so a slow consumer can't OOM us).

```python
class Bus:
    def __init__(self) -> None:
        self._topics: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, topic: str, maxsize: int = 256) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._topics[topic].append(q)
        return q

    async def publish(self, topic: str, event: dict) -> None:
        for q in self._topics[topic]:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, push newest. Logged but never blocks producers.
                _ = q.get_nowait()
                q.put_nowait(event)
                logger.warning("Bus topic %s dropped oldest event", topic)
```

Two design decisions to confirm:

- **Drop-on-full vs. block-on-full.** I'm proposing drop-oldest because a
  blocked Data Agent is worse than a dropped tick (next tick is 60s away
  anyway, and the new tick supersedes the old). Counter-argument: for
  `signal.approved` events we *cannot* drop — the trade would silently
  vanish. **Resolution:** topics are either "lossy" or "lossless", set at
  subscribe time. Price/bars are lossy; signal/position are lossless and
  block their producers.

- **No persistence.** Events live only in memory. If the spine crashes
  mid-event, that event is lost. The shared `bot_state` dict is the only
  persisted view of the world (and we already accept its losses today).
  **Push back if you want event sourcing** — that's a real call to make.

---

## 4. Shared state — what stays in `bot_state`, what moves out

Today `bot_state` is a giant dict. After the spine refactor, it stays as
the **read model** for the API (`/api/bot/*` endpoints), but the agents
each own their own piece of write authority:

| Field                | Owner                |
|----------------------|----------------------|
| `running`            | Spine                |
| `symbols`            | Spine (config)       |
| `strategies`         | Spine (config)       |
| `interval_seconds`   | Spine (config)       |
| `positions`          | Execution Agent      |
| `closed_trades`      | Execution Agent      |
| `signals`            | Signal Agent         |
| `signals_generated`  | Signal Agent         |
| `trades_placed`      | Execution Agent      |
| `last_macro_update`  | Macro Agent          |
| `risk_state`         | Risk Agent (NEW)     |

The frontend keeps reading the same `/api/bot/state` payload. Nothing in
the UI changes on day one.

---

## 5. Lifecycle

```python
class Spine:
    async def start(self, bot_state: dict) -> None:
        self.bus = Bus()
        self.agents = [
            DataAgent(self.bus, bot_state, self.engine),
            SignalAgent(self.bus, bot_state),
            RiskAgent(self.bus, bot_state),
            ExecutionAgent(self.bus, bot_state),
            MacroAgent(self.bus, bot_state),
        ]
        for a in self.agents:
            await a.start()

    async def stop(self) -> None:
        # Stop in reverse order so producers shut down before consumers.
        for a in reversed(self.agents):
            await a.stop()

    @property
    def health(self) -> dict:
        return {a.name: a.is_running for a in self.agents}
```

Every agent has the same shape:

```python
class Agent(Protocol):
    name: str
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    @property
    def is_running(self) -> bool: ...
```

Crash policy: if any agent's task dies with an unhandled exception, the
spine logs it, marks `is_running = False`, and **restarts that one
agent** after a 5-second backoff. The other four keep running. The
spine itself never dies — only `bot.stop()` from the API can kill it.

---

## 6. What the file layout looks like

```
backend/orchestrator/
  __init__.py
  spine.py            # Spine + Bus
  base.py             # Agent protocol + BaseAgent helper
  agents/
    __init__.py
    data.py           # DataAgent
    signal.py         # SignalAgent + strategy registry
    risk.py           # RiskAgent
    execution.py      # ExecutionAgent
    macro.py          # MacroAgent
  router.py           # Thin shim that delegates to Spine — kept so
                      # backend/api/app.py imports don't break on day one.
```

`router.py`'s `Orchestrator` class becomes a 30-line adapter:
construct a `Spine`, forward `start`/`stop`/`is_running`, expose
`price_cache` for backwards compat. The 374-line monolith goes away.

---

## 7. Migration path (no big-bang)

I'd build this in four PRs, each independently mergeable:

1. **PR1: Bus + Spine + DataAgent.** Spine wraps the existing `_tick`
   logic but routes all price work through `DataAgent`. Signal/risk/exec
   stay inline. Verifies the bus shape works without changing behavior.

2. **PR2: Extract SignalAgent and ExecutionAgent.** Now `_tick` is
   gone; signal generation and exit-checking are event-driven.
   Behavior should be observably identical — same trades, same logs.

3. **PR3: Add RiskAgent.** Move sizing + max-concurrent + symbol-dedup
   logic out of `_open_position`. Adds the seam for future risk rules
   without yet adding any new ones.

4. **PR4: Add MacroAgent.** Pulls the Macro Compass pipeline into the
   spine, fires `macro.update` events, and SignalAgent starts
   weighting strategies by regime.

Each PR is shippable. If you hate PR3, we stop and rethink without
having broken anything.

---

## 8. Decisions (locked 2026-04-07)

1. **Lossless persistence: YES.** All lossless topics are written to an
   append-only JSONL log at `data/spine-events.jsonl` BEFORE delivery to
   subscribers. The log is the source of truth for trades, positions,
   approvals, and rejections. Bus exposes `replay_log(since_ts=...)` for
   audit endpoints and (PR3+) state recovery on boot. Implemented in PR1.

2. **Risk Agent: resize allowed.** RiskAgent emits a numeric scale factor
   in `[0.0, 1.0]` along with approve/reject. A factor of 0 is a hard
   reject; 0.5 means approve at half the requested size. This lets us
   layer Kelly sizing, vol targeting, and portfolio-heat scaling without
   another redesign. Implemented in PR3.

3. **Macro Agent: full mobility.** MacroAgent can both (a) emit
   `macro.update` events that adjust SignalAgent's per-strategy weights
   and (b) emit `position.flatten` events that ExecutionAgent honors,
   closing matching positions immediately. Gated behind
   `bot_state["macro_can_flatten"]` (default True) so you can turn off
   proactive closes in one move if it ever overreacts. Implemented in PR4.

4. **Backtest replay constraint: enforced.** SignalAgent's only data
   source is `bars.update` events. There is no direct feed access from
   inside the agent. A backtest is just a `ReplayDataAgent` that
   publishes historical bars at configurable speed instead of polling
   live feeds. Same SignalAgent code, two data sources. Implemented in PR2.

5. **Per-asset cadence: YES, in PR1.** DataAgent runs two parallel inner
   loops:
     - equities at `bot_state["interval_seconds_equities"]` (default 60s)
     - crypto   at `bot_state["interval_seconds_crypto"]`   (default 10s)
   Both fall back to `interval_seconds` if the new keys aren't set, so
   existing configs keep working. Implemented in PR1.

---

## 9. Non-goals (explicit)

To keep this from sprawling:

- **No multi-process / no Celery / no Redis.** Single asyncio process.
  When we outgrow that we'll know.
- **No new strategies.** Phase 4 adds strategies. Phase 3 just rewires
  what exists.
- **No frontend changes.** `/bot` page keeps reading `/api/bot/state`
  and gets the same payload it gets today.
- **No live broker.** Paper-trading only. Live execution is its own
  phase with its own auth, slippage, and reconciliation problems.

---

## 10. Sign-off

✅ Signed off 2026-04-07. PR1 shipped (Bus + Spine + DataAgent +
lossless persistence + per-asset cadence). PR2 is next.
