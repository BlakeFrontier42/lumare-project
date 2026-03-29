# LUMARE MIE — Simulation & Live Execution Protocol

> Version: 1.0.0
> Last Updated: 2026-03-23

---

## 1. Execution Modes

| Mode | Capital | Exchange | Purpose |
|------|---------|----------|---------|
| Backtest | Simulated | None (replay) | Historical validation |
| Paper | Simulated | Paper APIs | Real-time validation |
| Live | Real | Blowfin/Alpaca | Production trading |

### Progression Gate

```
Backtest PASS → Paper trading (min 30 days) → Live review → Live deployment
```

No stage can be skipped. Each gate requires human review.

---

## 2. Paper Trading Simulation Framework

### 2.1 Simulation Models

**Slippage Model:**
```
total_slippage = base_slippage + volatility_component + size_component + noise

base_slippage = 5 bps (basis points)
volatility_component = (current_vol / baseline_vol) × base × 0.5
size_component = √(order_notional / (ADV × price)) × 10 bps
noise = Normal(0, base × 0.2)
```

**Fee Model:**
```
Maker (limit orders): 0.05% of notional
Taker (market orders): 0.10% of notional (DISABLED — limit only)
```

**Latency Model:**
```
latency = max(0, Normal(50ms, 15ms))
```

**Fill Probability:**
```
Limit order fill rate: 85%
Partial fill (when not fully filled): Uniform(50%, 99%)
Partial fill probability: 50% of unfilled attempts
```

**Market Impact (Almgren-Chriss Simplified):**
```
impact_bps = √(order_quantity / average_daily_volume) × 100
```

**Liquidity Constraint:**
```
Max position size = 5% of average daily volume
```

### 2.2 Position Limit Enforcement

| Limit | Value | Enforcement |
|-------|-------|-------------|
| Max position per instrument | 5% of ADV | Pre-order check |
| Max notional per position | Configurable | Pre-order check |
| Max margin utilization | Based on leverage rules | Pre-order check |
| Max open orders | Unlimited (but monitored) | Watchdog check |

### 2.3 Audit Trail

Every action is logged:

```
Orders:  order_id, timestamp, symbol, side, type, price, quantity, leverage, status
Fills:   fill_id, order_id, timestamp, price, quantity, fees, slippage, latency, impact
Cancels: order_id, timestamp, reason
```

Full reconstruction of every order book interaction is possible from logs.

---

## 3. Performance Tracking Dashboard Schema

### 3.1 Real-Time Metrics

```json
{
  "portfolio": {
    "total_value": 105234.50,
    "cash": 82100.00,
    "margin_used": 18500.00,
    "unrealized_pnl": 4634.50,
    "realized_pnl": 2340.00,
    "total_fees": 156.30,
    "num_positions": 2,
    "num_open_orders": 1
  },
  "performance": {
    "daily_return": 0.0234,
    "weekly_return": 0.0512,
    "monthly_return": 0.0823,
    "sharpe_rolling_30d": 2.34,
    "max_drawdown": -0.0456,
    "win_rate": 0.64,
    "profit_factor": 1.72,
    "total_trades": 47,
    "avg_trade_duration_hours": 8.5
  },
  "risk": {
    "portfolio_heat": 0.12,
    "daily_pnl": 0.0234,
    "var_99": 0.034,
    "correlation_exposure": 2,
    "drawdown_level": "NORMAL",
    "equity_governor": "NORMAL",
    "kill_switch": false
  },
  "regime": {
    "current": "TREND",
    "confidence": 0.82,
    "duration_hours": 72,
    "allowed_strategies": ["trend_following", "momentum"]
  }
}
```

### 3.2 Position Detail

```json
{
  "symbol": "BTCUSDT",
  "side": "LONG",
  "quantity": 0.15,
  "avg_entry": 67250.00,
  "current_price": 68100.00,
  "leverage": 5,
  "unrealized_pnl": 637.50,
  "unrealized_pnl_pct": 0.0126,
  "stop_price": 66500.00,
  "tp1_price": 68000.00,
  "tp1_hit": true,
  "tp2_price": 68750.00,
  "opened_at": "2026-03-22T14:30:00Z",
  "duration_hours": 24.5,
  "risk_amount": 112.50,
  "risk_pct_portfolio": 0.0107
}
```

### 3.3 Trade History

```json
{
  "trade_id": "abc123",
  "symbol": "ETHUSDT",
  "direction": "SHORT",
  "entry_price": 3450.00,
  "exit_price": 3380.00,
  "quantity": 2.5,
  "leverage": 3,
  "pnl": 525.00,
  "pnl_pct": 0.0203,
  "r_multiple": 1.8,
  "duration_hours": 12.3,
  "score_at_entry": 78,
  "regime_at_entry": "RISK_OFF",
  "fees": 17.50,
  "slippage_bps": 4.2,
  "explanation_id": "exp456"
}
```

---

## 4. Logging & Audit Architecture

### 4.1 Log Levels

| Level | Use Case |
|-------|----------|
| DEBUG | Engine internals, indicator values, bar-by-bar data |
| INFO | Trade decisions, cycle completions, regime changes |
| WARNING | Risk limit approaches, data staleness, partial fills |
| CRITICAL | Kill switch, circuit breakers, system errors |

### 4.2 Log Storage

```
logs/
├── lumare_2026-03-23.log          # Daily rotating file
├── lumare_2026-03-22.log
├── trades/
│   └── trade_log_2026-03.jsonl    # Structured trade log (JSON lines)
├── signals/
│   └── signal_log_2026-03.jsonl   # Every signal computation
└── risk/
    └── risk_events_2026-03.jsonl  # All risk events
```

### 4.3 Database Tables

```sql
-- All OHLCV data
candles (symbol, timeframe, timestamp, open, high, low, close, volume)

-- Every trade with full lifecycle
trades (id, symbol, direction, entry_price, exit_price, quantity, leverage,
        pnl, fees, stop, tp1, tp2, status, score, regime, opened_at, closed_at)

-- Every signal computation
signal_logs (timestamp, symbol, direction, score, components, regime, trade_eligible)

-- Regime transitions
regime_logs (timestamp, regime, confidence, factors, transition_from)

-- Portfolio snapshots (every cycle)
portfolio_snapshots (timestamp, total_value, cash, positions, unrealized, realized)

-- Risk events
risk_events (timestamp, event_type, description, severity, source)

-- Performance snapshots (daily)
performance_snapshots (date, sharpe, sortino, max_dd, win_rate, pf, total_trades)
```

---

## 5. Live Trading Mode

### 5.1 Prerequisites

All of the following must be true:
1. Backtest validation: ALL 16 checks PASSED
2. Paper trading: minimum 30 days with positive performance
3. Paper metrics within 80% of backtest metrics
4. Human review and sign-off
5. API keys configured and tested
6. Kill switch tested and functional
7. Watchdog operational

### 5.2 Live Mode Differences

| Aspect | Paper | Live |
|--------|-------|------|
| Orders | Simulated | Real Blowfin/Alpaca API |
| Slippage | Modeled | Real |
| Fees | Modeled | Real |
| Fills | Probabilistic | Exchange-determined |
| Capital | Virtual | Real money |
| Kill switch | Simulated | Cancels real orders |
| Watchdog interval | 60s | 30s |

### 5.3 Live Safety Layers

```
Layer 1: Engine risk checks (position size, heat, correlation, drawdown)
Layer 2: Equity governor (meta-risk on equity curve)
Layer 3: Watchdog circuit breakers (continuous monitoring)
Layer 4: Exchange-level limits (set via API)
Layer 5: Human monitoring (alerts sent)
```

### 5.4 Scaling Protocol

```
Month 1: $10,000 max capital, 2x max leverage
Month 2: $25,000 max, 3x max leverage (if metrics hold)
Month 3: $50,000 max, 5x max leverage
Month 6: Full allocation, 8x max leverage
Month 6+: Consider 20x unlock (if 6-month validation passes)
```

---

## 6. Deployment Readiness Checklist

### Infrastructure
- [ ] Python backend deployed (Railway/Docker)
- [ ] SQLite database initialized
- [ ] Environment variables configured
- [ ] API keys tested (all feeds returning data)
- [ ] Logging configured and writing to disk
- [ ] Watchdog operational

### Validation
- [ ] Backtest: all 16 checks PASS
- [ ] Walk-forward: OOS Sharpe > 1.5
- [ ] Monte Carlo: ruin probability < 1%
- [ ] Regime analysis: profitable in ≥4 regimes
- [ ] 30-day paper trading complete
- [ ] Paper metrics within 80% of backtest

### Risk Controls
- [ ] Kill switch tested (activate/deactivate)
- [ ] Drawdown breakers tested at each level
- [ ] Daily loss cap tested
- [ ] Correlation limits tested
- [ ] VaR calculation validated
- [ ] Market order rejection tested

### Operations
- [ ] Human monitoring schedule established
- [ ] Alert system configured (email/SMS/Slack)
- [ ] Escalation procedures documented
- [ ] Backup plan for API outages
- [ ] Emergency position closure procedure tested
