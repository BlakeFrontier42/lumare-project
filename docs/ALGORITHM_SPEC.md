# LUMARE MIE — Complete Algorithm Specification
## Institutional-Grade Quantitative Trading System

> Version: 1.0.0
> Classification: Internal — Proprietary
> Last Updated: 2026-03-23

---

## 1. System Overview

Lumare MIE (Macro Intelligence Engine) is a fully autonomous, multi-asset quantitative trading system designed for institutional-grade survivability and capital compounding.

### Design Principles
- **Survival > Aggression**: The system's primary objective is capital preservation
- **No Black Boxes**: Every decision is explainable with contributing signals, regime context, and risk adjustments
- **No Curve-Fitting**: All thresholds are statistically justified; walk-forward validation required
- **No Look-Ahead Bias**: Replay-based backtesting processes one bar at a time chronologically
- **No Survivorship Bias**: All instruments traded are pre-defined; no post-hoc selection

### Supported Asset Classes
| Phase | Asset Class | Exchange | Instruments |
|-------|------------|----------|-------------|
| 1 (Current) | Crypto Perpetual Futures | Blowfin | BTCUSDT, ETHUSDT |
| 2 | US Equities | Alpaca | Configurable universe |
| 3 | Prediction Markets | Polymarket | Event contracts |

---

## 2. Signal Architecture

### 2.1 Master Signal Schema

The system uses a 5-layer signal stack, each contributing 0-20 points to a 0-100 conviction score.

```
┌──────────────────────────────────────────┐
│          MASTER SIGNAL STACK             │
│                                          │
│  ┌─────────────┐  Score Range: 0-20      │
│  │ MACRO LAYER │  Fed rates, M2, VIX     │
│  └──────┬──────┘                         │
│  ┌──────┴──────┐  Score Range: 0-20      │
│  │ LIQUIDITY   │  Funding, OI, options   │
│  └──────┬──────┘                         │
│  ┌──────┴──────┐  Score Range: 0-20      │
│  │ STRUCTURE   │  ICT: BOS, FVG, sweeps  │
│  └──────┬──────┘                         │
│  ┌──────┴──────┐  Score Range: 0-20      │
│  │ MOMENTUM    │  RSI, MACD, ROC         │
│  └──────┬──────┘                         │
│  ┌──────┴──────┐  Score Range: 0-20      │
│  │ TREND       │  MA stack, ADX, LinReg  │
│  └─────────────┘                         │
│                                          │
│  TOTAL: 0-100 Conviction Score           │
│  Threshold: ≥70 to trade                 │
└──────────────────────────────────────────┘
```

### 2.2 Layer 1 — Trend Score (0-20)

| Sub-Signal | Points | Formula |
|-----------|--------|---------|
| MA Alignment | 0-8 | Check 20/50/200 EMA alignment: all bullish (20>50>200)=8, partial=4, counter=0 |
| ADX Strength | 0-6 | ADX(14): >40=6, >25=4, >15=2, <15=0 |
| Linear Regression | 0-6 | 20-period LinReg slope normalized by ATR: strong aligned=6, moderate=3, flat=0 |

**Variable Definitions:**
- `EMA(n)`: Exponential Moving Average with period n
- `ADX(14)`: Average Directional Index, 14-period
- `LinReg(20)`: Linear regression slope over 20 periods
- `ATR(14)`: Average True Range, 14-period

### 2.3 Layer 2 — Momentum Score (0-20)

| Sub-Signal | Points | Formula |
|-----------|--------|---------|
| RSI Regime | 0-7 | RSI(14) positioning + divergence detection. Oversold+bullish div=7, >50 momentum=5, crossing 50=3 |
| MACD | 0-7 | MACD(12,26,9) histogram direction + acceleration. Increasing above zero=7, fresh cross=5, decelerating=2 |
| Rate of Change | 0-6 | ROC(10): positive accelerating=6, positive decelerating=3, negative=0 |

**Divergence Detection:**
```
Bullish divergence = price makes lower low AND RSI makes higher low (5-bar window)
Bearish divergence = price makes higher high AND RSI makes lower high (5-bar window)
```

### 2.4 Layer 3 — Market Structure Score (0-20)

ICT (Inner Circle Trader) concepts quantified:

| Sub-Signal | Points | Formula |
|-----------|--------|---------|
| Liquidity Sweep | 0-6 | Price pierces swing high/low then reverses within N bars. Sweep + reversal=6, sweep only=2 |
| Break of Structure | 0-6 | Higher high/lower low on 2+ timeframes=6, single TF=3 |
| Fair Value Gap | 0-4 | 3-candle imbalance gap > 0.5x ATR. Price approaching FVG=4, FVG distant=2 |
| Displacement | 0-4 | Candle body > 1.5x ATR = institutional momentum. Aligned=4, moderate=2 |

**Swing Point Detection:**
```
Swing high = bar where high > high of N bars before AND after (lookback=20)
Swing low = bar where low < low of N bars before AND after (lookback=20)
```

### 2.5 Layer 4 — Flow/Liquidity Score (0-20)

**Crypto Mode:**

| Sub-Signal | Points | Formula |
|-----------|--------|---------|
| Funding Rate | 0-10 | Extreme negative + long signal=10 (contrarian). Neutral=3. Extreme positive=inverted |
| Open Interest | 0-10 | Rising OI + rising price=10 (conviction). Rising OI + falling price=6. Falling OI=3 |

**Equities Mode:**

| Sub-Signal | Points | Formula |
|-----------|--------|---------|
| Options Flow | 0-8 | Call/put ratio + sweep detection + unusual premium. Strong call sweeps=8 |
| Congressional | 0-6 | N politicians buying same ticker within 14 days. N≥3=6, N=2=3 |
| Insider Filing | 0-6 | Multiple Form 4 buys. ≥2 insiders=6, 1 significant=3 |

### 2.6 Layer 5 — Macro/Regime Score (0-20)

| Sub-Signal | Points | Formula |
|-----------|--------|---------|
| Volatility Percentile | 0-7 | Realized vol percentile (252-day). For longs: low vol=7, high vol=2. Extreme=CHAOTIC warning |
| Liquidity Index | 0-7 | Composite: 0.4×M2_growth_z + 0.6×net_liquidity_z → sigmoid(0-100). Expanding=7, contracting=2 |
| Risk-On Confirmation | 0-6 | Credit spreads + breadth + sector rotation. All confirming=6 |

**Liquidity Index Formula:**
```python
net_liquidity = fed_balance_sheet - reverse_repo
z_m2 = (m2_yoy_change - 0.06) / 0.03
z_net = (net_liquidity - 4_000_000_000) / 1_000_000_000
liquidity_index = 100 / (1 + exp(-(0.4 * z_m2 + 0.6 * z_net)))
```

---

## 3. Regime Detection Engine

### 3.1 Input Variables

| Variable | Source | Timeframe |
|----------|--------|-----------|
| 30-day ATR percentile | 4H candles | Rolling 30-day |
| ADX(14) | 4H candles | Current |
| Realized volatility percentile | Daily returns | 252-day |
| Volume expansion ratio | 4H candles | Current / 20-period avg |
| Fed funds rate trend | FRED | Monthly |
| M2 money supply growth | FRED | Monthly |
| Yield curve (10Y-2Y) | FRED | Daily |

### 3.2 State Definitions

| State | Condition | Trading Rules |
|-------|-----------|---------------|
| RISK_ON | Liquidity expanding, vol<60p, macro favorable | All strategies active |
| RISK_OFF | Vol>75p AND macro stress indicators | No momentum longs |
| RANGE | ADX<15 AND vol<50p | Mean-reversion only |
| TREND | ADX>25 AND vol<75p | Trend-following active |
| EXPANSION | ADX>25 AND volume_ratio>1.5 AND breakout | Breakout logic allowed |
| CHAOTIC | Vol>90p AND ATR>80p | **NO TRADING** |

### 3.3 Decision Tree

```
IF vol_percentile > 90 AND atr_percentile > 80:
    → CHAOTIC (confidence = vol_percentile / 100)
ELIF vol_percentile > 75 AND (yield_curve_inverted OR fed_tightening):
    → RISK_OFF (confidence based on # confirming indicators)
ELIF adx > 25 AND vol_percentile < 75:
    IF volume_ratio > 1.5 AND breakout_detected:
        → EXPANSION
    ELSE:
        → TREND
ELIF adx < 15 AND vol_percentile < 50:
    → RANGE
ELIF liquidity_index > 60 AND vol_percentile < 60:
    → RISK_ON
ELSE:
    → Weighted score → most probable state
```

### 3.4 Transition Rules

- Regime change requires **3 consecutive bars** confirming new state (prevents whipsaws)
- Transition to CHAOTIC: immediate (1 bar) — safety override
- Confidence threshold: must exceed 0.6 to switch regime

### 3.5 Regime-Adaptive Signal Weights

| Regime | Trend | Momentum | Structure | Flow | Macro |
|--------|-------|----------|-----------|------|-------|
| RISK_ON | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| RISK_OFF | 0.7 | 0.7 | 1.0 | 1.3 | 1.3 |
| RANGE | 0.5 | 1.0 | 1.5 | 1.0 | 1.0 |
| TREND | 1.3 | 1.2 | 0.8 | 0.9 | 0.8 |
| EXPANSION | 1.0 | 1.2 | 1.2 | 1.0 | 0.6 |
| CHAOTIC | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

Scores are normalized after weighting to maintain 0-100 range.

---

## 4. Risk Engine — Non-Negotiable Core

### 4.1 Position Sizing

```
base_risk = 1% of portfolio
dynamic_range = [0.75%, 1.25%] based on conviction + regime

risk_amount = portfolio_value × risk_pct
position_size = risk_amount / |entry_price - stop_price|
```

| Score | Risk % |
|-------|--------|
| 70-84 | 1.0% (standard) |
| 85+ | 1.25% (elevated) |
| Reduced regime | 0.75% (minimum) |

### 4.2 Leverage Rules (Crypto)

| Stop Distance | Max Leverage | Justification |
|---------------|-------------|---------------|
| < 0.5% | 8x | Tight stop requires leverage for meaningful position |
| < 1.0% | 5x | Medium stop, moderate leverage |
| > 1.0% | 2-3x | Wide stop, minimal leverage needed |

**20x leverage DISABLED until 6-month live validation complete.**

### 4.3 Portfolio Heat

```
portfolio_heat = Σ (position_risk_amount / portfolio_value) for all open positions
MAX: 20%
```

### 4.4 Correlation Controls

```
correlation_matrix = 30-day rolling Pearson correlation of daily returns
correlated = |correlation| > 0.7
MAX: 3 correlated positions simultaneously
```

### 4.5 Drawdown Circuit Breakers

| Level | Drawdown | Action |
|-------|----------|--------|
| 1 | -10% | Pause all new trades |
| 2 | -12% | Reduce position sizes by 50% |
| 3 | -15% | **HARD SHUTDOWN — no trading** |

### 4.6 Daily Loss Cap
- Maximum 4% portfolio loss in a single day
- Breach triggers immediate trading halt until next day

### 4.7 Kill Switch

Absolute override. When activated:
1. Cancel all open orders
2. No new orders allowed
3. Existing positions managed but no new entries
4. Requires manual deactivation

### 4.8 Enforcement Order

```
Priority 1: Kill switch (absolute override)
Priority 2: Drawdown shutdown (-15%)
Priority 3: Daily loss cap (4%)
Priority 4: Drawdown pause (-10%)
Priority 5: VaR limit (5% daily 99% VaR)
Priority 6: Portfolio heat (20%)
Priority 7: Correlation limit (3 positions)
Priority 8: Position size limits
```

### 4.9 Equity Governor (Meta-Risk)

The equity curve itself is monitored as a meta-signal:

| Equity State | Size Modifier | Logic |
|-------------|--------------|-------|
| At/near ATH | 1.0x | Normal sizing |
| Below 20-day MA | 0.75x | Early warning reduction |
| Below 50-day MA | 0.50x | Defensive reduction |
| Recovery mode | 0.5→1.0x ramp | Gradual 20-bar ramp back to full size |

### 4.10 VaR Configuration

```
Confidence: 99%
Lookback: 252 trading days
Max portfolio daily VaR: 5%
Methods: Parametric + Historical
```

### 4.11 Prohibited Behaviors

- NO averaging down
- NO martingale
- NO revenge scaling (increasing size after loss)
- NO market orders (limit only)
- NO live capital before validation

---

## 5. Execution Layer

### 5.1 Entry Protocol

- **Order type**: Limit orders ONLY (never market orders)
- **Timing**: 5M candle close only
- **Scale-in**:
  1. 25% starter at initial entry
  2. +25% on price confirmation (retest)
  3. Full size above key level confirmation

### 5.2 Exit Protocol

**Mean Reversion Trades:**
| Level | % of Position | Target |
|-------|--------------|--------|
| TP1 | 50% | 1R |
| TP2 | 50% | 2R |

**Expansion/Breakout Trades:**
| Level | % of Position | Target |
|-------|--------------|--------|
| TP1 | 25% | 1R |
| TP2 | 25% | 2R |
| TP3 | 25% | 3R |
| Runner | 25% | Trailing stop on structure |

### 5.3 Stop Management

- Initial stop: Structure-based + ATR buffer (1.5x ATR below/above)
- After TP1: Move stop to breakeven
- Runners: Trailing structure stop

### 5.4 Execution Simulation

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Slippage (base) | 5 bps | Median observed slippage for limit orders |
| Slippage (vol-adj) | +5-15 bps | Proportional to current vol / baseline vol |
| Maker fee | 0.05% | Blowfin limit order fee |
| Taker fee | 0.10% | Blowfin market order fee |
| Fill probability | 85% | Empirical limit order fill rate |
| Latency model | 50ms ± 15ms | Normal distribution |
| Market impact | √(Q/ADV) × 100 bps | Almgren-Chriss simplified |
| Max position | 5% of ADV | Liquidity constraint |

---

## 6. Timeframe Stack

| Timeframe | Purpose | Engine Usage |
|-----------|---------|-------------|
| 1D | Macro bias | Trend (MA stack), Macro engine |
| 4H | Regime classification | Regime engine, ADX, ATR |
| 1H | Liquidity mapping | Structure engine (FVG, sweeps) |
| 15M | Setup detection | Full signal stack |
| 5M | Execution trigger | Entry/exit decisions |
| 1M | Confirmation only | Scale-in confirmation |

---

## 7. Data Sources

| Source | Data | Update Frequency | Storage |
|--------|------|-------------------|---------|
| Blowfin REST/WS | Crypto OHLCV, funding, OI | 1M-1D candles | SQLite |
| Polygon.io | Equities OHLCV, fundamentals | 1M-1D | SQLite |
| FRED | Macro: rates, M2, GDP, CPI | Daily-Monthly | SQLite |
| Unusual Whales | Options flow, sweeps | Real-time | SQLite |
| Quiver Quant | Congressional trades | Daily | SQLite |
| SEC EDGAR | Insider Form 4 filings | Real-time RSS | SQLite |
| Anthropic Claude | Earnings sentiment | On-demand | Cache |

### Data Integrity Rules
- All timestamps in UTC
- No future data accessible during backtests (exclusive end boundary)
- Candles stored with composite key (symbol, timeframe, timestamp)
- Deduplication enforced via INSERT OR REPLACE

---

## 8. Assumptions

All explicitly stated:

1. **Market microstructure**: Crypto perp futures have sufficient liquidity for our position sizes
2. **Slippage model**: 5bps base is conservative for major pairs (BTC/ETH) on Blowfin
3. **Fee model**: Based on Blowfin's published fee schedule (maker 0.05%, taker 0.10%)
4. **Funding rate**: Assumed to be available and accurate from Blowfin API
5. **Macro data lag**: FRED data has publication delay (1-3 months for some series); we use latest available
6. **Correlation window**: 30-day rolling is sufficient for crypto assets; equities may need 60-day
7. **ATR baseline**: 14-period ATR is industry standard for volatility measurement
8. **Regime persistence**: Markets tend to stay in regimes for extended periods (mean duration ~2-4 weeks)
9. **Kill switch**: Assumes human monitoring available within 1 hour of activation
10. **No exchange risk**: Assumes Blowfin remains operational and solvent
