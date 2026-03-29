# LUMARE — Macro Intelligence Engine (MIE) Algorithm Specification

> You are the Chief Quant Architect and Lead Systems Engineer.
> This is a capital-compounding infrastructure designed for institutional-grade survivability and scalability.
> Survival > Aggression.

---

## Objective

Build a unified, modular, fully autonomous trading intelligence engine that:

1. Trades crypto perpetual futures (Blowfin) first
2. Expands to US equities/options (Alpaca + Polygon)
3. Integrates macro + options flow + insider + congressional data
4. Uses regime-aware scoring across all assets
5. Survives long enough to compound capital
6. Can later be deployed to a consumer Strategy Marketplace

### Validation Metrics (Must Pass Before Live Capital)

| Metric | Target |
|--------|--------|
| Win rate | > 60% (stretch: >65%) |
| Sharpe ratio | > 2.0 (stretch: >2.5) |
| Profit factor | > 1.5 |
| Max drawdown | < 15% |
| No martingale behavior | Enforced |
| No structural overexposure | Enforced |

---

## Phase 1 — Crypto Foundation

- **Exchange**: Blowfin
- **Mode**: Live data + Paper execution only (until metrics validated)
- **Instruments**: BTCUSDT perpetual, ETHUSDT perpetual

### Timeframe Stack
| Timeframe | Purpose |
|-----------|---------|
| 1D | Macro bias |
| 4H | Regime classification |
| 1H | Liquidity map |
| 15M | Setup detection |
| 5M | Execution trigger |
| 1M | Confirmation only |

### Execution Rules
- Candle-close only on 5M
- Limit orders only
- No market chasing

---

## Regime Engine (Global Filter)

Uses 4H + macro overlay.

### Inputs
- 30-day ATR percentile
- ADX
- Realized volatility percentile
- Volume expansion ratio
- FRED macro indicators (liquidity, rates)

### Output States
| State | Trading Rules |
|-------|--------------|
| `RISK_ON` | All strategies active |
| `RISK_OFF` | No momentum longs |
| `RANGE` | Mean-reversion only |
| `TREND` | Trend-following active |
| `EXPANSION` | Breakout logic allowed |
| `CHAOTIC` | **No trading** |

---

## Signal Scoring Model (0–100 Conviction)

Five categories, each scored 0–20 points:

### 1. Trend Score (0–20)
- MA alignment (multi-timeframe moving average stack)
- ADX strength (>25 trending, >40 strong trend)
- Linear regression slope (direction + steepness)

### 2. Momentum Score (0–20)
- RSI regime positioning (oversold/overbought + divergences)
- MACD histogram (direction, acceleration, crossovers)
- Rate of Change (ROC — momentum confirmation)

### 3. Structure Score (0–20) — ICT Quantified
- Liquidity sweep detection (stop hunts above/below key levels)
- Break of structure (BOS — higher high/lower low confirmation)
- Fair value gap (FVG — imbalance zones for entry)
- Displacement candle vs ATR (institutional momentum confirmation)

### 4. Flow Score (0–20)
**Crypto:**
- Funding rate delta (positive = longs paying, negative = shorts paying)
- Open interest delta (rising OI + price = conviction, falling OI = closing)

**Equities:**
- Options flow imbalance (call/put ratio, sweep detection, unusual premium)
- Congressional trade clusters (multiple politicians same ticker = signal)
- Insider transaction clusters (multiple Form 4 buys = strong signal)

### 5. Macro/Regime Score (0–20)
- Volatility percentile (VIX, realized vol, ATR percentile)
- Liquidity expansion/contraction (M2, reverse repo, Fed balance sheet)
- Risk-on confirmation (credit spreads, breadth, sector rotation)

### Trade Threshold
| Score | Action |
|-------|--------|
| < 70 | No trade |
| 70–84 | Standard position size |
| 85+ | Elevated risk tier (still within portfolio heat limits) |

---

## Risk Engine

### Position Sizing
- Base risk per trade: 1% of portfolio
- Dynamic range: 0.75–1.25% based on conviction score and regime
- ATR-based stop distance determines position size

### Portfolio Heat
- Max 20% of capital at risk simultaneously
- Includes all open positions' distance to stop

### Correlation Controls
- No more than 3 correlated positions at any time
- Correlation measured on 30-day rolling window

### Drawdown Controls
| Drawdown Level | Action |
|----------------|--------|
| -10% | Pause all new trades |
| -12% | Reduce position sizes by 50% |
| -15% | Hard shutdown — no trading |

### Crypto-Specific
- Daily loss cap: 4%
- No averaging down
- No martingale
- No revenge scaling

---

## Position Sizing & Leverage (Crypto)

### Leverage Rules
| Stop Distance | Max Leverage |
|---------------|-------------|
| < 0.5% | 8x max |
| < 1.0% | 5x |
| > 1.0% | 2–3x |

**20x leverage DISABLED until 6-month live validation complete.**

### Stop Placement
- Structure-based (below/above key level) + ATR buffer

### Take Profit Framework

**Mean Reversion Trades:**
| Level | Size | Action |
|-------|------|--------|
| TP1 | 50% | 1R target |
| TP2 | 50% | 2R target |

**Expansion/Breakout Trades:**
| Level | Size | Action |
|-------|------|--------|
| TP1 | 25% | 1R target |
| TP2 | 25% | 2R target |
| TP3 | 25% | 3R target |
| Runner | 25% | Trailing stop on structure |

---

## Execution Layer

### Entry
- Limit orders at key technical levels (never market orders)

### Scale-In Protocol
1. 25% starter position at initial entry
2. Add 25% on price confirmation (e.g., retest of breakout)
3. Full size only above key level confirmation

### Exit
- Trail stop to breakeven once TP1 hit
- Let TP2+ runners ride with trailing structure stop
- Alpaca API for equity execution, Blowfin API for crypto

---

## Data Sources

| Source | Data | API |
|--------|------|-----|
| Blowfin | Crypto OHLCV, funding, OI | Blowfin REST/WS |
| Polygon.io | Equities OHLCV, tickers | Polygon REST |
| Unusual Whales | Options flow, sweeps | UW REST |
| Quiver Quant | Congressional trades | Quiver REST |
| FRED | Macro data (rates, M2, GDP) | FRED REST |
| SEC EDGAR | Insider Form 4 filings | RSS/XBRL |
| Claude API | Earnings sentiment analysis | Anthropic REST |

All data stored in SQLite. No lookahead bias. Replay-based backtesting only.

---

## Backtest Requirements

### Minimum Coverage
- 1 year BTC data
- 1 year ETH data
- 300+ total trades

### Required Metrics
- Sharpe ratio
- Sortino ratio
- Profit factor
- Expectancy (avg win × win rate − avg loss × loss rate)
- Max drawdown
- Performance breakdown by regime

### Rules
- No live capital until all validation metrics pass
- No optimization on test set (walk-forward only)
- Slippage and commission modeled

---

## Development Order (MANDATORY)

```
1.  Build historical crypto data loader
2.  Build data aggregation engine
3.  Build replay simulator
4.  Build regime engine
5.  Build signal engines (trend, momentum, structure, flow, macro)
6.  Build scoring engine (combine all signals into 0-100)
7.  Build risk + portfolio engine
8.  Integrate into backtest framework
9.  Validate metrics (must pass all targets)
10. Deploy live paper runner
11. Only then expand to equities (Phase 2)
```

**Do not skip steps. Do not optimize prematurely. Do not introduce discretionary logic.**

---

## Phase 2+ Expansion

### Equities
- Alpaca API for execution
- Polygon.io for data
- Same scoring engine, adapted signal weights

### Prediction Markets
- Polymarket API integration

### Strategy Marketplace Integration
- Bot gets its own leaderboard card
- $49/mo subscription for signal access
- Backtest results displayed publicly before users commit capital
- Eventually: autonomous execution mode for opted-in users

---

## Core Principle

This system must:
- **Survive** volatility
- **Control** downside
- **Compound** slowly
- **Scale** responsibly

The objective is not to gamble.
The objective is to build a capital engine that can run for years.
