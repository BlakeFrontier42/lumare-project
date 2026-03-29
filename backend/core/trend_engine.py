"""
trend_engine.py — Trend Scoring Engine for Lumare MIE

Scores 0-20 based on three components:
  1. MA Alignment (0-8 pts): 20/50/200 EMA stack alignment
  2. ADX Strength (0-6 pts): Directional movement strength
  3. Linear Regression Slope (0-6 pts): Normalized slope direction

All calculations use only historical data (no lookahead bias).
Accepts pandas DataFrames, returns standardized score dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helper: Exponential Moving Average
# ---------------------------------------------------------------------------

def calc_ema(series: pd.Series, span: int) -> pd.Series:
    """
    Exponential Moving Average.

    Formula:
        multiplier = 2 / (span + 1)
        EMA_t = close_t * multiplier + EMA_{t-1} * (1 - multiplier)

    Uses pandas ewm which initialises with the first *span* values as SMA seed.
    """
    return series.ewm(span=span, adjust=False).mean()


# ---------------------------------------------------------------------------
# Helper: True Range & ATR
# ---------------------------------------------------------------------------

def calc_true_range(df: pd.DataFrame) -> pd.Series:
    """
    True Range = max(high - low, |high - prev_close|, |low - prev_close|)

    Requires columns: high, low, close.
    """
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range — Wilder smoothing (EMA with span = 2*period - 1).

    Formula:
        ATR_t = ATR_{t-1} * (period - 1) / period + TR_t / period
    which is equivalent to EMA with alpha = 1/period.
    """
    tr = calc_true_range(df)
    # Wilder smoothing: alpha = 1/period  => span = 2*period - 1
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Helper: ADX (Average Directional Index)
# ---------------------------------------------------------------------------

def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    ADX computed via Wilder's method.

    Steps:
        1. +DM = max(high - prev_high, 0) if > max(prev_low - low, 0) else 0
        2. -DM = max(prev_low - low, 0) if > max(high - prev_high, 0) else 0
        3. Smooth +DM, -DM, TR with Wilder smoothing (alpha = 1/period)
        4. +DI = 100 * smoothed_+DM / smoothed_TR
        5. -DI = 100 * smoothed_-DM / smoothed_TR
        6. DX = 100 * |+DI - -DI| / (+DI + -DI)
        7. ADX = Wilder smooth of DX

    Returns DataFrame with columns: plus_di, minus_di, adx.
    """
    high = df["high"]
    low = df["low"]

    prev_high = high.shift(1)
    prev_low = low.shift(1)

    plus_dm = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)

    # Zero out the smaller of the two when both are positive
    mask = plus_dm > minus_dm
    plus_dm = plus_dm.where(mask, 0.0)
    minus_dm = minus_dm.where(~mask, 0.0)

    tr = calc_true_range(df)

    alpha = 1.0 / period
    smooth_plus_dm = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=alpha, adjust=False).mean()
    smooth_tr = tr.ewm(alpha=alpha, adjust=False).mean()

    plus_di = 100.0 * smooth_plus_dm / smooth_tr.replace(0, np.nan)
    minus_di = 100.0 * smooth_minus_dm / smooth_tr.replace(0, np.nan)

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=alpha, adjust=False).mean()

    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx}, index=df.index)


# ---------------------------------------------------------------------------
# Helper: Linear Regression Slope
# ---------------------------------------------------------------------------

def calc_linreg_slope(series: pd.Series, period: int = 20) -> pd.Series:
    """
    Rolling ordinary-least-squares slope over *period* bars.

    Formula (vectorised via rolling cov / var):
        slope = Cov(x, y) / Var(x)
    where x = 0, 1, ..., period-1 and y = close values in the window.

    Returns a Series of slopes (units = price change per bar).
    """
    x = pd.Series(range(len(series)), index=series.index, dtype=float)
    xy_cov = series.rolling(period).cov(x)
    x_var = x.rolling(period).var()
    return xy_cov / x_var.replace(0, np.nan)


# ---------------------------------------------------------------------------
# Component 1: MA Alignment (0-8 pts)
# ---------------------------------------------------------------------------

def score_ma_alignment(
    df: pd.DataFrame,
    direction: str = "long",
) -> Tuple[int, str]:
    """
    Evaluate 20/50/200 EMA stack alignment.

    Bullish alignment (for longs): EMA20 > EMA50 > EMA200
    Bearish alignment (for shorts): EMA20 < EMA50 < EMA200

    Scoring:
        Full alignment with trade direction          = 8
        Partial (20 vs 50 aligned, 200 unconfirmed)  = 4
        Counter-trend (stack opposes direction)       = 0

    Uses the most recent row only (no lookahead).
    """
    ema20 = calc_ema(df["close"], 20).iloc[-1]
    ema50 = calc_ema(df["close"], 50).iloc[-1]
    ema200 = calc_ema(df["close"], 200).iloc[-1]

    bullish_full = ema20 > ema50 > ema200
    bearish_full = ema20 < ema50 < ema200

    bullish_partial = ema20 > ema50
    bearish_partial = ema20 < ema50

    if direction == "long":
        if bullish_full:
            return 8, "full_bullish_alignment"
        if bullish_partial:
            return 4, "partial_bullish_alignment"
        return 0, "counter_trend"
    else:  # short
        if bearish_full:
            return 8, "full_bearish_alignment"
        if bearish_partial:
            return 4, "partial_bearish_alignment"
        return 0, "counter_trend"


# ---------------------------------------------------------------------------
# Component 2: ADX Strength (0-6 pts)
# ---------------------------------------------------------------------------

def score_adx_strength(df: pd.DataFrame) -> Tuple[int, str]:
    """
    ADX-based trend strength scoring.

    Scoring:
        ADX > 40  =>  6 pts  (strong trend)
        ADX > 25  =>  4 pts  (trending)
        ADX > 15  =>  2 pts  (weak trend)
        ADX <= 15 =>  0 pts  (no trend / ranging)
    """
    adx_df = calc_adx(df)
    adx_val = adx_df["adx"].iloc[-1]

    if np.isnan(adx_val):
        return 0, "adx_insufficient_data"

    if adx_val > 40:
        return 6, f"strong_trend_adx_{adx_val:.1f}"
    if adx_val > 25:
        return 4, f"trending_adx_{adx_val:.1f}"
    if adx_val > 15:
        return 2, f"weak_trend_adx_{adx_val:.1f}"
    return 0, f"no_trend_adx_{adx_val:.1f}"


# ---------------------------------------------------------------------------
# Component 3: Linear Regression Slope (0-6 pts)
# ---------------------------------------------------------------------------

def score_linreg_slope(
    df: pd.DataFrame,
    direction: str = "long",
    period: int = 20,
) -> Tuple[int, str]:
    """
    Linear regression slope normalised by ATR.

    Normalised slope = slope / ATR  (dimensionless)

    Interpretation: how many ATRs the regression line gains per bar.

    Scoring (aligned with direction):
        |norm_slope| > 0.15  =>  6 pts  (strong directional move)
        |norm_slope| > 0.05  =>  3 pts  (moderate)
        else                 =>  0 pts  (flat or contrary)

    If slope opposes trade direction => 0 pts.
    """
    slope = calc_linreg_slope(df["close"], period).iloc[-1]
    atr = calc_atr(df).iloc[-1]

    if np.isnan(slope) or np.isnan(atr) or atr == 0:
        return 0, "linreg_insufficient_data"

    norm_slope = slope / atr

    # Check alignment with direction
    aligned = (direction == "long" and norm_slope > 0) or (
        direction == "short" and norm_slope < 0
    )

    if not aligned:
        return 0, f"contrary_slope_{norm_slope:.4f}"

    abs_ns = abs(norm_slope)
    if abs_ns > 0.15:
        return 6, f"strong_slope_{norm_slope:.4f}"
    if abs_ns > 0.05:
        return 3, f"moderate_slope_{norm_slope:.4f}"
    return 0, f"flat_slope_{norm_slope:.4f}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_trend(
    df: pd.DataFrame,
    direction: str = "long",
) -> Dict:
    """
    Compute the composite Trend Score (0-20).

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with columns: open, high, low, close, volume.
        Must contain >= 200 rows for EMA200.
        Index should be datetime-sorted ascending (oldest first).
    direction : str
        Trade direction — "long" or "short".

    Returns
    -------
    dict with keys:
        score       : int    (0-20)
        components  : dict   (breakdown per sub-score)
        confidence  : float  (0-1)
        signals     : list   (active signal descriptions)
    """
    # Require at least 50 bars for basic indicators (ADX, linreg).
    # EMA200 needs 200+ bars; if unavailable, use EMA50 as longest MA
    # and reduce the MA alignment max score accordingly.
    if len(df) < 50:
        return {
            "score": 0,
            "components": {},
            "confidence": 0.0,
            "signals": ["insufficient_data_for_trend"],
        }

    has_ema200 = len(df) >= 200

    # --- Component scores ---
    if has_ema200:
        ma_score, ma_label = score_ma_alignment(df, direction)
    else:
        # Fallback: use 20/50 alignment only (max 4 instead of 8)
        ema20 = calc_ema(df["close"], 20).iloc[-1]
        ema50 = calc_ema(df["close"], 50).iloc[-1]
        if direction == "long":
            if ema20 > ema50:
                ma_score, ma_label = 4, "partial_bullish_alignment_no_ema200"
            else:
                ma_score, ma_label = 0, "counter_trend_no_ema200"
        else:
            if ema20 < ema50:
                ma_score, ma_label = 4, "partial_bearish_alignment_no_ema200"
            else:
                ma_score, ma_label = 0, "counter_trend_no_ema200"

    adx_score, adx_label = score_adx_strength(df)
    lr_score, lr_label = score_linreg_slope(df, direction)

    total = ma_score + adx_score + lr_score

    # --- Confidence ---
    # Confidence is the fraction of maximum possible score achieved,
    # penalised when components disagree (e.g., strong ADX but no alignment).
    max_score = 20
    raw_confidence = total / max_score

    # Agreement penalty: if ADX is strong but MA not aligned, reduce confidence
    agreement_bonus = 1.0
    if adx_score >= 4 and ma_score == 0:
        agreement_bonus = 0.7  # conflicting signals
    if ma_score == 8 and adx_score == 0:
        agreement_bonus = 0.8  # aligned but no ADX confirmation

    confidence = round(min(1.0, raw_confidence * agreement_bonus), 3)

    # --- Signals ---
    signals: List[str] = []
    if ma_score == 8:
        signals.append(f"full_ema_alignment_{direction}")
    elif ma_score == 4:
        signals.append(f"partial_ema_alignment_{direction}")

    if adx_score >= 4:
        signals.append("strong_directional_trend")
    elif adx_score == 2:
        signals.append("weak_directional_trend")

    if lr_score >= 3:
        signals.append(f"positive_regression_slope_{direction}")

    return {
        "score": total,
        "components": {
            "ma_alignment": {"score": ma_score, "max": 8, "detail": ma_label},
            "adx_strength": {"score": adx_score, "max": 6, "detail": adx_label},
            "linreg_slope": {"score": lr_score, "max": 6, "detail": lr_label},
        },
        "confidence": confidence,
        "signals": signals,
    }


class TrendEngine:
    """Wrapper class adapting score_trend() to the SignalEngine protocol."""

    def __init__(self, settings=None):
        self.settings = settings

    def score(self, market_data: dict, direction: str = "long") -> dict:
        tf_data = market_data.get("timeframe_data", {})
        df = None
        for tf in ["1H", "4H", "1D"]:
            candidate = tf_data.get(tf)
            if candidate is not None and not candidate.empty:
                df = candidate
                break
        if df is None or len(df) < 10:
            return {"score": 0, "signals": [], "confidence": 0.0, "components": {}}
        result = score_trend(df, direction)
        result["score"] = min(100.0, float(result["score"]) * 5.0)  # scale 0-20 → 0-100
        return result
