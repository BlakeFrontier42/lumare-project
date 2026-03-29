"""
Lumare API — Pydantic schemas for request/response models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Generic ─────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: str
    version: str = "0.1.0"


# ─── Market Data ─────────────────────────────────────────

class PriceData(BaseModel):
    symbol: str
    price: float
    change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    timestamp: Optional[str] = None


class PricesResponse(BaseModel):
    prices: List[PriceData]
    timestamp: str


class CandleData(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: Optional[int] = None
    vwap: Optional[float] = None


class CandlesResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: List[CandleData]
    count: int


# ─── Scoring ─────────────────────────────────────────────

class SignalScore(BaseModel):
    symbol: str
    timestamp: Optional[str] = None
    composite_score: float
    trend_score: Optional[float] = None
    momentum_score: Optional[float] = None
    structure_score: Optional[float] = None
    flow_score: Optional[float] = None
    macro_score: Optional[float] = None
    direction: Optional[str] = None
    regime: Optional[str] = None
    action_taken: Optional[str] = None


class SignalScoreResponse(BaseModel):
    signal: Optional[SignalScore] = None
    message: Optional[str] = None


class RegimeResponse(BaseModel):
    symbol: str
    regime: Optional[str] = None
    previous_regime: Optional[str] = None
    trigger_reason: Optional[str] = None
    adx_value: Optional[float] = None
    atr_percentile: Optional[float] = None
    timestamp: Optional[str] = None


# ─── Portfolio ───────────────────────────────────────────

class PositionData(BaseModel):
    symbol: str
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    quantity: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class PortfolioSummaryResponse(BaseModel):
    total_equity: Optional[float] = None
    cash: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    total_pnl: Optional[float] = None
    portfolio_heat: Optional[float] = None
    open_positions: int = 0
    drawdown_pct: Optional[float] = None
    peak_equity: Optional[float] = None
    positions: List[PositionData] = []
    timestamp: Optional[str] = None


class TradeRecord(BaseModel):
    trade_id: Optional[str] = None
    symbol: str
    side: Optional[str] = None
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: Optional[float] = None
    leverage: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    r_multiple: Optional[float] = None
    fees: Optional[float] = None
    status: Optional[str] = None
    signal_score: Optional[int] = None
    regime: Optional[str] = None


class TradesResponse(BaseModel):
    trades: List[TradeRecord]
    count: int


# ─── Backtest ────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = Field(default=100_000.0, gt=0)


class BacktestResultSummary(BaseModel):
    symbol: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float
    final_equity: Optional[float] = None
    total_return_pct: Optional[float] = None
    total_trades: Optional[int] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    calmar_ratio: Optional[float] = None
    status: str = "completed"


class BacktestRunResponse(BaseModel):
    message: str
    result: Optional[BacktestResultSummary] = None
    error: Optional[str] = None


class BacktestResultsResponse(BaseModel):
    results: Optional[BacktestResultSummary] = None
    message: Optional[str] = None


# ─── Alpha ───────────────────────────────────────────────

class CongressionalTrade(BaseModel):
    politician: Optional[str] = None
    ticker: Optional[str] = None
    type: Optional[str] = None
    date: Optional[str] = None
    amount_range: Optional[str] = None


class CongressionalTradesResponse(BaseModel):
    trades: List[CongressionalTrade]
    count: int


class InsiderTransaction(BaseModel):
    insider: Optional[str] = None
    ticker: Optional[str] = None
    transaction_type: Optional[str] = None
    shares: Optional[float] = None
    price: Optional[float] = None
    date: Optional[str] = None
    title: Optional[str] = None


class InsiderTransactionsResponse(BaseModel):
    transactions: List[InsiderTransaction]
    count: int


# ─── Macro ──────────────────────────────────────────────

class MacroIndicator(BaseModel):
    key: str
    label: str
    value: Optional[float] = None
    unit: str = ""
    category: str = ""
    change: Optional[float] = None
    timestamp: Optional[str] = None
    source: Optional[str] = None


class MacroSnapshotResponse(BaseModel):
    indicators: List[MacroIndicator]
    regime: Optional[str] = None
    regime_timestamp: Optional[str] = None
    timestamp: str


# ─── Risk ──────────────────────────────────────────────

class RiskMetric(BaseModel):
    name: str
    value: Optional[float] = None
    unit: str = ""
    limit: Optional[float] = None
    status: str = "ok"  # ok, warning, danger


class StressTestResult(BaseModel):
    scenario: str
    market_impact: str
    portfolio_impact: Optional[float] = None
    portfolio_impact_pct: Optional[float] = None
    description: str = ""
    survives: bool = True


class RiskDashboardResponse(BaseModel):
    metrics: List[RiskMetric]
    stress_tests: List[StressTestResult]
    war_room_status: str = "NORMAL"
    total_equity: Optional[float] = None
    peak_equity: Optional[float] = None
    drawdown_pct: Optional[float] = None
    open_positions: int = 0
    timestamp: str


# ─── Float ──────────────────────────────────────────────

class FloatProfileResponse(BaseModel):
    symbol: str
    shares_outstanding: Optional[float] = None
    float_shares: Optional[float] = None
    restricted_shares: Optional[float] = None
    float_category: Optional[str] = None
    insider_ownership_pct: Optional[float] = None
    institutional_ownership_pct: Optional[float] = None
    public_float_pct: Optional[float] = None
    short_interest: Optional[float] = None
    short_pct_of_float: Optional[float] = None
    days_to_cover: Optional[float] = None
    avg_daily_volume: Optional[float] = None
    float_turnover_ratio: Optional[float] = None
    relative_volume: Optional[float] = None
    squeeze_potential: Optional[float] = None
    liquidity_score: Optional[float] = None
    volatility_multiplier: Optional[float] = None
    market_cap: Optional[float] = None
    last_updated: Optional[str] = None
    data_source: Optional[str] = None


class FloatSummaryResponse(BaseModel):
    profiles: List[FloatProfileResponse]
    count: int


class SqueezeCandidate(BaseModel):
    symbol: str
    float_shares: Optional[float] = None
    float_category: Optional[str] = None
    short_pct_of_float: Optional[float] = None
    squeeze_potential: Optional[float] = None
    volatility_multiplier: Optional[float] = None


class SqueezeCandidatesResponse(BaseModel):
    candidates: List[SqueezeCandidate]
    count: int


# ─── System ──────────────────────────────────────────────

class EngineStatus(BaseModel):
    engine_initialized: bool = False
    instruments: Optional[Dict[str, Any]] = None
    data_freshness: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None
    validation_targets: Optional[Dict[str, Any]] = None
    timestamp: str
