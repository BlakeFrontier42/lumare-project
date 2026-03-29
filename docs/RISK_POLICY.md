# LUMARE MIE — Risk Policy Document
## Institutional-Grade Risk Management Framework

> Version: 1.0.0
> Classification: Internal — Mandatory Compliance
> Last Updated: 2026-03-23
> Status: ACTIVE — All rules are non-negotiable

---

## 1. Risk Philosophy

This system operates under the principle: **Survival > Aggression**.

The risk engine has absolute authority over all trade decisions. No signal score, no matter how high, can override a risk limit. The system is designed to survive black swan events, extended drawdowns, and regime changes while preserving capital for future compounding.

---

## 2. Risk Limits Summary

| Parameter | Limit | Enforcement |
|-----------|-------|-------------|
| Base risk per trade | 1.0% of portfolio | Hard |
| Risk range | 0.75% — 1.25% | Dynamic (score + regime) |
| Max portfolio heat | 20% | Hard |
| Max correlated positions | 3 | Hard (ρ > 0.7) |
| Max daily loss | 4% | Hard — immediate halt |
| Drawdown pause | -10% | Automatic |
| Drawdown reduce | -12% | Automatic — 50% size cut |
| Drawdown shutdown | -15% | Hard — kill switch |
| Max leverage (crypto) | 8x | Hard (20x locked until 6mo validation) |
| Max daily VaR (99%) | 5% | Hard |
| Max position size | 5% of ADV | Hard |
| Order type | Limit only | Hard — market orders blocked |

---

## 3. Position Sizing Formula

```
risk_pct = f(conviction_score, regime)
    score 70-84: risk_pct = 1.0%
    score 85+:   risk_pct = 1.25%
    regime modifier: × equity_governor_modifier (0.5-1.0)

risk_amount = portfolio_value × risk_pct
stop_distance = |entry_price - stop_price|
position_size = risk_amount / stop_distance

For crypto with leverage:
    margin_required = (entry_price × position_size) / leverage
    leverage = f(stop_distance_pct)
        < 0.5%: max 8x
        < 1.0%: max 5x
        > 1.0%: max 2-3x
```

---

## 4. Drawdown Controls — Cascading Response

```
Stage 1: Drawdown reaches -10%
    Action: PAUSE all new trades
    Existing positions: managed normally (stops/TPs active)
    Resume: when drawdown recovers above -8%

Stage 2: Drawdown reaches -12%
    Action: REDUCE all new position sizes by 50%
    Existing positions: consider tightening stops
    Resume: when drawdown recovers above -10%

Stage 3: Drawdown reaches -15%
    Action: HARD SHUTDOWN — kill switch activated
    All open orders cancelled
    No new trades until manual review
    Existing positions: managed to exit only
    Resume: MANUAL ONLY after full review
```

---

## 5. Equity Governor — Meta-Risk Layer

The equity curve itself is monitored as a meta-signal:

```
equity_20ma = 20-period simple moving average of portfolio value
equity_50ma = 50-period simple moving average of portfolio value

IF portfolio_value >= ATH × 0.99:
    modifier = 1.0 (normal)
ELIF portfolio_value < equity_50ma:
    modifier = 0.50 (defensive)
ELIF portfolio_value < equity_20ma:
    modifier = 0.75 (caution)
ELIF recovering_from_drawdown:
    modifier = linear_ramp(0.50 → 1.00, over 20 bars)

All position sizes are multiplied by this modifier.
Size increases are gradual (max +0.25 per bar).
Size decreases are immediate (safety first).
```

---

## 6. Correlation Controls

```
correlation_matrix = rolling_pearson(daily_returns, window=30)

For any new trade:
    1. Calculate correlation with all open positions
    2. Count positions where |ρ| > 0.7
    3. If count ≥ 3: REJECT trade
    4. If count = 2: ALLOW but flag for monitoring

This prevents concentration in a single factor.
Example: BTC long + ETH long count as correlated (ρ ≈ 0.85)
```

---

## 7. VaR (Value at Risk)

```
Method: Parametric (primary) + Historical (validation)
Confidence: 99%
Lookback: 252 trading days
Max portfolio daily VaR: 5%

Parametric VaR = portfolio_value × Z(0.99) × σ_daily × √(holding_period)
    where Z(0.99) = 2.326
    σ_daily = portfolio standard deviation of daily returns

If VaR > 5% of portfolio:
    No new positions until VaR decreases
    Consider reducing existing positions
```

---

## 8. Kill Switch Protocol

**Activation triggers:**
- Manual activation (human operator)
- Drawdown reaches -15%
- Daily loss reaches 4%
- 5+ consecutive system errors
- API connectivity loss > 15 minutes
- Anomalous behavior detected (rapid equity drop, unusual trade frequency)

**Kill switch actions:**
1. Cancel ALL open orders on ALL exchanges
2. Block ALL new order submissions
3. Log activation with timestamp and reason
4. Continue monitoring existing positions
5. Alert human operator

**Deactivation:**
- MANUAL ONLY
- Requires review of:
  - Root cause of activation
  - Current market conditions
  - System health check
  - Portfolio state assessment

---

## 9. Prohibited Behaviors

These are hardcoded restrictions that cannot be overridden:

| Behavior | Enforcement | Rationale |
|----------|-------------|-----------|
| Market orders | Order type check — rejected | Prevents slippage in fast markets |
| Martingale (doubling after loss) | Size tracking — blocked | Mathematically guaranteed ruin |
| Averaging down | Position tracking — blocked | Adds to losers, magnifies losses |
| Revenge scaling | Loss tracking — blocked | Emotional response, not systematic |
| Live capital before validation | Mode gate — blocked | Must pass all metrics first |
| Skip risk checks | Enforcement chain — impossible | Risk engine has absolute priority |

---

## 10. Daily Risk Monitoring Checklist

Automated by the Watchdog system:

- [ ] Portfolio drawdown within limits
- [ ] Daily P&L within limits
- [ ] Portfolio heat within 20%
- [ ] Correlation exposure within limits
- [ ] VaR within limits
- [ ] All API connections active
- [ ] Data freshness < 10 minutes
- [ ] No anomalous trade patterns
- [ ] Kill switch status: inactive
- [ ] System resources healthy

---

## 11. Risk Event Logging

Every risk event is logged to the database with:
- Timestamp (UTC)
- Event type (drawdown_breach, daily_cap, correlation_limit, etc.)
- Severity (INFO, WARNING, CRITICAL)
- Current portfolio state
- Action taken
- Source system

Risk events are never deleted. Full audit trail maintained.

---

## 12. Stress Testing Requirements

Before any live capital deployment:

| Scenario | Required Test |
|----------|--------------|
| 2008 Financial Crisis | Simulate on equivalent crypto drawdown |
| March 2020 COVID Crash | 30%+ drawdown in 48 hours |
| May 2021 Crypto Crash | 50%+ BTC drawdown |
| Nov 2022 FTX Collapse | Exchange risk + rapid deleveraging |
| Monte Carlo | 1000 trade-order permutations |
| Walk-forward | 6-month train / 2-month test rolling windows |
| Regime-segmented | Performance breakdown by all 6 regime states |

All scenarios must show:
- Max drawdown < 15%
- No kill switch activation in non-extreme scenarios
- Recovery within 60 days from maximum drawdown
