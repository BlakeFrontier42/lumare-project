"""
Lumare API — FastAPI application.

Provides REST endpoints for the frontend to consume market data,
scoring signals, portfolio state, backtest results, and alpha feeds.
"""

import asyncio
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, WebSocket, WebSocketDisconnect
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
from backend.api.websocket import ws_manager

# ─── Engine Singleton ────────────────────────────────────

_engine = None
_last_backtest_result = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the LumareEngine on startup and start WebSocket streaming."""
    global _engine
    try:
        from backend.main import LumareEngine
        _engine = LumareEngine()
        logger.info("Lumare API started — engine initialized")

        # Start WebSocket price streaming in the background
        asyncio.create_task(ws_manager.start_price_stream(_engine))
    except Exception as exc:
        logger.error(f"Failed to initialize LumareEngine: {exc}")
        _engine = None
    yield
    ws_manager.stop()
    logger.info("Lumare API shutting down")


app = FastAPI(
    title="Lumare Capital Intelligence API",
    description="REST API for the Lumare Macro Intelligence Engine",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
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


# ═══════════════════════════════════════════════════════════
# Market Data
# ═══════════════════════════════════════════════════════════

@app.get("/api/markets/prices", response_model=PricesResponse, tags=["Markets"])
async def get_prices(engine=Depends(get_engine)):
    """Get latest prices for all watched symbols."""
    symbols = (
        engine.settings.instruments.crypto_pairs
        + engine.settings.instruments.equity_symbols
    )
    prices = []

    for symbol in symbols:
        try:
            ticker = await engine.crypto_feed.get_ticker(symbol)
            prices.append(PriceData(
                symbol=symbol,
                price=float(ticker.get("last", 0)),
                change_24h=float(ticker.get("percentage", 0)) if ticker.get("percentage") else None,
                volume_24h=float(ticker.get("quoteVolume", 0)) if ticker.get("quoteVolume") else None,
                high_24h=float(ticker.get("high", 0)) if ticker.get("high") else None,
                low_24h=float(ticker.get("low", 0)) if ticker.get("low") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
        except Exception as exc:
            logger.warning(f"Failed to fetch price for {symbol}: {exc}")
            prices.append(PriceData(
                symbol=symbol,
                price=0.0,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

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
    """Get OHLCV candle data for a symbol."""
    now = datetime.now(timezone.utc)
    if not end:
        end = now.isoformat()
    if not start:
        # Default: last 200 bars based on timeframe
        tf_minutes = engine.settings.timeframes.timeframe_minutes.get(timeframe, 60)
        start = (now - timedelta(minutes=tf_minutes * limit)).isoformat()

    try:
        df = engine.storage.get_candles(symbol, timeframe, start, end)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to retrieve candles: {exc}")

    if df is None or df.empty:
        return CandlesResponse(symbol=symbol, timeframe=timeframe, candles=[], count=0)

    # Limit rows
    df = df.tail(limit)

    candles = [
        CandleData(
            timestamp=str(row.get("timestamp", row.name if hasattr(row, "name") else "")),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            trade_count=int(row["trade_count"]) if pd.notna(row.get("trade_count")) else None,
            vwap=float(row["vwap"]) if pd.notna(row.get("vwap")) else None,
        )
        for _, row in df.iterrows()
    ]

    return CandlesResponse(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        count=len(candles),
    )


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
