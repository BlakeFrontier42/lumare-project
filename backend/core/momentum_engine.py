"""
momentum_engine.py — Momentum Scoring Engine for Lumare MIE

Scores 0-20 based on three components:
  1. RSI Regime (0-7 pts): RSI(14) positioning, divergences
  2. MACD (0-7 pts): Histogram direction, acceleration, crossovers
  3. Rate of Change (0-6 pts): ROC(10) direction and acceleration

All calculations use only historical data (no lookahead bias).
Accepts pandas DataFrames, returns standardized score dict.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helper: RSI (Relative Strength Index)
# ---------------------------------------------------------------------------

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI using Wilder smoothing (exponential moving average with alpha = 1/period).

    Formula:
        delta   = close_t - close_{t-1}
        gain    = max(delta, 0)
        loss    = max(-delta, 0)
        avg_gain = Wilder_smooth(gain, period)
        avg_loss = Wilder_smooth(loss, period)
        RS      = avg_gain / avg_loss
        RSI     = 100 - 100 / (1 + RS)
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi


# ---------------------------------------------------------------------------
# Helper: MACD
# ---------------------------------------------------------------------------

def calc_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    MACD (Moving Average Convergence Divergence).

    Formula:
        MACD_line  = EMA(close, fast) - EMA(close, slow)
        Signal     = EMA(MACD_line, signal)
        Histogram  = MACD_line - Signal

    Returns DataFrame with columns: macd, signal, histogram.
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram},
        index=series.index,
    )


# ---------------------------------------------------------------------------
# Helper: Rate of Change
# ---------------------------------------------------------------------------

def calc_roc(series: pd.Series, period: int = 10) -> pd.Series:
    """
    Rate of Change (percentage).

    Formula:
        ROC_t = (close_t - close_{t-period}) / close_{t-period} * 100
    """
    shifted = series.shift(period)
    return ((series - shifted) / shifted.replace(0, np.nan)) * 100.0


# ---------------------------------------------------------------------------
# Helper: Divergence Detection
# ---------------------------------------------------------------------------

def detect_rsi_divergence(
    df: pd.DataFrame,
    rsi: pd.Series,
    lookback: int = 20,
) -> str:
    """
    Detect bullish or bearish RSI divergence over the lookback window.

    Bullish divergence: price makes a lower low but RSI makes a higher low.
    Bearish divergence: price makes a higher high but RSI makes a lower high.

    Algorithm:
        1. Split the lookback window into two halves.
        2. Find the lowest close in each half (for bullish) or highest (for bearish).
        3. Compare price direction vs RSI direction at those points.

    Returns: "bullish", "bearish", or "none".
    """
    if len(df) < lookback:
        return "none"

    recent = df.iloc[-lookback:]
    rsi_recent = rsi.iloc[-lookback:]

    mid = lookback // 2
    first_half_close = recent["close"].iloc[:mid]
    second_half_close = recent["close"].iloc[mid:]
    first_half_rsi = rsi_recent.iloc[:mid]
    second_half_rsi = rsi_recent.iloc[mid:]

    # Bullish divergence: price lower low, RSI higher low
    price_low1_idx = first_half_close.idxmin()
    price_low2_idx = second_half_close.idxmin()

    if price_low1_idx is not np.nan and price_low2_idx is not np.nan:
        price_low1 = first_half_close[price_low1_idx]
        price_low2 = second_half_close[price_low2_idx]
        rsi_low1 = rsi.loc[price_low1_idx] if price_low1_idx in rsi.index else np.nan
        rsi_low2 = rsi.loc[price_low2_idx] if price_low2_idx in rsi.index else np.nan

        if not (np.isnan(rsi_low1) or np.isnan(rsi_low2)):
            if price_low2 < price_low1 and rsi_low2 > rsi_low1:
                return "bullish"

    # Bearish divergence: price higher high, RSI lower high
    price_high1_idx = first_half_close.idxmax()
    price_high2_idx = second_half_close.idxmax()

    if price_high1_idx is not np.nan and price_high2_idx is not np.nan:
        price_high1 = first_half_close[price_high1_idx]
        price_high2 = second_half_close[price_high2_idx]
        rsi_high1 = rsi.loc[price_high1_idx] if price_high1_idx in rsi.index else np.nan
        rsi_high2 = rsi.loc[price_high2_idx] if price_high2_idx in rsi.index else np.nan

        if not (np.isnan(rsi_high1) or np.isnan(rsi_high2)):
            if price_high2 > price_high1 and rsi_high2 < rsi_high1:
                return "bearish"

    return "none"


# ---------------------------------------------------------------------------
# Component 1: RSI Regime (0-7 pts)
# ---------------------------------------------------------------------------

def score_rsi_regime(
    df: pd.DataFrame,
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    RSI-based momentum scoring.

    For longs:
        RSI < 30 + bullish divergence       = 7 pts  (oversold reversal)
        RSI > 50 with positive momentum      = 5 pts  (trend continuation)
        RSI crossing above 50                = 3 pts  (early confirmation)
        RSI < 50 or bearish divergence       = 0 pts  (counter-signal)

    For shorts: thresholds are mirrored.
    """
    rsi = calc_rsi(df["close"])
    current_rsi = rsi.iloc[-1]
    prev_rsi = rsi.iloc[-2] if len(rsi) >= 2 else np.nan
    divergence = detect_rsi_divergence(df, rsi)

    signals: List[str] = []

    if np.isnan(current_rsi):
        return 0, "rsi_insufficient_data", signals

    if direction == "long":
        # Best: oversold with bullish divergence
        if current_rsi < 30 and divergence == "bullish":
            signals.append("bullish_divergence_oversold")
            return 7, f"oversold_bullish_div_rsi_{current_rsi:.1f}", signals

        # Good: above 50 with rising RSI (positive momentum)
        if current_rsi > 50 and not np.isnan(prev_rsi) and current_rsi > prev_rsi:
            signals.append("rsi_above_50_rising")
            return 5, f"rsi_bullish_momentum_{current_rsi:.1f}", signals

        # Acceptable: crossing above 50
        if (
            not np.isnan(prev_rsi)
            and prev_rsi <= 50
            and current_rsi > 50
        ):
            signals.append("rsi_cross_above_50")
            return 3, f"rsi_cross_50_{current_rsi:.1f}", signals

        # Bearish divergence or below 50
        if divergence == "bearish":
            signals.append("bearish_divergence_detected")
        return 0, f"rsi_counter_signal_{current_rsi:.1f}", signals

    else:  # short
        if current_rsi > 70 and divergence == "bearish":
            signals.append("bearish_divergence_overbought")
            return 7, f"overbought_bearish_div_rsi_{current_rsi:.1f}", signals

        if current_rsi < 50 and not np.isnan(prev_rsi) and current_rsi < prev_rsi:
            signals.append("rsi_below_50_falling")
            return 5, f"rsi_bearish_momentum_{current_rsi:.1f}", signals

        if (
            not np.isnan(prev_rsi)
            and prev_rsi >= 50
            and current_rsi < 50
        ):
            signals.append("rsi_cross_below_50")
            return 3, f"rsi_cross_50_{current_rsi:.1f}", signals

        if divergence == "bullish":
            signals.append("bullish_divergence_detected")
        return 0, f"rsi_counter_signal_{current_rsi:.1f}", signals


# ---------------------------------------------------------------------------
# Component 2: MACD (0-7 pts)
# ---------------------------------------------------------------------------

def score_macd(
    df: pd.DataFrame,
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    MACD-based scoring using histogram direction and crossovers.

    For longs:
        Histogram > 0 and increasing (accelerating)  = 7 pts
        Fresh bullish crossover (MACD crosses signal) = 5 pts
        Histogram > 0 but decreasing (decelerating)   = 2 pts
        Histogram < 0                                  = 0 pts

    For shorts: signs are inverted.
    """
    macd_df = calc_macd(df["close"])
    hist = macd_df["histogram"]
    macd_line = macd_df["macd"]
    signal_line = macd_df["signal"]

    current_hist = hist.iloc[-1]
    prev_hist = hist.iloc[-2] if len(hist) >= 2 else np.nan
    current_macd = macd_line.iloc[-1]
    prev_macd = macd_line.iloc[-2] if len(macd_line) >= 2 else np.nan
    current_signal = signal_line.iloc[-1]
    prev_signal = signal_line.iloc[-2] if len(signal_line) >= 2 else np.nan

    signals: List[str] = []

    if np.isnan(current_hist):
        return 0, "macd_insufficient_data", signals

    # Determine crossover
    bullish_cross = (
        not np.isnan(prev_macd)
        and not np.isnan(prev_signal)
        and prev_macd <= prev_signal
        and current_macd > current_signal
    )
    bearish_cross = (
        not np.isnan(prev_macd)
        and not np.isnan(prev_signal)
        and prev_macd >= prev_signal
        and current_macd < current_signal
    )

    if direction == "long":
        hist_positive = current_hist > 0
        hist_increasing = not np.isnan(prev_hist) and current_hist > prev_hist

        if hist_positive and hist_increasing:
            signals.append("macd_histogram_accelerating_bullish")
            return 7, f"macd_accel_bullish_{current_hist:.4f}", signals

        if bullish_cross:
            signals.append("macd_bullish_crossover")
            return 5, f"macd_bullish_cross_{current_macd:.4f}", signals

        if hist_positive and not hist_increasing:
            signals.append("macd_histogram_decelerating")
            return 2, f"macd_decel_bullish_{current_hist:.4f}", signals

        return 0, f"macd_bearish_{current_hist:.4f}", signals

    else:  # short
        hist_negative = current_hist < 0
        hist_decreasing = not np.isnan(prev_hist) and current_hist < prev_hist

        if hist_negative and hist_decreasing:
            signals.append("macd_histogram_accelerating_bearish")
            return 7, f"macd_accel_bearish_{current_hist:.4f}", signals

        if bearish_cross:
            signals.append("macd_bearish_crossover")
            return 5, f"macd_bearish_cross_{current_macd:.4f}", signals

        if hist_negative and not hist_decreasing:
            signals.append("macd_histogram_decelerating")
            return 2, f"macd_decel_bearish_{current_hist:.4f}", signals

        return 0, f"macd_bullish_{current_hist:.4f}", signals


# ---------------------------------------------------------------------------
# Component 3: Rate of Change (0-6 pts)
# ---------------------------------------------------------------------------

def score_roc(
    df: pd.DataFrame,
    direction: str = "long",
    period: int = 10,
) -> Tuple[int, str, List[str]]:
    """
    ROC-based scoring — direction and acceleration.

    For longs:
        ROC > 0 and accelerating (ROC increasing)  = 6 pts
        ROC > 0 but decelerating                    = 3 pts
        ROC <= 0                                    = 0 pts

    For shorts: signs inverted.
    """
    roc = calc_roc(df["close"], period)
    current_roc = roc.iloc[-1]
    prev_roc = roc.iloc[-2] if len(roc) >= 2 else np.nan

    signals: List[str] = []

    if np.isnan(current_roc):
        return 0, "roc_insufficient_data", signals

    if direction == "long":
        if current_roc > 0:
            accelerating = not np.isnan(prev_roc) and current_roc > prev_roc
            if accelerating:
                signals.append("roc_positive_accelerating")
                return 6, f"roc_accel_{current_roc:.2f}%", signals
            else:
                signals.append("roc_positive_decelerating")
                return 3, f"roc_decel_{current_roc:.2f}%", signals
        return 0, f"roc_negative_{current_roc:.2f}%", signals

    else:  # short
        if current_roc < 0:
            accelerating = not np.isnan(prev_roc) and current_roc < prev_roc
            if accelerating:
                signals.append("roc_negative_accelerating")
                return 6, f"roc_accel_{current_roc:.2f}%", signals
            else:
                signals.append("roc_negative_decelerating")
                return 3, f"roc_decel_{current_roc:.2f}%", signals
        return 0, f"roc_positive_{current_roc:.2f}%", signals


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_momentum(
    df: pd.DataFrame,
    direction: str = "long",
) -> Dict:
    """
    Compute the composite Momentum Score (0-20).

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with columns: open, high, low, close, volume.
        Must contain >= 35 rows (26 for MACD slow EMA + 9 for signal).
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
    min_rows = 35
    if len(df) < min_rows:
        return {
            "score": 0,
            "components": {},
            "confidence": 0.0,
            "signals": ["insufficient_data_for_momentum"],
        }

    # --- Component scores ---
    rsi_score, rsi_label, rsi_signals = score_rsi_regime(df, direction)
    macd_score, macd_label, macd_signals = score_macd(df, direction)
    roc_score, roc_label, roc_signals = score_roc(df, direction)

    total = rsi_score + macd_score + roc_score

    # --- Confidence ---
    # Base confidence from score ratio, with inter-component agreement boost.
    max_score = 20
    raw_confidence = total / max_score

    # Agreement: count how many components score above their midpoint
    components_firing = sum([
        rsi_score >= 3,
        macd_score >= 3,
        roc_score >= 3,
    ])

    # If all three agree, boost confidence; if only one fires, reduce it
    if components_firing == 3:
        agreement_factor = 1.0
    elif components_firing == 2:
        agreement_factor = 0.9
    elif components_firing == 1:
        agreement_factor = 0.75
    else:
        agreement_factor = 0.5

    confidence = round(min(1.0, raw_confidence * agreement_factor), 3)

    # --- Collect signals ---
    all_signals = rsi_signals + macd_signals + roc_signals

    return {
        "score": total,
        "components": {
            "rsi_regime": {"score": rsi_score, "max": 7, "detail": rsi_label},
            "macd": {"score": macd_score, "max": 7, "detail": macd_label},
            "rate_of_change": {"score": roc_score, "max": 6, "detail": roc_label},
        },
        "confidence": confidence,
        "signals": all_signals,
    }


class MomentumEngine:
    """Wrapper class adapting score_momentum() to the SignalEngine protocol."""

    def __init__(self, settings=None):
        self.settings = settings

    def score(self, market_data: dict, direction: str = "long") -> dict:
        tf_data = market_data.get("timeframe_data", {})
        df = None
        for tf in ["1H", "4H", "15M"]:
            candidate = tf_data.get(tf)
            if candidate is not None and not candidate.empty:
                df = candidate
                break
        if df is None or len(df) < 10:
            return {"score": 0, "signals": [], "confidence": 0.0, "components": {}}
        result = score_momentum(df, direction)
        result["score"] = min(100.0, float(result["score"]) * 5.0)  # scale 0-20 → 0-100
        return result
