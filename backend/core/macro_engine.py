"""
macro_engine.py — Macro Environment Scoring Engine for Lumare MIE

Scores 0-20 based on macro conditions:
  1. Volatility Percentile (0-7 pts)
  2. Liquidity Expansion/Contraction (0-7 pts)
  3. Risk-On Confirmation (0-6 pts)

All calculations use only historical data (no lookahead bias).
Accepts pandas DataFrames / dicts, returns standardized score dict.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helper: Realized Volatility
# ---------------------------------------------------------------------------

def calc_realized_vol(
    close: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Annualized realized volatility from log returns.

    Formula:
        log_ret = ln(close_t / close_{t-1})
        realized_vol = std(log_ret, window) * sqrt(252)

    252 = approximate trading days per year.
    """
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


def calc_vol_percentile(
    close: pd.Series,
    current_window: int = 20,
    lookback_days: int = 252,
) -> float:
    """
    Percentile rank of current realized volatility over the past year.

    Formula:
        rv_series = realized_vol over rolling *current_window*
        percentile = rank of rv_series[-1] within rv_series[-lookback_days:]

    Returns float in [0, 100].
    """
    rv = calc_realized_vol(close, current_window)

    if len(rv.dropna()) < lookback_days:
        # Use whatever history we have
        history = rv.dropna()
    else:
        history = rv.iloc[-lookback_days:]

    current_rv = rv.iloc[-1]
    if np.isnan(current_rv) or len(history) == 0:
        return 50.0  # default neutral

    percentile = (history < current_rv).sum() / len(history) * 100.0
    return percentile


# ---------------------------------------------------------------------------
# Helper: Liquidity Index Composite
# ---------------------------------------------------------------------------

def calc_liquidity_index(
    m2_growth: pd.Series,
    reverse_repo: pd.Series,
    fed_balance_sheet: pd.Series,
    weights: Optional[Dict[str, float]] = None,
) -> pd.Series:
    """
    Composite Liquidity Index combining three macro liquidity indicators.

    Formula:
        LIQ_t = w_m2 * norm(M2_growth_t)
              + w_rrp * norm(-ReverseRepo_change_t)   [negative = draining]
              + w_fed * norm(FedBS_change_t)

    Where:
        norm(x) = (x - mean(x)) / std(x)   (z-score normalisation)
        w_m2    = 0.40  (M2 money supply growth is the dominant driver)
        w_rrp   = 0.30  (reverse repo changes drain/add reserves)
        w_fed   = 0.30  (Fed balance sheet expansion/contraction)

    The reverse repo term is negated because rising RRP drains liquidity.

    Parameters
    ----------
    m2_growth : pd.Series
        Year-over-year M2 money supply growth rate (e.g., 0.05 = 5%).
    reverse_repo : pd.Series
        Reverse repo facility balance (absolute $ value).
    fed_balance_sheet : pd.Series
        Federal Reserve total assets (absolute $ value).
    weights : dict, optional
        Override default weights {"m2": 0.4, "rrp": 0.3, "fed": 0.3}.

    Returns
    -------
    pd.Series
        Composite liquidity index (z-score based, mean ~0).
    """
    if weights is None:
        weights = {"m2": 0.40, "rrp": 0.30, "fed": 0.30}

    def zscore(s: pd.Series) -> pd.Series:
        mean = s.expanding().mean()
        std = s.expanding().std().replace(0, np.nan)
        return (s - mean) / std

    # M2 growth — already a rate, just z-score it
    m2_z = zscore(m2_growth)

    # Reverse repo — compute change, negate (rising RRP = liquidity drain)
    rrp_change = reverse_repo.pct_change()
    rrp_z = zscore(-rrp_change)  # negative because rising RRP drains liquidity

    # Fed balance sheet — compute change
    fed_change = fed_balance_sheet.pct_change()
    fed_z = zscore(fed_change)

    composite = (
        weights["m2"] * m2_z.fillna(0)
        + weights["rrp"] * rrp_z.fillna(0)
        + weights["fed"] * fed_z.fillna(0)
    )

    return composite


# ---------------------------------------------------------------------------
# Component 1: Volatility Percentile (0-7 pts)
# ---------------------------------------------------------------------------

def score_volatility(
    close: pd.Series,
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    Realized volatility percentile scoring.

    For LONGS (prefer calm markets):
        vol_pct <  25  =>  7 pts  (low vol = favorable for longs)
        vol_pct <  50  =>  5 pts
        vol_pct <  75  =>  3 pts
        vol_pct >= 75  =>  2 pts  (high vol = unfavorable for longs)
        vol_pct >= 95  =>  0 pts  + CHAOTIC warning

    For SHORTS (prefer volatile markets):
        vol_pct >= 75  =>  7 pts  (high vol = favorable for shorts)
        vol_pct >= 50  =>  5 pts
        vol_pct >= 25  =>  3 pts
        vol_pct <  25  =>  2 pts
        vol_pct <   5  =>  0 pts  + COMPRESSED warning
    """
    signals: List[str] = []
    vol_pct = calc_vol_percentile(close)

    if direction == "long":
        if vol_pct >= 95:
            signals.append("CHAOTIC_volatility_extreme")
            return 0, f"vol_chaotic_{vol_pct:.1f}pct", signals
        if vol_pct >= 75:
            signals.append("high_volatility_unfavorable_longs")
            return 2, f"vol_high_{vol_pct:.1f}pct", signals
        if vol_pct >= 50:
            return 3, f"vol_moderate_{vol_pct:.1f}pct", signals
        if vol_pct >= 25:
            signals.append("low_volatility_favorable_longs")
            return 5, f"vol_low_{vol_pct:.1f}pct", signals
        signals.append("very_low_volatility_favorable_longs")
        return 7, f"vol_very_low_{vol_pct:.1f}pct", signals

    else:  # short
        if vol_pct < 5:
            signals.append("COMPRESSED_volatility_extreme")
            return 0, f"vol_compressed_{vol_pct:.1f}pct", signals
        if vol_pct < 25:
            signals.append("low_volatility_unfavorable_shorts")
            return 2, f"vol_low_{vol_pct:.1f}pct", signals
        if vol_pct < 50:
            return 3, f"vol_moderate_{vol_pct:.1f}pct", signals
        if vol_pct < 75:
            signals.append("elevated_volatility_favorable_shorts")
            return 5, f"vol_elevated_{vol_pct:.1f}pct", signals
        signals.append("high_volatility_favorable_shorts")
        return 7, f"vol_high_{vol_pct:.1f}pct", signals


# ---------------------------------------------------------------------------
# Component 2: Liquidity Expansion / Contraction (0-7 pts)
# ---------------------------------------------------------------------------

def score_liquidity(
    m2_growth: Optional[pd.Series] = None,
    reverse_repo: Optional[pd.Series] = None,
    fed_balance_sheet: Optional[pd.Series] = None,
    liquidity_index: Optional[pd.Series] = None,
) -> Tuple[int, str, List[str]]:
    """
    Liquidity environment scoring.

    If a pre-computed liquidity_index is provided, use it directly.
    Otherwise compute from the three component series.

    Scoring based on the latest liquidity index value (z-score):
        liq >  1.0  =>  7 pts  (strongly expanding — risk on)
        liq >  0.3  =>  5 pts  (expanding)
        liq > -0.3  =>  3 pts  (neutral)
        liq > -1.0  =>  2 pts  (contracting)
        liq <= -1.0 =>  0 pts  (rapidly contracting — risk off)
    """
    signals: List[str] = []

    if liquidity_index is not None:
        liq = liquidity_index
    elif m2_growth is not None and reverse_repo is not None and fed_balance_sheet is not None:
        liq = calc_liquidity_index(m2_growth, reverse_repo, fed_balance_sheet)
    else:
        return 0, "liquidity_insufficient_data", ["missing_liquidity_inputs"]

    current_liq = liq.iloc[-1]
    if np.isnan(current_liq):
        return 0, "liquidity_nan", signals

    if current_liq > 1.0:
        signals.append("liquidity_strongly_expanding")
        return 7, f"liq_expanding_{current_liq:.2f}", signals
    if current_liq > 0.3:
        signals.append("liquidity_expanding")
        return 5, f"liq_expanding_{current_liq:.2f}", signals
    if current_liq > -0.3:
        return 3, f"liq_neutral_{current_liq:.2f}", signals
    if current_liq > -1.0:
        signals.append("liquidity_contracting")
        return 2, f"liq_contracting_{current_liq:.2f}", signals

    signals.append("liquidity_rapidly_contracting")
    return 0, f"liq_rapid_contraction_{current_liq:.2f}", signals


# ---------------------------------------------------------------------------
# Component 3: Risk-On Confirmation (0-6 pts)
# ---------------------------------------------------------------------------

def score_risk_on(
    risk_data: Dict[str, Any],
) -> Tuple[int, str, List[str]]:
    """
    Composite risk-on / risk-off assessment.

    Expected keys in risk_data:
        credit_spread_compression : bool
            True if investment-grade credit spreads are tightening
            (= risk appetite increasing).

        breadth_improving : bool
            True if market breadth is expanding (advance/decline improving,
            % stocks above 200 MA rising).

        cyclical_rotation : bool
            True if sector rotation shows money moving into cyclicals
            (XLY/XLP ratio rising, XLF outperforming).

    Scoring:
        All 3 confirming risk-on  = 6 pts
        2 confirming              = 4 pts
        1 confirming              = 2 pts
        None                      = 0 pts
    """
    signals: List[str] = []

    credit = risk_data.get("credit_spread_compression", False)
    breadth = risk_data.get("breadth_improving", False)
    cyclical = risk_data.get("cyclical_rotation", False)

    confirming = sum([credit, breadth, cyclical])

    if credit:
        signals.append("credit_spreads_compressing")
    if breadth:
        signals.append("market_breadth_improving")
    if cyclical:
        signals.append("cyclical_sector_rotation")

    score_map = {0: 0, 1: 2, 2: 4, 3: 6}
    score = score_map[confirming]

    label = f"risk_on_{confirming}_of_3"
    return score, label, signals


# ---------------------------------------------------------------------------
# Helper: Credit Spread Analysis
# ---------------------------------------------------------------------------

def calc_credit_spread_trend(
    ig_spread: pd.Series,
    lookback: int = 20,
) -> bool:
    """
    Determine if investment-grade credit spreads are compressing.

    Formula:
        spread_change = ig_spread[-1] - ig_spread[-lookback]
        compressing = spread_change < 0

    Also checks that the trend is consistent (linear regression slope < 0).

    Parameters
    ----------
    ig_spread : pd.Series
        Investment-grade credit spread (e.g., ICE BofA IG OAS).

    Returns
    -------
    bool — True if spreads are compressing (risk-on).
    """
    if len(ig_spread) < lookback:
        return False

    recent = ig_spread.iloc[-lookback:]
    spread_change = recent.iloc[-1] - recent.iloc[0]

    # Also compute slope via simple regression
    x = np.arange(len(recent), dtype=float)
    y = recent.values.astype(float)
    valid = ~np.isnan(y)
    if valid.sum() < 5:
        return False

    slope = np.polyfit(x[valid], y[valid], 1)[0]
    return slope < 0 and spread_change < 0


# ---------------------------------------------------------------------------
# Helper: Market Breadth Analysis
# ---------------------------------------------------------------------------

def calc_breadth_trend(
    pct_above_200ma: pd.Series,
    lookback: int = 10,
) -> bool:
    """
    Determine if market breadth is improving.

    Formula:
        breadth_change = pct_above_200ma[-1] - pct_above_200ma[-lookback]
        improving = breadth_change > 0 and current > 50%

    Parameters
    ----------
    pct_above_200ma : pd.Series
        Percentage of index constituents trading above their 200-day MA.

    Returns
    -------
    bool — True if breadth is improving (risk-on).
    """
    if len(pct_above_200ma) < lookback:
        return False

    current = pct_above_200ma.iloc[-1]
    past = pct_above_200ma.iloc[-lookback]

    if np.isnan(current) or np.isnan(past):
        return False

    return current > past and current > 50.0


# ---------------------------------------------------------------------------
# Helper: Sector Rotation Analysis
# ---------------------------------------------------------------------------

def calc_cyclical_rotation(
    cyclical_series: pd.Series,
    defensive_series: pd.Series,
    lookback: int = 20,
) -> bool:
    """
    Detect rotation into cyclical sectors vs defensive sectors.

    Formula:
        ratio = cyclical / defensive  (e.g., XLY / XLP)
        ratio_change = ratio[-1] / ratio[-lookback] - 1
        rotating_in = ratio_change > 0.02  (>2% improvement)

    Parameters
    ----------
    cyclical_series : pd.Series
        Cyclical sector ETF price (e.g., XLY — Consumer Discretionary).
    defensive_series : pd.Series
        Defensive sector ETF price (e.g., XLP — Consumer Staples).

    Returns
    -------
    bool — True if cyclicals outperforming defensives (risk-on).
    """
    if len(cyclical_series) < lookback or len(defensive_series) < lookback:
        return False

    ratio = cyclical_series / defensive_series.replace(0, np.nan)
    current_ratio = ratio.iloc[-1]
    past_ratio = ratio.iloc[-lookback]

    if np.isnan(current_ratio) or np.isnan(past_ratio) or past_ratio == 0:
        return False

    ratio_change = current_ratio / past_ratio - 1.0
    return ratio_change > 0.02


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def score_macro(
    close: pd.Series,
    direction: str = "long",
    # Liquidity inputs (provide either composite or components)
    liquidity_index: Optional[pd.Series] = None,
    m2_growth: Optional[pd.Series] = None,
    reverse_repo: Optional[pd.Series] = None,
    fed_balance_sheet: Optional[pd.Series] = None,
    # Risk-on inputs (provide either pre-computed dict or raw series)
    risk_data: Optional[Dict[str, Any]] = None,
    ig_spread: Optional[pd.Series] = None,
    pct_above_200ma: Optional[pd.Series] = None,
    cyclical_series: Optional[pd.Series] = None,
    defensive_series: Optional[pd.Series] = None,
) -> Dict:
    """
    Compute the composite Macro Score (0-20).

    Parameters
    ----------
    close : pd.Series
        Asset close prices for volatility calculation (>= 252 rows ideal).
    direction : str
        "long" or "short".
    liquidity_index : pd.Series, optional
        Pre-computed liquidity composite.
    m2_growth, reverse_repo, fed_balance_sheet : pd.Series, optional
        Raw liquidity component series (used if liquidity_index not provided).
    risk_data : dict, optional
        Pre-computed risk-on flags. If not provided, will attempt to compute
        from ig_spread, pct_above_200ma, cyclical_series, defensive_series.
    ig_spread : pd.Series, optional
    pct_above_200ma : pd.Series, optional
    cyclical_series : pd.Series, optional
    defensive_series : pd.Series, optional

    Returns
    -------
    dict with keys: score, components, confidence, signals.
    """
    min_rows = 30
    if len(close) < min_rows:
        return {
            "score": 0,
            "components": {},
            "confidence": 0.0,
            "signals": ["insufficient_price_data_for_macro"],
        }

    # --- Component 1: Volatility ---
    vol_score, vol_label, vol_signals = score_volatility(close, direction)

    # --- Component 2: Liquidity ---
    has_liquidity_data = (
        liquidity_index is not None
        or (m2_growth is not None and reverse_repo is not None and fed_balance_sheet is not None)
    )
    if has_liquidity_data:
        liq_score, liq_label, liq_signals = score_liquidity(
            m2_growth=m2_growth,
            reverse_repo=reverse_repo,
            fed_balance_sheet=fed_balance_sheet,
            liquidity_index=liquidity_index,
        )
    else:
        # No FRED data (backtest mode) — neutral, not penalising
        liq_score = 3
        liq_label = "liquidity_neutral_no_data"
        liq_signals = ["liquidity_data_unavailable_neutral"]

    # --- Component 3: Risk-On ---
    if risk_data is None:
        # Attempt to build risk_data from raw series
        risk_data = {}
        if ig_spread is not None:
            risk_data["credit_spread_compression"] = calc_credit_spread_trend(ig_spread)
        if pct_above_200ma is not None:
            risk_data["breadth_improving"] = calc_breadth_trend(pct_above_200ma)
        if cyclical_series is not None and defensive_series is not None:
            risk_data["cyclical_rotation"] = calc_cyclical_rotation(
                cyclical_series, defensive_series
            )

    has_risk_data = bool(risk_data)
    if has_risk_data:
        risk_score, risk_label, risk_signals = score_risk_on(risk_data)
    else:
        # No risk-on data (backtest mode) — neutral
        risk_score = 3
        risk_label = "risk_on_neutral_no_data"
        risk_signals = ["risk_data_unavailable_neutral"]

    total = vol_score + liq_score + risk_score

    # --- Confidence ---
    max_score = 20
    raw_confidence = total / max_score

    # Macro signals are inherently lower-frequency; weight agreement
    components_active = sum([vol_score >= 3, liq_score >= 3, risk_score >= 2])
    agreement_map = {0: 0.4, 1: 0.6, 2: 0.8, 3: 1.0}
    agreement_factor = agreement_map.get(components_active, 0.4)

    confidence = round(min(1.0, raw_confidence * agreement_factor), 3)

    # --- CHAOTIC override ---
    chaotic = any("CHAOTIC" in s for s in vol_signals)
    if chaotic:
        confidence = min(confidence, 0.3)

    # --- Collect signals ---
    all_signals = vol_signals + liq_signals + risk_signals

    return {
        "score": total,
        "components": {
            "volatility_percentile": {"score": vol_score, "max": 7, "detail": vol_label},
            "liquidity": {"score": liq_score, "max": 7, "detail": liq_label},
            "risk_on": {"score": risk_score, "max": 6, "detail": risk_label},
        },
        "confidence": confidence,
        "signals": all_signals,
    }


class MacroEngine:
    """Wrapper class adapting score_macro() to the SignalEngine protocol."""

    def __init__(self, settings=None):
        self.settings = settings

    def score(self, market_data: dict, direction: str = "long") -> dict:
        tf_data = market_data.get("timeframe_data", {})
        df = None
        for tf in ["1D", "4H", "1H"]:
            candidate = tf_data.get(tf)
            if candidate is not None and not candidate.empty:
                df = candidate
                break
        if df is None or len(df) < 10:
            # No macro data available (e.g. backtest without FRED feed) — neutral, not bearish
            return {"score": 50.0, "signals": ["macro_data_unavailable_neutral"], "confidence": 0.3, "components": {}}
        close = df["close"].astype(float) if "close" in df.columns else pd.Series(dtype=float)
        result = score_macro(close=close, direction=direction)
        result["score"] = min(100.0, float(result["score"]) * 5.0)  # scale 0-20 → 0-100
        return result
