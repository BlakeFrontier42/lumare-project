"""
replay_engine.py -- Replay-based backtesting engine for Lumare MIE.

Processes candles one at a time in chronological order with ZERO lookahead bias.
Supports walk-forward validation, Monte Carlo stress testing, and regime-segmented
analysis.

All higher-timeframe candles are built incrementally from the 5M execution timeframe.
"""

from __future__ import annotations

import copy
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from backend.backtest.performance_metrics import (
    PerformanceMetrics,
    MetricsResult,
    check_overfitting,
    validate_results,
)
from backend.core.asset_profiles import AssetProfile, get_profile


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Complete backtest output."""
    symbol: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 0.0
    final_capital: float = 0.0
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    trades: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Optional[MetricsResult] = None
    regime_history: List[Dict[str, Any]] = field(default_factory=list)
    signals_log: List[Dict[str, Any]] = field(default_factory=list)
    total_bars_processed: int = 0
    execution_time_seconds: float = 0.0


@dataclass
class WalkForwardResult:
    """Walk-forward validation output."""
    combined_metrics: Optional[MetricsResult] = None
    combined_equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    combined_trades: List[Dict[str, Any]] = field(default_factory=list)
    per_window: List[Dict[str, Any]] = field(default_factory=list)
    overfitting_check: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonteCarloResult:
    """Monte Carlo stress test output."""
    n_simulations: int = 0
    median_final_equity: float = 0.0
    p5_final_equity: float = 0.0
    p95_final_equity: float = 0.0
    p5_max_drawdown: float = 0.0
    median_max_drawdown: float = 0.0
    p95_max_drawdown: float = 0.0
    sharpe_ci_low: float = 0.0
    sharpe_ci_high: float = 0.0
    max_dd_ci_low: float = 0.0
    max_dd_ci_high: float = 0.0
    final_equity_ci_low: float = 0.0
    final_equity_ci_high: float = 0.0
    ruin_probability: float = 0.0  # fraction of sims where equity drops below 50%


# ---------------------------------------------------------------------------
# Higher-timeframe candle builder (no lookahead)
# ---------------------------------------------------------------------------

class CandleAggregator:
    """
    Incrementally builds higher-timeframe candles from 5M bars.

    Each higher TF candle is only "completed" when all constituent 5M bars
    have been received.  At any point, the partial candle is available but
    clearly marked incomplete so downstream code never sees a future bar.
    """

    # Number of 5M bars per higher TF
    TF_MULTIPLIERS = {
        "5M": 1,
        "15M": 3,
        "1H": 12,
        "4H": 48,
        "1D": 288,
    }

    def __init__(self) -> None:
        self._buffers: Dict[str, List[Dict]] = {}  # tf -> list of 5M bars
        self._completed: Dict[str, List[Dict]] = {}  # tf -> completed candles
        for tf in self.TF_MULTIPLIERS:
            self._buffers[tf] = []
            self._completed[tf] = []

    def add_bar(self, bar: Dict) -> Dict[str, bool]:
        """
        Add a 5M bar and update all higher TF candles.

        Parameters
        ----------
        bar : dict
            Keys: timestamp, open, high, low, close, volume.

        Returns
        -------
        dict mapping timeframe -> True if a new completed candle was produced.
        """
        completions = {}

        for tf, multiplier in self.TF_MULTIPLIERS.items():
            self._buffers[tf].append(bar)
            if len(self._buffers[tf]) >= multiplier:
                candle = self._aggregate_buffer(self._buffers[tf])
                self._completed[tf].append(candle)
                self._buffers[tf] = []
                completions[tf] = True
            else:
                completions[tf] = False

        return completions

    def get_completed_candles(self, timeframe: str, lookback: int = 200) -> pd.DataFrame:
        """Return the last *lookback* completed candles for a timeframe as a DataFrame."""
        candles = self._completed.get(timeframe, [])
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        recent = candles[-lookback:]
        return pd.DataFrame(recent)

    def get_partial_candle(self, timeframe: str) -> Optional[Dict]:
        """Return the currently building (incomplete) candle, if any."""
        buf = self._buffers.get(timeframe, [])
        if not buf:
            return None
        return self._aggregate_buffer(buf)

    @staticmethod
    def _aggregate_buffer(bars: List[Dict]) -> Dict:
        return {
            "timestamp": bars[0]["timestamp"],
            "open": bars[0]["open"],
            "high": max(b["high"] for b in bars),
            "low": min(b["low"] for b in bars),
            "close": bars[-1]["close"],
            "volume": sum(b["volume"] for b in bars),
        }

    def reset(self) -> None:
        for tf in self.TF_MULTIPLIERS:
            self._buffers[tf] = []
            self._completed[tf] = []


# ---------------------------------------------------------------------------
# Simulated position tracker
# ---------------------------------------------------------------------------

@dataclass
class SimPosition:
    """A single simulated open position."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    side: str = "long"
    entry_price: float = 0.0
    quantity: float = 0.0
    entry_time: Any = None
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop_distance: float = 0.0
    trailing_stop_price: float = 0.0
    fees_paid: float = 0.0
    slippage_cost: float = 0.0
    score_at_entry: float = 0.0
    regime_at_entry: str = ""


# ---------------------------------------------------------------------------
# Replay Engine
# ---------------------------------------------------------------------------

class ReplayEngine:
    """
    Bar-by-bar replay backtester.

    Processes 5M candles chronologically, building higher-timeframe candles
    incrementally.  No future data is ever visible to the signal/risk pipeline.
    """

    # Slippage: 5 bps base + volatility component
    BASE_SLIPPAGE_BPS = 5.0
    # Fees: taker rate
    TAKER_FEE_RATE = 0.001
    MAKER_FEE_RATE = 0.0005
    # Minimum bars before trading starts (need enough for indicators)
    MIN_WARMUP_BARS = 250
    # Score threshold for trade entry.
    # NOTE: live target is 70. Backtest uses 65 (flow/macro neutralised at 50).
    SCORE_THRESHOLD = 65

    def __init__(
        self,
        settings: Any,
        storage: Any,
        regime_engine: Any,
        scoring_engine: Any,
        risk_engine: Any,
        portfolio_engine: Any,
        equity_governor: Any,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.regime_engine = regime_engine
        self.scoring_engine = scoring_engine
        self.risk_engine = risk_engine
        self.portfolio_engine = portfolio_engine
        self.equity_governor = equity_governor

        self._aggregator = CandleAggregator()
        self._positions: List[SimPosition] = []
        self._closed_trades: List[Dict[str, Any]] = []
        self._equity_history: List[Tuple[Any, float]] = []
        self._signals_log: List[Dict[str, Any]] = []
        self._regime_history: List[Dict[str, Any]] = []
        self._cash: float = 0.0
        self._bar_count: int = 0
        self._scores_logged: int = 0  # diagnostic: log first few scoring events at INFO

        # Active asset profile — set per run() call based on symbol.
        # Defaults to equity (conservative) until run() picks a profile.
        self._profile: AssetProfile = get_profile("SPY")
        self._regime_error_logged: bool = False

    # ------------------------------------------------------------------
    # Main backtest run
    # ------------------------------------------------------------------

    def run(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100_000.0,
    ) -> BacktestResult:
        """
        Run a full backtest for a single symbol.

        Parameters
        ----------
        symbol : str
            Instrument identifier (e.g. "BTC-USDT-PERP").
        start_date : str
            ISO date string for backtest start.
        end_date : str
            ISO date string for backtest end.
        initial_capital : float
            Starting equity.

        Returns
        -------
        BacktestResult with equity curve, trades, metrics, and logs.
        """
        import time as _time
        t0 = _time.monotonic()

        logger.info(
            "Backtest START: {} from {} to {} with ${:,.0f}",
            symbol, start_date, end_date, initial_capital,
        )

        # Reset state
        self._reset(initial_capital)

        # Pick asset profile for this symbol (crypto/equity/futures/options)
        self._profile = get_profile(symbol)
        self._regime_error_logged = False
        logger.info(
            "Profile: {} | regime_mode={} | score_threshold={} | rr={} | stop_atr={}",
            self._profile.name, self._profile.regime_mode,
            self._profile.score_threshold, self._profile.rr_ratio,
            self._profile.stop_atr_mult,
        )

        # Load historical 5M candles
        candles_5m = self._load_candles(symbol, start_date, end_date)
        if candles_5m.empty:
            logger.error("No candles loaded for {} -- aborting backtest", symbol)
            return BacktestResult(symbol=symbol, start_date=start_date, end_date=end_date)

        logger.info("Loaded {} 5M candles for {}", len(candles_5m), symbol)

        # Bar-by-bar replay
        total_bars = len(candles_5m)
        for idx in range(total_bars):
            row = candles_5m.iloc[idx]
            bar = {
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }

            self._process_bar(symbol, bar, idx)

            # Progress logging every 10% of bars
            if idx > 0 and idx % (total_bars // 10) == 0:
                pct = idx * 100 // total_bars
                logger.info(
                    "Progress: {}% ({}/{}) | trades={} | equity=${:,.0f}",
                    pct, idx, total_bars, len(self._closed_trades),
                    self._total_equity(bar["close"]),
                )

        # Flatten any remaining open positions at last close
        if candles_5m.shape[0] > 0:
            last_bar = candles_5m.iloc[-1]
            self._force_close_all(float(last_bar["close"]), last_bar["timestamp"])

        # Build equity curve
        equity_curve = pd.Series(
            [e[1] for e in self._equity_history],
            index=pd.DatetimeIndex([e[0] for e in self._equity_history]),
            name="equity",
        )

        # Compute metrics
        metrics = PerformanceMetrics.calculate_all(
            equity_curve, self._closed_trades
        )

        elapsed = _time.monotonic() - t0
        logger.info(
            "Backtest DONE: {} | {:.1f}s | {} trades | Sharpe={:.2f} | DD={:.1%}",
            symbol, elapsed, len(self._closed_trades),
            metrics.sharpe, metrics.max_drawdown.get("max_dd", 0),
        )

        # Exit reason breakdown
        from collections import Counter
        exit_reasons = Counter(t.get("exit_reason", "unknown") for t in self._closed_trades)
        reason_pnls = {}
        for t in self._closed_trades:
            r = t.get("exit_reason", "unknown")
            if r not in reason_pnls:
                reason_pnls[r] = {"wins": 0, "losses": 0, "pnl": 0.0}
            pnl = t.get("pnl", 0)
            reason_pnls[r]["pnl"] += pnl
            if pnl > 0:
                reason_pnls[r]["wins"] += 1
            else:
                reason_pnls[r]["losses"] += 1

        logger.info("Exit reason breakdown:")
        for reason, count in exit_reasons.most_common():
            rp = reason_pnls[reason]
            wr = rp["wins"] / count * 100 if count > 0 else 0
            logger.info(
                "  {}: {} trades (WR={:.0f}%) | PnL=${:.2f} | W={} L={}",
                reason, count, wr, rp["pnl"], rp["wins"], rp["losses"],
            )

        # Side breakdown
        longs = [t for t in self._closed_trades if t.get("side") == "long"]
        shorts = [t for t in self._closed_trades if t.get("side") == "short"]
        long_pnl = sum(t.get("pnl", 0) for t in longs)
        short_pnl = sum(t.get("pnl", 0) for t in shorts)
        logger.info("Side breakdown: Longs={} (${:.2f}) | Shorts={} (${:.2f})",
                     len(longs), long_pnl, len(shorts), short_pnl)

        # Score analysis: winners vs losers entry scores
        winners = [t for t in self._closed_trades if t.get("pnl", 0) > 0]
        losers = [t for t in self._closed_trades if t.get("pnl", 0) <= 0]
        if winners:
            avg_win_score = np.mean([t.get("score_at_entry", 0) for t in winners])
            logger.info("Winner avg entry score: {:.1f} (n={})", avg_win_score, len(winners))
        if losers:
            avg_loss_score = np.mean([t.get("score_at_entry", 0) for t in losers])
            logger.info("Loser avg entry score: {:.1f} (n={})", avg_loss_score, len(losers))

        # Regime breakdown
        from collections import defaultdict
        regime_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
        for t in self._closed_trades:
            r = t.get("regime_at_entry", "unknown")
            regime_stats[r]["pnl"] += t.get("pnl", 0)
            if t.get("pnl", 0) > 0:
                regime_stats[r]["wins"] += 1
            else:
                regime_stats[r]["losses"] += 1
        logger.info("Regime breakdown:")
        for regime, stats in sorted(regime_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
            total = stats["wins"] + stats["losses"]
            wr = stats["wins"] / total * 100 if total > 0 else 0
            logger.info("  {}: {} trades (WR={:.0f}%) | PnL=${:.2f}",
                        regime, total, wr, stats["pnl"])

        return BacktestResult(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=self._total_equity(
                float(candles_5m.iloc[-1]["close"]) if not candles_5m.empty else 0
            ),
            equity_curve=equity_curve,
            trades=self._closed_trades,
            metrics=metrics,
            regime_history=self._regime_history,
            signals_log=self._signals_log,
            total_bars_processed=self._bar_count,
            execution_time_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Bar processing
    # ------------------------------------------------------------------

    def _process_bar(self, symbol: str, bar: Dict, bar_idx: int) -> None:
        """Process a single 5M bar -- the core replay loop body."""
        self._bar_count += 1

        # 1. Update higher-timeframe candles
        completions = self._aggregator.add_bar(bar)

        # 2. Manage open positions (stops, take profits, trailing)
        self._manage_positions(bar)

        # 3. Record equity snapshot
        equity = self._total_equity(bar["close"])
        self._equity_history.append((bar["timestamp"], equity))

        # 4. Skip if still in warmup period
        if self._bar_count < self.MIN_WARMUP_BARS:
            return

        # 5. Run regime classification and scoring only on new 1H candle
        # (running on every 5M bar is 12x redundant and very slow)
        if not completions.get("1H", False):
            return

        current_regime = self._classify_regime(completions)

        # Log a sample score every 24 hours (every 24th 1H candle) for diagnostics
        _sample = (self._bar_count // 12) % 24 == 0

        # 6. Run signal scoring (both long and short)
        long_score = self._score_signal(symbol, "long", completions, current_regime)
        short_score = self._score_signal(symbol, "short", completions, current_regime)

        if _sample:
            logger.debug("Score sample | regime={} long={:.1f} short={:.1f}", current_regime, long_score, short_score)

        # Log signals
        self._signals_log.append({
            "timestamp": bar["timestamp"],
            "bar_idx": bar_idx,
            "long_score": long_score,
            "short_score": short_score,
            "regime": current_regime,
            "close": bar["close"],
        })

        # 7. Check if score threshold met, generate trade proposal
        best_side = None
        best_score = 0.0
        # Shorts require higher conviction (asset profile defines long bias offset)
        long_threshold = self._profile.score_threshold
        short_threshold = long_threshold + self._profile.short_threshold_bonus
        if not self._profile.allow_shorts:
            short_threshold = float("inf")
        if long_score >= long_threshold and long_score >= short_score:
            best_side = "long"
            best_score = long_score
        elif short_score >= short_threshold and short_score > long_score:
            best_side = "short"
            best_score = short_score

        if best_side is None:
            return

        # Quality gate 1: require the winning score to be at least 5 pts above
        # the opposing direction to avoid ambiguous / choppy signals
        opposing_score = short_score if best_side == "long" else long_score
        if best_score - opposing_score < 5.0:
            return

        # Quality gate 2: soft trend alignment on 4H timeframe
        # Block trades that are clearly against the 4H trend (price on wrong side of EMA50)
        # Neutral/sideways markets still allow trading
        df_4h = self._aggregator.get_completed_candles("4H", lookback=60)
        if len(df_4h) >= 50:
            closes_4h = df_4h["close"].astype(float)
            ema50 = closes_4h.ewm(span=50, adjust=False).mean()
            current_price = closes_4h.iloc[-1]
            ema50_val = ema50.iloc[-1]
            # Percentage distance from EMA50
            distance_pct = (current_price - ema50_val) / ema50_val

            # Only block when clearly against the trend (>2% on wrong side)
            if best_side == "long" and distance_pct < -0.02:
                return  # Price is >2% below EMA50 — don't go long
            if best_side == "short" and distance_pct > 0.02:
                return  # Price is >2% above EMA50 — don't go short

        # Quality gate 3: loss streak filter — after 4 consecutive losses,
        # require a HIGHER score (65+) before re-entering
        if len(self._closed_trades) >= 4:
            last_4 = self._closed_trades[-4:]
            if all(t["pnl"] < 0 for t in last_4):
                if best_score < self._profile.score_threshold:
                    return  # Need stronger conviction after losing streak

        # Don't enter if already in a position for this symbol on this side
        if any(p.symbol == symbol and p.side == best_side for p in self._positions):
            return

        # Cooldown: after a stop loss, wait at least 12 bars (1H) before re-entering
        # This prevents re-entering at the same bad level after being stopped out
        if self._closed_trades:
            last_trade = self._closed_trades[-1]
            if last_trade.get("exit_reason") == "stop_loss" and last_trade.get("symbol") == symbol:
                # Check how many bars since the last exit
                last_exit_time = last_trade.get("exit_time")
                current_time = bar.get("timestamp")
                if last_exit_time and current_time:
                    try:
                        from datetime import datetime
                        if isinstance(last_exit_time, str):
                            last_exit_time = pd.Timestamp(last_exit_time)
                        if isinstance(current_time, str):
                            current_time = pd.Timestamp(current_time)
                        bars_since = (current_time - last_exit_time).total_seconds() / 300  # 5M bars
                        if bars_since < 12:  # Less than 1 hour
                            return
                    except Exception:
                        pass  # Ignore timestamp parsing failures

        # 8. Generate trade proposal
        proposal = self._create_proposal(symbol, best_side, best_score, bar, current_regime)

        # 9. Risk checks
        if not self._passes_risk_checks(proposal, bar):
            return

        # 10. Execute simulated entry
        self._execute_entry(proposal, bar)

    def _classify_regime(self, completions: Dict[str, bool]) -> str:
        """Run regime classification on 1H data if available."""
        df_1h = self._aggregator.get_completed_candles("1H", lookback=200)
        if df_1h.empty or len(df_1h) < 50:
            return "RISK_ON"

        try:
            closes = df_1h["close"].astype(float)
            highs = df_1h["high"].astype(float)
            lows = df_1h["low"].astype(float)
            volumes = df_1h["volume"].astype(float)

            # ATR
            prev_close = closes.shift(1)
            tr = pd.concat([highs - lows, (highs - prev_close).abs(), (lows - prev_close).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            current_atr = float(atr.iloc[-1]) if not atr.empty else 0.0
            atr_pct = float((atr.dropna() <= current_atr).mean() * 100)

            # Volatility percentile (annualised returns std)
            returns = closes.pct_change().dropna()
            rolling_vol = returns.rolling(14).std()
            current_vol = float(rolling_vol.iloc[-1]) if not rolling_vol.empty else 0.0
            vol_pct = float((rolling_vol.dropna() <= current_vol).mean() * 100)

            # ADX (simple DX approximation)
            plus_dm = (highs.diff()).clip(lower=0)
            minus_dm = (-lows.diff()).clip(lower=0)
            plus_dm[plus_dm < minus_dm] = 0
            minus_dm[minus_dm < plus_dm] = 0
            smoothed_plus = plus_dm.rolling(14).mean()
            smoothed_minus = minus_dm.rolling(14).mean()
            smoothed_tr = tr.rolling(14).mean()
            plus_di = 100 * smoothed_plus / smoothed_tr.replace(0, float("nan"))
            minus_di = 100 * smoothed_minus / smoothed_tr.replace(0, float("nan"))
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
            adx_val = float(dx.rolling(14).mean().iloc[-1]) if not dx.empty else 20.0
            adx_val = 0.0 if pd.isna(adx_val) else adx_val

            # Volume ratio
            avg_vol = float(volumes.rolling(20).mean().iloc[-1]) or 1.0
            vol_ratio = float(volumes.iloc[-1]) / avg_vol

            # Breakout: close > recent 20-bar high
            recent_high = highs.iloc[-21:-1].max() if len(highs) > 21 else highs.max()
            breakout = bool(closes.iloc[-1] > recent_high)

            market_data_dict = {
                "vol_percentile": vol_pct,
                "atr_percentile": atr_pct,
                "adx": adx_val,
                "volume_ratio": vol_ratio,
                "breakout_detected": breakout,
                "macro_stress": False,
                "macro_liquidity_expanding": True,
            }

            result = self.regime_engine.classify(market_data_dict)
            regime_raw = result.state.value if hasattr(result, "state") else "RISK_ON"
            if self._bar_count < 5000 and self._bar_count % 1000 == 0:
                logger.info("Regime debug bar={}: adx={:.1f} atr_pct={:.0f} vol_pct={:.0f} vol_ratio={:.2f} breakout={} → {}",
                            self._bar_count, adx_val, atr_pct, vol_pct, vol_ratio, breakout, regime_raw)
        except Exception as exc:
            if not self._regime_error_logged:
                logger.warning("Regime classification failed (first occurrence): {}", exc)
                self._regime_error_logged = True
            else:
                logger.debug("Regime classification failed: {}", exc)
            regime_raw = "RISK_ON"

        # Apply per-asset profile gating
        if self._profile.regime_mode == "bypass":
            regime = "RISK_ON"
        elif self._profile.regime_mode == "permissive":
            regime = "RISK_ON" if regime_raw == "CHAOTIC" else regime_raw
        else:  # strict
            regime = regime_raw

        if not self._regime_history or self._regime_history[-1].get("regime") != regime:
            self._regime_history.append({
                "timestamp": df_1h.iloc[-1]["timestamp"] if "timestamp" in df_1h.columns else None,
                "regime": regime,
                "bar_count": self._bar_count,
            })

        return regime

    def _score_signal(
        self, symbol: str, direction: str, completions: Dict[str, bool], regime_str: str = "RISK_ON"
    ) -> float:
        """
        Run the scoring engine for a given direction.

        Collects data from multiple timeframes and passes to the scoring engine.
        Returns composite score 0-100.
        """
        from backend.core.regime_engine import RegimeState

        # Build multi-timeframe data bundle
        tf_data = {}
        for tf in ["5M", "15M", "1H", "4H", "1D"]:
            df = self._aggregator.get_completed_candles(tf, lookback=200)
            if not df.empty:
                tf_data[tf] = df

        if "1H" not in tf_data or len(tf_data["1H"]) < 50:
            return 0.0

        try:
            try:
                regime = RegimeState(regime_str)
            except ValueError:
                regime = RegimeState.RISK_ON

            market_data = {"timeframe_data": tf_data, "symbol": symbol}
            result = self.scoring_engine.score(market_data, regime, direction)

            score_val = 0.0
            if hasattr(result, "total_score"):
                score_val = float(result.total_score)
            elif isinstance(result, dict):
                score_val = float(result.get("score", 0))

            # Log per-engine breakdown for the first 3 scoring events
            if self._scores_logged < 3 and hasattr(result, "component_scores"):
                breakdown = " | ".join(
                    f"{n}={cs.raw_score:.0f}"
                    for n, cs in result.component_scores.items()
                )
                logger.info("Score breakdown [{}] {} → {} | total={:.1f}",
                            direction, symbol, breakdown, score_val)
                self._scores_logged += 1

            return score_val
        except Exception as exc:
            logger.debug("Scoring failed for {} {}: {}", symbol, direction, exc)
            return 0.0

    def _create_proposal(
        self, symbol: str, side: str, score: float, bar: Dict, regime: str
    ) -> Dict[str, Any]:
        """Build a trade proposal dict for risk engine evaluation."""
        close = bar["close"]
        atr = self._estimate_atr(close)

        # Position sizing: per-asset profile risk multiplier x base 1% per trade
        prof = self._profile
        equity = self._total_equity(close)
        risk_per_trade = equity * 0.01 * prof.risk_per_trade_mult
        stop_distance = atr * prof.stop_atr_mult
        if stop_distance <= 0:
            stop_distance = close * 0.02  # fallback 2%

        quantity = risk_per_trade / stop_distance
        notional = quantity * close

        # CAP: notional must never exceed 0.5x equity (conservative, no leverage)
        max_notional = equity * 0.5
        if notional > max_notional:
            quantity = max_notional / close
            notional = max_notional

        # R:R ratio defined per asset profile.
        rr_ratio = prof.rr_ratio

        if side == "long":
            limit_price = close * 0.9998
            stop_loss = close - stop_distance
            take_profit = close + stop_distance * rr_ratio
        else:
            limit_price = close * 1.0002
            stop_loss = close + stop_distance
            take_profit = close - stop_distance * rr_ratio

        # Trailing stop: profile-defined ATR multiple of stop distance.
        trailing_stop_dist = stop_distance * prof.trailing_mult

        return {
            "symbol": symbol,
            "side": side,
            "score": score,
            "limit_price": limit_price,
            "quantity": quantity,
            "notional": notional,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "trailing_stop_distance": trailing_stop_dist,
            "atr": atr,
            "regime": regime,
            "timestamp": bar["timestamp"],
            "equity_at_entry": equity,
        }

    def _passes_risk_checks(self, proposal: Dict, bar: Dict) -> bool:
        """Run the risk engine's pre-trade checks."""
        # Portfolio heat check: max 6% total portfolio at risk
        current_risk = sum(
            abs(p.quantity * (p.entry_price - p.stop_loss))
            for p in self._positions
        )
        equity = self._total_equity(bar["close"])
        proposed_risk = abs(proposal["quantity"] * (proposal["limit_price"] - proposal["stop_loss"]))
        total_heat = (current_risk + proposed_risk) / equity if equity > 0 else 1.0

        if total_heat > 0.06:
            logger.debug("Risk check FAIL: portfolio heat {:.1%} > 6%", total_heat)
            return False

        # Max concurrent positions: 5
        if len(self._positions) >= 5:
            logger.debug("Risk check FAIL: max positions reached ({})", len(self._positions))
            return False

        # Drawdown check via equity governor
        try:
            peak_equity = max(e[1] for e in self._equity_history) if self._equity_history else equity
            current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            if current_dd > 0.10:
                logger.debug("Risk check FAIL: drawdown {:.1%} > 10% -- reducing exposure", current_dd)
                return False
        except Exception:
            pass

        # Daily loss limit: 3% of starting equity
        try:
            today_start_eq = self._get_day_start_equity(bar["timestamp"])
            daily_loss = (today_start_eq - equity) / today_start_eq if today_start_eq > 0 else 0
            if daily_loss > 0.03:
                logger.debug("Risk check FAIL: daily loss {:.1%} > 3%", daily_loss)
                return False
        except Exception:
            pass

        # Delegate to risk engine for VaR / correlation checks
        try:
            risk_result = self.risk_engine.check(proposal)
            if isinstance(risk_result, dict) and not risk_result.get("approved", True):
                logger.debug("Risk engine rejected: {}", risk_result.get("reason", ""))
                return False
        except Exception:
            pass  # If risk engine not implemented, pass through

        return True

    def _execute_entry(self, proposal: Dict, bar: Dict) -> None:
        """Simulate a limit order fill with slippage and fees."""
        close = bar["close"]
        side = proposal["side"]

        # Slippage model: base + volatility-adjusted
        atr = proposal.get("atr", close * 0.01)
        vol_slippage_bps = (atr / close) * 100 * 0.1  # 10% of ATR as bps
        total_slippage_bps = self.BASE_SLIPPAGE_BPS + vol_slippage_bps
        slippage_fraction = total_slippage_bps / 10_000

        if side == "long":
            fill_price = close * (1 + slippage_fraction)
        else:
            fill_price = close * (1 - slippage_fraction)

        # Limit order check: for a long, fill only if limit >= fill price
        # In backtest we assume the limit order gets filled at the close + slippage
        # (conservative: assumes we cross the spread)

        quantity = proposal["quantity"]
        notional = quantity * fill_price

        # Fees (taker)
        fees = notional * self.TAKER_FEE_RATE
        slippage_cost = abs(fill_price - close) * quantity

        # Deduct cash
        if side == "long":
            self._cash -= (notional + fees)
        else:
            # Short: receive proceeds but need margin
            self._cash -= fees  # simplified: just deduct fees for shorts

        pos = SimPosition(
            symbol=proposal["symbol"],
            side=side,
            entry_price=fill_price,
            quantity=quantity,
            entry_time=bar["timestamp"],
            stop_loss=proposal["stop_loss"],
            take_profit=proposal["take_profit"],
            trailing_stop_distance=proposal.get("trailing_stop_distance", 0),
            trailing_stop_price=0.0,  # Disabled until activation threshold (2R profit) is reached
            fees_paid=fees,
            slippage_cost=slippage_cost,
            score_at_entry=proposal["score"],
            regime_at_entry=proposal.get("regime", "unknown"),
        )

        self._positions.append(pos)
        logger.debug(
            "ENTRY: {} {} {:.4f} @ {:.2f} | SL={:.2f} TP={:.2f} | score={:.0f}",
            side, proposal["symbol"], quantity, fill_price,
            proposal["stop_loss"], proposal["take_profit"], proposal["score"],
        )

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def _manage_positions(self, bar: Dict) -> None:
        """Check stops, take profits, and trailing stops for open positions."""
        to_close: List[Tuple[SimPosition, str, float]] = []

        for pos in self._positions:
            high = bar["high"]
            low = bar["low"]
            close = bar["close"]

            # Update trailing stop — only activates after enough profit that
            # the trail exit would be at or above breakeven.
            # With 4 ATR trail distance, activate after 4 ATR profit (2R).
            # This ensures trailing stop exits are NEVER losses.
            if pos.trailing_stop_distance > 0:
                activation_dist = pos.trailing_stop_distance  # trail can't lose once active
                if pos.side == "long":
                    if high > pos.entry_price + activation_dist:
                        new_trail = high - pos.trailing_stop_distance
                        if new_trail > pos.trailing_stop_price:
                            pos.trailing_stop_price = new_trail
                else:
                    if low < pos.entry_price - activation_dist:
                        new_trail = low + pos.trailing_stop_distance
                        if new_trail < pos.trailing_stop_price or pos.trailing_stop_price <= 0:
                            pos.trailing_stop_price = new_trail

            # Check stop loss
            if pos.side == "long":
                if low <= pos.stop_loss:
                    to_close.append((pos, "stop_loss", pos.stop_loss))
                    continue
                if pos.trailing_stop_price > 0 and low <= pos.trailing_stop_price:
                    to_close.append((pos, "trailing_stop", pos.trailing_stop_price))
                    continue
                if high >= pos.take_profit:
                    to_close.append((pos, "take_profit", pos.take_profit))
                    continue
            else:  # short
                if high >= pos.stop_loss:
                    to_close.append((pos, "stop_loss", pos.stop_loss))
                    continue
                if pos.trailing_stop_price > 0 and high >= pos.trailing_stop_price:
                    to_close.append((pos, "trailing_stop", pos.trailing_stop_price))
                    continue
                if low <= pos.take_profit:
                    to_close.append((pos, "take_profit", pos.take_profit))
                    continue

        for pos, reason, exit_price in to_close:
            self._close_position(pos, exit_price, bar["timestamp"], reason)

    def _close_position(
        self, pos: SimPosition, exit_price: float, timestamp: Any, reason: str
    ) -> None:
        """Close a position and record the trade."""
        # Apply exit slippage
        slippage_fraction = self.BASE_SLIPPAGE_BPS / 10_000
        if pos.side == "long":
            actual_exit = exit_price * (1 - slippage_fraction)
        else:
            actual_exit = exit_price * (1 + slippage_fraction)

        # Exit fees
        exit_notional = pos.quantity * actual_exit
        exit_fees = exit_notional * self.TAKER_FEE_RATE

        # PnL
        if pos.side == "long":
            raw_pnl = (actual_exit - pos.entry_price) * pos.quantity
        else:
            raw_pnl = (pos.entry_price - actual_exit) * pos.quantity

        total_fees = pos.fees_paid + exit_fees
        net_pnl = raw_pnl - total_fees

        # Return cash
        if pos.side == "long":
            self._cash += (exit_notional - exit_fees)
        else:
            self._cash += (raw_pnl - exit_fees)

        trade_record = {
            "id": pos.id,
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": actual_exit,
            "quantity": pos.quantity,
            "entry_time": pos.entry_time,
            "exit_time": timestamp,
            "pnl": round(net_pnl, 2),
            "raw_pnl": round(raw_pnl, 2),
            "fees": round(total_fees, 2),
            "slippage_cost": round(pos.slippage_cost, 2),
            "exit_reason": reason,
            "score_at_entry": pos.score_at_entry,
            "regime_at_entry": pos.regime_at_entry,
            "return_pct": round(net_pnl / (pos.entry_price * pos.quantity) * 100, 4)
            if pos.entry_price * pos.quantity > 0 else 0.0,
        }

        self._closed_trades.append(trade_record)
        self._positions.remove(pos)

        logger.debug(
            "EXIT [{}]: {} {} @ {:.2f} -> {:.2f} | PnL=${:.2f} | {}",
            pos.id, pos.side, pos.symbol, pos.entry_price, actual_exit, net_pnl, reason,
        )

    def _force_close_all(self, last_price: float, timestamp: Any) -> None:
        """Close all remaining positions at end of backtest."""
        for pos in list(self._positions):
            self._close_position(pos, last_price, timestamp, "backtest_end")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_candles(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Load 5M candles from storage."""
        try:
            candles = self.storage.get_candles(
                symbol=symbol,
                timeframe="5M",
                start=start_date,
                end=end_date,
            )
            if isinstance(candles, pd.DataFrame) and not candles.empty:
                required = {"timestamp", "open", "high", "low", "close", "volume"}
                if required.issubset(set(candles.columns)):
                    candles = candles.sort_values("timestamp").reset_index(drop=True)
                    return candles
            logger.warning("Storage returned no valid candles for {}", symbol)
            return pd.DataFrame()
        except Exception as exc:
            logger.error("Failed to load candles from storage: {}", exc)
            return pd.DataFrame()

    def _total_equity(self, current_price: float) -> float:
        """Calculate total equity: cash + mark-to-market positions."""
        position_value = 0.0
        for pos in self._positions:
            if pos.side == "long":
                position_value += pos.quantity * current_price
            else:
                # Short PnL
                position_value += pos.quantity * (pos.entry_price - current_price)
        return self._cash + position_value

    def _estimate_atr(self, current_price: float, lookback: int = 14) -> float:
        """Estimate ATR from recent 5M candles."""
        df = self._aggregator.get_completed_candles("1H", lookback=lookback + 1)
        if df.empty or len(df) < 3:
            return current_price * 0.01  # fallback: 1% of price

        highs = df["high"].astype(float)
        lows = df["low"].astype(float)
        closes = df["close"].astype(float)

        prev_close = closes.shift(1)
        tr1 = highs - lows
        tr2 = (highs - prev_close).abs()
        tr3 = (lows - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return float(tr.iloc[-lookback:].mean()) if len(tr) >= lookback else float(tr.mean())

    def _get_day_start_equity(self, timestamp: Any) -> float:
        """Get the equity at the start of the current day."""
        if not self._equity_history:
            return self._cash

        try:
            ts = pd.Timestamp(timestamp)
            day_start = ts.normalize()
            for t, eq in self._equity_history:
                if pd.Timestamp(t) >= day_start:
                    return eq
        except Exception:
            pass

        return self._equity_history[0][1] if self._equity_history else self._cash

    def _reset(self, initial_capital: float) -> None:
        """Reset all backtest state."""
        self._aggregator.reset()
        self._positions = []
        self._closed_trades = []
        self._equity_history = []
        self._signals_log = []
        self._regime_history = []
        self._cash = initial_capital
        self._bar_count = 0
        self._scores_logged = 0

    # ------------------------------------------------------------------
    # Walk-Forward Validation
    # ------------------------------------------------------------------

    def run_walk_forward(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        train_window: int = 90,
        test_window: int = 30,
        step: int = 30,
        initial_capital: float = 100_000.0,
    ) -> WalkForwardResult:
        """
        Walk-forward validation with rolling train/test windows.

        Parameters
        ----------
        symbol : str
            Instrument identifier.
        start_date, end_date : str
            ISO date strings for the full period.
        train_window : int
            In-sample training window in calendar days.
        test_window : int
            Out-of-sample test window in calendar days.
        step : int
            Step size in calendar days between windows.
        initial_capital : float
            Starting equity for each window.

        Returns
        -------
        WalkForwardResult with combined OOS metrics and per-window breakdown.
        """
        logger.info(
            "Walk-forward: {} | train={}d test={}d step={}d | {} to {}",
            symbol, train_window, test_window, step, start_date, end_date,
        )

        start_dt = pd.Timestamp(start_date)
        end_dt = pd.Timestamp(end_date)

        all_is_metrics: List[MetricsResult] = []
        all_oos_metrics: List[MetricsResult] = []
        all_oos_trades: List[Dict] = []
        all_oos_equity: List[pd.Series] = []
        window_results: List[Dict] = []

        window_start = start_dt

        while window_start + timedelta(days=train_window + test_window) <= end_dt:
            train_start = window_start
            train_end = window_start + timedelta(days=train_window)
            test_start = train_end
            test_end = test_start + timedelta(days=test_window)

            logger.info(
                "  Window: train [{} -> {}] test [{} -> {}]",
                train_start.date(), train_end.date(), test_start.date(), test_end.date(),
            )

            # In-sample run
            is_result = self.run(
                symbol,
                str(train_start.date()),
                str(train_end.date()),
                initial_capital,
            )

            # Out-of-sample run
            oos_result = self.run(
                symbol,
                str(test_start.date()),
                str(test_end.date()),
                initial_capital,
            )

            all_is_metrics.append(is_result.metrics)
            all_oos_metrics.append(oos_result.metrics)
            all_oos_trades.extend(oos_result.trades)

            if not oos_result.equity_curve.empty:
                all_oos_equity.append(oos_result.equity_curve)

            window_results.append({
                "train_start": str(train_start.date()),
                "train_end": str(train_end.date()),
                "test_start": str(test_start.date()),
                "test_end": str(test_end.date()),
                "is_sharpe": is_result.metrics.sharpe if is_result.metrics else 0,
                "oos_sharpe": oos_result.metrics.sharpe if oos_result.metrics else 0,
                "is_win_rate": is_result.metrics.win_rate if is_result.metrics else 0,
                "oos_win_rate": oos_result.metrics.win_rate if oos_result.metrics else 0,
                "is_trades": len(is_result.trades),
                "oos_trades": len(oos_result.trades),
                "oos_pnl": sum(t.get("pnl", 0) for t in oos_result.trades),
            })

            window_start += timedelta(days=step)

        # Combine OOS equity curves
        combined_equity = pd.Series(dtype=float)
        if all_oos_equity:
            combined_equity = pd.concat(all_oos_equity).sort_index()

        # Combined OOS metrics
        combined_metrics = PerformanceMetrics.calculate_all(
            combined_equity, all_oos_trades
        ) if not combined_equity.empty else MetricsResult()

        # Aggregate IS metrics for overfitting check
        if all_is_metrics and all_oos_metrics:
            avg_is = MetricsResult(
                sharpe=float(np.mean([m.sharpe for m in all_is_metrics if m])),
                win_rate=float(np.mean([m.win_rate for m in all_is_metrics if m])),
                profit_factor=float(np.mean([m.profit_factor for m in all_is_metrics if m])),
            )
            avg_oos = MetricsResult(
                sharpe=float(np.mean([m.sharpe for m in all_oos_metrics if m])),
                win_rate=float(np.mean([m.win_rate for m in all_oos_metrics if m])),
                profit_factor=float(np.mean([m.profit_factor for m in all_oos_metrics if m])),
            )
            overfit_check = check_overfitting(avg_is, avg_oos)
        else:
            overfit_check = {"passed": False, "details": "Insufficient windows"}

        logger.info(
            "Walk-forward DONE: {} windows | OOS Sharpe={:.2f} | Overfit={}",
            len(window_results), combined_metrics.sharpe,
            "PASS" if overfit_check.get("passed") else "FAIL",
        )

        return WalkForwardResult(
            combined_metrics=combined_metrics,
            combined_equity_curve=combined_equity,
            combined_trades=all_oos_trades,
            per_window=window_results,
            overfitting_check=overfit_check,
        )

    # ------------------------------------------------------------------
    # Monte Carlo Stress Test
    # ------------------------------------------------------------------

    def run_monte_carlo(
        self,
        trades: List[Dict],
        n_simulations: int = 1000,
        initial_capital: float = 100_000.0,
    ) -> MonteCarloResult:
        """
        Monte Carlo simulation by shuffling trade order.

        Preserves individual trade characteristics (PnL, duration) but
        randomises the sequence to test robustness of the equity curve.

        Parameters
        ----------
        trades : list of dict
            Completed trade records (must have 'pnl' key).
        n_simulations : int
            Number of random permutations to simulate.
        initial_capital : float
            Starting equity for each simulation.

        Returns
        -------
        MonteCarloResult with confidence intervals on key metrics.
        """
        if not trades:
            logger.warning("Monte Carlo: no trades to simulate")
            return MonteCarloResult()

        logger.info("Monte Carlo: {} simulations on {} trades", n_simulations, len(trades))

        pnls = [t.get("pnl", 0) for t in trades]
        final_equities = []
        max_drawdowns = []
        sharpes = []

        for i in range(n_simulations):
            shuffled = pnls.copy()
            random.shuffle(shuffled)

            # Build equity curve from shuffled PnLs
            equity = [initial_capital]
            for pnl in shuffled:
                equity.append(equity[-1] + pnl)

            eq_series = pd.Series(equity)
            final_equities.append(equity[-1])

            # Max drawdown
            running_max = eq_series.cummax()
            dd = (eq_series - running_max) / running_max
            max_drawdowns.append(abs(dd.min()))

            # Sharpe (from trade returns)
            returns = pd.Series(shuffled) / initial_capital
            if returns.std() > 0:
                sh = float(returns.mean() / returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR))
            else:
                sh = 0.0
            sharpes.append(sh)

        final_equities = np.array(final_equities)
        max_drawdowns = np.array(max_drawdowns)
        sharpes = np.array(sharpes)

        # Ruin probability: equity drops below 50% of initial
        ruin_count = np.sum(final_equities < initial_capital * 0.50)

        result = MonteCarloResult(
            n_simulations=n_simulations,
            median_final_equity=float(np.median(final_equities)),
            p5_final_equity=float(np.percentile(final_equities, 5)),
            p95_final_equity=float(np.percentile(final_equities, 95)),
            p5_max_drawdown=float(np.percentile(max_drawdowns, 5)),
            median_max_drawdown=float(np.median(max_drawdowns)),
            p95_max_drawdown=float(np.percentile(max_drawdowns, 95)),
            sharpe_ci_low=float(np.percentile(sharpes, 5)),
            sharpe_ci_high=float(np.percentile(sharpes, 95)),
            max_dd_ci_low=float(np.percentile(max_drawdowns, 5)),
            max_dd_ci_high=float(np.percentile(max_drawdowns, 95)),
            final_equity_ci_low=float(np.percentile(final_equities, 5)),
            final_equity_ci_high=float(np.percentile(final_equities, 95)),
            ruin_probability=float(ruin_count / n_simulations),
        )

        logger.info(
            "Monte Carlo DONE: median equity=${:,.0f} | 95th DD={:.1%} | ruin={:.1%}",
            result.median_final_equity, result.p95_max_drawdown, result.ruin_probability,
        )

        return result

    # ------------------------------------------------------------------
    # Regime-Segmented Analysis
    # ------------------------------------------------------------------

    def analyze_by_regime(
        self,
        trades: List[Dict],
        regime_history: List[Dict],
    ) -> Dict[str, Any]:
        """
        Break down performance metrics by regime state.

        Each trade is assigned the regime that was active at its entry time.
        Returns a dict keyed by regime name with full metrics for each.
        """
        if not trades or not regime_history:
            return {}

        # Build regime lookup: list of (start_time, regime)
        regime_periods = []
        for i, rh in enumerate(regime_history):
            start = rh.get("timestamp") or rh.get("bar_count", 0)
            regime_periods.append((start, rh["regime"]))

        # Assign regime to each trade
        regime_trades: Dict[str, List[Dict]] = {}
        for trade in trades:
            regime = trade.get("regime_at_entry", "unknown")
            if regime not in regime_trades:
                regime_trades[regime] = []
            regime_trades[regime].append(trade)

        # Compute metrics per regime
        analysis = {}
        for regime, rtrades in regime_trades.items():
            pnls = [t.get("pnl", 0) for t in rtrades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]

            wr = len(wins) / len(rtrades) if rtrades else 0
            avg_w = float(np.mean(wins)) if wins else 0
            avg_l = float(np.mean([abs(l) for l in losses])) if losses else 0
            gross_w = sum(wins)
            gross_l = abs(sum(losses))
            pf = gross_w / gross_l if gross_l > 0 else (float("inf") if gross_w > 0 else 0)

            analysis[regime] = {
                "total_trades": len(rtrades),
                "win_rate": round(wr, 4),
                "avg_win": round(avg_w, 2),
                "avg_loss": round(avg_l, 2),
                "profit_factor": round(pf, 4),
                "total_pnl": round(sum(pnls), 2),
                "expectancy": round(avg_w * wr - avg_l * (1 - wr), 2),
                "best_trade": round(max(pnls), 2) if pnls else 0,
                "worst_trade": round(min(pnls), 2) if pnls else 0,
            }

        # Identify best/worst regimes
        if analysis:
            best = max(analysis.items(), key=lambda x: x[1]["total_pnl"])
            worst = min(analysis.items(), key=lambda x: x[1]["total_pnl"])
            analysis["_summary"] = {
                "best_regime": best[0],
                "best_regime_pnl": best[1]["total_pnl"],
                "worst_regime": worst[0],
                "worst_regime_pnl": worst[1]["total_pnl"],
                "regimes_tested": list(analysis.keys()),
            }

        return analysis


# ---------------------------------------------------------------------------
# Convenience constant for annualisation
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252
