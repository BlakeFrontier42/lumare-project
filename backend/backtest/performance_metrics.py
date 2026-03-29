"""
performance_metrics.py -- Comprehensive backtesting metrics for Lumare MIE.

Calculates Sharpe, Sortino, Calmar, profit factor, expectancy, drawdowns,
tail risk, rolling statistics, and anti-overfitting guards.

All functions accept plain numpy/pandas objects and return dicts or scalars.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class MetricsResult:
    """Full suite of performance metrics."""
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    max_drawdown: Dict[str, Any] = field(default_factory=dict)
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_trade_duration: timedelta = field(default_factory=lambda: timedelta(0))
    risk_reward_ratio: float = 0.0
    tail_risk: Dict[str, float] = field(default_factory=dict)
    annual_return: float = 0.0
    total_return: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    ulcer_index: float = 0.0
    omega_ratio: float = 0.0
    monthly_returns: Optional[pd.DataFrame] = None
    drawdown_series: Optional[pd.Series] = None
    rolling_sharpe: Optional[pd.Series] = None


@dataclass
class ValidationResult:
    """Pass/fail validation of metrics against targets."""
    passed: bool = False
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252
BARS_5M_PER_DAY = 288  # 24h * 12 bars/hr for crypto


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------

def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.05) -> float:
    """
    Annualised Sharpe ratio.

    Formula:
        Sharpe = (mean(R) - Rf_daily) / std(R) * sqrt(annualisation_factor)

    Uses daily returns for annualisation. If intraday, caller should
    pre-aggregate to daily.
    """
    if returns.empty or returns.std() == 0:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = returns.mean() - daily_rf
    return float(excess / returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.05) -> float:
    """
    Annualised Sortino ratio -- penalises only downside volatility.

    Formula:
        Sortino = (mean(R) - Rf_daily) / downside_std * sqrt(annualisation)

    Downside deviation computed only from returns < 0.
    """
    if returns.empty:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    downside = returns[returns < 0]
    if downside.empty or downside.std() == 0:
        return float("inf") if returns.mean() > daily_rf else 0.0
    excess = returns.mean() - daily_rf
    return float(excess / downside.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def calmar_ratio(annual_ret: float, max_dd: float) -> float:
    """
    Calmar ratio = annualised return / max drawdown.

    A negative max_dd (expressed as a positive fraction, e.g. 0.15 for 15%)
    is expected.
    """
    if max_dd == 0:
        return 0.0
    return float(annual_ret / abs(max_dd))


def profit_factor(trades: List[Dict]) -> float:
    """
    Gross profit / gross loss.

    A PF > 1 means gross winners exceed gross losers.
    """
    gross_win = sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0)
    gross_loss_val = abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0))
    if gross_loss_val == 0:
        return float("inf") if gross_win > 0 else 0.0
    return float(gross_win / gross_loss_val)


def win_rate(trades: List[Dict]) -> float:
    """Fraction of trades with positive PnL."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    return float(wins / len(trades))


def avg_win(trades: List[Dict]) -> float:
    """Average profit on winning trades."""
    winners = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
    return float(np.mean(winners)) if winners else 0.0


def avg_loss(trades: List[Dict]) -> float:
    """Average loss on losing trades (returned as positive number)."""
    losers = [abs(t["pnl"]) for t in trades if t.get("pnl", 0) < 0]
    return float(np.mean(losers)) if losers else 0.0


def expectancy(trades: List[Dict]) -> float:
    """
    Expectancy per trade.

    Formula: avg_win * win_rate - avg_loss * loss_rate
    """
    wr = win_rate(trades)
    lr = 1.0 - wr
    return float(avg_win(trades) * wr - avg_loss(trades) * lr)


def max_drawdown(equity_curve: pd.Series) -> Dict[str, Any]:
    """
    Maximum drawdown analysis.

    Returns dict with:
        max_dd       : float  (fraction, e.g. 0.15 = 15%)
        max_dd_dollar: float  (absolute dollar drawdown)
        peak         : float  (equity at peak)
        trough       : float  (equity at trough)
        peak_date    : datetime
        trough_date  : datetime
        duration     : int    (bars from peak to trough)
        recovery_time: int | None  (bars from trough to recovery, None if not recovered)
    """
    if equity_curve.empty:
        return {
            "max_dd": 0.0, "max_dd_dollar": 0.0,
            "peak": 0.0, "trough": 0.0,
            "peak_date": None, "trough_date": None,
            "duration": 0, "recovery_time": None,
        }

    running_max = equity_curve.cummax()
    drawdowns = (equity_curve - running_max) / running_max

    if drawdowns.min() == 0:
        return {
            "max_dd": 0.0, "max_dd_dollar": 0.0,
            "peak": float(equity_curve.iloc[-1]),
            "trough": float(equity_curve.iloc[-1]),
            "peak_date": equity_curve.index[0] if hasattr(equity_curve.index[0], 'isoformat') else None,
            "trough_date": equity_curve.index[0] if hasattr(equity_curve.index[0], 'isoformat') else None,
            "duration": 0, "recovery_time": None,
        }

    trough_idx = drawdowns.idxmin()
    trough_pos = equity_curve.index.get_loc(trough_idx)

    # Find the peak before the trough
    peak_val = running_max.loc[trough_idx]
    peak_candidates = equity_curve.iloc[:trough_pos + 1]
    peak_idx = peak_candidates.idxmax()

    peak_pos = equity_curve.index.get_loc(peak_idx)
    duration = trough_pos - peak_pos

    # Find recovery (first time equity >= peak_val after trough)
    recovery_time = None
    post_trough = equity_curve.iloc[trough_pos:]
    recovered = post_trough[post_trough >= peak_val]
    if not recovered.empty:
        recovery_idx = recovered.index[0]
        recovery_pos = equity_curve.index.get_loc(recovery_idx)
        recovery_time = recovery_pos - trough_pos

    trough_val = float(equity_curve.loc[trough_idx])
    max_dd_frac = abs(float(drawdowns.min()))
    max_dd_dollar = float(peak_val - trough_val)

    return {
        "max_dd": max_dd_frac,
        "max_dd_dollar": max_dd_dollar,
        "peak": float(peak_val),
        "trough": trough_val,
        "peak_date": peak_idx,
        "trough_date": trough_idx,
        "duration": int(duration),
        "recovery_time": int(recovery_time) if recovery_time is not None else None,
    }


def max_consecutive_wins(trades: List[Dict]) -> int:
    """Longest winning streak."""
    if not trades:
        return 0
    best = 0
    current = 0
    for t in trades:
        if t.get("pnl", 0) > 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def max_consecutive_losses(trades: List[Dict]) -> int:
    """Longest losing streak."""
    if not trades:
        return 0
    best = 0
    current = 0
    for t in trades:
        if t.get("pnl", 0) <= 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def avg_trade_duration(trades: List[Dict]) -> timedelta:
    """Mean holding time across all trades."""
    if not trades:
        return timedelta(0)
    durations = []
    for t in trades:
        entry_time = t.get("entry_time")
        exit_time = t.get("exit_time")
        if entry_time and exit_time:
            if isinstance(entry_time, str):
                entry_time = pd.Timestamp(entry_time)
            if isinstance(exit_time, str):
                exit_time = pd.Timestamp(exit_time)
            durations.append((exit_time - entry_time).total_seconds())
    if not durations:
        return timedelta(0)
    return timedelta(seconds=float(np.mean(durations)))


def risk_reward_ratio(trades: List[Dict]) -> float:
    """Average win / average loss."""
    aw = avg_win(trades)
    al = avg_loss(trades)
    if al == 0:
        return float("inf") if aw > 0 else 0.0
    return float(aw / al)


def tail_risk_metrics(returns: pd.Series) -> Dict[str, float]:
    """
    Tail risk analysis.

    Returns skewness, kurtosis, VaR (95/99), and CVaR (95/99).
    VaR is the loss at the given percentile (positive = loss).
    CVaR (Expected Shortfall) is the mean of losses beyond VaR.
    """
    if returns.empty or len(returns) < 10:
        return {
            "skewness": 0.0, "kurtosis": 0.0,
            "var_95": 0.0, "var_99": 0.0,
            "cvar_95": 0.0, "cvar_99": 0.0,
        }

    skew = float(returns.skew())
    kurt = float(returns.kurtosis())

    var_95 = float(-np.percentile(returns, 5))
    var_99 = float(-np.percentile(returns, 1))

    tail_95 = returns[returns <= -var_95]
    cvar_95 = float(-tail_95.mean()) if not tail_95.empty else var_95

    tail_99 = returns[returns <= -var_99]
    cvar_99 = float(-tail_99.mean()) if not tail_99.empty else var_99

    return {
        "skewness": round(skew, 4),
        "kurtosis": round(kurt, 4),
        "var_95": round(var_95, 6),
        "var_99": round(var_99, 6),
        "cvar_95": round(cvar_95, 6),
        "cvar_99": round(cvar_99, 6),
    }


def annual_return(equity_curve: pd.Series) -> float:
    """
    Compound Annual Growth Rate (CAGR).

    Formula: (final / initial) ^ (365 / days) - 1
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0
    initial = float(equity_curve.iloc[0])
    final = float(equity_curve.iloc[-1])
    if initial <= 0:
        return 0.0

    # Determine number of calendar days
    if hasattr(equity_curve.index, 'to_pydatetime'):
        try:
            days = (equity_curve.index[-1] - equity_curve.index[0]).days
        except Exception:
            days = len(equity_curve)
    else:
        days = len(equity_curve)

    if days <= 0:
        days = 1

    return float((final / initial) ** (365.0 / days) - 1.0)


def monthly_returns(equity_curve: pd.Series) -> pd.DataFrame:
    """
    Monthly returns pivot table (year x month).

    Expects a DatetimeIndex on the equity curve.
    Returns a DataFrame with years as rows, months 1-12 as columns.
    """
    if equity_curve.empty:
        return pd.DataFrame()

    if not isinstance(equity_curve.index, pd.DatetimeIndex):
        logger.warning("monthly_returns requires DatetimeIndex; returning empty")
        return pd.DataFrame()

    # Resample to month-end equity, then compute returns
    monthly_eq = equity_curve.resample("ME").last().dropna()
    monthly_ret = monthly_eq.pct_change().dropna()

    if monthly_ret.empty:
        return pd.DataFrame()

    df = pd.DataFrame({
        "year": monthly_ret.index.year,
        "month": monthly_ret.index.month,
        "return": monthly_ret.values,
    })

    pivot = df.pivot_table(index="year", columns="month", values="return", aggfunc="sum")
    pivot.columns = [f"M{int(c):02d}" for c in pivot.columns]
    return pivot


def drawdown_series(equity_curve: pd.Series) -> pd.Series:
    """Running drawdown from peak as a fraction (always <= 0)."""
    if equity_curve.empty:
        return pd.Series(dtype=float)
    running_max = equity_curve.cummax()
    return (equity_curve - running_max) / running_max


def rolling_sharpe(returns: pd.Series, window: int = 60, risk_free_rate: float = 0.05) -> pd.Series:
    """
    Rolling annualised Sharpe ratio over a given window of daily returns.
    """
    if returns.empty or len(returns) < window:
        return pd.Series(dtype=float)

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    roll_mean = returns.rolling(window).mean() - daily_rf
    roll_std = returns.rolling(window).std()
    return (roll_mean / roll_std.replace(0, np.nan)) * math.sqrt(TRADING_DAYS_PER_YEAR)


def ulcer_index(equity_curve: pd.Series) -> float:
    """
    Ulcer Index -- RMS of percentage drawdowns from peak.

    Lower is better. Penalises both depth and duration of drawdowns.
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0
    dd = drawdown_series(equity_curve)
    return float(np.sqrt((dd ** 2).mean()))


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float:
    """
    Omega ratio -- probability-weighted gain/loss above/below threshold.

    Formula: sum(max(R - threshold, 0)) / sum(max(threshold - R, 0))
    """
    if returns.empty:
        return 0.0
    gains = np.maximum(returns - threshold, 0).sum()
    losses = np.maximum(threshold - returns, 0).sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


# ---------------------------------------------------------------------------
# Aggregate calculator
# ---------------------------------------------------------------------------

class PerformanceMetrics:
    """Calculate all performance metrics from an equity curve and trade list."""

    @staticmethod
    def calculate_all(
        equity_curve: pd.Series,
        trades: List[Dict],
        risk_free_rate: float = 0.05,
    ) -> MetricsResult:
        """
        Compute full metrics suite.

        Parameters
        ----------
        equity_curve : pd.Series
            Time-indexed equity values.
        trades : list of dict
            Each dict has at minimum: pnl, entry_time, exit_time, side.
        risk_free_rate : float
            Annualised risk-free rate for Sharpe/Sortino.

        Returns
        -------
        MetricsResult with all fields populated.
        """
        result = MetricsResult()

        if equity_curve.empty:
            logger.warning("Empty equity curve -- returning zero metrics")
            return result

        # Daily returns for ratio calculations
        if isinstance(equity_curve.index, pd.DatetimeIndex):
            daily_eq = equity_curve.resample("D").last().dropna()
        else:
            daily_eq = equity_curve

        daily_returns = daily_eq.pct_change().dropna()
        daily_returns = daily_returns.replace([np.inf, -np.inf], 0.0)

        # Ratios
        result.sharpe = round(sharpe_ratio(daily_returns, risk_free_rate), 4)
        result.sortino = round(sortino_ratio(daily_returns, risk_free_rate), 4)

        # Drawdown
        dd_info = max_drawdown(equity_curve)
        result.max_drawdown = dd_info

        # Annual return
        result.annual_return = round(annual_return(equity_curve), 4)
        result.total_return = round(
            float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0), 4
        )

        # Calmar
        result.calmar = round(calmar_ratio(result.annual_return, dd_info["max_dd"]), 4)

        # Trade stats
        result.total_trades = len(trades)
        result.win_rate = round(win_rate(trades), 4)
        result.avg_win = round(avg_win(trades), 2)
        result.avg_loss = round(avg_loss(trades), 2)
        result.profit_factor = round(profit_factor(trades), 4)
        result.expectancy = round(expectancy(trades), 2)
        result.risk_reward_ratio = round(risk_reward_ratio(trades), 4)
        result.max_consecutive_wins = max_consecutive_wins(trades)
        result.max_consecutive_losses = max_consecutive_losses(trades)
        result.avg_trade_duration = avg_trade_duration(trades)

        result.winning_trades = sum(1 for t in trades if t.get("pnl", 0) > 0)
        result.losing_trades = sum(1 for t in trades if t.get("pnl", 0) <= 0)
        result.gross_profit = round(sum(t["pnl"] for t in trades if t.get("pnl", 0) > 0), 2)
        result.gross_loss = round(abs(sum(t["pnl"] for t in trades if t.get("pnl", 0) < 0)), 2)

        # Tail risk
        result.tail_risk = tail_risk_metrics(daily_returns)

        # Advanced metrics
        result.ulcer_index = round(ulcer_index(equity_curve), 6)
        result.omega_ratio = round(omega_ratio(daily_returns), 4)

        # Series outputs
        result.monthly_returns = monthly_returns(equity_curve)
        result.drawdown_series = drawdown_series(equity_curve)
        result.rolling_sharpe = rolling_sharpe(daily_returns, window=60, risk_free_rate=risk_free_rate)

        return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_results(metrics: MetricsResult) -> ValidationResult:
    """
    Validate metrics against target thresholds.

    Thresholds:
        Win rate      >= 60%
        Sharpe        >= 2.0
        Profit factor >= 1.5
        Max drawdown  <= 15%
    """
    result = ValidationResult(passed=True)

    # Win rate check
    wr_pass = metrics.win_rate >= 0.60
    result.checks["win_rate"] = {
        "value": metrics.win_rate,
        "target": 0.60,
        "passed": wr_pass,
    }
    if not wr_pass:
        result.passed = False
    if 0.55 <= metrics.win_rate < 0.60:
        result.warnings.append(f"Win rate {metrics.win_rate:.1%} is borderline (target: 60%)")

    # Sharpe check
    sharpe_pass = metrics.sharpe >= 2.0
    result.checks["sharpe"] = {
        "value": metrics.sharpe,
        "target": 2.0,
        "passed": sharpe_pass,
    }
    if not sharpe_pass:
        result.passed = False
    if 1.5 <= metrics.sharpe < 2.0:
        result.warnings.append(f"Sharpe {metrics.sharpe:.2f} is borderline (target: 2.0)")

    # Profit factor check
    pf_pass = metrics.profit_factor >= 1.5
    result.checks["profit_factor"] = {
        "value": metrics.profit_factor,
        "target": 1.5,
        "passed": pf_pass,
    }
    if not pf_pass:
        result.passed = False
    if 1.2 <= metrics.profit_factor < 1.5:
        result.warnings.append(f"Profit factor {metrics.profit_factor:.2f} is borderline (target: 1.5)")

    # Max drawdown check
    dd_val = metrics.max_drawdown.get("max_dd", 0.0)
    dd_pass = dd_val <= 0.15
    result.checks["max_drawdown"] = {
        "value": dd_val,
        "target": 0.15,
        "passed": dd_pass,
    }
    if not dd_pass:
        result.passed = False
    if 0.12 <= dd_val <= 0.15:
        result.warnings.append(f"Max DD {dd_val:.1%} is borderline (target: <=15%)")

    return result


# ---------------------------------------------------------------------------
# Anti-overfitting
# ---------------------------------------------------------------------------

def check_overfitting(
    in_sample_metrics: MetricsResult,
    out_of_sample_metrics: MetricsResult,
) -> Dict[str, Any]:
    """
    Compare in-sample vs out-of-sample to detect overfitting.

    Rules:
        - If OOS Sharpe < 50% of IS Sharpe: FAIL (likely overfit)
        - Sharpe degradation ratio computed
        - PBO (Probability of Backtest Overfitting) estimation via degradation heuristic

    Returns dict with pass/fail, degradation ratio, PBO estimate, and details.
    """
    is_sharpe = in_sample_metrics.sharpe
    oos_sharpe = out_of_sample_metrics.sharpe

    # Sharpe degradation
    if is_sharpe > 0:
        degradation_ratio = oos_sharpe / is_sharpe
    else:
        degradation_ratio = 1.0 if oos_sharpe >= 0 else 0.0

    sharpe_pass = degradation_ratio >= 0.50

    # Win-rate degradation
    is_wr = in_sample_metrics.win_rate
    oos_wr = out_of_sample_metrics.win_rate
    wr_degradation = (oos_wr / is_wr) if is_wr > 0 else 1.0

    # PF degradation
    is_pf = in_sample_metrics.profit_factor
    oos_pf = out_of_sample_metrics.profit_factor
    pf_degradation = (oos_pf / is_pf) if is_pf > 0 and is_pf != float("inf") else 1.0

    # PBO heuristic estimation:
    # Based on average degradation across key metrics.
    # PBO ~ 1 - avg_degradation (clamped to [0, 1]).
    avg_deg = np.mean([
        min(degradation_ratio, 1.0),
        min(wr_degradation, 1.0),
        min(pf_degradation, 1.0),
    ])
    pbo_estimate = max(0.0, min(1.0, 1.0 - avg_deg))

    overall_pass = sharpe_pass and pbo_estimate < 0.50

    return {
        "passed": overall_pass,
        "sharpe_degradation_ratio": round(degradation_ratio, 4),
        "sharpe_pass": sharpe_pass,
        "win_rate_degradation": round(wr_degradation, 4),
        "profit_factor_degradation": round(pf_degradation, 4),
        "pbo_estimate": round(pbo_estimate, 4),
        "in_sample_sharpe": is_sharpe,
        "out_of_sample_sharpe": oos_sharpe,
        "in_sample_win_rate": is_wr,
        "out_of_sample_win_rate": oos_wr,
        "in_sample_pf": is_pf,
        "out_of_sample_pf": oos_pf,
        "details": (
            "PASS: OOS metrics within acceptable degradation"
            if overall_pass
            else "FAIL: Likely overfitting -- OOS metrics degraded significantly"
        ),
    }
