"""
structure_engine.py — Market Structure (ICT) Scoring Engine for Lumare MIE

Scores 0-20 based on ICT (Inner Circle Trader) concepts, quantified:
  1. Liquidity Sweep Detection (0-6 pts)
  2. Break of Structure — BOS (0-6 pts)
  3. Fair Value Gap — FVG (0-4 pts)
  4. Displacement (0-4 pts)

All calculations use only historical data (no lookahead bias).
Accepts pandas DataFrames, returns standardized score dict.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helper: ATR
# ---------------------------------------------------------------------------

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range with Wilder smoothing.

    Formula:
        TR = max(high - low, |high - prev_close|, |low - prev_close|)
        ATR = EMA(TR, alpha=1/period)
    """
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Helper: Swing High / Swing Low Detection
# ---------------------------------------------------------------------------

def detect_swing_highs(df: pd.DataFrame, order: int = 5) -> pd.Series:
    """
    Detect swing highs using vectorized rolling max comparison.
    A swing high at index i is confirmed once bar i+order is available.
    """
    highs = df["high"].values
    n = len(highs)
    is_swing = np.zeros(n, dtype=bool)

    if n < 2 * order + 1:
        return pd.Series(is_swing, index=df.index)

    # Vectorised: rolling max on left and right windows
    for i in range(order, n - order):
        left_max = highs[i - order:i].max()
        right_max = highs[i + 1:i + 1 + order].max()
        if highs[i] > left_max and highs[i] > right_max:
            is_swing[i] = True

    return pd.Series(is_swing, index=df.index)


def detect_swing_lows(df: pd.DataFrame, order: int = 5) -> pd.Series:
    """
    Detect swing lows using vectorized rolling min comparison.
    """
    lows = df["low"].values
    n = len(lows)
    is_swing = np.zeros(n, dtype=bool)

    if n < 2 * order + 1:
        return pd.Series(is_swing, index=df.index)

    for i in range(order, n - order):
        left_min = lows[i - order:i].min()
        right_min = lows[i + 1:i + 1 + order].min()
        if lows[i] < left_min and lows[i] < right_min:
            is_swing[i] = True

    return pd.Series(is_swing, index=df.index)


def get_recent_swing_levels(
    df: pd.DataFrame,
    order: int = 5,
    n: int = 3,
) -> Tuple[List[float], List[float]]:
    """
    Return the last *n* swing highs and swing lows as price levels.
    """
    sh = detect_swing_highs(df, order)
    sl = detect_swing_lows(df, order)

    swing_highs = df.loc[sh, "high"].tolist()[-n:]
    swing_lows = df.loc[sl, "low"].tolist()[-n:]

    return swing_highs, swing_lows


# ---------------------------------------------------------------------------
# Helper: Fair Value Gap (FVG) Detection
# ---------------------------------------------------------------------------

def detect_fvgs(
    df: pd.DataFrame,
    lookback: int = 20,
) -> List[Dict]:
    """
    Detect Fair Value Gaps (three-candle imbalance zones).

    Bullish FVG: candle[i-1].high < candle[i+1].low
        => gap between candle[i-1].high and candle[i+1].low
        (price skipped this zone on the way up — expect retracement fill)

    Bearish FVG: candle[i-1].low > candle[i+1].high
        => gap between candle[i+1].high and candle[i-1].low
        (price skipped this zone on the way down)

    Only checks the last *lookback* bars (no lookahead: candle i+1 must exist).
    """
    fvgs: List[Dict] = []
    start = max(1, len(df) - lookback - 1)

    for i in range(start, len(df) - 1):
        prev_high = df["high"].iloc[i - 1]
        prev_low = df["low"].iloc[i - 1]
        next_high = df["high"].iloc[i + 1]
        next_low = df["low"].iloc[i + 1]

        # Bullish FVG: gap-up imbalance
        if next_low > prev_high:
            fvgs.append({
                "type": "bullish",
                "top": next_low,
                "bottom": prev_high,
                "bar_index": i,
                "size": next_low - prev_high,
            })

        # Bearish FVG: gap-down imbalance
        if next_high < prev_low:
            fvgs.append({
                "type": "bearish",
                "top": prev_low,
                "bottom": next_high,
                "bar_index": i,
                "size": prev_low - next_high,
            })

    return fvgs


# ---------------------------------------------------------------------------
# Helper: Break of Structure (BOS) Detection
# ---------------------------------------------------------------------------

def detect_bos(
    df: pd.DataFrame,
    order: int = 5,
) -> Optional[str]:
    """
    Detect Break of Structure on a single timeframe.

    Bullish BOS: most recent swing high is broken to the upside
        => current close > most recent confirmed swing high

    Bearish BOS: most recent swing low is broken to the downside
        => current close < most recent confirmed swing low

    Returns "bullish", "bearish", or None.
    """
    swing_highs, swing_lows = get_recent_swing_levels(df, order, n=2)
    current_close = df["close"].iloc[-1]

    if swing_highs and current_close > swing_highs[-1]:
        return "bullish"
    if swing_lows and current_close < swing_lows[-1]:
        return "bearish"
    return None


# ---------------------------------------------------------------------------
# Component 1: Liquidity Sweep Detection (0-6 pts)
# ---------------------------------------------------------------------------

def score_liquidity_sweep(
    df: pd.DataFrame,
    direction: str = "long",
    lookback: int = 5,
) -> Tuple[int, str, List[str]]:
    """
    Detect stop-hunt / liquidity sweep patterns.

    Bullish sweep (for longs):
        Price pierces below recent swing low (wick) then closes back above it.
        => Stops below the swing low are triggered, then price reverses.

    Bearish sweep (for shorts):
        Price pierces above recent swing high then closes back below it.

    Scoring:
        Sweep + reversal confirmation (close back inside range) = 6 pts
        Sweep without reversal (still outside)                  = 2 pts
        No sweep detected                                       = 0 pts
    """
    signals: List[str] = []
    swing_highs, swing_lows = get_recent_swing_levels(df, order=5, n=3)

    if not swing_highs and not swing_lows:
        return 0, "no_swing_levels", signals

    current_close = df["close"].iloc[-1]
    current_low = df["low"].iloc[-1]
    current_high = df["high"].iloc[-1]

    # Check last few bars for sweep patterns
    recent = df.iloc[-lookback:]

    if direction == "long" and swing_lows:
        target_level = swing_lows[-1]
        # Did any recent bar's low pierce below the swing low?
        pierced = recent["low"].min() < target_level
        # Did price recover (close back above)?
        recovered = current_close > target_level

        if pierced and recovered:
            signals.append("bullish_liquidity_sweep_reversal")
            return 6, f"sweep_low_{target_level:.4f}_reversed", signals
        if pierced and not recovered:
            signals.append("bullish_liquidity_sweep_no_reversal")
            return 2, f"sweep_low_{target_level:.4f}_no_reversal", signals

    elif direction == "short" and swing_highs:
        target_level = swing_highs[-1]
        pierced = recent["high"].max() > target_level
        recovered = current_close < target_level

        if pierced and recovered:
            signals.append("bearish_liquidity_sweep_reversal")
            return 6, f"sweep_high_{target_level:.4f}_reversed", signals
        if pierced and not recovered:
            signals.append("bearish_liquidity_sweep_no_reversal")
            return 2, f"sweep_high_{target_level:.4f}_no_reversal", signals

    return 0, "no_sweep_detected", signals


# ---------------------------------------------------------------------------
# Component 2: Break of Structure (0-6 pts)
# ---------------------------------------------------------------------------

def score_bos(
    df: pd.DataFrame,
    direction: str = "long",
    htf_df: Optional[pd.DataFrame] = None,
) -> Tuple[int, str, List[str]]:
    """
    Break of Structure scoring across timeframes.

    Scoring:
        BOS aligned with direction on 2+ timeframes  = 6 pts
        BOS on single (primary) timeframe only        = 3 pts
        No BOS or counter-direction BOS               = 0 pts

    Parameters
    ----------
    df : pd.DataFrame
        Primary timeframe OHLCV data.
    htf_df : pd.DataFrame, optional
        Higher timeframe OHLCV data for multi-TF confirmation.
    """
    signals: List[str] = []

    primary_bos = detect_bos(df)
    htf_bos = detect_bos(htf_df) if htf_df is not None and len(htf_df) > 15 else None

    target = "bullish" if direction == "long" else "bearish"

    primary_aligned = primary_bos == target
    htf_aligned = htf_bos == target

    if primary_aligned and htf_aligned:
        signals.append(f"bos_{target}_multi_timeframe")
        return 6, f"bos_{target}_2tf", signals

    if primary_aligned:
        signals.append(f"bos_{target}_primary_tf")
        return 3, f"bos_{target}_1tf", signals

    if htf_aligned:
        signals.append(f"bos_{target}_htf_only")
        return 3, f"bos_{target}_htf_only", signals

    return 0, "no_aligned_bos", signals


# ---------------------------------------------------------------------------
# Component 3: Fair Value Gap (0-4 pts)
# ---------------------------------------------------------------------------

def score_fvg(
    df: pd.DataFrame,
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    Fair Value Gap scoring based on proximity to current price.

    For longs: bullish FVGs below current price are potential support.
    For shorts: bearish FVGs above current price are potential resistance.

    Scoring:
        FVG present and price approaching (within 1 ATR) = 4 pts
        FVG present but distant (> 1 ATR away)           = 2 pts
        No relevant FVG                                   = 0 pts
    """
    signals: List[str] = []
    fvgs = detect_fvgs(df, lookback=30)
    atr = calc_atr(df).iloc[-1]
    current_close = df["close"].iloc[-1]

    if np.isnan(atr) or atr == 0:
        return 0, "fvg_insufficient_data", signals

    target_type = "bullish" if direction == "long" else "bearish"
    relevant = [f for f in fvgs if f["type"] == target_type]

    if not relevant:
        return 0, "no_relevant_fvg", signals

    # Find the nearest relevant FVG
    if direction == "long":
        # Bullish FVGs below price — look for closest below
        below = [f for f in relevant if f["top"] <= current_close]
        if not below:
            # FVG exists but above current price (already filled or not useful)
            return 0, "no_fvg_below_price", signals
        nearest = max(below, key=lambda f: f["top"])
        distance = current_close - nearest["top"]
    else:
        # Bearish FVGs above price
        above = [f for f in relevant if f["bottom"] >= current_close]
        if not above:
            return 0, "no_fvg_above_price", signals
        nearest = min(above, key=lambda f: f["bottom"])
        distance = nearest["bottom"] - current_close

    if distance <= atr:
        signals.append(f"{target_type}_fvg_approaching")
        return 4, f"fvg_{target_type}_near_{distance / atr:.2f}atr", signals
    else:
        signals.append(f"{target_type}_fvg_distant")
        return 2, f"fvg_{target_type}_far_{distance / atr:.2f}atr", signals


# ---------------------------------------------------------------------------
# Component 4: Displacement (0-4 pts)
# ---------------------------------------------------------------------------

def score_displacement(
    df: pd.DataFrame,
    direction: str = "long",
    lookback: int = 5,
) -> Tuple[int, str, List[str]]:
    """
    Displacement detection — large candle bodies indicating institutional flow.

    A displacement candle has body > 1.5x ATR.

    Formula:
        body = |close - open|
        displacement_ratio = body / ATR

    Scoring (within last *lookback* bars, aligned with direction):
        displacement_ratio > 2.0  =>  4 pts  (strong displacement)
        displacement_ratio > 1.5  =>  2 pts  (moderate displacement)
        below threshold           =>  0 pts

    Direction alignment:
        Long: close > open (bullish candle)
        Short: close < open (bearish candle)
    """
    signals: List[str] = []
    atr = calc_atr(df).iloc[-1]

    if np.isnan(atr) or atr == 0:
        return 0, "displacement_insufficient_data", signals

    recent = df.iloc[-lookback:]
    bodies = (recent["close"] - recent["open"]).abs()
    ratios = bodies / atr

    # Filter for direction-aligned candles
    if direction == "long":
        aligned_mask = recent["close"] > recent["open"]
    else:
        aligned_mask = recent["close"] < recent["open"]

    aligned_ratios = ratios[aligned_mask]

    if aligned_ratios.empty:
        return 0, "no_aligned_displacement", signals

    max_ratio = aligned_ratios.max()

    if max_ratio > 2.0:
        signals.append(f"strong_displacement_{direction}")
        return 4, f"displacement_{max_ratio:.2f}x_atr", signals
    if max_ratio > 1.5:
        signals.append(f"moderate_displacement_{direction}")
        return 2, f"displacement_{max_ratio:.2f}x_atr", signals

    return 0, f"weak_displacement_{max_ratio:.2f}x_atr", signals


# ---------------------------------------------------------------------------
# Component 5: Order Block Detection (0-4 pts)
# ---------------------------------------------------------------------------

def score_order_block(
    df: pd.DataFrame,
    direction: str = "long",
    lookback: int = 30,
) -> Tuple[int, str, List[str]]:
    """
    Detect Order Blocks — the last opposing candle before a strong move.
    Uses numpy arrays for performance.
    """
    signals: List[str] = []
    atr_series = calc_atr(df)
    atr = float(atr_series.iloc[-1])

    if np.isnan(atr) or atr <= 0 or len(df) < lookback:
        return 0, "ob_insufficient_data", signals

    # Work with numpy arrays for speed
    opens = df["open"].values[-lookback:]
    closes = df["close"].values[-lookback:]
    current_close = closes[-1]

    bodies = closes - opens
    abs_bodies = np.abs(bodies)
    strong_mask = abs_bodies > (atr * 1.2)

    if direction == "long":
        # Find strong bullish candles, check the candle before each
        strong_indices = np.where(strong_mask & (bodies > 0))[0]
        for i in reversed(strong_indices):
            if i < 1:
                continue
            prev_open = opens[i - 1]
            prev_close = closes[i - 1]
            if prev_close < prev_open:  # bearish candle = order block
                ob_top = prev_open
                ob_bottom = prev_close
                if ob_bottom <= current_close <= ob_top + atr * 0.3:
                    signals.append("bullish_order_block_retest")
                    return 4, f"ob_bull_retest_{ob_bottom:.0f}_{ob_top:.0f}", signals
                elif current_close > ob_top and current_close - ob_top < atr * 2:
                    signals.append("bullish_order_block_nearby")
                    return 2, f"ob_bull_near_{ob_bottom:.0f}_{ob_top:.0f}", signals
    else:
        strong_indices = np.where(strong_mask & (bodies < 0))[0]
        for i in reversed(strong_indices):
            if i < 1:
                continue
            prev_open = opens[i - 1]
            prev_close = closes[i - 1]
            if prev_close > prev_open:  # bullish candle = order block
                ob_top = prev_close
                ob_bottom = prev_open
                if ob_bottom - atr * 0.3 <= current_close <= ob_top:
                    signals.append("bearish_order_block_retest")
                    return 4, f"ob_bear_retest_{ob_bottom:.0f}_{ob_top:.0f}", signals
                elif current_close < ob_bottom and ob_bottom - current_close < atr * 2:
                    signals.append("bearish_order_block_nearby")
                    return 2, f"ob_bear_near_{ob_bottom:.0f}_{ob_top:.0f}", signals

    return 0, "no_order_block", signals


# ---------------------------------------------------------------------------
# Component 6: Premium/Discount Zone + OTE (0-4 pts)
# ---------------------------------------------------------------------------

def score_premium_discount(
    df: pd.DataFrame,
    direction: str = "long",
    swing_lookback: int = 50,
) -> Tuple[int, str, List[str]]:
    """
    ICT Premium/Discount zones with Optimal Trade Entry (OTE).

    Divide the range between the most recent swing high and swing low into:
        - Premium zone: upper 50% (above equilibrium) — sell zone
        - Discount zone: lower 50% (below equilibrium) — buy zone
        - OTE sweet spot: 62-79% Fibonacci retracement of the last impulse move

    Scoring:
        In OTE zone (62-79% retracement) aligned with direction = 4 pts
        In correct zone (discount for long, premium for short)  = 2 pts
        In wrong zone or insufficient data                      = 0 pts
    """
    signals: List[str] = []

    swing_highs, swing_lows = get_recent_swing_levels(df, order=5, n=3)

    if not swing_highs or not swing_lows:
        return 0, "pd_no_swing_levels", signals

    # Use the most recent significant range
    range_high = max(swing_highs)
    range_low = min(swing_lows)
    range_size = range_high - range_low

    if range_size <= 0:
        return 0, "pd_flat_range", signals

    current_close = df["close"].iloc[-1]
    equilibrium = (range_high + range_low) / 2.0

    # Position within the range (0 = low, 1 = high)
    position_pct = (current_close - range_low) / range_size

    if direction == "long":
        # For longs: we want price in discount zone (below equilibrium)
        # OTE: 62-79% retracement from the high = 21-38% of the range from the bottom
        ote_low = range_low + range_size * 0.21   # 79% retracement
        ote_high = range_low + range_size * 0.38  # 62% retracement

        if ote_low <= current_close <= ote_high:
            signals.append("long_ote_zone")
            return 4, f"ote_long_{position_pct:.2f}_in_range", signals
        elif current_close < equilibrium:
            signals.append("long_discount_zone")
            return 2, f"discount_{position_pct:.2f}_in_range", signals
        else:
            return 0, f"long_premium_zone_{position_pct:.2f}", signals

    else:  # short
        # For shorts: we want price in premium zone (above equilibrium)
        # OTE: 62-79% retracement from the low = 62-79% of the range from the bottom
        ote_low = range_low + range_size * 0.62   # 62% retracement
        ote_high = range_low + range_size * 0.79  # 79% retracement

        if ote_low <= current_close <= ote_high:
            signals.append("short_ote_zone")
            return 4, f"ote_short_{position_pct:.2f}_in_range", signals
        elif current_close > equilibrium:
            signals.append("short_premium_zone")
            return 2, f"premium_{position_pct:.2f}_in_range", signals
        else:
            return 0, f"short_discount_zone_{position_pct:.2f}", signals


# ---------------------------------------------------------------------------
# Component 7: Session / Killzone Alignment (0-2 pts)
# ---------------------------------------------------------------------------

def score_session_alignment(
    df: pd.DataFrame,
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    ICT Killzone alignment — check if current bar falls within high-probability
    trading sessions (London Open, NY Open, NY-London overlap).

    Since backtest uses UTC timestamps:
        London Open killzone:  02:00-05:00 UTC (07:00-10:00 GMT)
        NY Open killzone:      12:00-15:00 UTC (07:00-10:00 EST)
        NY-London overlap:     12:00-16:00 UTC (highest volume period)

    Scoring:
        In killzone  = 2 pts
        Outside      = 0 pts
    """
    signals: List[str] = []

    try:
        ts = df["timestamp"].iloc[-1]
        if isinstance(ts, str):
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(ts.replace("Z", "+00:00"))
        hour = ts.hour if hasattr(ts, 'hour') else 12  # default mid-day
    except Exception:
        return 0, "session_no_timestamp", signals

    # London Open: 02-05 UTC, NY Open: 12-15 UTC
    in_killzone = (2 <= hour <= 5) or (12 <= hour <= 15)

    if in_killzone:
        signals.append("ict_killzone_active")
        return 2, f"killzone_h{hour}", signals

    return 0, f"outside_killzone_h{hour}", signals


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_structure(
    df: pd.DataFrame,
    direction: str = "long",
    htf_df: Optional[pd.DataFrame] = None,
) -> Dict:
    """
    Compute the composite Market Structure Score (0-30).

    Seven ICT components:
        1. Liquidity Sweep (0-6)
        2. Break of Structure (0-6)
        3. Fair Value Gap (0-4)
        4. Displacement (0-4)
        5. Order Block (0-4)
        6. Premium/Discount + OTE (0-4)
        7. Session/Killzone (0-2)

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data with columns: open, high, low, close, volume.
        Must contain >= 50 rows for swing detection + ATR.
    direction : str
        Trade direction — "long" or "short".
    htf_df : pd.DataFrame, optional
        Higher timeframe OHLCV data for multi-TF BOS confirmation.

    Returns
    -------
    dict with keys:
        score       : int    (0-30)
        components  : dict   (breakdown per sub-score)
        confidence  : float  (0-1)
        signals     : list   (active signal descriptions)
    """
    min_rows = 50
    if len(df) < min_rows:
        return {
            "score": 0,
            "components": {},
            "confidence": 0.0,
            "signals": ["insufficient_data_for_structure"],
        }

    # --- Component scores (original 4) ---
    sweep_score, sweep_label, sweep_signals = score_liquidity_sweep(df, direction)
    bos_score, bos_label, bos_signals = score_bos(df, direction, htf_df)
    fvg_score, fvg_label, fvg_signals = score_fvg(df, direction)
    disp_score, disp_label, disp_signals = score_displacement(df, direction)

    # --- New ICT components ---
    ob_score, ob_label, ob_signals = score_order_block(df, direction)
    pd_score, pd_label, pd_signals = score_premium_discount(df, direction)
    sess_score, sess_label, sess_signals = score_session_alignment(df, direction)

    total = (sweep_score + bos_score + fvg_score + disp_score
             + ob_score + pd_score + sess_score)

    # --- Confidence ---
    max_score = 30
    raw_confidence = total / max_score

    # ICT confluence: the more components agree, the higher the confidence.
    components_active = sum([
        sweep_score > 0,
        bos_score > 0,
        fvg_score > 0,
        disp_score > 0,
        ob_score > 0,
        pd_score > 0,
        sess_score > 0,
    ])

    confluence_map = {0: 0.2, 1: 0.4, 2: 0.6, 3: 0.7, 4: 0.8, 5: 0.9, 6: 0.95, 7: 1.0}
    confluence_factor = confluence_map.get(components_active, 0.2)

    confidence = round(min(1.0, raw_confidence * confluence_factor), 3)

    # --- Collect signals ---
    all_signals = (sweep_signals + bos_signals + fvg_signals + disp_signals
                   + ob_signals + pd_signals + sess_signals)

    return {
        "score": total,
        "components": {
            "liquidity_sweep": {"score": sweep_score, "max": 6, "detail": sweep_label},
            "break_of_structure": {"score": bos_score, "max": 6, "detail": bos_label},
            "fair_value_gap": {"score": fvg_score, "max": 4, "detail": fvg_label},
            "displacement": {"score": disp_score, "max": 4, "detail": disp_label},
            "order_block": {"score": ob_score, "max": 4, "detail": ob_label},
            "premium_discount_ote": {"score": pd_score, "max": 4, "detail": pd_label},
            "session_killzone": {"score": sess_score, "max": 2, "detail": sess_label},
        },
        "confidence": confidence,
        "signals": all_signals,
    }


class StructureEngine:
    """Wrapper class adapting score_structure() to the SignalEngine protocol."""

    def __init__(self, settings=None):
        self.settings = settings

    def score(self, market_data: dict, direction: str = "long") -> dict:
        tf_data = market_data.get("timeframe_data", {})
        df = None
        for tf in ["15M", "1H"]:
            candidate = tf_data.get(tf)
            if candidate is not None and not candidate.empty:
                # Limit to last 100 bars for performance
                df = candidate.tail(100).reset_index(drop=True)
                break
        htf_df = None
        for tf in (["1H", "4H"] if "15M" in tf_data else ["4H", "1D"]):
            candidate = tf_data.get(tf)
            if candidate is not None and not candidate.empty:
                htf_df = candidate.tail(60).reset_index(drop=True)
                break
        if df is None or len(df) < 10:
            return {"score": 0, "signals": [], "confidence": 0.0, "components": {}}
        result = score_structure(df, direction, htf_df=htf_df)

        # Scale 0-30 raw → 0-100 normalised for the scoring engine.
        # Use 100/30 = 3.33x scaling (linear). With weight rebalancing
        # in the scoring engine, the structure engine doesn't need
        # artificial boosting — it just needs honest scoring.
        result["score"] = min(100.0, float(result["score"]) * (100.0 / 30.0))
        return result
