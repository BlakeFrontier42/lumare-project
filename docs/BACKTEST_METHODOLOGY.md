# LUMARE MIE — Backtesting Methodology Report
## Validation Framework & Anti-Overfitting Protocol

> Version: 1.0.0
> Last Updated: 2026-03-23

---

## 1. Backtesting Philosophy

**Goal: Robustness, NOT optimization theater.**

We are testing whether the strategy has a genuine edge, not fitting a model to historical noise. Every design decision prioritizes out-of-sample validity over in-sample performance.

---

## 2. Historical Data Requirements

| Requirement | Specification |
|------------|---------------|
| Minimum history | 1 year per instrument |
| Instruments | BTCUSDT, ETHUSDT (Phase 1) |
| Timeframes | 1M, 5M, 15M, 1H, 4H, 1D |
| Data source | Blowfin API (live) + CSV fallback |
| Minimum trades | 300+ total across all instruments |
| Data quality | No gaps > 1 hour; deduplication enforced |
| Storage | SQLite with indexed timestamps |

---

## 3. Replay Engine Design

### 3.1 Core Principle: No Lookahead Bias

The replay engine processes candles **one at a time** in chronological order. At any bar `t`:
- Only data from bars `[0, t]` is accessible
- Higher timeframe candles are built incrementally from lower timeframes
- No future data is ever accessible
- Timestamp queries use exclusive end: `WHERE timestamp < current_time`

### 3.2 Bar Processing Loop

```
For each 5M candle in [start_date, end_date]:
    1. Update higher timeframe candle builders (1H, 4H, 1D)
    2. If higher TF candle completed → add to available data
    3. Run regime classification (using only completed candles)
    4. Run all 5 signal engines
    5. Compute conviction score
    6. If score ≥ 70 → generate trade proposal
    7. Run risk checks against current portfolio state
    8. If approved → simulate execution with slippage model
    9. Manage open positions (stops, TPs, trailing)
    10. Update equity curve
    11. Log all decisions with explainability data
```

### 3.3 Higher Timeframe Construction

Higher timeframes are built incrementally:

```python
# Example: building 1H candle from 5M candles
# A 1H candle is complete when 12 consecutive 5M candles are collected
# At bar t (5M), we have:
#   - Complete 1H candles: all 1H candles closed before t
#   - Current (incomplete) 1H candle: NOT used for signals
```

This prevents the common bug where higher TF candles include future data.

---

## 4. Walk-Forward Validation

### 4.1 Protocol

Walk-forward validation splits the data into rolling in-sample (IS) and out-of-sample (OOS) windows:

```
Total data: [──────────────────────────────────────]

Window 1:   [IS: 6 months][OOS: 2 months]
Window 2:        [IS: 6 months][OOS: 2 months]
Window 3:             [IS: 6 months][OOS: 2 months]
...

Step size: 1 month
```

### 4.2 Parameters

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Training window | 180 days (6 months) | Captures full market cycles |
| Testing window | 60 days (2 months) | Sufficient for statistical significance |
| Step size | 30 days (1 month) | Granular progression |
| Min trades per window | 25 | Statistical minimum |

### 4.3 Evaluation

For each OOS window, compute all metrics independently. The final validation uses **only OOS metrics** aggregated across all windows.

---

## 5. Monte Carlo Stress Testing

### 5.1 Trade Permutation

```
1. Take the complete list of trade results (PnL per trade)
2. Randomly shuffle the order (preserving trade characteristics)
3. Rebuild the equity curve from shuffled sequence
4. Repeat 1,000 times
5. Analyze distribution of outcomes
```

### 5.2 Metrics from Monte Carlo

| Metric | What it tells us |
|--------|------------------|
| Median final equity | Expected outcome |
| 5th percentile final equity | Worst realistic scenario |
| 95th percentile max drawdown | Worst realistic drawdown |
| Probability of ruin (equity < 50%) | Tail risk |
| 95% CI on Sharpe ratio | Confidence in Sharpe estimate |

### 5.3 Pass/Fail

- 5th percentile equity must be > initial capital (no expected loss)
- 95th percentile drawdown must be < 25%
- Probability of ruin must be < 1%

---

## 6. Regime-Segmented Analysis

Performance is broken down by each of the 6 regime states:

| Regime | Metrics Computed |
|--------|-----------------|
| RISK_ON | Sharpe, Sortino, Win rate, PF, Max DD, # trades |
| RISK_OFF | Same |
| RANGE | Same |
| TREND | Same |
| EXPANSION | Same |
| CHAOTIC | Should show 0 trades (no trading allowed) |

### Pass Criteria

- Strategy must be profitable in at least 4 of 5 active regimes
- No single regime should contribute > 60% of total profit (robustness)
- CHAOTIC regime must show exactly 0 trades

---

## 7. Performance Metrics

### 7.1 Required Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| Sharpe Ratio | (R̄ - Rf) / σ(R) × √252 | > 2.0 (stretch: 2.5) |
| Sortino Ratio | (R̄ - Rf) / σ_down(R) × √252 | > 2.0 |
| Calmar Ratio | Annual return / Max drawdown | > 1.5 |
| Profit Factor | Gross profit / Gross loss | > 1.5 |
| Win Rate | # winning trades / # total trades | > 60% (stretch: 65%) |
| Expectancy | Avg_win × win_rate - Avg_loss × loss_rate | > 0 |
| Max Drawdown | Max peak-to-trough decline | < 15% |
| Avg Win / Avg Loss | Mean winning PnL / Mean losing PnL | > 1.0 |

### 7.2 Tail Risk Metrics

| Metric | Formula |
|--------|---------|
| Skewness | Third moment of return distribution |
| Kurtosis | Fourth moment (excess kurtosis) |
| VaR (95%) | 5th percentile of daily returns |
| VaR (99%) | 1st percentile of daily returns |
| CVaR (95%) | Mean of returns below VaR(95%) |
| CVaR (99%) | Mean of returns below VaR(99%) |

### 7.3 Supplementary Metrics

- Max consecutive wins / losses
- Average trade duration
- Monthly returns table (year × month pivot)
- Rolling Sharpe (60-day window)
- Ulcer Index
- Omega Ratio

---

## 8. Validation Checklist

### 8.1 Pre-Live Deployment Gate

| # | Check | Target | Pass/Fail |
|---|-------|--------|-----------|
| 1 | Win rate | > 60% | |
| 2 | Sharpe ratio | > 2.0 | |
| 3 | Sortino ratio | > 2.0 | |
| 4 | Profit factor | > 1.5 | |
| 5 | Max drawdown | < 15% | |
| 6 | Calmar ratio | > 1.5 | |
| 7 | Min trades | > 300 | |
| 8 | Walk-forward OOS Sharpe | > 1.5 | |
| 9 | OOS Sharpe / IS Sharpe | > 50% | |
| 10 | Monte Carlo 5th pctile equity | > initial | |
| 11 | Monte Carlo ruin probability | < 1% | |
| 12 | Profitable in ≥4 regimes | Yes | |
| 13 | No concentration (regime < 60% profit) | Yes | |
| 14 | CHAOTIC regime: 0 trades | Yes | |
| 15 | No martingale patterns detected | Yes | |
| 16 | All risk limits respected | Yes | |

**ALL 16 checks must PASS before live deployment.**

---

## 9. Anti-Overfitting Guards

### 9.1 Probability of Backtest Overfitting (PBO)

```
Compare IS vs OOS Sharpe across all walk-forward windows.
PBO = fraction of windows where OOS Sharpe < 0
Target: PBO < 25%
```

### 9.2 Degradation Ratio

```
degradation = OOS_Sharpe / IS_Sharpe
If degradation < 0.5: FAIL (likely overfit)
If degradation < 0.7: WARNING
If degradation > 0.7: PASS
```

### 9.3 Parameter Sensitivity

The system uses **fixed parameters** (not optimized per-asset):
- RSI period: 14 (industry standard)
- MACD: 12/26/9 (industry standard)
- ADX: 14 (industry standard)
- ATR: 14 (industry standard)
- Moving averages: 20/50/200 (widely used)

These are not optimized because:
1. They are industry conventions with decades of empirical support
2. Optimizing them on our data would create overfitting risk
3. The signal scoring model works by combining multiple indicators, not by perfecting any single one

### 9.4 Optimization Guardrails

What we DO NOT optimize:
- Technical indicator periods
- Signal weights within categories
- Threshold values (70 for trade entry)
- Risk percentages

What we CAN adjust (with walk-forward validation):
- Regime-adaptive weight modifiers (bounded 0.5-1.5)
- Equity governor MA periods (bounded 15-30 and 40-60)

---

## 10. Constraints — Explicitly Stated

1. **No curve-fitting**: Parameters are industry standards or statistically justified
2. **No look-ahead bias**: Replay engine enforces chronological-only access
3. **No survivorship bias**: Instruments are pre-defined, not selected post-hoc
4. **All assumptions stated**: See Algorithm Spec section 8
5. **All thresholds justified**: Each threshold has documented statistical basis
6. **Slippage and fees modeled**: Every simulated trade includes realistic friction
7. **Walk-forward required**: In-sample metrics alone are insufficient
8. **Monte Carlo required**: Sequence risk must be quantified
