# RUN LUMARE — Deploy + Operate

> **Goal:** get the full Lumare stack (backend + frontend + autonomous bot) running on a developer machine in under 5 minutes, and understand how to operate it safely.

---

## Prerequisites

- **Python 3.10+** (3.11 recommended) — `python --version`
- **Node 18+** with npm — `node --version`
- **Windows / macOS / Linux** — Windows ships with `start-lumare.bat` for one-click launch
- **Optional**: API keys for live data sources. Without keys the stack runs on mock + yfinance data and is fully functional for paper trading.

---

## Quick Start — Windows (One-Click)

```cmd
git clone https://github.com/BlakeFrontier42/lumare-project.git
cd lumare-project
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
start-lumare.bat
```

`start-lumare.bat` will:

1. Kill any stale processes on ports 8000/3000
2. Clear the Next.js cache (OneDrive sometimes corrupts it)
3. Launch the backend on **port 8000** with `--reload`
4. Launch the frontend on **port 3000**
5. Wait for the frontend to come online and open it in your browser

---

## Quick Start — macOS / Linux

```bash
# Terminal 1 — backend
pip install -r backend/requirements.txt
python -m uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — frontend
cd frontend && npm install && npm run dev

# Then open http://localhost:3000
```

---

## Running the Bot

1. Open **http://localhost:3000/bot**
2. Pick an asset class pill (`crypto`, `equity`, `futures`, `options`)
3. Verify **Demo** mode is active (amber pill, top right of header) — this lowers the score threshold so trades fire on simulated data
4. Click **Start**

Within ~15 seconds you should see:

- Status pill turn **green: RUNNING**
- Cycle counter tick upward
- Signals appear in the **Signals** tab
- Positions appear in the **Positions** tab with live unrealized P&L
- Trades appear in the **Activity** feed

Click **Stop** at any time. Closing an individual position uses the X button on the position card — this calls `POST /api/bot/positions/{symbol}/close` which atomically exits at the last known price.

### Demo vs Live

| Mode | Min Score | Real Money | Env Var |
|------|-----------|------------|---------|
| **Demo** | 5 | No (paper) | none |
| **Paper** (default) | 30+ (profile threshold) | No (paper) | none |
| **Live** | 30+ (profile threshold) | **YES** | `LUMARE_ALLOW_LIVE=1` + Coinbase keys |

If the API receives `mode: "live"` and `LUMARE_ALLOW_LIVE` is not exactly `1`, it **silently coerces to `paper`** and logs a warning. This is a hard safety gate — there is no way to accidentally route real-money orders.

### Live Trading (Coinbase)

Live crypto trading goes through `backend/execution/coinbase_executor.py` — a drop-in replacement for the paper simulator that talks to Coinbase Advanced Trade with HMAC-signed requests. To arm:

```bash
export LUMARE_ALLOW_LIVE=1
export COINBASE_API_KEY=...
export COINBASE_API_SECRET=...
# Start the backend, then in the UI: select "crypto" asset class and Live mode.
```

What the executor does:
- Places **limit** orders only (no market orders — slippage protection)
- Signs every request with HMAC-SHA256 (timestamp + method + path + body)
- Pulls your real USD balance from `/api/v3/brokerage/accounts` on startup
- Polls `/orders/historical/fills` each cycle and updates local position state from real fills
- If credentials are missing or `LUMARE_ALLOW_LIVE` is unset, every order is REJECTED with a clear reason — **no HTTP request is made**

Equity / futures / options live execution still routes through the paper simulator (broker integration is per-asset-class — adding Alpaca/IBKR is a future wave).

---

## Architecture

```
┌──────────────────┐       ┌──────────────────┐
│  Next.js 14      │  /api │  FastAPI         │
│  (port 3000)     │ ────▶ │  (port 8000)     │
│  Bot page        │       │                  │
│  Macro page      │       │  ┌────────────┐  │
│  Backtest page   │       │  │  AutoBot   │──┼──▶ asyncio task
│  ...             │       │  │ (singleton)│  │   ┌─────────────┐
└──────────────────┘       │  └─────┬──────┘  │   │ LiveRunner  │
                           │        │         │   │             │
                           │        ▼         │   │ ┌─────────┐ │
                           │  /api/bot/*      │   │ │ Regime  │ │
                           │   start/stop     │   │ ├─────────┤ │
                           │   status         │   │ │ Scoring │ │
                           │   signals        │   │ ├─────────┤ │
                           │   activity       │   │ │ Risk    │ │
                           │   positions      │   │ ├─────────┤ │
                           │   trades         │   │ │Executor │ │
                           │   performance    │   │ └─────────┘ │
                           └──────────────────┘   └─────────────┘
                                                         │
                                                         ▼
                                                  ┌──────────┐
                                                  │ SQLite   │
                                                  │  trades  │
                                                  │  signals │
                                                  │  regime  │
                                                  └──────────┘
```

Per-asset profiles (`backend/core/asset_profiles.py`) route each symbol through tuned parameters (regime gating, R:R, stop multiplier, score threshold).

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LUMARE_ALLOW_LIVE` | unset | Required (`=1`) to permit real-money orders |
| `POLYGON_API_KEY` | unset | Equity 5m data. Falls back to yfinance when missing |
| `BLOWFIN_API_KEY` | unset | Crypto data + execution. Falls back to mock when missing |
| `BLOWFIN_API_SECRET` | unset | Paired with `BLOWFIN_API_KEY` |
| `BLOWFIN_API_PASSPHRASE` | unset | Paired with `BLOWFIN_API_KEY` |
| `FRED_API_KEY` | unset | Macro data feed. Falls back to mock when missing |
| `LUMARE_DIAG_THRESHOLD` | unset | Override `min_score_to_trade` from the CLI |

Place these in a `.env` at the repo root (gitignored).

### Bot Tuning

Per-asset profiles in `backend/core/asset_profiles.py`:

- **crypto_v1** — bypass regime, score≥65, rr=3.0 (PF 1.93 on BTC 1Y)
- **equity_v1** — strict regime, score≥62, wider stops, 0.8× size
- **futures_v1** — strict regime, symmetric (no long bias)
- **options_v1** — permissive regime, score≥70, 0.5× size

Global thresholds in `backend/config/settings.py` (`min_score_to_trade=70`).

---

## API Reference (bot endpoints)

| Method | Path | Body / Query | Returns |
|--------|------|--------------|---------|
| POST | `/api/bot/start` | `{symbols, strategies, interval, max_concurrent, min_score?, mode?}` | status + message |
| POST | `/api/bot/stop` | — | status + message |
| GET | `/api/bot/status` | — | `{running, uptime_seconds, symbols, signals_generated, trades_placed, current_regime, ...}` |
| GET | `/api/bot/signals` | `?limit=50` | `{signals: [...]}` |
| GET | `/api/bot/activity` | `?limit=100` | `{activity: [...]}` |
| GET | `/api/bot/performance` | — | `{total_pnl, win_rate, profit_factor, sharpe, ...}` |
| GET | `/api/bot/positions` | — | `{positions: [...]}` live executor positions |
| GET | `/api/bot/trades` | `?limit=100` | `{trades: [...]}` closed trades from storage |
| POST | `/api/bot/positions/{symbol}/close` | — | `{closed, exit_price, pnl}` |

OpenAPI docs at `http://localhost:8000/docs`.

---

## Troubleshooting

**"database disk image is malformed"** — Move or delete `data/lumare.db` (back it up if you care about history). Storage will recreate the schema on next boot.

**Frontend cannot reach /api** — Frontend rewrites `/api/*` to `http://localhost:8000/api/*`. Verify backend is on port 8000 and the Next.js dev server is running.

**Signals fire but no trades** — Score is below the threshold. In **Demo** mode the floor is 5; in **Paper/Live** the floor is `settings.trade.min_score_to_trade` (default 70). Mock data typically produces scores around 10 — that's why Demo exists.

**Bot won't start after crash** — `POST /api/bot/stop` to clear the task, then `POST /api/bot/start` again. The runner is a singleton; once cancelled it can be re-launched cleanly.

**Port already in use** — `start-lumare.bat` auto-kills processes on 8000 and 3000. On non-Windows, find and kill manually: `lsof -ti:8000 | xargs kill`.

---

## Production Deployment

For a real (non-dev) deployment:

1. Set `LUMARE_ALLOW_LIVE=1` only after extensive paper-mode validation
2. Set real API keys for the asset classes you trade
3. Replace SQLite with Postgres (storage layer is pluggable — see `backend/data/storage.py`)
4. Put the backend behind a reverse proxy (Caddy / Nginx) with TLS
5. Run uvicorn with `--workers 1` (the bot is a singleton — multiple workers will fight)
6. Set up a process manager (systemd / pm2) to auto-restart on crash
7. Monitor `data/lumare.db` for the WAL — vacuum periodically

The architecture is single-tenant by design; for multi-tenant, replace the global `autobot` singleton with a per-user instance keyed off an auth token.

---

## Status (May 2026 — escape velocity wave)

- ✅ Bot fully wired end-to-end (signals + positions + trades + close button all work)
- ✅ Asset class profiles for crypto/equity/futures/options
- ✅ Per-asset data routing (yfinance for equities, Blowfin or mock for crypto)
- ✅ Demo/Live mode safety gate
- ✅ Real-time portfolio updates via 3s polling
- ✅ Manual close + auto-managed stops/TPs

**Next:** real broker integration, walk-forward validation harness, alert system, multi-user auth.
