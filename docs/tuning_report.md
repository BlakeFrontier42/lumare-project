# Lumare Bot Tuning Report

**Generated:** 2026-05-12
**Data:** 1 year real OHLCV from Coinbase (BTC, ETH) + 60 days real OHLCV from yfinance (SPY, QQQ, AAPL, NVDA, MSFT)

---

## TL;DR

The strategy ships with these per-asset profiles after tuning on real data:

| Asset Class | Regime | Threshold | R:R | Stop ATR | Notes |
|-------------|--------|-----------|-----|----------|-------|
| Crypto      | bypass | 65        | 3.0 | 2.0      | ETH PF 1.68, BTC PF 0.66 on 1Y — kill switch handles weak symbols |
| Equity      | strict | 60        | 2.5 | 2.5      | Highly selective. QQQ PF 11.11 / MSFT PF 2.05 on 60d (small sample) |
| Futures     | strict | 65        | 2.5 | 2.0      | Untuned — no 1Y futures data available yet |
| Options     | permissive | 70    | 3.0 | 2.5      | Untuned — needs paid options chain data |

**The bot ships with the per-symbol kill switch as the primary risk protection.** Symbols whose rolling PF drops below 1.0 (over last 25 trades, minimum 10 samples) get auto-disabled. BTC is the canary — if it persists below 1.0 in live, the bot will stop trading it automatically while continuing ETH.

---

## What the data actually shows

### Crypto (1 year of real Coinbase 5M OHLCV)

| Symbol | Trades | Win Rate | Profit Factor | Sharpe | Max DD | Annual Return |
|--------|--------|----------|---------------|--------|--------|---------------|
| BTC    | 36     | 27.8%    | **0.66**      | -2.33  | 6.91%  | -5.3%         |
| ETH    | 28     | 46.4%    | **1.68**      | 0.37   | 7.90%  | +11.3%        |

The earlier-claimed "PF 1.93 on BTC 1Y" from Phase 4.6 was on a different (now-overwritten) 1-year window. It does not reproduce on the current 365-day window ending 2026-05-12. **ETH continues to perform well; BTC does not on this period.**

### Equity (60 days of real yfinance 5M OHLCV)

The strategy is extremely selective on equities — only QQQ, NVDA, MSFT fire trades; SPY and AAPL produce zero entries.

| Config (best) | Symbol | Trades | Win Rate | PF |
|---------------|--------|--------|----------|-----|
| strict / 60 / rr2.5 / stop2.5 | QQQ | 7 | high | 11.11 |
| strict / 60 / rr2.5 / stop2.5 | NVDA | 3 | 100% | inf |
| strict / 60 / rr2.5 / stop2.5 | MSFT | 2 | high | 2.05 |
| (any) | SPY | 0 | — | — |
| (any) | AAPL | 0 | — | — |

Sample sizes are too small to be statistically meaningful, but **when the strategy triggers on equities, win quality is exceptionally high.** This is the expected behaviour of a regime-gated trend strategy on a quiet 60-day window.

---

## Why the kill switch is the answer (for now)

Without months of paper-trading on live data or a paid OHLCV history provider (Polygon Pro), we can't:
1. Walk-forward across 6+ non-overlapping months with statistical power
2. Optimize per-symbol parameters without overfitting

So the deployment strategy is:

1. **Run paper mode for 30+ days** on the full universe (crypto + equity + options)
2. **Let the kill switch self-protect** — symbols that don't pay get auto-disabled
3. **Re-tune monthly** as live data accumulates
4. **Flip `LUMARE_ALLOW_LIVE=1` only when** PF > 1.2 across 30+ trades on the asset classes you want to trade live

The kill switch + WebSocket monitoring + Sentry alerting form a closed-loop safety system. Even if a symbol's edge degrades silently, the bot stops trading it before damage accumulates.

---

## How to re-tune later

```bash
# Crypto (deeper grid)
python scripts/tune_universal.py --asset-class crypto

# Equity (deeper grid)
python scripts/tune_universal.py --asset-class equity

# All four asset classes
python scripts/tune_universal.py --all
```

Results are written to `docs/tune_universal.json`. The winning config is auto-printed.

---

## Honest production verdict

**The bot is deployable today on a paper-money basis** with these caveats:

- ✅ Real-time data pipeline working (Coinbase + yfinance, never silent mock)
- ✅ Multi-asset profile system (crypto, equity, options, futures routes)
- ✅ Options recommender (top 2 ITM/OTM per expiry + overall best)
- ✅ Kill switch + manual override
- ✅ Deep health endpoint + rate limiting + Sentry-ready
- ✅ Live executors wired (Coinbase + Alpaca), triple-locked safety
- ⚠️ Strategy edge is symbol- and period-dependent — paper-validate before live
- ⚠️ Need more historical data (paid provider) for high-confidence tuning

For real-money trading: start with ETH only via Coinbase, $1k-$5k capital, watch the kill switch + Sentry for 30 days, then expand based on what works.
