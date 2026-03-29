"""
flow_engine.py — Order Flow Scoring Engine for Lumare MIE

Dual-mode engine: crypto vs equities.

**Crypto Mode (0-20):**
  1. Funding Rate Delta (0-10 pts)
  2. Open Interest Delta (0-10 pts)

**Equities Mode (0-20):**
  1. Options Flow Imbalance (0-8 pts)
  2. Congressional Trade Clusters (0-6 pts)
  3. Insider Transaction Clusters (0-6 pts)

All calculations use only historical data (no lookahead bias).
Accepts pandas DataFrames / dicts, returns standardized score dict.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ===========================================================================
# CRYPTO MODE
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper: Funding Rate Classification
# ---------------------------------------------------------------------------

def classify_funding_rate(rate: float) -> str:
    """
    Classify funding rate into regimes.

    Typical perpetual swap funding rates (8-hour):
        Extreme negative:  < -0.03%   (shorts paying heavily)
        Moderate negative: -0.03% to -0.01%
        Neutral:           -0.01% to  0.01%
        Moderate positive:  0.01% to  0.03%
        Extreme positive:  > 0.03%    (longs paying heavily)
    """
    if rate < -0.0003:
        return "extreme_negative"
    if rate < -0.0001:
        return "moderate_negative"
    if rate <= 0.0001:
        return "neutral"
    if rate <= 0.0003:
        return "moderate_positive"
    return "extreme_positive"


# ---------------------------------------------------------------------------
# Component: Funding Rate Delta (0-10 pts) — Crypto
# ---------------------------------------------------------------------------

def score_funding_rate(
    funding_rate: float,
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    Score based on funding rate as a contrarian / confirmation signal.

    For LONGS:
        Extreme negative funding = 10 pts
            (shorts are crowded and paying; potential short squeeze)
        Moderate negative        = 6 pts
        Neutral                  = 3 pts
        Moderate positive        = 1 pt
            (longs paying; crowded long, less favorable)
        Extreme positive         = 0 pts
            (very crowded longs; contrarian short signal)

    For SHORTS: scoring is inverted.

    Formula:
        regime = classify_funding_rate(rate)
        score  = lookup[direction][regime]
    """
    signals: List[str] = []
    regime = classify_funding_rate(funding_rate)

    long_scores = {
        "extreme_negative": 10,
        "moderate_negative": 6,
        "neutral": 3,
        "moderate_positive": 1,
        "extreme_positive": 0,
    }

    short_scores = {
        "extreme_positive": 10,
        "moderate_positive": 6,
        "neutral": 3,
        "moderate_negative": 1,
        "extreme_negative": 0,
    }

    lookup = long_scores if direction == "long" else short_scores
    score = lookup[regime]

    if score >= 6:
        signals.append(f"funding_{regime}_favorable_{direction}")
    elif score <= 1:
        signals.append(f"funding_{regime}_unfavorable_{direction}")

    label = f"funding_{regime}_{funding_rate:.6f}"
    return score, label, signals


# ---------------------------------------------------------------------------
# Component: Open Interest Delta (0-10 pts) — Crypto
# ---------------------------------------------------------------------------

def score_open_interest(
    oi_df: pd.DataFrame,
    price_df: pd.DataFrame,
    direction: str = "long",
    lookback: int = 10,
) -> Tuple[int, str, List[str]]:
    """
    Score based on open interest changes relative to price movement.

    Requires:
        oi_df    — DataFrame with column 'open_interest' (absolute value)
        price_df — DataFrame with column 'close'

    Analysis over the last *lookback* bars:
        OI change  = (OI[-1] - OI[-lookback]) / OI[-lookback]
        Price change = (close[-1] - close[-lookback]) / close[-lookback]

    For LONGS:
        Rising OI + rising price  = 10 pts (new money entering, bullish conviction)
        Rising OI + falling price =  6 pts (short buildup — potential squeeze)
        Falling OI                =  3 pts (positions closing, less conviction)

    For SHORTS:
        Rising OI + falling price = 10 pts (new money entering, bearish conviction)
        Rising OI + rising price  =  6 pts (long buildup — potential long squeeze)
        Falling OI                =  3 pts (positions closing)
    """
    signals: List[str] = []

    if len(oi_df) < lookback or len(price_df) < lookback:
        return 0, "oi_insufficient_data", signals

    oi_start = oi_df["open_interest"].iloc[-lookback]
    oi_end = oi_df["open_interest"].iloc[-1]
    price_start = price_df["close"].iloc[-lookback]
    price_end = price_df["close"].iloc[-1]

    if oi_start == 0 or price_start == 0:
        return 0, "oi_zero_base", signals

    oi_change = (oi_end - oi_start) / oi_start
    price_change = (price_end - price_start) / price_start

    oi_rising = oi_change > 0.01   # > 1% increase
    price_rising = price_change > 0

    if direction == "long":
        if oi_rising and price_rising:
            signals.append("oi_rising_price_rising_bullish")
            return 10, f"oi_conviction_long_oi{oi_change:.2%}_p{price_change:.2%}", signals
        if oi_rising and not price_rising:
            signals.append("oi_rising_price_falling_short_buildup")
            return 6, f"oi_short_buildup_oi{oi_change:.2%}_p{price_change:.2%}", signals
        signals.append("oi_declining_positions_closing")
        return 3, f"oi_closing_oi{oi_change:.2%}", signals

    else:  # short
        if oi_rising and not price_rising:
            signals.append("oi_rising_price_falling_bearish")
            return 10, f"oi_conviction_short_oi{oi_change:.2%}_p{price_change:.2%}", signals
        if oi_rising and price_rising:
            signals.append("oi_rising_price_rising_long_buildup")
            return 6, f"oi_long_buildup_oi{oi_change:.2%}_p{price_change:.2%}", signals
        signals.append("oi_declining_positions_closing")
        return 3, f"oi_closing_oi{oi_change:.2%}", signals


# ---------------------------------------------------------------------------
# Crypto Mode Composite
# ---------------------------------------------------------------------------

def score_flow_crypto(
    funding_rate: float,
    oi_df: pd.DataFrame,
    price_df: pd.DataFrame,
    direction: str = "long",
) -> Dict:
    """
    Composite crypto flow score (0-20).

    Parameters
    ----------
    funding_rate : float
        Current funding rate (e.g., 0.0001 = 0.01%).
    oi_df : pd.DataFrame
        Open interest data with column 'open_interest'.
    price_df : pd.DataFrame
        Price data with column 'close'.
    direction : str
        "long" or "short".
    """
    fr_score, fr_label, fr_signals = score_funding_rate(funding_rate, direction)
    oi_score, oi_label, oi_signals = score_open_interest(oi_df, price_df, direction)

    total = fr_score + oi_score

    # Confidence: both components confirming yields higher confidence
    both_high = fr_score >= 6 and oi_score >= 6
    confidence = round(min(1.0, (total / 20) * (1.0 if both_high else 0.8)), 3)

    return {
        "score": total,
        "components": {
            "funding_rate": {"score": fr_score, "max": 10, "detail": fr_label},
            "open_interest": {"score": oi_score, "max": 10, "detail": oi_label},
        },
        "confidence": confidence,
        "signals": fr_signals + oi_signals,
    }


# ===========================================================================
# EQUITIES MODE
# ===========================================================================

# ---------------------------------------------------------------------------
# Component: Options Flow Imbalance (0-8 pts) — Equities
# ---------------------------------------------------------------------------

def score_options_flow(
    options_data: Dict[str, Any],
    direction: str = "long",
) -> Tuple[int, str, List[str]]:
    """
    Score based on options market flow imbalance.

    Expected keys in options_data:
        call_volume       : int   — total call option volume
        put_volume        : int   — total put option volume
        call_sweep_count  : int   — aggressive call sweeps detected
        put_sweep_count   : int   — aggressive put sweeps detected
        unusual_premium   : float — total unusual premium (in $ millions)

    Formula:
        call_put_ratio = call_volume / put_volume
        sweep_imbalance = call_sweep_count - put_sweep_count  (for longs)

    Scoring (for longs):
        Strong call sweeps + unusual premium > $1M  = 8 pts
        Call/put ratio > 2.0 + sweeps               = 6 pts
        Moderate call bias (ratio > 1.5)             = 4 pts
        Neutral or put-heavy                         = 0 pts

    For shorts: scoring is inverted (put dominance is favorable).
    """
    signals: List[str] = []

    call_vol = options_data.get("call_volume", 0)
    put_vol = options_data.get("put_volume", 0)
    call_sweeps = options_data.get("call_sweep_count", 0)
    put_sweeps = options_data.get("put_sweep_count", 0)
    unusual_premium = options_data.get("unusual_premium", 0.0)

    total_vol = call_vol + put_vol
    if total_vol == 0:
        return 0, "no_options_volume", signals

    cp_ratio = call_vol / max(put_vol, 1)
    pc_ratio = put_vol / max(call_vol, 1)

    if direction == "long":
        dominant_sweeps = call_sweeps
        dominant_ratio = cp_ratio
        sweep_label = "call"
    else:
        dominant_sweeps = put_sweeps
        dominant_ratio = pc_ratio
        sweep_label = "put"

    # Strong: dominant sweeps + unusual premium
    if dominant_sweeps >= 3 and unusual_premium > 1.0:
        signals.append(f"strong_{sweep_label}_sweeps_unusual_premium")
        return 8, f"options_strong_{sweep_label}_{dominant_ratio:.2f}", signals

    # Good: high ratio + sweeps
    if dominant_ratio > 2.0 and dominant_sweeps >= 1:
        signals.append(f"{sweep_label}_ratio_with_sweeps")
        return 6, f"options_{sweep_label}_bias_{dominant_ratio:.2f}", signals

    # Moderate: decent ratio
    if dominant_ratio > 1.5:
        signals.append(f"moderate_{sweep_label}_bias")
        return 4, f"options_moderate_{sweep_label}_{dominant_ratio:.2f}", signals

    return 0, f"options_neutral_{cp_ratio:.2f}", signals


# ---------------------------------------------------------------------------
# Component: Congressional Trade Clusters (0-6 pts) — Equities
# ---------------------------------------------------------------------------

def score_congressional_trades(
    trades: List[Dict[str, Any]],
    ticker: str,
    window_days: int = 14,
) -> Tuple[int, str, List[str]]:
    """
    Score based on clustering of congressional trades.

    Expected trade dict keys:
        politician  : str  — name of the politician
        ticker      : str  — stock ticker
        trade_date  : str  — ISO date string (YYYY-MM-DD)
        trade_type  : str  — "buy" or "sell"

    Algorithm:
        1. Filter trades for the target ticker within the last *window_days*.
        2. Count unique politicians trading in the same direction.

    Scoring:
        3+ unique politicians buying within window  = 6 pts
        2 unique politicians                        = 3 pts
        1 or fewer                                  = 0 pts
    """
    signals: List[str] = []

    if not trades:
        return 0, "no_congressional_data", signals

    # Filter for target ticker
    ticker_upper = ticker.upper()
    relevant = [
        t for t in trades
        if t.get("ticker", "").upper() == ticker_upper
    ]

    if not relevant:
        return 0, f"no_trades_for_{ticker}", signals

    # Parse dates and filter by window
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=window_days)
    recent = []
    for t in relevant:
        try:
            trade_date = pd.Timestamp(t["trade_date"])
            if trade_date >= cutoff:
                recent.append(t)
        except (ValueError, KeyError):
            continue

    # Count unique politicians buying
    buyers = set()
    sellers = set()
    for t in recent:
        politician = t.get("politician", "unknown")
        if t.get("trade_type", "").lower() == "buy":
            buyers.add(politician)
        elif t.get("trade_type", "").lower() == "sell":
            sellers.add(politician)

    n_buyers = len(buyers)
    n_sellers = len(sellers)

    # Score based on buy clusters (primary signal for longs)
    if n_buyers >= 3:
        signals.append(f"congressional_cluster_{n_buyers}_buyers")
        return 6, f"congress_{n_buyers}_buyers_{window_days}d", signals
    if n_buyers >= 2:
        signals.append(f"congressional_pair_{n_buyers}_buyers")
        return 3, f"congress_{n_buyers}_buyers_{window_days}d", signals

    # Also check sell clusters for shorts
    if n_sellers >= 3:
        signals.append(f"congressional_cluster_{n_sellers}_sellers")
        return 6, f"congress_{n_sellers}_sellers_{window_days}d", signals
    if n_sellers >= 2:
        signals.append(f"congressional_pair_{n_sellers}_sellers")
        return 3, f"congress_{n_sellers}_sellers_{window_days}d", signals

    return 0, "no_congressional_cluster", signals


# ---------------------------------------------------------------------------
# Component: Insider Transaction Clusters (0-6 pts) — Equities
# ---------------------------------------------------------------------------

def score_insider_transactions(
    transactions: List[Dict[str, Any]],
    ticker: str,
    window_days: int = 30,
    significant_threshold: float = 100_000.0,
) -> Tuple[int, str, List[str]]:
    """
    Score based on SEC Form 4 insider transaction clustering.

    Expected transaction dict keys:
        insider     : str   — insider name
        ticker      : str   — stock ticker
        trade_date  : str   — ISO date string
        trade_type  : str   — "buy" or "sell"
        value       : float — dollar value of transaction

    Scoring:
        3+ insiders buying within window (Form 4 cluster) = 6 pts
        1-2 insiders with significant buy (> $100k)       = 3 pts
        No significant insider buys                        = 0 pts
    """
    signals: List[str] = []

    if not transactions:
        return 0, "no_insider_data", signals

    ticker_upper = ticker.upper()
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=window_days)

    recent_buys: List[Dict] = []
    for t in transactions:
        if t.get("ticker", "").upper() != ticker_upper:
            continue
        if t.get("trade_type", "").lower() != "buy":
            continue
        try:
            trade_date = pd.Timestamp(t["trade_date"])
            if trade_date >= cutoff:
                recent_buys.append(t)
        except (ValueError, KeyError):
            continue

    # Count unique insiders
    unique_insiders = set(t.get("insider", "unknown") for t in recent_buys)
    n_insiders = len(unique_insiders)

    # Check for significant buys
    total_value = sum(t.get("value", 0) for t in recent_buys)
    has_significant = any(
        t.get("value", 0) >= significant_threshold for t in recent_buys
    )

    if n_insiders >= 3:
        signals.append(f"insider_cluster_{n_insiders}_buyers_${total_value:,.0f}")
        return 6, f"insider_{n_insiders}_buys_${total_value:,.0f}", signals

    if n_insiders >= 1 and has_significant:
        signals.append(f"insider_significant_buy_${total_value:,.0f}")
        return 3, f"insider_{n_insiders}_sig_buy_${total_value:,.0f}", signals

    return 0, "no_insider_cluster", signals


# ---------------------------------------------------------------------------
# Equities Mode Composite
# ---------------------------------------------------------------------------

def score_flow_equities(
    options_data: Dict[str, Any],
    congressional_trades: List[Dict[str, Any]],
    insider_transactions: List[Dict[str, Any]],
    ticker: str,
    direction: str = "long",
) -> Dict:
    """
    Composite equities flow score (0-20).

    Parameters
    ----------
    options_data : dict
        Options flow data (call/put volumes, sweeps, unusual premium).
    congressional_trades : list of dict
        Congressional disclosure data.
    insider_transactions : list of dict
        SEC Form 4 insider transactions.
    ticker : str
        Stock ticker symbol.
    direction : str
        "long" or "short".
    """
    opt_score, opt_label, opt_signals = score_options_flow(options_data, direction)
    cong_score, cong_label, cong_signals = score_congressional_trades(
        congressional_trades, ticker
    )
    ins_score, ins_label, ins_signals = score_insider_transactions(
        insider_transactions, ticker
    )

    total = opt_score + cong_score + ins_score

    # Confidence
    components_active = sum([opt_score > 0, cong_score > 0, ins_score > 0])
    confidence_map = {0: 0.2, 1: 0.5, 2: 0.75, 3: 1.0}
    confidence = round(
        min(1.0, (total / 20) * confidence_map.get(components_active, 0.2)), 3
    )

    return {
        "score": total,
        "components": {
            "options_flow": {"score": opt_score, "max": 8, "detail": opt_label},
            "congressional_trades": {"score": cong_score, "max": 6, "detail": cong_label},
            "insider_transactions": {"score": ins_score, "max": 6, "detail": ins_label},
        },
        "confidence": confidence,
        "signals": opt_signals + cong_signals + ins_signals,
    }


# ===========================================================================
# UNIFIED ENTRY POINT
# ===========================================================================

def score_flow(
    mode: str = "crypto",
    direction: str = "long",
    # Crypto params
    funding_rate: Optional[float] = None,
    oi_df: Optional[pd.DataFrame] = None,
    price_df: Optional[pd.DataFrame] = None,
    # Equities params
    options_data: Optional[Dict[str, Any]] = None,
    congressional_trades: Optional[List[Dict[str, Any]]] = None,
    insider_transactions: Optional[List[Dict[str, Any]]] = None,
    ticker: Optional[str] = None,
) -> Dict:
    """
    Unified flow scoring entry point.

    Parameters
    ----------
    mode : str
        "crypto" or "equities".
    direction : str
        "long" or "short".

    Crypto-specific:
        funding_rate : float
        oi_df        : DataFrame with 'open_interest' column
        price_df     : DataFrame with 'close' column

    Equities-specific:
        options_data          : dict
        congressional_trades  : list of dicts
        insider_transactions  : list of dicts
        ticker               : str

    Returns
    -------
    dict with keys: score, components, confidence, signals.
    """
    if mode == "crypto":
        if funding_rate is None or oi_df is None or price_df is None:
            return {
                "score": 0,
                "components": {},
                "confidence": 0.0,
                "signals": ["missing_crypto_flow_data"],
            }
        return score_flow_crypto(funding_rate, oi_df, price_df, direction)

    elif mode == "equities":
        if options_data is None:
            options_data = {}
        if congressional_trades is None:
            congressional_trades = []
        if insider_transactions is None:
            insider_transactions = []
        if ticker is None:
            return {
                "score": 0,
                "components": {},
                "confidence": 0.0,
                "signals": ["missing_ticker_for_equities_flow"],
            }
        return score_flow_equities(
            options_data, congressional_trades, insider_transactions, ticker, direction
        )

    else:
        return {
            "score": 0,
            "components": {},
            "confidence": 0.0,
            "signals": [f"unknown_flow_mode_{mode}"],
        }


class FlowEngine:
    """Wrapper class adapting score_flow() to the SignalEngine protocol."""

    def __init__(self, settings=None):
        self.settings = settings

    def score(self, market_data: dict, direction: str = "long") -> dict:
        tf_data = market_data.get("timeframe_data", {})
        price_df = None
        for tf in ["1H", "4H"]:
            candidate = tf_data.get(tf)
            if candidate is not None and not candidate.empty:
                price_df = candidate
                break
        funding_rate = market_data.get("funding_rate")
        oi_df = market_data.get("oi_df")
        # When flow data is unavailable (backtest without live feeds), return
        # neutral 50 rather than 0 — absence of data is not a bearish signal.
        if funding_rate is None or oi_df is None:
            return {"score": 50.0, "signals": ["flow_data_unavailable_neutral"], "confidence": 0.3, "components": {}}
        result = score_flow(
            mode="crypto",
            direction=direction,
            funding_rate=funding_rate,
            oi_df=oi_df,
            price_df=price_df,
        )
        result["score"] = min(100.0, float(result["score"]) * 5.0)  # scale 0-20 → 0-100
        return result
