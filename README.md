# Lumare — Capital Intelligence Platform

> **Bloomberg Terminal × Renaissance Technologies × Stripe — for capital allocation.**
> A vertically integrated trading, market intelligence, and autonomous-bot platform built from scratch in Python + Next.js.

**Built by [Blake Holley](https://www.linkedin.com/in/blake-holley-0b4753235)** — IT & Automation Engineer / Python Developer
📧 blake.frontierlabs@gmail.com  ·  🐙 [github.com/BlakeFrontier42](https://github.com/BlakeFrontier42)

---

## TL;DR for Hiring Managers

Lumare is a **full-stack autonomous trading platform** I designed and built solo. It demonstrates:

- **System design at scale** — 30+ Python modules across data ingestion, signal generation, execution, risk, and orchestration; multi-asset (crypto / equity / futures / options); Next.js + React frontend with live WebSocket telemetry.
- **Production-grade safety engineering** — triple-locked live-trading gate, per-symbol kill switches, watchdog process, atomic position close, deliberate silent coercion of unsafe API calls to paper mode.
- **Real automation** — autonomous bot loops through ingest → score → size → execute → reconcile every cycle. Live frontend shows running state, positions, signals, and an activity feed.
- **Honest, measurable results** — recent walk-forward tuning achieved **Profit Factor 1.5+** across multiple regimes (see `docs/tuning_report.md`).
- **Operational discipline** — Windows one-click launch, Postgres migration path, full deployment doc, kill-switch docs, methodology docs for every backtest claim.

If you're hiring for **NOC, IT Support, Junior Systems Administrator, Technical Support Engineer, or Automation Engineer** roles, this repo is evidence I can: own a system end-to-end, debug across the stack, operate live services safely, and write code that actually runs in production conditions.

---

## What's Actually Running

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js Frontend (port 3000)                                   │
│  ├─ /bot — live trading control surface                         │
│  ├─ Signals · Positions · Activity · Risk · Kill switches       │
│  └─ Real-time updates via WebSocket                             │
└─────────────────────────────────────────────────────────────────┘
                            ▲ WS + REST
                            │
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8000)                                    │
│  ├─ api/        — HTTP + WebSocket surface, auth, schemas       │
│  ├─ core/       — 9+ engines: scoring, trend, momentum, flow,   │
│  │                regime, structure, risk, portfolio, equity    │
│  │                governor, options pricer + recommender,       │
│  │                macro, explainability                         │
│  ├─ data/       — ingestion: crypto, equities, options flow,    │
│  │                insider, congressional, macro, float          │
│  ├─ execution/  — adapters: Alpaca, Blowfin, Coinbase,          │
│  │                Polymarket, paper simulator                   │
│  ├─ live/       — runner loop + watchdog                        │
│  ├─ orchestrator/ — agent spine, bus, router, autobot           │
│  └─ backtest/   — replay engine + performance metrics           │
└─────────────────────────────────────────────────────────────────┘
                            ▲
                            │
┌─────────────────────────────────────────────────────────────────┐
│  Storage                                                        │
│  ├─ SQLite (local dev) — lumare.db, insider_cache.db            │
│  └─ Postgres (production path — see docs/POSTGRES_MIGRATION.md) │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5-Minute Quickstart

**Windows (one-click):**
```cmd
git clone https://github.com/BlakeFrontier42/lumare-project.git
cd lumare-project
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
start-lumare.bat
```

**macOS / Linux:**
```bash
# Terminal 1
pip install -r backend/requirements.txt
python -m uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2
cd frontend && npm install && npm run dev
```

Open <http://localhost:3000/bot> → pick an asset class → press **Start**. Within ~15s you'll see the bot cycling, signals appearing, positions opening, P&L updating live.

Full operating manual: [**RUN.md**](RUN.md).

---

## Safety Engineering Highlights

This is real-money software. The safety architecture is deliberate:

| Layer | Mechanism |
|---|---|
| **Live trading gate** | Requires `LUMARE_ALLOW_LIVE=1` env + valid exchange keys + `mode: "live"` in request. Missing any one → silently coerced to paper. |
| **Per-symbol kill switches** | Operator can disable trading on any symbol independently; UI surfaces state with one-click re-enable. |
| **Watchdog** | Independent process monitors the runner; restarts on crash, alerts on stall. |
| **Atomic close** | `POST /api/bot/positions/{symbol}/close` exits at last known price as a single transaction. |
| **Score thresholds** | Production profile requires score ≥30 to enter; demo mode lowers to 5 for testing. |
| **Equity governor** | Hard caps on per-trade size, daily loss, drawdown. |

---

## Demonstrated Skills

| Domain | Evidence in this repo |
|---|---|
| **Python** | 30+ modules, async I/O, FastAPI, SQLAlchemy, pandas, numpy |
| **System design** | Layered architecture, dependency injection, agent orchestration via bus |
| **Linux / CLI / scripting** | Bash + cmd launchers, watchdog process management |
| **APIs & integrations** | 5 exchange/broker adapters, multiple market data providers |
| **Databases** | SQLite locally, documented Postgres migration path, schema versioning |
| **Frontend** | Next.js 14, TypeScript, React hooks, custom store, WebSocket clients |
| **DevOps / operations** | One-click launch, deployment summary doc, runbook, kill-switch SOPs |
| **Testing & validation** | Walk-forward backtest framework, profit factor metrics, score distribution analysis |
| **Documentation** | 27 docs covering spec, architecture, algorithm, risk policy, deployment |
| **AI tooling / agent design** | Orchestrator spine, autobot loop, multi-agent routing |

---

## Repo Map

| Path | Contents |
|---|---|
| `backend/` | Python — FastAPI + core engines + data + execution + live runner |
| `frontend/` | Next.js + TypeScript trading control surface |
| `docs/` | Product spec, architecture, algorithm, risk policy, deployment, methodology |
| `scripts/` | Tuning, backtesting, data loading utilities |
| `config/` | Settings templates, environment variables |
| `prompts/` | System prompts for the agent orchestrator |
| `RUN.md` | Full operator manual |
| `start-lumare.bat` | Windows one-click launch |

---

## Status & Roadmap

**Working today:** Backend + frontend boot to a usable trading surface in <5 min. Bot runs multi-asset, generates signals, opens/closes positions in paper mode. Kill switches functional. Backtest harness produces walk-forward metrics.

**Not yet:** Live retail user onboarding, Stripe billing, Supabase auth, marketplace tier — these are specced (`docs/REVENUE_MODEL.md`, `docs/ROADMAP.md`) but not built. This is a portfolio-grade single-operator deployment, not a multi-tenant SaaS.

**Phase 5+ in plan:** Postgres migration, multi-user auth, paper trading marketplace, signal copying.

---

## Contact

I'm currently looking for full-time IT & automation roles — NOC, IT Support, Junior Systems Administrator, Technical Support Engineer, or Automation Engineer. Open to **Denver / Boulder / Colorado Springs CO** or **Remote**.

- **Email**: blake.frontierlabs@gmail.com
- **LinkedIn**: <https://www.linkedin.com/in/blake-holley-0b4753235>
- **GitHub**: <https://github.com/BlakeFrontier42>

If anything in this repo is interesting to you, I'd be glad to walk you through the architecture, the safety decisions, or the live trading loop on a call.
