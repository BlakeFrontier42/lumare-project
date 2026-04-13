# Lumare Project — Cocreator Handoff Prompt

> Copy-paste this entire document into a new Claude Max conversation to get your cocreator fully up to speed.

---

## Prompt for Claude Max

You are picking up development on **Lumare**, an institutional-grade autonomous multi-asset trading platform. The repo is at `https://github.com/BlakeFrontier42/lumare-project` — clone it and familiarize yourself with the full codebase before making changes.

---

### 1. PROJECT OVERVIEW

Lumare is a full-stack autonomous trading bot + portfolio dashboard:

- **Backend**: Python (FastAPI), SQLite (`data/lumare.db`), modular engine architecture
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS, Zustand state management
- **Architecture**: Regime classification → Signal scoring → Risk management → Execution

The platform trades **crypto, equities, futures, and options** via a unified per-asset-class profile system. Each asset class gets independently tuned parameters (regime gating, entry thresholds, R:R ratios, stop distances) so they can't regress each other.

---

### 2. CURRENT STATUS (Phase 4.6 — Complete)

**What's built and working:**

- **Frontend**: 6 of 9 planned pages are live:
  - `/` Dashboard — portfolio overview, equity curve, allocation breakdown
  - `/bot` — Autonomous trading bot command center with live positions, P&L tracking, trade grading (A-F by R-multiple), config panel, asset-class mode switcher
  - `/macro` — Market regime dashboard (RISK_ON / RISK_OFF / TRANSITIONAL / CHAOTIC)
  - `/backtest` — Historical strategy backtesting interface
  - `/assets` — Asset explorer with search
  - `/research` — Perplexity-powered research tab
  
- **Backend engines** (all functional):
  - `RegimeClassifier` — ATR/ADX/volume/volatility percentile → 4 regime states, with `confirmation_bars` parameter to prevent whipsaw
  - `ScoringEngine` — Multi-timeframe (5M/15M/1H/4H/1D) composite scoring, 0-100 scale
  - `RiskEngine` — Portfolio heat checks (max 6%), position sizing, correlation limits
  - `ReplayEngine` — Bar-by-bar backtester on 5M candles with full trade simulation (fees, slippage, trailing stops)
  - `EquityGovernor` — Drawdown circuit breaker
  
- **Multi-asset profile system** (`backend/core/asset_profiles.py`):
  - `AssetProfile` dataclass with: regime_mode, score_threshold, short_threshold_bonus, risk_per_trade_mult, stop_atr_mult, rr_ratio, trailing_mult, allow_shorts
  - 4 registered profiles:
    - **crypto_v1**: regime_mode=bypass, threshold=65, rr=3.0, stop=2.0 ATR (PF 1.93 on BTC 1Y)
    - **equity_v1**: regime_mode=strict, threshold=62, rr=2.8, stop=2.2 ATR, risk_mult=0.8
    - **futures_v1**: regime_mode=strict, threshold=65, no short bonus
    - **options_v1**: regime_mode=permissive, threshold=70, risk_mult=0.5
  - `classify_symbol()` auto-detects asset class from symbol (USDT/USD→crypto, ES/NQ/CL→futures, default→equity)
  
- **Orchestrator / Agent Spine** (`backend/orchestrator/`):
  - Event bus, agent base class, router
  - Specialized agents: data, signal, risk, execution, macro, replay
  - See `docs/agent-spine-spec.md` for architecture details

- **Backtest results** (see `docs/phase4-backtest-report.md`):
  - BTC 1Y: PF 1.93, Win Rate 57.9%, Sharpe 2.6 (after Phase 4.6 grid tuning)
  - ETH 1Y: PF 2.30, Win Rate 63.6%
  - Equities: MSFT and GOOGL generating trades with strict regime gating; SPY/AAPL/TSLA need further threshold tuning

---

### 3. WHAT WAS JUST COMPLETED (This Session)

1. **Diagnosed and fixed BTC PF regression** (1.52 → 0.91 → 1.93):
   - Root cause: Phase 4 parameters were calibrated against a broken regime engine that was always returning RISK_ON
   - After fixing the regime engine (adding `confirmation_bars`), the honest regime gating killed too many valid crypto signals
   - Solution: Created `regime_mode="bypass"` for crypto (preserves Phase 4 calibration), then grid-searched R:R ratio + trailing stop → winner was rr=3.0 (PF 1.93, +27% over baseline)

2. **Built the multi-asset profile system** so one codebase handles crypto/equities/futures/options with isolated tuning

3. **Added frontend asset-class mode switcher** — 4 pills (Crypto/Equity/Futures/Options) on the bot page that swap the symbol universe

4. **Loaded equities data**: 28,782 rows of 5M candles for AAPL, MSFT, NVDA, GOOGL, META, AMZN, TSLA, SPY, QQQ via yfinance

5. **Ran 11-symbol multi-asset sweep** to validate profiles across both crypto and equity symbols

---

### 4. WHAT NEEDS TO BE DONE NEXT (Phase 5 Priorities)

**HIGH PRIORITY:**

1. **Equity profile tuning** — Run grid search on equity symbols (MSFT, GOOGL, NVDA, AAPL, TSLA, SPY, QQQ) to optimize EQUITY_PROFILE parameters. Currently only MSFT and GOOGL are generating trades; SPY/AAPL/TSLA produce zero trades with current thresholds. Try:
   - Lower score_threshold (60, 58)
   - Wider stops (2.5, 3.0 ATR)
   - Permissive regime mode for some equities
   - Use `scripts/tune_crypto_profile.py` as a template for equity tuning

2. **Futures & options profile tuning** — Same grid search approach for ES, NQ, CL futures and options profiles. Need to source futures data (Polygon API key needed — currently not configured, env var `POLYGON_API_KEY`).

3. **Walk-forward validation** — Current backtests use a single window. Implement walk-forward (train on 6 months, test on next 2 months, roll forward) to prove the profiles aren't overfit.

4. **Live paper trading integration** — Connect ReplayEngine profile system to the live runner (`backend/live/runner.py`) so paper trading uses the same per-asset profiles. The runner already has the RegimeClassifier fix applied.

**MEDIUM PRIORITY:**

5. **Remaining 3 frontend pages**:
   - `/settings` — User preferences, API key management, notification config
   - `/journal` — Trade journal with tagging, notes, screenshots
   - `/alerts` — Custom alert rules (price, regime change, drawdown)

6. **Real-time data pipeline** — Replace polling with WebSocket feeds for live price updates. Consider ccxt for crypto, alpaca/polygon for equities.

7. **Multi-position management** — Currently max 1 position per symbol per side. Allow scaled entries (pyramiding) with proper portfolio-level correlation checks.

**LOWER PRIORITY:**

8. **Options-specific logic** — Greeks-aware scoring, IV percentile filters, spread strategies (verticals, iron condors)
9. **Futures session awareness** — RTH vs ETH regime handling, rollover logic
10. **Performance analytics page** — Detailed drawdown analysis, monthly returns heatmap, trade distribution histograms

---

### 5. KEY FILES TO UNDERSTAND

| File | Purpose |
|------|---------|
| `backend/core/asset_profiles.py` | Per-asset-class profile definitions (THE core of multi-asset) |
| `backend/backtest/replay_engine.py` | Bar-by-bar backtester — all profile params wired in |
| `backend/core/regime_engine.py` | RegimeClassifier with confirmation_bars |
| `backend/core/scoring_engine.py` | Multi-timeframe composite signal scoring |
| `backend/core/risk_engine.py` | Pre-trade risk checks, position sizing |
| `backend/live/runner.py` | Live/paper trading loop |
| `backend/main.py` | FastAPI app + engine initialization |
| `backend/orchestrator/spine.py` | Agent orchestration spine |
| `frontend/store/index.ts` | Zustand state (includes botAssetClass) |
| `frontend/app/bot/page.tsx` | Bot command center UI |
| `scripts/tune_crypto_profile.py` | Grid search template (adapt for other asset classes) |
| `scripts/multi_asset_backtest.py` | Multi-symbol sweep runner |
| `docs/phase4-backtest-report.md` | Full backtest results + methodology |

---

### 6. DEVELOPMENT PRINCIPLES

- **Institutional quality** — This is meant to be production-grade. No toy code, no shortcuts on risk management.
- **Work autonomously** — Blake (the founder) prefers you execute without asking permission at every step. Build real functionality, not stubs.
- **Profile isolation** — Never let changes to one asset class's parameters affect another. The profile system exists precisely for this.
- **Backtest before shipping** — Any parameter change must be validated with a backtest. Target: PF ≥ 1.5, Win Rate ≥ 50%, Max DD ≤ 3%.
- **No data snooping** — Walk-forward validation is the gold standard. Single-window backtests are directionally useful but not proof of edge.

---

### 7. HOW TO RUN

```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Backtest (single symbol)
cd backend && python -m backtest.replay_engine  # or use scripts/multi_asset_backtest.py

# Grid search tuning
python scripts/tune_crypto_profile.py  # ~6 min per variant

# Start everything (Windows)
start-lumare.bat
```

---

### 8. WHERE WE'RE HEADED

Lumare's end-state is a **fully autonomous, multi-asset trading system** that:
- Trades crypto, equities, futures, and options with per-asset-class optimization
- Runs 24/7 with regime-aware position management
- Provides institutional-grade risk controls (portfolio heat, correlation, drawdown circuit breakers)
- Has a polished dark-mode dashboard for monitoring and manual override
- Achieves consistent PF ≥ 1.5 across all asset classes in walk-forward validation

The immediate goal is to **get all 4 asset profiles validated with PF ≥ 1.5**, then move to live paper trading to prove real-time execution works. After that, real capital deployment with conservative sizing.

---

*Generated 2026-04-13. Commit 257c58d on main.*
