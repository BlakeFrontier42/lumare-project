"""
Lumare MIE — Master Configuration
All thresholds statistically justified. No magic numbers without documentation.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


# ─── API Keys ───────────────────────────────────────────────
class APIConfig:
    POLYGON_KEY = os.getenv("POLYGON_API_KEY", "")
    ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ALPACA_KEY = os.getenv("ALPACA_KEY", "")
    ALPACA_SECRET = os.getenv("ALPACA_SECRET", "")
    BLOWFIN_KEY = os.getenv("BLOWFIN_API_KEY", "")
    BLOWFIN_SECRET = os.getenv("BLOWFIN_SECRET", "")
    UNUSUAL_WHALES_KEY = os.getenv("UNUSUAL_WHALES_KEY", "")
    QUIVER_QUANT_KEY = os.getenv("QUIVER_QUANT_KEY", "")
    FRED_KEY = os.getenv("FRED_API_KEY", "")


# ─── Regime States ──────────────────────────────────────────
class RegimeState(Enum):
    RISK_ON = "RISK_ON"              # All strategies active
    RISK_OFF = "RISK_OFF"            # No momentum longs
    RANGE = "RANGE"                  # Mean-reversion only
    TREND = "TREND"                  # Trend-following active
    EXPANSION = "EXPANSION"          # Breakout logic allowed
    CHAOTIC = "CHAOTIC"              # NO TRADING


# ─── Regime Thresholds ──────────────────────────────────────
# Based on percentile analysis of historical BTC/ETH volatility
@dataclass
class RegimeThresholds:
    atr_percentile_high: float = 80.0     # Above = high vol
    atr_percentile_low: float = 20.0      # Below = low vol / range
    adx_trending: float = 25.0            # ADX > 25 = trending
    adx_strong_trend: float = 40.0        # ADX > 40 = strong trend
    adx_weak: float = 15.0               # ADX < 15 = range-bound
    vol_percentile_extreme: float = 90.0  # Chaotic threshold
    vol_percentile_high: float = 75.0     # High vol shock
    volume_expansion_ratio: float = 1.5   # 1.5x avg = expansion
    regime_lookback_period: int = 30      # Days for ATR percentile calc
    regime_confirmation_bars: int = 3     # Bars to confirm regime change


# ─── Signal Weights ─────────────────────────────────────────
# Each category scores 0-20, total 0-100
@dataclass
class SignalWeights:
    trend_weight: float = 1.0       # Max 20 points
    momentum_weight: float = 1.0    # Max 20 points
    structure_weight: float = 1.0   # Max 20 points
    flow_weight: float = 1.0       # Max 20 points
    macro_weight: float = 1.0      # Max 20 points


# ─── Signal Thresholds ──────────────────────────────────────
@dataclass
class SignalThresholds:
    # Trend
    adx_trending: float = 25.0
    adx_strong: float = 40.0
    ma_periods: List[int] = field(default_factory=lambda: [20, 50, 200])
    linreg_period: int = 20

    # Momentum
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    roc_period: int = 10

    # Structure (ICT)
    swing_lookback: int = 20
    fvg_min_gap_atr_multiple: float = 0.5  # FVG must be > 0.5x ATR
    displacement_atr_multiple: float = 1.5  # Displacement candle > 1.5x ATR
    bos_confirmation_candles: int = 2

    # Flow (Crypto)
    funding_rate_extreme_positive: float = 0.01   # 1% = heavily long
    funding_rate_extreme_negative: float = -0.01  # -1% = heavily short
    oi_change_significant: float = 0.05            # 5% OI change = significant

    # Flow (Equities)
    options_flow_imbalance_threshold: float = 0.6  # 60% calls = bullish
    congressional_cluster_min: int = 3             # 3+ politicians = signal
    insider_cluster_min: int = 2                   # 2+ insiders = signal


# ─── Trade Thresholds ───────────────────────────────────────
@dataclass
class TradeThresholds:
    # Global floor — per-asset profiles in core/asset_profiles.py set the
    # actual entry threshold per market. PHASE 4.6 VALIDATED: 70 was the
    # default that paired with crypto threshold 65 to produce PF 1.93 on
    # BTC 1Y. Do not lower without a fresh multi-month backtest.
    min_score_to_trade: int = 70
    elevated_score: int = 85              # Above = elevated position size
    standard_risk_pct: float = 0.01       # 1% base risk
    elevated_risk_pct: float = 0.0125     # 1.25% elevated risk
    reduced_risk_pct: float = 0.0075      # 0.75% reduced risk


# ─── Risk Engine Configuration ──────────────────────────────
@dataclass
class RiskConfig:
    base_risk_per_trade: float = 0.01     # 1% of portfolio
    min_risk_per_trade: float = 0.0075    # 0.75% minimum
    max_risk_per_trade: float = 0.0125    # 1.25% maximum
    max_portfolio_heat: float = 0.20      # 20% max capital at risk
    max_correlated_positions: int = 3     # Max correlated positions
    correlation_threshold: float = 0.7    # Above = considered correlated
    correlation_window: int = 30          # Rolling window in days

    # Drawdown circuit breakers
    drawdown_pause_threshold: float = -0.10   # -10% = pause new trades
    drawdown_reduce_threshold: float = -0.12  # -12% = reduce size 50%
    drawdown_shutdown_threshold: float = -0.15 # -15% = hard shutdown

    # Crypto-specific
    daily_loss_cap: float = 0.04          # 4% daily loss cap
    no_averaging_down: bool = True
    no_martingale: bool = True
    no_revenge_scaling: bool = True


# ─── Leverage Rules (Crypto) ────────────────────────────────
@dataclass
class LeverageConfig:
    # Stop distance -> max leverage mapping
    tight_stop_threshold: float = 0.005   # < 0.5% stop
    tight_stop_max_leverage: float = 8.0
    medium_stop_threshold: float = 0.01   # < 1.0% stop
    medium_stop_max_leverage: float = 5.0
    wide_stop_max_leverage: float = 3.0   # > 1.0% stop

    # 20x DISABLED until 6-month validation
    absolute_max_leverage: float = 8.0
    high_leverage_unlocked: bool = False
    high_leverage_max: float = 20.0


# ─── Position Management ────────────────────────────────────
@dataclass
class PositionConfig:
    # Scale-in protocol
    initial_entry_pct: float = 0.25       # 25% starter
    confirmation_add_pct: float = 0.25    # +25% on confirmation
    full_add_pct: float = 0.50            # Full size on key level break

    # Take profit - Mean Reversion
    mr_tp1_pct: float = 0.50             # 50% at 1R
    mr_tp1_r: float = 1.0
    mr_tp2_pct: float = 0.50             # 50% at 2R
    mr_tp2_r: float = 2.0

    # Take profit - Expansion/Breakout
    exp_tp1_pct: float = 0.25            # 25% at 1R
    exp_tp1_r: float = 1.0
    exp_tp2_pct: float = 0.25            # 25% at 2R
    exp_tp2_r: float = 2.0
    exp_tp3_pct: float = 0.25            # 25% at 3R
    exp_tp3_r: float = 3.0
    exp_runner_pct: float = 0.25         # 25% trailing stop


# ─── Timeframe Configuration ────────────────────────────────
@dataclass
class TimeframeConfig:
    macro_bias: str = "1D"
    regime_classification: str = "4H"
    liquidity_map: str = "1H"
    setup_detection: str = "15M"
    execution_trigger: str = "5M"
    confirmation: str = "1M"

    # Map to minutes for internal use
    timeframe_minutes: Dict[str, int] = field(default_factory=lambda: {
        "1M": 1, "5M": 5, "15M": 15, "1H": 60, "4H": 240, "1D": 1440
    })


# ─── Backtest Configuration ─────────────────────────────────
@dataclass
class BacktestConfig:
    min_trades: int = 300
    min_history_days: int = 365
    slippage_bps: float = 5.0            # 5 basis points
    commission_pct: float = 0.001         # 0.1% per trade (taker)
    maker_commission_pct: float = 0.0005  # 0.05% (maker/limit)

    # Walk-forward settings
    train_window_days: int = 180          # 6 months training
    test_window_days: int = 60            # 2 months testing
    walk_forward_step_days: int = 30      # 1 month step

    # Monte Carlo
    monte_carlo_iterations: int = 1000
    monte_carlo_confidence: float = 0.95


# ─── Validation Targets ─────────────────────────────────────
@dataclass
class ValidationTargets:
    min_win_rate: float = 0.60
    stretch_win_rate: float = 0.65
    min_sharpe: float = 2.0
    stretch_sharpe: float = 2.5
    min_profit_factor: float = 1.5
    max_drawdown: float = 0.15            # 15%
    min_trades: int = 300
    min_sortino: float = 2.0
    min_calmar: float = 1.5


# ─── Execution Configuration ────────────────────────────────
@dataclass
class ExecutionConfig:
    order_type: str = "limit"             # Limit orders only
    max_slippage_bps: float = 10.0        # Max acceptable slippage
    order_timeout_seconds: int = 300       # Cancel unfilled after 5min
    latency_model_ms: float = 50.0        # Simulated latency

    # Simulation
    sim_fill_probability: float = 0.85    # Limit order fill rate
    sim_partial_fill_min: float = 0.5     # Min partial fill


# ─── Instruments ────────────────────────────────────────────
@dataclass
class InstrumentConfig:
    crypto_pairs: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT"])
    equity_symbols: List[str] = field(default_factory=lambda: ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN"])


# ─── VaR Configuration ──────────────────────────────────────
@dataclass
class VaRConfig:
    confidence_level: float = 0.99        # 99% VaR
    lookback_days: int = 252              # 1 year of trading days
    max_portfolio_var_pct: float = 0.05   # 5% max daily VaR
    parametric: bool = True
    historical: bool = True
    monte_carlo_sims: int = 10000


# ─── Master Settings ────────────────────────────────────────
@dataclass
class Settings:
    api: APIConfig = field(default_factory=APIConfig)
    regime: RegimeThresholds = field(default_factory=RegimeThresholds)
    signals: SignalThresholds = field(default_factory=SignalThresholds)
    signal_weights: SignalWeights = field(default_factory=SignalWeights)
    trade: TradeThresholds = field(default_factory=TradeThresholds)
    risk: RiskConfig = field(default_factory=RiskConfig)
    leverage: LeverageConfig = field(default_factory=LeverageConfig)
    position: PositionConfig = field(default_factory=PositionConfig)
    timeframes: TimeframeConfig = field(default_factory=TimeframeConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    validation: ValidationTargets = field(default_factory=ValidationTargets)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    instruments: InstrumentConfig = field(default_factory=InstrumentConfig)
    var: VaRConfig = field(default_factory=VaRConfig)

    # Database
    db_path: str = "data/lumare.db"
    log_level: str = "INFO"


# Singleton
SETTINGS = Settings()
