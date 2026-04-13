"""
Strategy registry — pure functions that turn an OHLCV DataFrame into a
signal dict (or None).

Kept dependency-free on purpose: this module is the one place where
trading logic lives. Both SignalAgent (live) and ReplayDataAgent (backtest)
call into here, and unit tests can call it directly with synthetic bars.

A strategy function takes:
    df: pd.DataFrame with at least columns close, high, low (any extras OK)
    symbol: str

and returns either:
    None — no signal this bar
    dict — {symbol, direction, strategy, score, price, reason, rsi, timestamp}

`compute_signal` runs the price-based ensemble. `compute_macro_signal` is a
separate entry point that turns the *current macro regime* (as published by
MacroAgent into bot_state["macro_state"]) into a tradeable bias signal —
strong bullish/risk-off readings translate to long/short biases on broad
index ETFs. SignalAgent calls both and lets the ensemble pick the highest
scorer.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


def compute_signal(df: pd.DataFrame, symbol: str) -> Optional[dict]:
    """
    Run the standard ensemble (momentum + trend + breakout + mean-rev) on
    a real OHLCV DataFrame and return the highest-scoring signal, or None.

    Identical math to the legacy `router._compute_signal` — this file is
    where it lives going forward; the router function is now a thin wrapper
    that re-exports it for backwards compat.
    """
    if df is None or len(df) < 30:
        return None

    close = df["close"].astype(float)
    last = float(close.iloc[-1])

    # EMAs
    ema_fast = close.ewm(span=9, adjust=False).mean()
    ema_slow = close.ewm(span=21, adjust=False).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    # Donchian channel
    high20 = float(df["high"].astype(float).rolling(20).max().iloc[-2])
    low20 = float(df["low"].astype(float).rolling(20).min().iloc[-2])

    votes: list[tuple[str, str, float, str]] = []

    # Momentum — fast EMA above slow EMA + RSI confirmation
    if float(ema_fast.iloc[-1]) > float(ema_slow.iloc[-1]) and last_rsi > 52:
        crossed = float(ema_fast.iloc[-2]) <= float(ema_slow.iloc[-2])
        score = 70 + min(20, last_rsi - 50) + (10 if crossed else 0)
        votes.append(("momentum", "LONG", score,
                      f"EMA9>EMA21{' (cross)' if crossed else ''}, RSI={last_rsi:.1f}"))
    elif float(ema_fast.iloc[-1]) < float(ema_slow.iloc[-1]) and last_rsi < 48:
        crossed = float(ema_fast.iloc[-2]) >= float(ema_slow.iloc[-2])
        score = 70 + min(20, 50 - last_rsi) + (10 if crossed else 0)
        votes.append(("momentum", "SHORT", score,
                      f"EMA9<EMA21{' (cross)' if crossed else ''}, RSI={last_rsi:.1f}"))

    # Trend following — slow EMA slope
    ema_slope = (float(ema_slow.iloc[-1]) - float(ema_slow.iloc[-5])) / max(float(ema_slow.iloc[-5]), 1e-9) * 100
    if ema_slope > 0.3:
        votes.append(("trend_following", "LONG", 68 + min(15, ema_slope * 2),
                      f"EMA21 slope +{ema_slope:.2f}%"))
    elif ema_slope < -0.3:
        votes.append(("trend_following", "SHORT", 68 + min(15, -ema_slope * 2),
                      f"EMA21 slope {ema_slope:.2f}%"))

    # Breakout
    if last > high20:
        votes.append(("breakout", "LONG", 75.0,
                      f"Close {last:.2f} > 20-bar high {high20:.2f}"))
    elif last < low20:
        votes.append(("breakout", "SHORT", 75.0,
                      f"Close {last:.2f} < 20-bar low {low20:.2f}"))

    # Mean reversion
    if last_rsi < 30:
        votes.append(("mean_reversion", "LONG", 65.0,
                      f"RSI oversold at {last_rsi:.1f}"))
    elif last_rsi > 70:
        votes.append(("mean_reversion", "SHORT", 65.0,
                      f"RSI overbought at {last_rsi:.1f}"))

    if not votes:
        return None

    votes.sort(key=lambda v: v[2], reverse=True)
    strat, direction, score, reason = votes[0]

    return {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "direction": direction,
        "strategy": strat,
        "score": round(score, 2),
        "price": last,
        "reason": reason,
        "rsi": round(last_rsi, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Symbols that are *liquid index proxies* — the only places we want to act on
# pure macro-regime signals. Acting on macro for an individual stock would be
# noise; acting on it via SPY/QQQ/etc gives the bias clean expression.
_MACRO_TRADEABLE = {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO"}


def compute_macro_signal(
    df: pd.DataFrame,
    symbol: str,
    macro_state: Optional[dict],
) -> Optional[dict]:
    """
    Macro Compass strategy — translates the *current* macro regime (already
    derived by MacroAgent and stashed in bot_state["macro_state"]) into a
    directional bias trade on broad index ETFs.

    Why this is its own strategy and not a global multiplier:
      • The existing macro→strategy weight system in SignalAgent *dampens*
        other strategies during risk-off but never *initiates* a trade.
      • Pure regime trades (e.g. "VIX > 35, get short SPY") are a real edge
        in their own right and should compete in the ensemble on their own
        merits, not just trim other strategies.

    Rules (kept conservative — macro shifts slowly so signals shouldn't fire
    every bar):

      • Only fires for symbols in `_MACRO_TRADEABLE`.
      • risk_off  → SHORT bias on broad index, base score 72 + vix kicker.
      • bullish   → LONG  bias on broad index, base score 70 + calm kicker.
      • neutral   → no signal.

    Returns the standard signal dict shape so RiskAgent + ExecutionAgent can
    consume it without any special-casing.
    """
    if macro_state is None:
        return None
    if symbol.upper() not in _MACRO_TRADEABLE:
        return None
    if df is None or len(df) < 5:
        return None

    regime = macro_state.get("regime")
    if regime not in ("risk_off", "bullish"):
        return None

    last = float(df["close"].astype(float).iloc[-1])
    vix = macro_state.get("vix")
    score_field = float(macro_state.get("score") or 50.0)

    if regime == "risk_off":
        direction = "SHORT"
        # Higher VIX = stronger conviction. Cap the kicker at +15 so the
        # macro strategy never blows past the price-based ensemble's ceiling.
        kicker = 0.0
        if isinstance(vix, (int, float)) and vix > 28:
            kicker = min(15.0, (float(vix) - 28.0) * 0.8)
        score = 72.0 + kicker
        reason = f"Macro regime risk_off (vix={vix}, score={score_field:.0f})"
    else:  # bullish
        direction = "LONG"
        kicker = 0.0
        if isinstance(vix, (int, float)) and vix < 16:
            kicker = min(12.0, (16.0 - float(vix)) * 1.5)
        score = 70.0 + kicker
        reason = f"Macro regime bullish (vix={vix}, score={score_field:.0f})"

    return {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol,
        "direction": direction,
        "strategy": "macro_compass",
        "score": round(score, 2),
        "price": last,
        "reason": reason,
        "rsi": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
