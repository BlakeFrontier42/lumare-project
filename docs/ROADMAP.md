# LUMARE — Development Roadmap

---

## Phase 0: Foundation (Current → Week 1)
**Goal**: Get the project off the ground with a deployable frontend.

- [ ] Structure React mockup into Next.js App Router project
- [ ] Set up Tailwind CSS with design tokens (colors, fonts, spacing)
- [ ] Implement responsive layout (mobile bottom tabs + desktop sidebar)
- [ ] Elevate desktop UI (multi-column grids, data tables, split-pane views)
- [ ] Re-add the Plan tab (financial planning) that was dropped
- [ ] Deploy to Vercel
- [ ] Register `lumare.app` domain
- [ ] Build waitlist landing page

**Deliverable**: Polished, deployed frontend with mock data at lumare.app

---

## Phase 1: Data Infrastructure (Weeks 2–3)
**Goal**: Replace mock data with real data.

- [ ] Polygon.io integration (live prices, OHLCV, ticker search)
- [ ] TradingView widget integration (charts on Asset Detail)
- [ ] FRED API integration (macro data for Macro tab)
- [ ] Quiver Quant integration (congressional trades for Alpha tab)
- [ ] SEC EDGAR RSS parser (insider transactions for Alpha tab)
- [ ] Supabase setup (auth, user profiles, watchlists)
- [ ] Environment variable management (.env.local + Vercel)

**Deliverable**: Markets tab + Macro tab showing real data

---

## Phase 2: Intelligence Layer (Weeks 3–5)
**Goal**: Power the Intel tab with real AI analysis.

- [ ] Claude API integration for technical analysis
- [ ] Build analysis prompt templates for each of the 7 modules:
  - Signal, Trend, Patterns, Candles, Volume, Wyckoff, Elliott
- [ ] Asset selector + re-run functionality
- [ ] Cache analysis results (don't re-analyze on every page load)
- [ ] Unusual Whales integration (options flow for Flow tab)

**Deliverable**: Intel tab producing real AI analysis on any ticker

---

## Phase 3: Trading Engine — Crypto (Weeks 5–8)
**Goal**: Build and validate the MIE algorithm on crypto.

Follow MANDATORY development order from ALGORITHM.md:
1. [ ] Historical crypto data loader (Blowfin API)
2. [ ] Data aggregation engine
3. [ ] Replay simulator (backtesting framework)
4. [ ] Regime engine
5. [ ] Signal engines (trend, momentum, structure, flow, macro)
6. [ ] Scoring engine (0–100 conviction)
7. [ ] Risk + portfolio engine
8. [ ] Integrate into backtest
9. [ ] Validate metrics (Sharpe >2.0, win rate >60%, max DD <15%)
10. [ ] Deploy live paper runner

**Deliverable**: Validated trading algorithm on BTC/ETH with passing metrics

---

## Phase 4: Trading Execution — Equities (Weeks 8–10)
**Goal**: Enable paper + live trading through Alpaca.

- [ ] Alpaca API integration (paper trading mode)
- [ ] Trade tab implementation (Buy/Sell, order types, position tracking)
- [ ] Intel signal pre-fill (auto-populate orders from analysis)
- [ ] Paper/Live toggle with safety confirmation
- [ ] Portfolio positions view with real-time P&L

**Deliverable**: Users can paper trade and eventually live trade equities

---

## Phase 5: Auth & Payments (Weeks 10–12)
**Goal**: User accounts and subscription billing.

- [ ] Supabase Auth (email/password + Google OAuth)
- [ ] User profile + preferences storage
- [ ] Stripe integration (subscription checkout)
- [ ] Implement tier gating (Core/Wealth/Private)
- [ ] Upgrade flow UI
- [ ] Linked accounts management

**Deliverable**: Full auth, billing, and feature gating

---

## Phase 6: Portfolio Builder (Weeks 12–14)
**Goal**: AI-powered guided portfolio construction.

- [ ] 6-step onboarding flow UI
- [ ] Claude API prompts for portfolio generation
- [ ] Manager style templates (Druckenmiller, O'Neil, Burry, Dalio)
- [ ] Portfolio output with weights, entry zones, conviction scores
- [ ] Save generated portfolios to user profile

**Deliverable**: Working Portfolio Builder that generates real portfolios

---

## Phase 7: Copy Trading & Marketplace (Weeks 14–18)
**Goal**: Strategy Marketplace MVP.

- [ ] Leaderboard UI (Sharpe, win rate, drawdown, subscribers)
- [ ] Strategy publishing flow
- [ ] Strategy subscription (Stripe integration)
- [ ] Trade mirroring infrastructure
- [ ] Performance verification system
- [ ] Blend builder (multi-strategy allocation)
- [ ] Backtest on blend

**Deliverable**: Users can publish, subscribe to, and blend strategies

---

## Phase 8: Risk War Room (Weeks 18–20)
**Goal**: Institutional-grade portfolio stress testing.

- [ ] Pre-built scenario library (2008, 2020, 2022, etc.)
- [ ] Portfolio impact calculator
- [ ] Custom scenario builder
- [ ] Live risk dashboard (VaR, beta, correlation matrix)
- [ ] AI-generated hedge recommendations

**Deliverable**: Full Risk War Room with stress testing and live risk monitoring

---

## Phase 9: Financial Planning (Weeks 20–22)
**Goal**: All-inclusive financial planning tab.

- [ ] Net worth unification (linked accounts)
- [ ] Retirement modeling (Monte Carlo)
- [ ] Goal tracking
- [ ] Budget and cash flow
- [ ] Integration options (MoneyGuidePro or custom)

**Deliverable**: Plan tab makes Lumare a complete wealth management platform

---

## Phase 10: Scale & Polish (Ongoing)
- [ ] Performance optimization
- [ ] Advanced TradingView Charting Library integration
- [ ] Push notifications (price alerts, macro events, sweep alerts)
- [ ] RIA/institutional dashboards
- [ ] Managed AUM product
- [ ] Proprietary fund setup
- [ ] Mobile native app (React Native or Swift)

---

## Known Issues to Fix

1. **Plan tab missing**: Existed in earlier version, dropped in most recent build. Must be re-added.
2. **Desktop UI quality**: Mobile is clean, desktop looks low-quality. Must be elevated with sidebar nav, multi-column layout, data tables, split-pane views.
3. **Macro Portfolio Builder**: Some versions had a macro aspect that allows building a portfolio — this disappeared in the most recent version. Needs to be restored and blended.
4. **All data is mock**: Every price, analysis, and signal is placeholder data.
