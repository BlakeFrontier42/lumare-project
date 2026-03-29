# LUMARE — Architecture & Tech Stack

---

## Frontend

### Current State
- Single-file React JSX mockup (`lumare_v3.jsx`)
- Full navigation and mock data
- Mobile UI: strong, clean design
- Desktop UI: needs significant upgrade (see UI_DESIGN.md)

### Target Stack
- **Framework**: Next.js (App Router)
- **Styling**: Tailwind CSS
- **Charts**: TradingView Charting Library (upgrade from free widget for programmatic overlays)
- **State Management**: Zustand or React Context
- **Auth**: Supabase Auth (email/password + OAuth)
- **Payments**: Stripe (subscription billing)
- **Hosting**: Vercel

### Design System
- **Fonts**:
  - Headings: Space Grotesk
  - Body: Inter
  - Numbers/Data: Space Mono
- **Color Palette**: Pure monochrome
  - Background: `#080808`
  - Cards: `#111111`
  - Primary text: `#ffffff`
  - Secondary text: `#888888`
  - Green (profit/buy): `#22c55e`
  - Red (loss/sell): `#e05252`
  - No other colors. Color is reserved exclusively for P&L signals.

---

## Backend

### API Layer (Next.js API Routes or separate service)

All server-side logic runs through Next.js API routes initially, with the option to extract into microservices later.

### Database
- **Primary**: Supabase (PostgreSQL)
  - User accounts, profiles, preferences
  - Linked accounts
  - Subscription status
  - Watchlists
  - Portfolio holdings
  - Strategy marketplace data
- **Time Series / Cache**: SQLite (for algorithm backtesting data) or TimescaleDB extension
- **Cache**: Vercel KV or Upstash Redis (for rate-limited API responses)

---

## External APIs

| API | Purpose | Cost | Key Variable |
|-----|---------|------|-------------|
| **Polygon.io** | Live/historical price data (OHLCV), tickers, fundamentals | $29/mo | `POLYGON_API_KEY` |
| **Anthropic Claude** | AI analysis engine (Intel tab, earnings sentiment, portfolio builder) | Usage-based | `ANTHROPIC_API_KEY` |
| **Alpaca** | Paper + live trading execution, account management | Free (trading) | `ALPACA_KEY`, `ALPACA_SECRET` |
| **Unusual Whales** | Options flow data (sweeps, premium, sentiment) | $50/mo | `UNUSUAL_WHALES_KEY` |
| **Quiver Quant** | Congressional trades, insider transactions | Free tier | `QUIVER_QUANT_KEY` |
| **FRED** | Macro economic data (rates, M2, yield curves, GDP) | Free | No key needed (or free key) |
| **SEC EDGAR** | Insider Form 4 filings, 8-K/10-K/10-Q | Free (RSS) | No key needed |
| **Blowfin** | Crypto perpetual futures (Phase 1 algorithm) | Free | `BLOWFIN_API_KEY`, `BLOWFIN_SECRET` |
| **TradingView** | Charting library | Free widget / paid library | Widget = no key |

---

## Environment Variables

All stored as Vercel environment variables in production. For local dev, use `.env.local`.

```bash
# Prices & Market Data
POLYGON_API_KEY=

# AI Analysis Engine
ANTHROPIC_API_KEY=

# Trade Execution (Equities)
ALPACA_KEY=
ALPACA_SECRET=

# Options Flow
UNUSUAL_WHALES_KEY=

# Political Alpha
QUIVER_QUANT_KEY=

# Crypto Execution (Phase 1)
BLOWFIN_API_KEY=
BLOWFIN_SECRET=

# Auth
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Payments
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=

# Hosting
VERCEL_URL=
```

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js)                     │
│  ┌──────┐ ┌────────┐ ┌───────┐ ┌───────┐ ┌─────────┐  │
│  │ Home │ │Markets │ │ Intel │ │ Macro │ │ Profile │  │
│  └──┬───┘ └───┬────┘ └──┬────┘ └──┬────┘ └────┬────┘  │
│     │         │         │         │            │        │
│  ┌──┴─────────┴─────────┴─────────┴────────────┴──┐    │
│  │              Next.js API Routes                  │    │
│  └──┬─────┬─────┬──────┬──────┬──────┬──────┬─────┘    │
└─────┼─────┼─────┼──────┼──────┼──────┼──────┼──────────┘
      │     │     │      │      │      │      │
      ▼     ▼     ▼      ▼      ▼      ▼      ▼
   Polygon Claude Alpaca  UW   Quiver FRED  Blowfin
   (.io)  (API)  (API)  (API) (API)  (API)  (API)
                    │
                    ▼
              ┌──────────┐
              │ Supabase │ ← Auth, DB, Storage
              └──────────┘
                    │
                    ▼
              ┌──────────┐
              │  Stripe  │ ← Subscriptions
              └──────────┘
```

---

## Macro Intelligence Engine (MIE) — Backend Architecture

The trading algorithm runs as a separate Python service (can be containerized).

```
macro_intelligence_engine/
├── core/
│   ├── regime_engine.py      # Market regime classification
│   ├── macro_engine.py       # Macro data processing
│   ├── flow_engine.py        # Options flow analysis
│   ├── structure_engine.py   # ICT structure detection
│   ├── trend_engine.py       # Trend signal scoring
│   ├── momentum_engine.py    # Momentum signal scoring
│   ├── scoring_engine.py     # Master 0-100 conviction scorer
│   ├── risk_engine.py        # Position sizing, drawdown controls
│   ├── portfolio_engine.py   # Portfolio heat, correlation management
│   └── equity_governor.py    # Equity curve protection
├── data/
│   ├── crypto_feed.py        # Blowfin API connector
│   ├── equities_feed.py      # Polygon.io connector
│   ├── options_flow_feed.py  # Unusual Whales connector
│   ├── congressional_feed.py # Quiver Quant connector
│   ├── macro_feed.py         # FRED API connector
│   ├── insider_feed.py       # SEC EDGAR RSS parser
│   ├── aggregator.py         # Unified data pipeline
│   └── storage.py            # SQLite storage layer
├── execution/
│   ├── blowfin_executor.py   # Crypto order execution
│   ├── alpaca_executor.py    # Equities order execution
│   ├── polymarket_executor.py # Prediction market execution
│   └── paper_simulator.py    # Paper trading simulation
├── backtest/
│   ├── replay_engine.py      # Historical replay simulator
│   └── performance_metrics.py # Sharpe, Sortino, PF, etc.
├── live/
│   ├── runner.py             # Live trading loop
│   └── watchdog.py           # Health monitoring
└── config/
    └── settings.py           # All configuration
```

---

## Deployment

### Frontend
- Vercel (automatic from GitHub)
- Domain: `lumare.app` (to be registered)

### Backend (MIE)
- Initially: Vercel serverless functions or Railway
- Scale: Dedicated container (Docker on AWS/GCP/Railway)

### Database
- Supabase managed PostgreSQL

### Monitoring
- Vercel Analytics (frontend)
- Custom watchdog (MIE)
- Error tracking: Sentry (planned)
