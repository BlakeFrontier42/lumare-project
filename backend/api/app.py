"""
Lumare API — FastAPI application.

Provides REST endpoints for the frontend to consume market data,
scoring signals, portfolio state, backtest results, and alpha feeds.
"""

import asyncio
import math
import os
import random
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from backend.api.schemas import (
    BacktestRequest,
    BacktestResultSummary,
    BacktestResultsResponse,
    BacktestRunResponse,
    CandleData,
    CandlesResponse,
    CongressionalTrade,
    CongressionalTradesResponse,
    EngineStatus,
    ErrorResponse,
    FloatProfileResponse,
    FloatSummaryResponse,
    SqueezeCandidate,
    SqueezeCandidatesResponse,
    HealthResponse,
    InsiderTransaction,
    InsiderTransactionsResponse,
    MacroIndicator,
    MacroSnapshotResponse,
    PortfolioSummaryResponse,
    PositionData,
    PriceData,
    PricesResponse,
    RegimeResponse,
    RiskDashboardResponse,
    RiskMetric,
    StressTestResult,
    SignalScore,
    SignalScoreResponse,
    TradeRecord,
    TradesResponse,
)
from backend.api.websocket import ws_manager, notification_manager

# ─── Engine Singleton ────────────────────────────────────

_engine = None
_orchestrator = None
_last_backtest_result = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the LumareEngine and Orchestrator on startup."""
    global _engine, _orchestrator
    try:
        from backend.main import LumareEngine
        from backend.orchestrator.router import Orchestrator
        _engine = LumareEngine()
        _orchestrator = Orchestrator(engine=_engine, settings=_engine.settings)
        logger.info("Lumare API started — engine + orchestrator initialized")

        # Start WebSocket price streaming in the background
        asyncio.create_task(ws_manager.start_price_stream(_engine))

        # Start SL/TP monitoring background task
        asyncio.create_task(_monitor_sl_tp_task(_engine))
    except Exception as exc:
        logger.error(f"Failed to initialize LumareEngine: {exc}")
        _engine = None
        _orchestrator = None
    yield
    ws_manager.stop()
    logger.info("Lumare API shutting down")


# ─── Sentry (production error tracking, opt-in via env) ───────
# Set SENTRY_DSN to enable. No-op when unset, so dev stays untouched.
_SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
        from sentry_sdk.integrations.asyncio import AsyncioIntegration  # type: ignore
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FastApiIntegration(), AsyncioIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE", "0.05")),
            environment=os.getenv("LUMARE_ENV", "production"),
            release=os.getenv("LUMARE_RELEASE", "1.0.0"),
        )
        logger.info("Sentry initialised")
    except ImportError:
        logger.warning(
            "SENTRY_DSN set but sentry-sdk not installed. "
            "Run: pip install 'sentry-sdk[fastapi]'"
        )

app = FastAPI(
    title="Lumare Capital Intelligence API",
    description="REST API for the Lumare Macro Intelligence Engine",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── Rate limiting (in-memory token bucket per client IP) ─────
# Lightweight protection against runaway clients. Production deployments
# behind a reverse proxy should layer their own rate limit at the edge
# (Cloudflare, Caddy, Nginx) — this is a baseline so the API is never
# unprotected. No Redis dep so it works on free-tier deployments.

from collections import defaultdict
from threading import Lock

_RATE_BUCKETS: dict[tuple[str, str], list[float]] = defaultdict(list)
_RATE_LOCK = Lock()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(window_seconds: float, max_calls: int):
    """FastAPI dependency that throws 429 when client exceeds budget."""

    async def _check(request: Request):
        now = time.monotonic()
        key = (_client_ip(request), request.url.path)
        with _RATE_LOCK:
            bucket = _RATE_BUCKETS[key]
            # Evict expired
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.pop(0)
            if len(bucket) >= max_calls:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise HTTPException(
                    429,
                    detail=f"Rate limit exceeded ({max_calls}/{int(window_seconds)}s). "
                           f"Retry in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
    return _check


# Convenience presets for common patterns
_burst_limit = rate_limit(window_seconds=10, max_calls=10)    # mutation calls
_read_limit = rate_limit(window_seconds=10, max_calls=100)    # read calls
_expensive_limit = rate_limit(window_seconds=60, max_calls=20)  # heavy compute


# ─── CORS ────────────────────────────────────────────────
# Production: set LUMARE_CORS_ORIGINS to a comma-separated list of exact
# allowed origins, e.g. "https://app.lumare.io,https://lumare.vercel.app".
# Localhost is always allowed for dev. Empty / unset means localhost-only.

_extra_origins = [
    o.strip()
    for o in os.getenv("LUMARE_CORS_ORIGINS", "").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_extra_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


# ─── Dependencies ────────────────────────────────────────

def get_engine():
    """Dependency that provides the LumareEngine instance."""
    if _engine is None:
        raise HTTPException(
            status_code=503,
            detail="Engine not initialized. The server is starting up or encountered an error.",
        )
    return _engine


# ─── Error Handler ───────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc),
            status_code=500,
        ).model_dump(),
    )


# ─── Health ──────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(
        status="ok" if _engine is not None else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/health/deep", tags=["System"])
async def health_check_deep():
    """Deep health probe for production uptime monitoring.

    Verifies engine, storage, and at least one live data source. Returns
    a structured payload your monitoring service (UptimeRobot, BetterStack,
    Datadog, etc.) can alert on.
    """
    status = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "checks": {},
    }

    # Engine check
    status["checks"]["engine"] = "ok" if _engine is not None else "fail"

    # Storage check — quick SELECT
    if _engine is not None:
        try:
            _engine.storage._get_connection().execute("SELECT 1").fetchone()
            status["checks"]["storage"] = "ok"
        except Exception as exc:
            status["checks"]["storage"] = f"fail: {exc}"

    # Live data check — Coinbase ping
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as c:
            r = await c.get("https://api.exchange.coinbase.com/time")
            status["checks"]["coinbase"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except Exception as exc:
        status["checks"]["coinbase"] = f"fail: {exc}"

    # Bot autobot health
    try:
        from backend.orchestrator.autobot import autobot
        bot_status = autobot.get_status()
        status["checks"]["autobot"] = {
            "running": bot_status.get("running", False),
            "any_mock_data": bot_status.get("any_mock_data", False),
            "kill_switch": bot_status.get("kill_switch", False),
        }
    except Exception as exc:
        status["checks"]["autobot"] = f"fail: {exc}"

    # Aggregate
    all_ok = all(
        v == "ok" or (isinstance(v, dict) and not v.get("kill_switch"))
        for v in status["checks"].values()
    )
    if not all_ok:
        status["status"] = "degraded"
    return status


# ═══════════════════════════════════════════════════════════
# Market Data
# ═══════════════════════════════════════════════════════════

@app.get("/api/markets/prices", response_model=PricesResponse, tags=["Markets"])
async def get_prices(engine=Depends(get_engine)):
    """Get latest prices for all watched symbols via Kraken (crypto) + equities feed."""

    crypto_symbols = engine.settings.instruments.crypto_pairs
    equity_symbols = engine.settings.instruments.equity_symbols
    prices = []

    # ── Crypto: batch fetch from Kraken ──
    _KRAKEN_MAP = {
        "BTCUSDT": "XBTUSD", "ETHUSDT": "ETHUSD", "SOLUSDT": "SOLUSD",
        "XRPUSDT": "XRPUSD", "ADAUSDT": "ADAUSD", "AVAXUSDT": "AVAXUSD",
        "DOGEUSDT": "XDGUSD", "LINKUSDT": "LINKUSD", "DOTUSDT": "DOTUSD",
        "MATICUSDT": "MATICUSD",
    }
    # Kraken returns inconsistent keys — build a reverse map of all possible forms
    _KRAKEN_ALIASES = {
        "XBTUSD": ["XXBTZUSD", "XBTUSD"],
        "ETHUSD": ["XETHZUSD", "ETHUSD"],
        "SOLUSD": ["SOLUSD"],
        "XRPUSD": ["XXRPZUSD", "XRPUSD"],
        "ADAUSD": ["ADAUSD"],
        "AVAXUSD": ["AVAXUSD"],
        "XDGUSD": ["XXDGZUSD", "XDGUSD"],
        "LINKUSD": ["LINKUSD"],
        "DOTUSD": ["DOTUSD"],
        "MATICUSD": ["MATICUSD"],
    }
    kraken_pairs = [_KRAKEN_MAP.get(s, s) for s in crypto_symbols if s in _KRAKEN_MAP]
    kraken_data = {}
    if kraken_pairs:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(
                    f"https://api.kraken.com/0/public/Ticker?pair={','.join(kraken_pairs)}"
                )
                if resp.status_code == 200:
                    kraken_data = resp.json().get("result", {})
        except Exception as exc:
            logger.warning(f"Kraken batch fetch failed: {exc}")

    def _find_kraken(pair: str) -> dict | None:
        # Direct lookup
        if pair in kraken_data:
            return kraken_data[pair]
        # Alias lookup
        for alias in _KRAKEN_ALIASES.get(pair, []):
            if alias in kraken_data:
                return kraken_data[alias]
        return None

    for sym in crypto_symbols:
        kp = _KRAKEN_MAP.get(sym)
        kd = _find_kraken(kp) if kp else None
        if kd:
            last = float(kd["c"][0])
            open_24h = float(kd["o"])
            change_pct = ((last - open_24h) / open_24h * 100) if open_24h else 0
            prices.append(PriceData(
                symbol=sym,
                price=last,
                change_24h=round(change_pct, 2),
                volume_24h=float(kd["v"][1]),
                high_24h=float(kd["h"][1]),
                low_24h=float(kd["l"][1]),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
        else:
            prices.append(PriceData(symbol=sym, price=0.0, timestamp=datetime.now(timezone.utc).isoformat()))

    # ── Equities: use equities feed ──
    for sym in equity_symbols:
        try:
            quote = await engine.equities_feed.get_quote(sym)
            prices.append(PriceData(
                symbol=sym,
                price=float(quote.get("price", 0) or quote.get("last_price", 0)),
                change_24h=float(quote.get("change_pct", 0) or quote.get("change_24h_pct", 0)),
                volume_24h=float(quote.get("volume", 0) or quote.get("volume_24h", 0)) or None,
                high_24h=float(quote.get("high", 0) or quote.get("high_24h", 0)) or None,
                low_24h=float(quote.get("low", 0) or quote.get("low_24h", 0)) or None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
        except Exception as exc:
            logger.warning(f"Failed to fetch equity price for {sym}: {exc}")
            prices.append(PriceData(symbol=sym, price=0.0, timestamp=datetime.now(timezone.utc).isoformat()))

    return PricesResponse(
        prices=prices,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/markets/candles/{symbol}", response_model=CandlesResponse, tags=["Markets"])
async def get_candles(
    symbol: str,
    timeframe: str = Query(default="1H", description="Candle timeframe: 1M, 5M, 15M, 1H, 4H, 1D"),
    start: Optional[str] = Query(default=None, description="Start time ISO-8601"),
    end: Optional[str] = Query(default=None, description="End time ISO-8601"),
    limit: int = Query(default=200, ge=1, le=2000, description="Max candles to return"),
    engine=Depends(get_engine),
):
    """Get OHLCV candle data — Kraken for crypto, yfinance/Polygon for equities."""
    _TF_MINUTES = {"1M": 1, "5M": 5, "15M": 15, "1H": 60, "4H": 240, "1D": 1440}
    _KRK = {
        "BTCUSDT": "XBTUSD", "ETHUSDT": "ETHUSD", "SOLUSDT": "SOLUSD",
        "XRPUSDT": "XRPUSD", "ADAUSDT": "ADAUSD", "AVAXUSDT": "AVAXUSD",
        "DOGEUSDT": "XDGUSD", "LINKUSDT": "LINKUSD",
    }

    interval = _TF_MINUTES.get(timeframe, 60)
    candles = []

    # Try Kraken for crypto symbols
    if symbol in _KRK:
        try:
            since = int((datetime.now(timezone.utc) - timedelta(minutes=interval * limit)).timestamp())
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.kraken.com/0/public/OHLC?pair={_KRK[symbol]}&interval={interval}&since={since}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("result", {})
                    # Kraken returns data under a key that varies — grab the first array
                    ohlc_data = None
                    for k, v in result.items():
                        if isinstance(v, list) and len(v) > 0:
                            ohlc_data = v
                            break
                    if ohlc_data:
                        for row in ohlc_data[-limit:]:
                            # [timestamp, open, high, low, close, vwap, volume, count]
                            candles.append(CandleData(
                                timestamp=datetime.fromtimestamp(int(row[0]), tz=timezone.utc).isoformat(),
                                open=float(row[1]),
                                high=float(row[2]),
                                low=float(row[3]),
                                close=float(row[4]),
                                volume=float(row[6]),
                                vwap=float(row[5]) if row[5] else None,
                                trade_count=int(row[7]) if len(row) > 7 else None,
                            ))
        except Exception as exc:
            logger.warning(f"Kraken OHLC failed for {symbol}: {exc}")

    # Fallback for equities: use yfinance via equities_feed, then mock as last resort
    if not candles:
        # Map API timeframe to equities_feed timeframe
        _API_TO_FEED_TF = {
            "1M": "1min", "5M": "5min", "15M": "15min",
            "1H": "1hour", "4H": "1hour", "1D": "1day",
        }
        feed_tf = _API_TO_FEED_TF.get(timeframe, "1day")

        try:
            df = await engine.equities_feed.get_ohlcv(
                symbol=symbol,
                timeframe=feed_tf,
                start_date=start if start else None,
                end_date=end if end else None,
            )
            if not df.empty:
                for _, row in df.tail(limit).iterrows():
                    ts = row["timestamp"]
                    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                    candles.append(CandleData(
                        timestamp=ts_str,
                        open=round(float(row["open"]), 6),
                        high=round(float(row["high"]), 6),
                        low=round(float(row["low"]), 6),
                        close=round(float(row["close"]), 6),
                        volume=round(float(row["volume"])),
                    ))
        except Exception as exc:
            logger.warning(f"Equities feed OHLCV failed for {symbol}: {exc}")

    # Last-resort mock if still no candles (e.g. unknown symbol, all APIs failed)
    if not candles:
        import math, random
        _BASES = {"SPY": 568, "QQQ": 487, "AAPL": 217, "TSLA": 172, "NVDA": 950,
                  "AMZN": 187, "MSFT": 390, "GOOGL": 160, "META": 590, "AMD": 105,
                  "BTCUSDT": 67500, "ETHUSDT": 2060, "SOLUSDT": 84, "XRPUSDT": 1.34}
        base = _BASES.get(symbol, 100)
        now_ts = datetime.now(timezone.utc)
        price = base * (0.97 + random.random() * 0.06)
        vol = base * 0.008
        for i in range(limit, 0, -1):
            ts = now_ts - timedelta(minutes=interval * i)
            drift = math.sin(i / 40) * vol * 0.5
            o = price + drift
            move = (random.random() - 0.48) * vol * 2
            c = o + move
            h = max(o, c) + random.random() * vol * 0.7
            l = min(o, c) - random.random() * vol * 0.7
            candles.append(CandleData(
                timestamp=ts.isoformat(),
                open=round(o, 6), high=round(h, 6), low=round(l, 6),
                close=round(c, 6), volume=round(base * (500 + random.random() * 2000)),
            ))
            price = c

    return CandlesResponse(symbol=symbol, timeframe=timeframe, candles=candles, count=len(candles))


# ═══════════════════════════════════════════════════════════
# Scoring
# ═══════════════════════════════════════════════════════════

@app.get("/api/scoring/latest/{symbol}", response_model=SignalScoreResponse, tags=["Scoring"])
async def get_latest_signal(symbol: str, engine=Depends(get_engine)):
    """Get the most recent signal score for a symbol."""
    try:
        logs = engine.storage.get_signal_logs(
            symbol=symbol,
            start=(datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            end=datetime.now(timezone.utc).isoformat(),
            limit=1,
        )
    except Exception:
        logs = []

    if not logs:
        return SignalScoreResponse(
            signal=None,
            message=f"No recent signal data for {symbol}",
        )

    latest = logs[0]
    return SignalScoreResponse(
        signal=SignalScore(
            symbol=symbol,
            timestamp=latest.get("timestamp"),
            composite_score=float(latest.get("composite_score", 0)),
            trend_score=_safe_float(latest.get("trend_score")),
            momentum_score=_safe_float(latest.get("momentum_score")),
            structure_score=_safe_float(latest.get("structure_score")),
            flow_score=_safe_float(latest.get("flow_score")),
            macro_score=_safe_float(latest.get("macro_score")),
            direction=latest.get("direction"),
            regime=latest.get("regime"),
            action_taken=latest.get("action_taken"),
        ),
    )


@app.get("/api/scoring/regime", response_model=RegimeResponse, tags=["Scoring"])
async def get_current_regime(
    symbol: str = Query(default="BTCUSDT", description="Symbol to check regime for"),
    engine=Depends(get_engine),
):
    """Get the current market regime classification."""
    regime_data = engine.storage.get_latest_regime(symbol)

    if not regime_data:
        return RegimeResponse(
            symbol=symbol,
            regime=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    return RegimeResponse(
        symbol=symbol,
        regime=regime_data.get("new_regime"),
        previous_regime=regime_data.get("previous_regime"),
        trigger_reason=regime_data.get("trigger_reason"),
        adx_value=_safe_float(regime_data.get("adx_value")),
        atr_percentile=_safe_float(regime_data.get("atr_percentile")),
        timestamp=regime_data.get("timestamp"),
    )


# ═══════════════════════════════════════════════════════════
# Portfolio
# ═══════════════════════════════════════════════════════════

@app.get("/api/portfolio/summary", response_model=PortfolioSummaryResponse, tags=["Portfolio"])
async def get_portfolio_summary(engine=Depends(get_engine)):
    """Get current portfolio summary: equity, positions, P&L."""
    snapshot = engine.storage.get_latest_portfolio_snapshot()

    if not snapshot:
        return PortfolioSummaryResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # Parse positions from the snapshot
    positions_raw = snapshot.get("positions_json", [])
    positions = []
    if isinstance(positions_raw, list):
        for p in positions_raw:
            positions.append(PositionData(
                symbol=p.get("symbol", ""),
                direction=p.get("direction"),
                entry_price=_safe_float(p.get("entry_price")),
                current_price=_safe_float(p.get("current_price")),
                quantity=_safe_float(p.get("quantity") or p.get("position_size")),
                unrealized_pnl=_safe_float(p.get("unrealized_pnl")),
                stop_loss=_safe_float(p.get("stop_loss") or p.get("stop_price")),
                take_profit=_safe_float(p.get("take_profit")),
            ))

    return PortfolioSummaryResponse(
        total_equity=_safe_float(snapshot.get("total_equity")),
        cash=_safe_float(snapshot.get("cash")),
        unrealized_pnl=_safe_float(snapshot.get("unrealized_pnl")),
        realized_pnl=_safe_float(snapshot.get("realized_pnl")),
        total_pnl=_safe_float(
            (snapshot.get("unrealized_pnl") or 0) + (snapshot.get("realized_pnl") or 0)
        ),
        portfolio_heat=_safe_float(snapshot.get("portfolio_heat")),
        open_positions=int(snapshot.get("open_positions", 0)),
        drawdown_pct=_safe_float(snapshot.get("drawdown_pct")),
        peak_equity=_safe_float(snapshot.get("peak_equity")),
        positions=positions,
        timestamp=snapshot.get("timestamp"),
    )


@app.get("/api/portfolio/trades", response_model=TradesResponse, tags=["Portfolio"])
async def get_trade_history(
    days: int = Query(default=30, ge=1, le=365, description="Lookback days"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    status: Optional[str] = Query(default=None, description="Filter by status: OPEN, CLOSED, CANCELLED"),
    engine=Depends(get_engine),
):
    """Get trade history."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()
    end = now.isoformat()

    try:
        raw_trades = engine.storage.get_trades(start, end, symbol=symbol, status=status)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to retrieve trades: {exc}")

    trades = [
        TradeRecord(
            trade_id=t.get("trade_id"),
            symbol=t.get("symbol", ""),
            side=t.get("side"),
            entry_time=t.get("entry_time"),
            exit_time=t.get("exit_time"),
            entry_price=_safe_float(t.get("entry_price")),
            exit_price=_safe_float(t.get("exit_price")),
            quantity=_safe_float(t.get("quantity")),
            leverage=_safe_float(t.get("leverage")),
            pnl=_safe_float(t.get("pnl")),
            pnl_pct=_safe_float(t.get("pnl_pct")),
            r_multiple=_safe_float(t.get("r_multiple")),
            fees=_safe_float(t.get("fees")),
            status=t.get("status"),
            signal_score=int(t["signal_score"]) if t.get("signal_score") is not None else None,
            regime=t.get("regime"),
        )
        for t in raw_trades
    ]

    return TradesResponse(trades=trades, count=len(trades))


# ═══════════════════════════════════════════════════════════
# Backtest
# ═══════════════════════════════════════════════════════════

@app.post("/api/backtest/run", response_model=BacktestRunResponse, tags=["Backtest"])
async def run_backtest(req: BacktestRequest, engine=Depends(get_engine)):
    """Trigger a backtest with the given parameters."""
    global _last_backtest_result

    try:
        result = engine.run_backtest(
            symbol=req.symbol,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
        )

        # Extract metrics from result (result structure varies)
        summary = _extract_backtest_summary(result, req)
        _last_backtest_result = summary

        return BacktestRunResponse(
            message=f"Backtest completed for {req.symbol}",
            result=summary,
        )

    except Exception as exc:
        logger.error(f"Backtest failed: {exc}\n{traceback.format_exc()}")
        return BacktestRunResponse(
            message="Backtest failed",
            error=str(exc),
        )


@app.get("/api/backtest/results", response_model=BacktestResultsResponse, tags=["Backtest"])
async def get_backtest_results():
    """Get the latest backtest results."""
    if _last_backtest_result is None:
        return BacktestResultsResponse(
            results=None,
            message="No backtest results available. Run a backtest first.",
        )
    return BacktestResultsResponse(results=_last_backtest_result)


# ═══════════════════════════════════════════════════════════
# Alpha
# ═══════════════════════════════════════════════════════════

@app.get(
    "/api/alpha/congressional",
    response_model=CongressionalTradesResponse,
    tags=["Alpha"],
)
async def get_congressional_trades(
    days: int = Query(default=30, ge=1, le=365, description="Lookback days"),
    engine=Depends(get_engine),
):
    """Get recent congressional trading activity."""
    try:
        df = await engine.aggregator.congressional_feed.get_recent_trades(days=days)
    except Exception as exc:
        logger.error(f"Congressional trades fetch failed: {exc}")
        return CongressionalTradesResponse(trades=[], count=0)

    if df is None or df.empty:
        return CongressionalTradesResponse(trades=[], count=0)

    trades = []
    for _, row in df.iterrows():
        trades.append(CongressionalTrade(
            politician=str(row.get("politician", "")) if pd.notna(row.get("politician")) else None,
            ticker=str(row.get("ticker", "")) if pd.notna(row.get("ticker")) else None,
            type=str(row.get("type", "")) if pd.notna(row.get("type")) else None,
            date=str(row.get("date", "")) if pd.notna(row.get("date")) else None,
            amount_range=str(row.get("amount_range", "")) if pd.notna(row.get("amount_range")) else None,
        ))

    return CongressionalTradesResponse(trades=trades, count=len(trades))


@app.get(
    "/api/alpha/insider",
    response_model=InsiderTransactionsResponse,
    tags=["Alpha"],
)
async def get_insider_transactions(
    days: int = Query(default=30, ge=1, le=365, description="Lookback days"),
    engine=Depends(get_engine),
):
    """Get recent insider Form 4 filings."""
    try:
        df = await engine.aggregator.insider_feed.get_recent_filings(days=days)
    except Exception as exc:
        logger.error(f"Insider filings fetch failed: {exc}")
        return InsiderTransactionsResponse(transactions=[], count=0)

    if df is None or df.empty:
        return InsiderTransactionsResponse(transactions=[], count=0)

    txns = []
    for _, row in df.iterrows():
        txns.append(InsiderTransaction(
            insider=str(row.get("insider", "")) if pd.notna(row.get("insider")) else None,
            ticker=str(row.get("ticker", "")) if pd.notna(row.get("ticker")) else None,
            transaction_type=str(row.get("transaction_type", "")) if pd.notna(row.get("transaction_type")) else None,
            shares=_safe_float(row.get("shares")),
            price=_safe_float(row.get("price")),
            date=str(row.get("date", "")) if pd.notna(row.get("date")) else None,
            title=str(row.get("title", "")) if pd.notna(row.get("title")) else None,
        ))

    return InsiderTransactionsResponse(transactions=txns, count=len(txns))


# ═══════════════════════════════════════════════════════════
# Float Data
# ═══════════════════════════════════════════════════════════

_float_feed = None


def _get_float_feed():
    global _float_feed
    if _float_feed is None:
        from backend.data.float_feed import FloatFeed
        _float_feed = FloatFeed()
    return _float_feed


@app.get("/api/float/{symbol}", response_model=FloatProfileResponse, tags=["Float"])
async def get_float_profile(symbol: str):
    """Get complete float analysis for a symbol."""
    feed = _get_float_feed()
    try:
        profile = await feed.get_float_profile(symbol)
        return FloatProfileResponse(**profile.to_dict())
    except Exception as exc:
        logger.error(f"Float profile failed for {symbol}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/float/summary", response_model=FloatSummaryResponse, tags=["Float"])
async def get_float_summary(
    symbols: str = Query(description="Comma-separated symbols (e.g., AAPL,TSLA,GME)"),
):
    """Get float summary for multiple symbols."""
    feed = _get_float_feed()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    profiles = []
    for sym in symbol_list[:50]:  # Cap at 50
        try:
            p = await feed.get_float_profile(sym)
            profiles.append(FloatProfileResponse(**p.to_dict()))
        except Exception as exc:
            logger.warning(f"Float fetch failed for {sym}: {exc}")

    return FloatSummaryResponse(profiles=profiles, count=len(profiles))


@app.get("/api/float/squeeze-candidates", response_model=SqueezeCandidatesResponse, tags=["Float"])
async def get_squeeze_candidates(
    symbols: str = Query(description="Comma-separated symbols to scan"),
    min_score: float = Query(default=60.0, ge=0, le=100, description="Minimum squeeze score"),
):
    """Find stocks with high short-squeeze potential based on float analysis."""
    feed = _get_float_feed()
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    try:
        candidates = await feed.get_squeeze_candidates(symbol_list[:100], min_squeeze_score=min_score)
        return SqueezeCandidatesResponse(
            candidates=[
                SqueezeCandidate(
                    symbol=c.symbol,
                    float_shares=c.float_shares,
                    float_category=c.float_category,
                    short_pct_of_float=c.short_pct_of_float,
                    squeeze_potential=c.squeeze_potential,
                    volatility_multiplier=c.volatility_multiplier,
                )
                for c in candidates
            ],
            count=len(candidates),
        )
    except Exception as exc:
        logger.error(f"Squeeze scan failed: {exc}")
        return SqueezeCandidatesResponse(candidates=[], count=0)


# ═══════════════════════════════════════════════════════════
# WebSocket — Real-Time Price Stream
# ═══════════════════════════════════════════════════════════

@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """WebSocket endpoint for real-time price streaming."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can send subscription changes
            data = await websocket.receive_text()
            # Future: handle symbol subscription changes
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """WebSocket endpoint for real-time trade/system notifications."""
    await notification_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; clients can send ping/ack
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        notification_manager.disconnect(websocket)


@app.websocket("/ws/bot")
async def websocket_bot(websocket: WebSocket):
    """Stream the full bot snapshot (status, positions, signals,
    activity, trades, performance) to the connected client at ~1Hz.

    Replaces six parallel polls per second from the bot page — one open
    socket per browser tab instead.
    """
    from backend.orchestrator.autobot import autobot as _bot
    import asyncio as _asyncio
    import json as _json

    await websocket.accept()
    try:
        while True:
            snapshot = _bot.get_snapshot()
            await websocket.send_text(_json.dumps({
                "type": "bot_snapshot",
                "data": snapshot,
            }))
            await _asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug(f"WS /ws/bot ended: {exc}")


# ═══════════════════════════════════════════════════════════
# Notification History
# ═══════════════════════════════════════════════════════════

@app.get("/api/notifications/history", tags=["Notifications"])
async def get_notification_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    type: Optional[str] = Query(None),
):
    """Return stored notification history with optional type filter."""
    items = notification_manager.history
    if type:
        items = [n for n in items if n.get("type") == type]
    total = len(items)
    page = items[offset : offset + limit]
    return {"notifications": page, "total": total, "limit": limit, "offset": offset}


# ═══════════════════════════════════════════════════════════
# Macro Intelligence
# ═══════════════════════════════════════════════════════════

@app.get("/api/macro/snapshot", response_model=MacroSnapshotResponse, tags=["Macro"])
async def get_macro_snapshot(engine=Depends(get_engine)):
    """Get current macro economic indicators from FRED and regime data."""
    indicators = []

    # Try to get real FRED data from macro_feed
    try:
        snapshot = await engine.aggregator.macro_feed.get_macro_snapshot()
        if snapshot and isinstance(snapshot, dict):
            indicator_map = {
                "fed_funds_rate": ("Fed Funds Rate", "%", "Rates"),
                "dgs2": ("2Y Treasury", "%", "Rates"),
                "dgs10": ("10Y Treasury", "%", "Rates"),
                "t10y2y": ("2s10s Spread", "bps", "Rates"),
                "cpiaucsl": ("CPI YoY", "%", "Inflation"),
                "unrate": ("Unemployment", "%", "Labor"),
                "m2sl": ("M2 Money Supply", "$T", "Liquidity"),
                "walcl": ("Fed Balance Sheet", "$T", "Liquidity"),
                "vixcls": ("VIX", "", "Volatility"),
                "dxy": ("Dollar Index", "", "FX"),
            }
            for key, (label, unit, category) in indicator_map.items():
                val = snapshot.get(key)
                if val is not None:
                    indicators.append(MacroIndicator(
                        key=key,
                        label=label,
                        value=round(float(val), 4) if val else None,
                        unit=unit,
                        category=category,
                        timestamp=snapshot.get("timestamp"),
                    ))
    except Exception as exc:
        logger.warning(f"FRED data fetch failed: {exc}")

    # If FRED unavailable, provide fallback with latest known values from DB
    if not indicators:
        indicators = _get_fallback_macro_indicators(engine)

    # Get regime info
    regime_data = engine.storage.get_latest_regime("BTCUSDT")
    regime = regime_data.get("new_regime") if regime_data else None

    return MacroSnapshotResponse(
        indicators=indicators,
        regime=regime,
        regime_timestamp=regime_data.get("timestamp") if regime_data else None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _get_fallback_macro_indicators(engine) -> list:
    """Provide hardcoded-but-realistic macro values when FRED is unavailable."""
    # These are approximate current values — better than showing "--"
    fallback = [
        ("fed_funds_rate", "Fed Funds Rate", 4.33, "%", "Rates"),
        ("dgs2", "2Y Treasury", 3.95, "%", "Rates"),
        ("dgs10", "10Y Treasury", 4.25, "%", "Rates"),
        ("t10y2y", "2s10s Spread", 30, "bps", "Rates"),
        ("cpi_yoy", "CPI YoY", 2.8, "%", "Inflation"),
        ("unrate", "Unemployment", 4.1, "%", "Labor"),
        ("m2sl", "M2 Money Supply", 21.7, "$T", "Liquidity"),
        ("walcl", "Fed Balance Sheet", 6.8, "$T", "Liquidity"),
    ]
    return [
        MacroIndicator(
            key=key, label=label, value=val, unit=unit, category=cat,
            source="fallback",
        )
        for key, label, val, unit, cat in fallback
    ]


# ═══════════════════════════════════════════════════════════
# Risk War Room
# ═══════════════════════════════════════════════════════════

@app.get("/api/risk/dashboard", response_model=RiskDashboardResponse, tags=["Risk"])
async def get_risk_dashboard(engine=Depends(get_engine)):
    """Get comprehensive risk metrics for the War Room."""
    snapshot = engine.storage.get_latest_portfolio_snapshot()

    # Portfolio heat (% of capital at risk in open positions)
    portfolio_heat = _safe_float(snapshot.get("portfolio_heat")) if snapshot else None
    drawdown_pct = _safe_float(snapshot.get("drawdown_pct")) if snapshot else None
    total_equity = _safe_float(snapshot.get("total_equity")) if snapshot else 100000.0
    peak_equity = _safe_float(snapshot.get("peak_equity")) if snapshot else total_equity

    # Compute VaR from recent trade history
    var_95, var_99 = _compute_var(engine)

    # Sharpe / Sortino from equity curve
    sharpe, sortino = _compute_risk_ratios(engine)

    # Daily P&L
    daily_pnl = _compute_daily_pnl(engine)

    # War room status
    dd = abs(drawdown_pct) if drawdown_pct else 0
    if dd >= 0.15:
        war_room_status = "SHUTDOWN"
    elif dd >= 0.12:
        war_room_status = "REDUCE"
    elif dd >= 0.10:
        war_room_status = "ALERT"
    else:
        war_room_status = "NORMAL"

    metrics = [
        RiskMetric(name="Portfolio Heat", value=portfolio_heat, unit="%", limit=20.0,
                   status="ok" if (portfolio_heat or 0) < 15 else "warning"),
        RiskMetric(name="VaR (95%)", value=var_95, unit="$", limit=total_equity * 0.05 if total_equity else None,
                   status="ok" if (var_95 or 0) < (total_equity or 100000) * 0.05 else "warning"),
        RiskMetric(name="VaR (99%)", value=var_99, unit="$",
                   status="ok" if (var_99 or 0) < (total_equity or 100000) * 0.08 else "danger"),
        RiskMetric(name="Max Drawdown", value=round(dd * 100, 2) if drawdown_pct else None, unit="%", limit=15.0,
                   status="ok" if dd < 0.10 else "warning" if dd < 0.15 else "danger"),
        RiskMetric(name="Sharpe Ratio", value=sharpe, unit="",
                   status="ok" if (sharpe or 0) > 1.0 else "warning"),
        RiskMetric(name="Sortino Ratio", value=sortino, unit="",
                   status="ok" if (sortino or 0) > 1.5 else "warning"),
        RiskMetric(name="Daily P&L", value=daily_pnl, unit="$",
                   status="ok" if (daily_pnl or 0) >= 0 else "warning"),
    ]

    # Stress test scenarios
    stress_tests = _compute_stress_tests(engine, total_equity or 100000.0)

    return RiskDashboardResponse(
        metrics=metrics,
        stress_tests=stress_tests,
        war_room_status=war_room_status,
        total_equity=total_equity,
        peak_equity=peak_equity,
        drawdown_pct=drawdown_pct,
        open_positions=int(snapshot.get("open_positions", 0)) if snapshot else 0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _compute_var(engine, confidence_95=0.05, confidence_99=0.01):
    """Compute historical VaR from trade history."""
    try:
        trades = engine.storage.get_trades(
            start=(datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),
            end=datetime.now(timezone.utc).isoformat(),
        )
        if not trades or len(trades) < 5:
            return None, None
        pnls = [float(t.get("pnl", 0)) for t in trades if t.get("pnl") is not None]
        if len(pnls) < 5:
            return None, None
        var_95 = round(abs(float(np.percentile(pnls, confidence_95 * 100))), 2)
        var_99 = round(abs(float(np.percentile(pnls, confidence_99 * 100))), 2)
        return var_95, var_99
    except Exception:
        return None, None


def _compute_risk_ratios(engine):
    """Compute Sharpe and Sortino from trade returns."""
    try:
        trades = engine.storage.get_trades(
            start=(datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),
            end=datetime.now(timezone.utc).isoformat(),
        )
        if not trades or len(trades) < 10:
            return None, None
        returns = [float(t.get("pnl", 0)) for t in trades if t.get("pnl") is not None]
        if len(returns) < 10:
            return None, None
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        sharpe = round(float(mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0, 2)
        downside = [r for r in returns if r < 0]
        down_std = np.std(downside) if len(downside) > 2 else std_ret
        sortino = round(float(mean_ret / down_std * np.sqrt(252)) if down_std > 0 else 0, 2)
        return sharpe, sortino
    except Exception:
        return None, None


def _compute_daily_pnl(engine):
    """Get today's P&L from trades closed today."""
    try:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
        trades = engine.storage.get_trades(start=today_start, end=datetime.now(timezone.utc).isoformat())
        if not trades:
            return 0.0
        return round(sum(float(t.get("pnl", 0)) for t in trades), 2)
    except Exception:
        return 0.0


def _compute_stress_tests(engine, equity: float) -> list:
    """Run portfolio stress test scenarios."""
    scenarios = [
        {"name": "2020 COVID Crash", "market_drop": -0.34, "description": "Rapid liquidity crisis, VIX spike to 82"},
        {"name": "2022 Rate Hike Cycle", "market_drop": -0.33, "description": "Sustained hawkish tightening, growth selloff"},
        {"name": "Flash Crash", "market_drop": -0.10, "description": "Sudden intraday liquidity vacuum"},
        {"name": "Crypto Winter", "market_drop": -0.77, "description": "Prolonged crypto bear market (BTC -77%)"},
        {"name": "Black Monday (1987)", "market_drop": -0.22, "description": "Single-day 22% market crash"},
        {"name": "2008 Financial Crisis", "market_drop": -0.57, "description": "Credit crisis, bank failures, contagion"},
    ]

    results = []
    for s in scenarios:
        # Estimate portfolio impact based on market drop and current positions
        est_impact = round(equity * s["market_drop"] * 0.5, 2)  # Assume 50% beta
        survival = equity + est_impact > 0
        results.append(StressTestResult(
            scenario=s["name"],
            market_impact=f"{s['market_drop']*100:.0f}%",
            portfolio_impact=round(est_impact, 2),
            portfolio_impact_pct=round(s["market_drop"] * 50, 2),  # 50% beta
            description=s["description"],
            survives=survival,
        ))

    return results


# ═══════════════════════════════════════════════════════════
# Advanced Risk Analytics (VaR, Stress, Correlation, Metrics)
# ═══════════════════════════════════════════════════════════

_risk_engine = None


def _get_risk_engine():
    global _risk_engine
    if _risk_engine is None:
        from backend.orchestrator.risk_analytics import RiskAnalyticsEngine
        _risk_engine = RiskAnalyticsEngine()
    return _risk_engine


@app.get("/api/risk/var", tags=["Risk Analytics"])
async def risk_var(confidence: float = 0.95):
    """Value at Risk — Historical, Parametric, Monte Carlo."""
    engine = _get_risk_engine()
    return engine.get_var(confidence)


@app.get("/api/risk/stress", tags=["Risk Analytics"])
async def risk_stress():
    """Stress test scenarios with portfolio impact."""
    engine = _get_risk_engine()
    return {"scenarios": engine.get_stress_tests()}


@app.get("/api/risk/correlation", tags=["Risk Analytics"])
async def risk_correlation():
    """Pairwise correlation matrix for portfolio holdings."""
    engine = _get_risk_engine()
    return engine.get_correlation()


@app.get("/api/risk/metrics", tags=["Risk Analytics"])
async def risk_metrics():
    """Full risk metrics: Beta, Sortino, Max DD, Calmar, CVaR."""
    engine = _get_risk_engine()
    return engine.get_metrics()


# ═══════════════════════════════════════════════════════════
# Live Signal Scoring (compute on demand)
# ═══════════════════════════════════════════════════════════

@app.get("/api/scoring/compute/{symbol}", response_model=SignalScoreResponse, tags=["Scoring"])
async def compute_signal_score(
    symbol: str,
    direction: str = Query(default="long", description="Trade direction: long or short"),
    engine=Depends(get_engine),
):
    """Compute a fresh signal score for a symbol using all engines."""
    try:
        # Get market data from storage
        now = datetime.now(timezone.utc)
        timeframes = {"5M": 200, "15M": 100, "1H": 200, "4H": 60, "1D": 30}
        tf_data = {}
        for tf, lookback in timeframes.items():
            tf_minutes = engine.settings.timeframes.timeframe_minutes.get(tf, 60)
            start = (now - timedelta(minutes=tf_minutes * lookback)).isoformat()
            df = engine.storage.get_candles(symbol, tf, start, now.isoformat())
            if df is not None and not df.empty:
                tf_data[tf] = df

        if not tf_data:
            return SignalScoreResponse(
                signal=None,
                message=f"No market data available for {symbol}",
            )

        market_data = {"timeframe_data": tf_data, "symbol": symbol}

        # Score through each engine
        scores = {}
        for name, eng in [
            ("trend", engine.trend_engine),
            ("momentum", engine.momentum_engine),
            ("structure", engine.structure_engine),
        ]:
            try:
                result = eng.score(market_data, direction)
                scores[name] = result
            except Exception as exc:
                logger.debug(f"Engine {name} failed for {symbol}: {exc}")
                scores[name] = {"score": 50, "confidence": 0.0}

        # Composite
        trend_s = float(scores.get("trend", {}).get("score", 50))
        momentum_s = float(scores.get("momentum", {}).get("score", 50))
        structure_s = float(scores.get("structure", {}).get("score", 50))
        flow_s = 50.0  # Neutral when no live flow data
        macro_s = 50.0  # Neutral when no live macro data

        # Use RISK_ON weights (default): 0.25, 0.25, 0.25, 0.15, 0.10
        composite = (trend_s * 0.25 + momentum_s * 0.25 + structure_s * 0.25 +
                     flow_s * 0.15 + macro_s * 0.10)

        return SignalScoreResponse(
            signal=SignalScore(
                symbol=symbol,
                timestamp=now.isoformat(),
                composite_score=round(composite, 1),
                trend_score=round(trend_s, 1),
                momentum_score=round(momentum_s, 1),
                structure_score=round(structure_s, 1),
                flow_score=round(flow_s, 1),
                macro_score=round(macro_s, 1),
                direction=direction,
                regime=engine.regime_engine.current_regime.value if hasattr(engine, "regime_engine") else None,
            ),
        )
    except Exception as exc:
        logger.error(f"Score computation failed for {symbol}: {exc}")
        return SignalScoreResponse(signal=None, message=str(exc))


# ═══════════════════════════════════════════════════════════
# System
# ═══════════════════════════════════════════════════════════

@app.get("/api/system/status", response_model=EngineStatus, tags=["System"])
async def get_system_status(engine=Depends(get_engine)):
    """Get engine status and configuration metrics."""
    try:
        freshness = engine.aggregator.get_data_freshness()
    except Exception:
        freshness = None

    return EngineStatus(
        engine_initialized=True,
        instruments={
            "crypto": engine.settings.instruments.crypto_pairs,
            "equities": engine.settings.instruments.equity_symbols,
        },
        data_freshness=freshness,
        risk_config={
            "base_risk": engine.settings.risk.base_risk_per_trade,
            "max_heat": engine.settings.risk.max_portfolio_heat,
            "max_correlated": engine.settings.risk.max_correlated_positions,
            "drawdown_pause": engine.settings.risk.drawdown_pause_threshold,
            "drawdown_reduce": engine.settings.risk.drawdown_reduce_threshold,
            "drawdown_shutdown": engine.settings.risk.drawdown_shutdown_threshold,
            "daily_loss_cap": engine.settings.risk.daily_loss_cap,
        },
        validation_targets={
            "min_win_rate": engine.settings.validation.min_win_rate,
            "min_sharpe": engine.settings.validation.min_sharpe,
            "min_profit_factor": engine.settings.validation.min_profit_factor,
            "max_drawdown": engine.settings.validation.max_drawdown,
            "min_trades": engine.settings.validation.min_trades,
        },
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ─── Helpers ─────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if pd.notna(f) else None
    except (ValueError, TypeError):
        return None


def _extract_backtest_summary(result, req: BacktestRequest) -> BacktestResultSummary:
    """Extract a BacktestResultSummary from the engine's backtest result object."""
    # The result can be a dict or an object with a .metrics attribute
    metrics = {}
    if isinstance(result, dict):
        metrics = result.get("metrics", result)
    elif hasattr(result, "metrics") and result.metrics:
        m = result.metrics
        metrics = m if isinstance(m, dict) else (m.__dict__ if hasattr(m, "__dict__") else {})

    return BacktestResultSummary(
        symbol=req.symbol,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        final_equity=_safe_float(metrics.get("final_equity")),
        total_return_pct=_safe_float(metrics.get("total_return_pct") or metrics.get("total_return")),
        total_trades=int(metrics["total_trades"]) if metrics.get("total_trades") is not None else None,
        win_rate=_safe_float(metrics.get("win_rate")),
        profit_factor=_safe_float(metrics.get("profit_factor")),
        sharpe_ratio=_safe_float(metrics.get("sharpe_ratio") or metrics.get("sharpe")),
        sortino_ratio=_safe_float(metrics.get("sortino_ratio") or metrics.get("sortino")),
        max_drawdown=_safe_float(metrics.get("max_drawdown")),
        calmar_ratio=_safe_float(metrics.get("calmar_ratio") or metrics.get("calmar")),
        status="completed",
    )


# ═══════════════════════════════════════════════════════════
# Orchestrator API Endpoints
# ═══════════════════════════════════════════════════════════

def get_orchestrator():
    """Dependency that provides the Orchestrator instance."""
    if _orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not initialized.",
        )
    return _orchestrator


@app.post("/api/orchestrator/query")
async def orchestrator_query(
    body: dict,
    orchestrator=Depends(get_orchestrator),
):
    """
    Main orchestrator endpoint. Accepts a query and returns
    a unified structured response with routing, policy, and content blocks.
    """
    from backend.orchestrator.schemas import OrchestratorRequest

    request = OrchestratorRequest(
        query=body.get("query", ""),
        user_id=body.get("user_id", "default"),
        symbol=body.get("symbol"),
        symbols=body.get("symbols", []),
        context=body.get("context", {}),
        session_id=body.get("session_id"),
        category_hint=body.get("category_hint"),
    )

    response = await orchestrator.process(request)
    return response.model_dump()


@app.get("/api/orchestrator/audit")
async def orchestrator_audit(
    user_id: str = "default",
    limit: int = 50,
    orchestrator=Depends(get_orchestrator),
):
    """Get the decision audit log for a user."""
    return {"decisions": orchestrator.get_audit_log(user_id, limit)}


@app.get("/api/orchestrator/memory/preferences")
async def orchestrator_preferences(
    user_id: str = "default",
    orchestrator=Depends(get_orchestrator),
):
    """Get all user preferences."""
    return orchestrator.memory.get_all_preferences(user_id)


@app.post("/api/orchestrator/memory/preferences")
async def set_orchestrator_preference(
    body: dict,
    orchestrator=Depends(get_orchestrator),
):
    """Set a user preference."""
    orchestrator.set_user_preference(
        user_id=body.get("user_id", "default"),
        key=body.get("key", ""),
        value=body.get("value"),
    )
    return {"status": "ok"}


@app.get("/api/orchestrator/memory/signals")
async def orchestrator_signal_history(
    user_id: str = "default",
    symbol: Optional[str] = None,
    limit: int = 50,
    orchestrator=Depends(get_orchestrator),
):
    """Get signal outcome history."""
    return {
        "signals": orchestrator.memory.get_signal_history(user_id, limit, symbol),
        "stats": orchestrator.memory.get_signal_stats(user_id),
    }


@app.get("/api/orchestrator/memory/profile")
async def orchestrator_user_profile(
    user_id: str = "default",
    orchestrator=Depends(get_orchestrator),
):
    """Get assembled user profile (preferences + signal stats)."""
    return orchestrator.memory.get_user_profile(user_id)


# ═══════════════════════════════════════════════════════════
# Paper Trading
# ═══════════════════════════════════════════════════════════

# In-memory paper trading state — resets on server restart
_paper_positions: dict = {}       # id -> position dict
_paper_closed_trades: list = []   # closed positions with P&L
_paper_next_id: int = 1


# ─── SL / TP Background Monitor ─────────────────────────

async def _monitor_sl_tp_task(engine):
    """
    Background task: every 5 seconds, check open paper positions against
    current prices.  If a stop-loss or take-profit is hit, auto-close the
    position and broadcast a notification.
    """
    from backend.api.websocket import _fetch_all_prices

    logger.info("SL/TP monitor started")

    while True:
        try:
            await asyncio.sleep(5)

            open_ids = [
                pid for pid, p in _paper_positions.items() if p["status"] == "open"
            ]
            if not open_ids:
                continue

            # Fetch latest prices into a symbol -> price map
            prices_list = await _fetch_all_prices(engine)
            price_map: dict[str, float] = {}
            for p in prices_list:
                price_map[p["symbol"]] = p["price"]

            for pid in open_ids:
                pos = _paper_positions.get(pid)
                if pos is None or pos["status"] != "open":
                    continue

                current_price = price_map.get(pos["symbol"])
                if current_price is None:
                    continue

                sl = pos.get("stop_loss")
                tp = pos.get("take_profit")
                triggered = None
                trigger_type = None

                if pos["side"] == "long":
                    if sl is not None and current_price <= sl:
                        triggered = sl
                        trigger_type = "sl_hit"
                    elif tp is not None and current_price >= tp:
                        triggered = tp
                        trigger_type = "tp_hit"
                else:  # short
                    if sl is not None and current_price >= sl:
                        triggered = sl
                        trigger_type = "sl_hit"
                    elif tp is not None and current_price <= tp:
                        triggered = tp
                        trigger_type = "tp_hit"

                if triggered is None:
                    continue

                # Auto-close the position at the trigger price
                exit_price = float(triggered)
                if pos["side"] == "long":
                    pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
                else:
                    pnl = (pos["entry_price"] - exit_price) * pos["quantity"]

                pnl_pct = (pnl / (pos["entry_price"] * pos["quantity"])) * 100

                r_multiple = None
                if pos["stop_loss"] is not None:
                    risk_per_unit = abs(pos["entry_price"] - pos["stop_loss"])
                    if risk_per_unit > 0:
                        r_multiple = round(pnl / (risk_per_unit * pos["quantity"]), 2)

                pos["status"] = "closed"
                pos["exit_price"] = exit_price
                pos["close_time"] = _now_iso()
                pos["pnl"] = round(pnl, 2)
                pos["pnl_pct"] = round(pnl_pct, 2)
                pos["r_multiple"] = r_multiple
                pos["close_reason"] = trigger_type

                _paper_closed_trades.append(pos)
                del _paper_positions[pid]

                label = "Stop-Loss Hit" if trigger_type == "sl_hit" else "Take-Profit Hit"
                pnl_word = "Profit" if pnl >= 0 else "Loss"

                logger.info(
                    f"[{label}] {pos['symbol']}: closed @ ${exit_price:,.2f} | "
                    f"P&L ${pnl:+,.2f} ({pnl_pct:+.1f}%)"
                )

                await notification_manager.notify(
                    trigger_type,
                    f"{label} — {pos['symbol']}",
                    f"Closed @ ${exit_price:,.2f} | {pnl_word}: ${pnl:+,.2f} ({pnl_pct:+.1f}%)",
                    data=pos,
                )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"SL/TP monitor error: {exc}")
            await asyncio.sleep(5)

    logger.info("SL/TP monitor stopped")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.post("/api/paper/order", tags=["Paper Trading"])
async def paper_submit_order(body: dict):
    """
    Submit a paper trade order.

    Body: { symbol, side: "long"|"short", quantity, entry_price,
            stop_loss?, take_profit? }
    """
    global _paper_next_id

    symbol = body.get("symbol")
    side = body.get("side")
    quantity = body.get("quantity")
    entry_price = body.get("entry_price")

    if not symbol or not side or quantity is None or entry_price is None:
        raise HTTPException(status_code=400, detail="Missing required fields: symbol, side, quantity, entry_price")

    if side not in ("long", "short"):
        raise HTTPException(status_code=400, detail="side must be 'long' or 'short'")

    if quantity <= 0 or entry_price <= 0:
        raise HTTPException(status_code=400, detail="quantity and entry_price must be positive")

    pos_id = str(_paper_next_id)
    _paper_next_id += 1

    position = {
        "id": pos_id,
        "symbol": symbol.upper(),
        "side": side,
        "entry_price": float(entry_price),
        "quantity": float(quantity),
        "stop_loss": float(body["stop_loss"]) if body.get("stop_loss") is not None else None,
        "take_profit": float(body["take_profit"]) if body.get("take_profit") is not None else None,
        "open_time": _now_iso(),
        "status": "open",
    }

    _paper_positions[pos_id] = position
    logger.info(f"Paper order: {side.upper()} {quantity} {symbol} @ {entry_price}")

    # Broadcast notification
    sl_str = f" | SL: {position['stop_loss']}" if position["stop_loss"] else ""
    tp_str = f" | TP: {position['take_profit']}" if position["take_profit"] else ""
    await notification_manager.notify(
        "signal_triggered",
        f"Order Placed — {symbol.upper()}",
        f"{side.upper()} {quantity} @ ${entry_price:,.2f}{sl_str}{tp_str}",
        data=position,
    )

    return {"status": "ok", "position": position}


@app.get("/api/paper/positions", tags=["Paper Trading"])
async def paper_get_positions():
    """Get all open paper positions."""
    open_positions = [p for p in _paper_positions.values() if p["status"] == "open"]
    return {"positions": open_positions}


@app.post("/api/paper/close/{position_id}", tags=["Paper Trading"])
async def paper_close_position(position_id: str, body: dict):
    """
    Close a paper position at the given exit price.

    Body: { exit_price }
    """
    if position_id not in _paper_positions:
        raise HTTPException(status_code=404, detail="Position not found")

    pos = _paper_positions[position_id]
    if pos["status"] != "open":
        raise HTTPException(status_code=400, detail="Position is already closed")

    exit_price = body.get("exit_price")
    if exit_price is None or exit_price <= 0:
        raise HTTPException(status_code=400, detail="exit_price is required and must be positive")

    exit_price = float(exit_price)

    # Calculate P&L
    if pos["side"] == "long":
        pnl = (exit_price - pos["entry_price"]) * pos["quantity"]
    else:
        pnl = (pos["entry_price"] - exit_price) * pos["quantity"]

    pnl_pct = (pnl / (pos["entry_price"] * pos["quantity"])) * 100

    # Calculate R-multiple if stop_loss was set
    r_multiple = None
    if pos["stop_loss"] is not None:
        risk_per_unit = abs(pos["entry_price"] - pos["stop_loss"])
        if risk_per_unit > 0:
            r_multiple = round(pnl / (risk_per_unit * pos["quantity"]), 2)

    # Mark position closed
    pos["status"] = "closed"
    pos["exit_price"] = exit_price
    pos["close_time"] = _now_iso()
    pos["pnl"] = round(pnl, 2)
    pos["pnl_pct"] = round(pnl_pct, 2)
    pos["r_multiple"] = r_multiple

    _paper_closed_trades.append(pos)
    del _paper_positions[position_id]

    # Auto-record closed trade as a tax lot
    try:
        from backend.orchestrator.taxes import get_tax_engine
        tax_eng = get_tax_engine()
        lot_id = tax_eng.record_lot(
            symbol=pos["symbol"],
            quantity=pos["quantity"],
            price=pos["entry_price"],
            date=pos.get("opened_at", _now_iso())[:10],
            side=pos.get("side", "long"),
        )
        tax_eng.close_lot(lot_id, exit_price, pos["close_time"][:10])
        logger.info(f"Tax lot recorded for closed paper trade: {lot_id}")
    except Exception as tax_exc:
        logger.warning(f"Failed to record tax lot for paper trade: {tax_exc}")

    logger.info(f"Paper close: {pos['symbol']} P&L ${pnl:+.2f} ({pnl_pct:+.1f}%)")

    # Broadcast notification
    pnl_label = "Profit" if pnl >= 0 else "Loss"
    await notification_manager.notify(
        "position_closed",
        f"Position Closed — {pos['symbol']}",
        f"{pnl_label}: ${pnl:+,.2f} ({pnl_pct:+.1f}%)",
        data=pos,
    )

    return {"status": "ok", "trade": pos}


@app.get("/api/paper/history", tags=["Paper Trading"])
async def paper_trade_history():
    """Get closed trade history with P&L."""
    return {"trades": list(reversed(_paper_closed_trades))}


@app.get("/api/paper/stats", tags=["Paper Trading"])
async def paper_trading_stats():
    """Get paper trading stats: total P&L, win rate, avg R, etc."""
    trades = _paper_closed_trades
    if not trades:
        return {
            "total_trades": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "avg_pnl_pct": 0.0,
            "avg_r": None,
            "best_trade": None,
            "worst_trade": None,
            "open_positions": len([p for p in _paper_positions.values() if p["status"] == "open"]),
        }

    total_pnl = sum(t["pnl"] for t in trades)
    winners = [t for t in trades if t["pnl"] > 0]
    losers = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(winners) / len(trades)) * 100 if trades else 0

    r_values = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    avg_r = round(sum(r_values) / len(r_values), 2) if r_values else None

    sorted_by_pnl = sorted(trades, key=lambda t: t["pnl"])
    best = sorted_by_pnl[-1]
    worst = sorted_by_pnl[0]

    return {
        "total_trades": len(trades),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(total_pnl / len(trades), 2),
        "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 2),
        "avg_r": avg_r,
        "winners": len(winners),
        "losers": len(losers),
        "best_trade": {"symbol": best["symbol"], "pnl": best["pnl"], "pnl_pct": best["pnl_pct"]},
        "worst_trade": {"symbol": worst["symbol"], "pnl": worst["pnl"], "pnl_pct": worst["pnl_pct"]},
        "open_positions": len([p for p in _paper_positions.values() if p["status"] == "open"]),
    }


# ═══════════════════════════════════════════════════════════
# Authentication
# ═══════════════════════════════════════════════════════════

import hashlib
import secrets
import json as _json

_auth_db_path = "data/lumare_auth.db"
_auth_tokens: dict[str, str] = {}  # token -> user_id


def _get_auth_db():
    import sqlite3
    conn = sqlite3.connect(_auth_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    # Insert demo user if not exists
    demo_hash = hashlib.sha256("demo123".encode()).hexdigest()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            ("demo-user-001", "demo@lumare.com", "Demo Trader", demo_hash,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except Exception:
        pass
    return conn


@app.post("/api/auth/register", tags=["Auth"])
async def auth_register(body: dict):
    """Register a new user."""
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    name = body.get("name", "").strip()

    if not email or not password or not name:
        raise HTTPException(400, "Email, password, and name are required")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    conn = _get_auth_db()
    existing = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if existing:
        raise HTTPException(409, "Email already registered")

    user_id = f"user-{secrets.token_hex(8)}"
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, email, name, pw_hash, now),
    )
    conn.commit()

    token = secrets.token_urlsafe(32)
    _auth_tokens[token] = user_id

    return {"token": token, "user": {"id": user_id, "email": email, "name": name, "created_at": now}}


@app.post("/api/auth/login", tags=["Auth"])
async def auth_login(body: dict):
    """Login with email and password."""
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    conn = _get_auth_db()
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    user = conn.execute(
        "SELECT id, email, name, created_at FROM users WHERE email=? AND password_hash=?",
        (email, pw_hash),
    ).fetchone()

    if not user:
        raise HTTPException(401, "Invalid email or password")

    token = secrets.token_urlsafe(32)
    _auth_tokens[token] = user["id"]

    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "name": user["name"], "created_at": user["created_at"]},
    }


@app.get("/api/auth/me", tags=["Auth"])
async def auth_me(request: "Request"):
    """Get current user from Bearer token."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth.split(" ", 1)[1]
    user_id = _auth_tokens.get(token)
    if not user_id:
        raise HTTPException(401, "Invalid or expired token")

    conn = _get_auth_db()
    user = conn.execute("SELECT id, email, name, created_at FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(401, "User not found")

    return {"id": user["id"], "email": user["email"], "name": user["name"], "created_at": user["created_at"]}


@app.post("/api/auth/logout", tags=["Auth"])
async def auth_logout(request: "Request"):
    """Invalidate token."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        _auth_tokens.pop(token, None)
    return {"status": "ok"}


# ─── Adaptive Learning Engine ─────────────────────────────

def _get_learning_engine():
    """Lazy import to avoid circular deps; reuses orchestrator's instance when available."""
    if _orchestrator is not None and hasattr(_orchestrator, "learning"):
        return _orchestrator.learning
    from backend.orchestrator.learning import get_learning_engine
    return get_learning_engine()


@app.get("/api/learning/weights", tags=["Learning"])
async def learning_weights(
    regime: str = Query("RISK_ON", description="Market regime (RISK_ON, RISK_OFF, RANGE, TREND, EXPANSION)"),
    symbol: str = Query("*", description="Symbol filter or * for global"),
    user_id: str = Query("default"),
):
    """Return current adaptive weights blending static regime priors with learned performance."""
    try:
        engine = _get_learning_engine()
        return engine.get_weights(regime=regime, symbol=symbol, user_id=user_id)
    except Exception as exc:
        logger.error(f"Learning weights error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.get("/api/learning/performance", tags=["Learning"])
async def learning_performance(user_id: str = Query("default")):
    """Return full performance report: win rates, Sharpe, Sortino, regime breakdowns, recommendations."""
    try:
        engine = _get_learning_engine()
        return engine.get_report(user_id=user_id)
    except Exception as exc:
        logger.error(f"Learning performance error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.post("/api/learning/feedback", tags=["Learning"])
async def learning_feedback(request: Request):
    """
    Submit outcome feedback for a previously generated signal.

    Body JSON:
        signal_id  (str)  — ID of the signal to resolve
        outcome    (str)  — "win", "loss", or "scratch"
        exit_price (float) — exit fill price
        pnl        (float) — absolute PnL
        pnl_pct    (float) — PnL as a percentage of entry
        r_multiple (float, optional) — reward/risk ratio achieved
    """
    try:
        body = await request.json()
        signal_id = body.get("signal_id")
        outcome = body.get("outcome")
        exit_price = body.get("exit_price", 0)
        pnl = body.get("pnl", 0)
        pnl_pct = body.get("pnl_pct", 0)
        r_multiple = body.get("r_multiple", 0)

        if not signal_id or not outcome:
            raise HTTPException(400, detail="signal_id and outcome are required")
        if outcome not in ("win", "loss", "scratch"):
            raise HTTPException(400, detail="outcome must be 'win', 'loss', or 'scratch'")

        engine = _get_learning_engine()
        engine.tracker.resolve_signal(
            signal_id=signal_id,
            outcome=outcome,
            exit_price=float(exit_price),
            pnl=float(pnl),
            pnl_pct=float(pnl_pct),
            r_multiple=float(r_multiple),
        )
        return {"status": "ok", "signal_id": signal_id, "outcome": outcome}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Learning feedback error: {exc}")
        raise HTTPException(500, detail=str(exc))


# ═══════════════════════════════════════════════════════════
# Tax Estimation
# ═══════════════════════════════════════════════════════════

def _get_tax_engine():
    from backend.orchestrator.taxes import get_tax_engine
    return get_tax_engine()


@app.get("/api/tax/summary", tags=["Tax"])
async def tax_summary(year: int = Query(default=2026), filing_status: str = Query(default="single")):
    """Realized gains and estimated tax liability for a given year."""
    try:
        engine = _get_tax_engine()
        gains = engine.get_realized_gains(year)
        liability = engine.estimate_tax_liability(year, filing_status)
        return {
            "year": year,
            "realized_gains": gains,
            "liability": liability,
        }
    except Exception as exc:
        logger.error(f"Tax summary error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.get("/api/tax/lots", tags=["Tax"])
async def tax_lots(
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None),
):
    """Get tax lot details with optional filters."""
    try:
        engine = _get_tax_engine()
        lots = engine.get_lots(symbol=symbol, status=status, year=year)
        return {"lots": lots, "count": len(lots)}
    except Exception as exc:
        logger.error(f"Tax lots error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.get("/api/tax/harvest", tags=["Tax"])
async def tax_harvest_candidates():
    """Tax loss harvesting candidates from open paper positions."""
    try:
        engine = _get_tax_engine()
        # Build positions from open paper positions
        open_positions = [p for p in _paper_positions.values() if p["status"] == "open"]
        positions = [
            {
                "symbol": p["symbol"],
                "quantity": p["quantity"],
                "entry_price": p["entry_price"],
                "side": p.get("side", "long"),
            }
            for p in open_positions
        ]
        # Also include open tax lots
        open_lots = engine.get_lots(status="open")
        for lot in open_lots:
            positions.append({
                "symbol": lot["symbol"],
                "quantity": lot["quantity"],
                "entry_price": lot["entry_price"],
                "side": lot.get("side", "long"),
            })

        # Get current prices from the WebSocket manager
        current_prices: dict[str, float] = {}
        for p in positions:
            sym = p["symbol"].upper()
            if sym not in current_prices:
                # Try to get price from ws_manager
                price_data = ws_manager.last_prices.get(sym)
                if price_data and "price" in price_data:
                    current_prices[sym] = price_data["price"]

        candidates = engine.tax_loss_harvest_candidates(positions, current_prices)
        return {"candidates": candidates, "count": len(candidates)}
    except Exception as exc:
        logger.error(f"Tax harvest error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.get("/api/tax/wash-sales", tags=["Tax"])
async def tax_wash_sales():
    """Get wash sale warnings."""
    try:
        engine = _get_tax_engine()
        flags = engine.get_all_wash_sale_flags()
        return {"wash_sales": flags, "count": len(flags)}
    except Exception as exc:
        logger.error(f"Tax wash sales error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.post("/api/tax/record-lot", tags=["Tax"])
async def tax_record_lot(request: Request):
    """
    Manually record a tax lot.

    Body JSON:
        symbol     (str)   — ticker symbol
        quantity   (float) — number of units
        price      (float) — entry price per unit
        date       (str)   — entry date (ISO format)
        side       (str)   — 'long' or 'short' (default: 'long')
    """
    try:
        body = await request.json()
        symbol = body.get("symbol")
        quantity = body.get("quantity")
        price = body.get("price")
        date = body.get("date")
        side = body.get("side", "long")

        if not all([symbol, quantity, price, date]):
            raise HTTPException(400, detail="symbol, quantity, price, and date are required")

        engine = _get_tax_engine()
        lot_id = engine.record_lot(
            symbol=symbol,
            quantity=float(quantity),
            price=float(price),
            date=date,
            side=side,
        )
        return {"status": "ok", "lot_id": lot_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Tax record lot error: {exc}")
        raise HTTPException(500, detail=str(exc))


# ═══════════════════════════════════════════════════════════
# Autonomous Bot endpoints
# ═══════════════════════════════════════════════════════════

from backend.orchestrator.autobot import autobot


@app.post("/api/bot/start", tags=["Bot"], dependencies=[Depends(_burst_limit)])
async def bot_start(request: Request):
    try:
        body = await request.json()
        symbols = body.get("symbols", ["BTCUSDT", "ETHUSDT"])
        strategies = body.get("strategies", ["momentum", "mean_reversion", "trend_following", "breakout"])
        interval = int(body.get("interval", 60))
        max_concurrent = int(body.get("max_concurrent", 3))
        min_score = body.get("min_score")
        mode = body.get("mode", "paper")
        asset_class = body.get("asset_class", "crypto")
        autobot.start(
            symbols=symbols,
            strategies=strategies,
            interval_seconds=interval,
            max_concurrent=max_concurrent,
            min_score=int(min_score) if min_score is not None else None,
            mode=str(mode),
            asset_class=str(asset_class),
        )
        return {"status": "ok", "message": "Bot started", **autobot.get_status()}
    except Exception as exc:
        logger.error(f"Bot start error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.post("/api/bot/stop", tags=["Bot"], dependencies=[Depends(_burst_limit)])
async def bot_stop():
    autobot.stop()
    return {"status": "ok", "message": "Bot stopped"}


@app.get("/api/bot/status", tags=["Bot"])
async def bot_status():
    autobot.update_closed_trades()
    return autobot.get_status()


@app.get("/api/bot/performance", tags=["Bot"])
async def bot_performance():
    autobot.update_closed_trades()
    return autobot.get_performance()


@app.get("/api/bot/signals", tags=["Bot"])
async def bot_signals(limit: int = 50):
    return {"signals": autobot.get_signals(limit)}


@app.get("/api/bot/activity", tags=["Bot"])
async def bot_activity(limit: int = 100):
    return {"activity": autobot.get_activity_log(limit)}


@app.get("/api/bot/positions", tags=["Bot"])
async def bot_positions():
    """Live open positions from the paper executor."""
    return {"positions": autobot.get_open_positions()}


@app.get("/api/bot/trades", tags=["Bot"])
async def bot_trades(limit: int = 100):
    """Closed trades from persistent storage."""
    return {"trades": autobot.get_closed_trades(limit)}


@app.post("/api/bot/positions/{symbol}/close", tags=["Bot"], dependencies=[Depends(_burst_limit)])
async def bot_close_position(symbol: str):
    """Force-close an open position at market price."""
    return autobot.close_position(symbol)


@app.post("/api/bot/symbols/{symbol}/kill", tags=["Bot"], dependencies=[Depends(_burst_limit)])
async def bot_kill_symbol(symbol: str, reason: str = "manual"):
    """Manually disable a symbol from new entries. Existing positions still managed."""
    return autobot.kill_symbol(symbol, reason)


@app.post("/api/bot/symbols/{symbol}/reset", tags=["Bot"], dependencies=[Depends(_burst_limit)])
async def bot_reset_symbol(symbol: str):
    """Clear a symbol's kill state — re-enable new entries."""
    return autobot.reset_symbol_kill(symbol)


# ═══════════════════════════════════════════════════════════
# Options Recommender
# ═══════════════════════════════════════════════════════════

@app.get("/api/options/recommendations", tags=["Options"], dependencies=[Depends(_expensive_limit)])
async def options_recommendations(
    symbols: str = "SPY,QQQ,AAPL,NVDA,TSLA,MSFT,META",
    weeks: int = 3,
):
    """Top picks per (symbol, expiration) plus a single overall best trade.

    Returns, for each (symbol × expiration):
      * top_itm_calls — 2 best in-the-money calls (bullish, conviction)
      * top_otm_calls — 2 best out-of-the-money calls (bullish, leveraged)
      * top_itm_puts  — 2 best in-the-money puts  (bearish, conviction)
      * top_otm_puts  — 2 best out-of-the-money puts (bearish, leveraged)

    Plus the single highest-composite-score contract across the whole
    universe as overall_best_trade.

    Composite score (0-100):
      30% probability of profit, 25% liquidity, 20% spread tightness,
      15% greek fit (delta in target band), 10% IV value vs realised vol.
    """
    from backend.core.options_recommender import recommend_universe

    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    weeks_ahead = list(range(max(1, min(weeks, 6))))

    # Pull live underlying prices + recent returns for IV estimation.
    if _engine is None:
        raise HTTPException(503, "Engine not initialised")

    universe: list[tuple[str, float, list[float]]] = []
    for sym in syms:
        try:
            quote = await _engine.equities_feed.get_quote(sym)
            spot = float(quote.get("price") or 0) if quote else 0.0
        except Exception as exc:
            logger.debug(f"options spot lookup failed for {sym}: {exc}")
            spot = 0.0
        if spot <= 0:
            continue

        # 5m returns for realised vol estimate
        try:
            from datetime import date as _date, timedelta as _td
            today = _date.today()
            df = await _engine.equities_feed.get_ohlcv(
                sym, "5min",
                (today - _td(days=2)).isoformat(),
                today.isoformat(),
            )
            closes = df["close"].astype(float)
            returns = closes.pct_change().dropna().tail(50).tolist()
        except Exception:
            returns = []

        universe.append((sym, spot, returns))

    if not universe:
        return {"error": "no underlying prices available", "by_symbol": []}

    return recommend_universe(
        universe,
        expiries_weeks_ahead=weeks_ahead,
        top_n=2,
    )


# ═══════════════════════════════════════════════════════════
# Real Estate Portfolio endpoints
# ═══════════════════════════════════════════════════════════

_re_engine = None


def _get_re_engine():
    global _re_engine
    if _re_engine is None:
        from backend.orchestrator.realestate import RealEstateEngine
        _re_engine = RealEstateEngine()
    return _re_engine


@app.get("/api/realestate/portfolio", tags=["RealEstate"])
async def re_portfolio():
    engine = _get_re_engine()
    return engine.get_portfolio_summary()


@app.get("/api/realestate/property/{property_id}", tags=["RealEstate"])
async def re_property_detail(property_id: str):
    engine = _get_re_engine()
    prop = engine.get_property(property_id)
    if not prop:
        raise HTTPException(404, detail="Property not found")
    metrics = engine.calculate_metrics(property_id)
    return {**prop, "metrics": metrics}


@app.post("/api/realestate/property", tags=["RealEstate"])
async def re_add_property(request: Request):
    try:
        body = await request.json()
        engine = _get_re_engine()
        prop = engine.add_property(**body)
        return {"status": "ok", "property": prop}
    except Exception as exc:
        logger.error(f"Real estate add error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.put("/api/realestate/property/{property_id}", tags=["RealEstate"])
async def re_update_property(property_id: str, request: Request):
    try:
        body = await request.json()
        engine = _get_re_engine()
        with engine._conn() as conn:
            cols = [k for k in body.keys() if k != "id"]
            if not cols:
                return {"status": "ok"}
            set_clause = ", ".join(f"{c} = ?" for c in cols)
            vals = [body[c] for c in cols]
            conn.execute(f"UPDATE properties SET {set_clause} WHERE id = ?", vals + [property_id])
        return {"status": "ok"}
    except Exception as exc:
        logger.error(f"Real estate update error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.post("/api/realestate/property/{property_id}/transaction", tags=["RealEstate"])
async def re_add_transaction(property_id: str, request: Request):
    try:
        body = await request.json()
        engine = _get_re_engine()
        txn = engine.record_transaction(
            property_id=property_id,
            txn_type=body.get("type", "expense"),
            amount=float(body.get("amount", 0)),
            date=body.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            description=body.get("description", ""),
        )
        return {"status": "ok", "transaction": txn}
    except Exception as exc:
        logger.error(f"Real estate transaction error: {exc}")
        raise HTTPException(500, detail=str(exc))


@app.get("/api/realestate/property/{property_id}/cashflow", tags=["RealEstate"])
async def re_cashflow(property_id: str, months: int = 12):
    engine = _get_re_engine()
    return engine.get_cashflow_report(property_id, months)


@app.post("/api/realestate/seed", tags=["RealEstate"])
async def re_seed():
    engine = _get_re_engine()
    props = engine.seed_demo_properties()
    return {"status": "ok", "properties": props, "count": len(props)}
