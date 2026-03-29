# LUMARE — Product Specification

## Overview

Lumare is a vertically integrated Capital Intelligence OS. It unifies portfolio tracking, institutional-grade analysis, macro intelligence, copy trading, political alpha, strategy marketplace, risk management, financial planning, and trade execution into a single platform.

Target users: retail investors who've outgrown basic apps, RIAs, family offices, hedge funds.

---

## Navigation Structure

### Primary Tabs (Bottom Nav)
1. **Home**
2. **Markets**
3. **Intel**
4. **Macro**
5. **Profile**

### Full Pages (Accessed via Home/Markets)
6. **Strategy Marketplace**
7. **Risk War Room**
8. **Portfolio Builder**
9. **Plan** (Financial Planning — to be added)

### Flows
10. **Upgrade Flow** (3-tier paywall)
11. **Asset Detail** (opened from Markets → Assets)

---

## 1. HOME — Net Worth Dashboard

**Purpose**: Unified net worth view across all asset classes.

**Components**:
- Total net worth display (assets minus liabilities)
- Area chart with time range toggles: 1M / 3M / 6M / 1Y / All
- Asset allocation pie chart
- Breakdown by category:
  - Investments (stocks, ETFs, options)
  - Real estate
  - Crypto
  - Cash & equivalents
  - Liabilities (mortgages, loans, credit)
- Search bar for any asset
- Quick access cards: Strategy Marketplace, Risk War Room, Portfolio Builder

---

## 2. MARKETS — 4 Sub-Tabs

### 2a. Assets
- Live watchlist with ticker, price, % change, sparkline
- Tap any asset → opens Asset Detail page
- Search/filter functionality
- Sector grouping option

### 2b. Flow (Options Flow)
- Real-time options flow feed
- Fields: ticker, strike, expiry, type (CALL/PUT), size, premium, sweep detection
- Color coding: calls green, puts red, sweeps highlighted
- Filter by: premium size, ticker, type, sweep only
- Requires: Unusual Whales API ($50/mo)

### 2c. Copy (Copy Trading)
- **Leaderboard**: Ranked by Sharpe ratio, win rate, max drawdown, total return
- **Live Trade Mirror Feed**: Real-time trades from followed strategists
- **Bot Signals Tab**: Automated strategy signals with entry/stop/target
- Subscribe to individual traders or bots
- Performance verification (cryptographic)

### 2d. Alpha (Political & Insider)
- **Congressional Trades**: Disclosures within hours of filing (Quiver Quant API)
  - Politician name, ticker, transaction type, amount, date filed vs date traded
- **Reverse Cramer**: Contrarian signals based on Jim Cramer's public calls
- **SEC Form 4 Insider Transactions**: Officer/director buys and sells
  - Cluster detection (multiple insiders buying = stronger signal)

---

## 3. ASSET DETAIL — 3 Views

Opened by tapping any asset from Markets → Assets.

### 3a. Chart
- Full TradingView chart widget
- Interval tabs: 1H / 4H / 1D / 1W / 1M
- Toggleable indicators: RSI, MACD, Bollinger Bands, VWAP, Volume, EMA50
- Future: upgrade to TradingView Charting Library for programmatic overlays

### 3b. Analyse (AI Analysis)
- Full CMT-grade analysis with 7 sub-tabs:
  1. **Signal**: Master BUY/SELL/HOLD with confidence %, entry price, stop loss, target prices (T1/T2/T3), risk-reward ratio
  2. **Trend**: Stage 2.0 analysis, MA stack alignment, ADX strength, Linear Regression slope, trend grade
  3. **Patterns**: Chart pattern detection (double top/bottom, cup & handle, H&S, flags, wedges) with pattern type, reliability score, projected target, stop level
  4. **Candles**: Candlestick pattern detection with SVG visual diagrams (hammer, engulfing, doji, morning star, etc.)
  5. **Volume**: Volume Profile with VAH (Value Area High), POC (Point of Control), VAL (Value Area Low), OBV analysis
  6. **Wyckoff**: Phase identification (Accumulation phases A→E, Distribution phases A→E), annotated phase map
  7. **Elliott**: Wave count identification, Fibonacci retracement/extension levels, wave degree classification

### 3c. Trade
- Paper / Live toggle switch
- Buy / Sell buttons
- Order types: Market, Limit, Stop-Limit
- Intel signal pre-fill (auto-populates entry/stop/target from Signal tab)
- Quantity / dollar amount input
- Position tracking (open positions, P&L)
- Execution via Alpaca API

---

## 4. INTEL — Standalone Analysis Page

**Purpose**: Deep-dive analysis on any asset without navigating to Markets first.

**Components**:
- Asset selector (search any ticker)
- Re-run analysis button
- Same 7 analysis sections as Asset Detail → Analyse:
  - Signal, Trend, Patterns, Candles, Volume, Wyckoff, Elliott
- Powered by Claude API (currently mock data)

---

## 5. MACRO — 3 Sub-Tabs

### 5a. Regime
- Current market regime classification: Risk-On / Risk-Off / Transitional
- Indicator dashboard:
  - VIX level + percentile
  - DXY (Dollar Index) trend
  - 10Y yield + yield curve status
  - Market breadth (advance/decline, % above 200MA)
- Current playbook recommendation based on regime

### 5b. Calendar
- Economic event calendar:
  - FOMC meetings (rate decisions, minutes, speeches)
  - CPI / PPI releases
  - NFP (Non-Farm Payrolls)
  - Earnings dates for watchlist stocks
- Each event shows: expected value, prior value, historical market impact
- Countdown to next major event

### 5c. Scenarios
- Bull / Base / Bear probability distribution
- Each scenario includes:
  - Probability percentage
  - Trigger conditions (what would cause this scenario)
  - Market impact projections
  - Recommended playbook / positioning
- Custom scenario builder

---

## 6. STRATEGY MARKETPLACE

**Purpose**: The "App Store of Alpha" — users publish, subscribe to, and blend strategy signal streams.

**Components**:
- **Leaderboard**: Strategies ranked by Sharpe ratio, win rate, max drawdown, total return, profit factor
- **Strategy Cards**: Each shows performance metrics, description, subscriber count, price
- **Subscribe**: One-click subscription to individual strategies
- **Blend Builder**: Select multiple strategies, set allocation percentages per strategy
- **Deploy**: Execute the blend (paper or live)
- **Backtest**: Run historical backtest on any strategy or blend
- **Publish**: Users can publish their own strategies (70% revenue share to creator, 30% to Lumare → updated to 80/20 take rate per investor brief)
- **Verification**: Performance cryptographically verified, no paper-trading inflation

---

## 7. RISK WAR ROOM

**Purpose**: Institutional-grade portfolio stress testing and risk monitoring.

### Stress Test Tab
- Pre-built scenarios:
  - 2008 GFC (Global Financial Crisis)
  - 2020 COVID Crash
  - 2022 QT (Quantitative Tightening)
  - Oil Shock
  - 50bps Emergency Rate Hike
  - Regional Banking Crisis
  - Custom (user-defined parameters)
- Output per scenario:
  - Portfolio % impact
  - Dollar impact
  - Worst exposed positions
  - Hedge effectiveness
  - AI-generated recommendation

### Live Risk Tab
- Real-time VaR (Value at Risk) per position and portfolio-level
- Beta per position
- Correlation matrix with heat map coloring
- Portfolio heat indicator (% of capital at risk)
- Tail risk probability estimate
- Drawdown tracker

---

## 8. PORTFOLIO BUILDER

**Purpose**: Guided portfolio construction in 6 steps.

**Steps**:
1. **Risk Profile**: Conservative / Moderate / Aggressive / Opportunistic
2. **Time Horizon**: <1yr / 1-3yr / 3-5yr / 5-10yr / 10+yr
3. **Conviction Themes**: AI, Energy, Biotech, Macro, Crypto, Value, Growth, Dividends, etc.
4. **Manager Style**: Choose from institutional archetypes:
   - Druckenmiller (macro, conviction, concentration)
   - O'Neil (CANSLIM, growth momentum)
   - Burry (deep value, contrarian)
   - Dalio (all-weather, risk parity)
   - Custom blend
5. **Portfolio Size**: Dollar amount to allocate
6. **Execution Preference**: Manual / Semi-auto / Fully autonomous

**Output**:
- AI-generated portfolio with:
  - Specific ticker selections
  - Weight allocations per position
  - Entry zones (price levels)
  - Conviction scores per position
  - Rebalancing logic

---

## 9. PLAN — Financial Planning (TO BE ADDED)

**Purpose**: All-inclusive financial planning tab to make Lumare a complete wealth management app.

**Components** (planned):
- Net worth unification (linked accounts)
- Retirement modeling (Monte Carlo simulations)
- Goal tracking (house, education, retirement, etc.)
- Budget tracking and cash flow analysis
- Tax optimization suggestions
- Integration with financial planning software (MoneyGuidePro or similar)
- Live financial plan view

**Note**: This tab existed in an earlier version but was dropped in the most recent build. Needs to be re-added and blended with the current navigation.

---

## 10. PROFILE

**Components**:
- Avatar / profile photo
- Stats display: net worth, YTD return, streak
- Upgrade CTA button
- Personal info section
- Settings sub-screens:
  - **Notifications**: Price alerts, sweep alerts, macro events, earnings, strategy signals (working toggles)
  - **Security**: 2FA, password change, session management
  - **Preferences**: Theme, default chart interval, data refresh rate
  - **Linked Accounts**: Brokerages (Alpaca), banks, crypto exchanges (with connection status)
- Support / Help
- Sign Out

---

## 11. UPGRADE FLOW

### Tiers:
| Tier | Price | Features |
|------|-------|----------|
| **Core** | Free | Portfolio tracker, basic markets, limited analysis |
| **Wealth** | $49/mo | Full Intel, options flow, AI analysis, copy trading, macro, Risk War Room |
| **Private** | $199/mo | Dedicated advisor, 1:1 portfolio reviews, custom entry mapping, priority research |

### Additional Revenue Streams (not in-app tiers):
| Stream | Price | Description |
|--------|-------|-------------|
| **RIA Seat** | $500–2K/mo | Multi-client dashboards, white-label option |
| **Managed** | 0.75% AUM | Lumare manages portfolio using platform intelligence |
| **Marketplace** | 20% take rate | Revenue from strategy signal stream subscriptions |
| **Proprietary Fund** | 2/20 | Endgame: run the bot on Lumare's own capital |
