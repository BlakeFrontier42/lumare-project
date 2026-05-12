# Lumare — Deployment Summary

**Status:** Deployment-ready on paper-trading basis. Live-trading wired but DISARMED by default.
**Date:** 2026-05-12

---

## Ship-Ready Checklist

### Backend
- [x] FastAPI + uvicorn on port 8000
- [x] 73 routes including bot, options recommender, alpha, scoring, portfolio, etc.
- [x] WebSocket `/ws/bot` streams full snapshot at 1Hz
- [x] WebSocket `/ws/prices` streams Kraken+yfinance prices
- [x] CORS lockdown via `LUMARE_CORS_ORIGINS` env
- [x] Rate limiting (10/10s on mutations, 20/60s on expensive, 100/10s on reads)
- [x] Deep health probe at `/api/health/deep`
- [x] Sentry integration (opt-in via `SENTRY_DSN`)

### Bot
- [x] `/api/bot/start` accepts mode, asset_class, min_score, symbols, interval
- [x] Real-time signals + position fills via paper sim or live broker
- [x] Per-symbol kill switch (rolling PF < 1.0 → auto-disable)
- [x] Manual kill + reset endpoints
- [x] Status surfaces data provenance (live vs mock) per symbol

### Live Execution (DISARMED until env vars set)
- [x] **Coinbase Advanced Trade** for crypto (HMAC-signed, limit-only)
- [x] **Alpaca** for US equities + options (paper API default, flip URL for live)
- [x] **Blowfin** for crypto perpetuals (HMAC-signed)
- [x] **Polymarket** for prediction markets
- [x] Triple-locked safety: `LUMARE_ALLOW_LIVE=1` + API keys + `mode="live"` all required

### Data Sources
- [x] **Coinbase Exchange** public OHLCV (no API key needed — paginated 1Y BTC = 104k bars works)
- [x] **yfinance** for equity OHLCV (5M: 60d, 1H: 2y, 1D: 5y)
- [x] **Polygon** (optional, paid) for equity 1-min real-time
- [x] **FRED** (optional) for macro
- [x] **Unusual Whales / Quiver Quant** (optional) for flow + congressional

### Frontend (Next.js 14)
- [x] 30 pages (bot, alpha, options, screener, watchlist, journal, settings, etc.)
- [x] Bot page: positions/signals/activity/trades all backed by real API
- [x] Options page: Best Plays recommender at top, full chain, flow, strategy builder
- [x] LIVE DATA / MOCK DATA badge on bot page (never silently mocked)
- [x] Kill-switch banner with re-enable button

### Database
- [x] SQLite default (`data/lumare.db`)
- [x] 9 tables: candles, trades, signal_logs, regime_logs, portfolio_snapshots, risk_events, performance_snapshots, sqlite_sequence
- [x] Postgres migration path documented (storage layer is pluggable)
- [x] 104k bars of 1Y BTC + 104k ETH + 2y 1H equity already loaded

### Documentation
- [x] `RUN.md` — 5-minute deploy guide + API reference + deployment checklist
- [x] `.env.example` — every env var with comments
- [x] `docs/tuning_report.md` — what the strategy actually does on real data
- [x] `docs/cocreator-handoff.md` — full project briefing for handoff
- [x] OpenAPI auto-docs at `/docs`

---

## What's Honestly Tuned vs Untuned

| Asset Class | 1Y Real-Data Tuned? | Verdict |
|-------------|---------------------|---------|
| Crypto      | ETH yes (PF 1.68), BTC no (PF 0.66) | Trade ETH first, let kill switch disable BTC if it underperforms |
| Equity      | 60-day data only — too short for stat-sig tuning | Strategy is highly selective. Paper-trade 30+ days first |
| Options     | Recommender works (Black-Scholes + composite scoring on 5 dimensions). Bot routing works. Not backtested. | Use recommender for trade picks; bot for paper execution |
| Futures     | No data available yet | Wired but not validated |

---

## Recommended Live-Trading Path

1. **Week 1-2 (paper):** Start the bot in paper mode on crypto with BTC+ETH+SOL. Watch the LIVE DATA badge stay green. Verify position fills, kill switch behaviour, regime classification.

2. **Week 3-4 (paper):** Add equity (SPY, QQQ, AAPL, NVDA, MSFT) and options modes. Run all four asset classes through 30+ days. Track per-asset-class PF in the bot's `/api/bot/performance` endpoint.

3. **Week 5+ (live, conservative):** If 30-day rolling PF > 1.2 on a given symbol+asset-class combo:
   - Set `COINBASE_API_KEY` + `COINBASE_API_SECRET`
   - Set `LUMARE_ALLOW_LIVE=1`
   - Start bot with `mode="live"`, $1k-$5k starting capital
   - Trade ONLY symbols that proved out in paper

4. **Ongoing:** Re-tune monthly via `scripts/tune_universal.py`. Track Sentry alerts. Watch kill switch arms.

---

## The single thing that would most improve the bot

**A paid OHLCV provider with 2-5 years of intraday data.** Currently we're limited to:
- Coinbase free: 1Y of 5M (good)
- yfinance free: 60 days of 5M (the limiting factor)

With 2-5 years of 5M equity data, the equity grid would have statistical power. Right now equity tuning is hopeful guidance, not validated edge.

Options costs:
- Polygon Stocks Starter: $29/mo (5 years of historical intraday)
- Tiingo: $30/mo
- Databento: $100/mo (institutional quality)

Recommended: **Polygon Stocks Starter** as the next $29/mo to unlock proper equity tuning.

---

## What runs and what doesn't (final smoke verified 2026-05-12)

```
GET  /api/health/deep           → status=ok (engine + storage + coinbase + autobot all green)
POST /api/bot/start             → bot running on real Coinbase BTC/ETH/SOL data
GET  /api/bot/positions         → returns live position with real $80,785 BTC entry
GET  /api/options/recommendations → returns "QQQ 2026-05-15 P 730 composite 82.0"
POST /api/bot/stop              → bot stops cleanly, no zombie state
```

All wired. All real. Ship it.
