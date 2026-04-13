"""
asset_profiles.py — Per-asset-class trading profiles for Lumare.

Different markets have fundamentally different microstructure:
- Crypto: 24/7, high volatility, structural long bias, no sessions
- US equities: 6.5h sessions, lower 5m vol, gap risk, fundamental-driven
- Futures: leveraged, session-bound, roll management
- Options: time decay, implied vol regime

Phase 4 proved that a single global configuration tuned for crypto produces
PF 1.5+ on BTC/ETH but zero trades on equities when the regime engine is
strict. The fix is not to force one calibration on all assets — it's to give
each asset class its own profile.

Profile knobs:
- ``regime_mode``: how the regime classifier gates entries
    * ``"bypass"``    : always pass RISK_ON to scoring (Phase 4 crypto behavior)
    * ``"permissive"``: respect regime but never force NO_TRADE
    * ``"strict"``    : full regime gating (Phase 4.5 default)
- ``score_threshold``: minimum total score for trade entry
- ``short_threshold_bonus``: extra score required for short entries
- ``risk_per_trade_mult``: multiplier on base risk (1.0 = standard)
- ``allow_shorts``: master short switch
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Profile dataclass
# ---------------------------------------------------------------------------

@dataclass
class AssetProfile:
    """Per-asset-class trading configuration."""

    name: str
    asset_class: str                    # "crypto" | "equity" | "futures" | "options"
    regime_mode: str = "strict"         # "bypass" | "permissive" | "strict"
    score_threshold: int = 65
    short_threshold_bonus: int = 8      # shorts need SCORE_THRESHOLD + this
    risk_per_trade_mult: float = 1.0
    allow_shorts: bool = True
    # Stop/TP tuning (multipliers on ATR)
    stop_atr_mult: float = 2.0
    rr_ratio: float = 2.5               # take_profit = stop_distance * rr_ratio
    trailing_mult: float = 2.0          # trailing distance = stop_distance * trailing_mult
    # Per-asset-class notes for explainability
    notes: str = ""


# ---------------------------------------------------------------------------
# Registered profiles
# ---------------------------------------------------------------------------

CRYPTO_PROFILE = AssetProfile(
    name="crypto_v1",
    asset_class="crypto",
    # Crypto Phase 4 was tuned against an always-RISK_ON regime engine.
    # Restoring that behavior recovers PF 1.52 on BTC. Regime is still
    # classified and logged for explainability, but it does NOT gate entries.
    regime_mode="bypass",
    score_threshold=65,
    short_threshold_bonus=8,
    risk_per_trade_mult=1.0,
    allow_shorts=True,
    stop_atr_mult=2.0,
    rr_ratio=3.0,        # Phase 4.6 tuning: 2.5 → 3.0 lifts BTC PF 1.52 → 1.93 (+27%)
    trailing_mult=2.0,
    notes="Crypto trades 24/7 with structural long bias. Phase 4.6 tuned: PF 1.93 on BTC 1Y.",
)

EQUITY_PROFILE = AssetProfile(
    name="equity_v1",
    asset_class="equity",
    # Equities use strict regime gating — the lower 5m volatility and gap risk
    # mean regime filtering is valuable (don't trade SPY into CHAOTIC days).
    regime_mode="strict",
    score_threshold=62,          # slightly lower to accommodate equity score dist.
    short_threshold_bonus=6,     # equities have less structural long bias than crypto
    risk_per_trade_mult=0.8,     # smaller first until validated on real PnL
    allow_shorts=True,
    stop_atr_mult=2.2,           # wider stops — intraday equity whipsaws + gap risk
    rr_ratio=2.8,                # slightly higher R:R to offset lower frequency
    trailing_mult=2.2,
    notes="US equities: strict regime gating, wider stops, smaller size.",
)

FUTURES_PROFILE = AssetProfile(
    name="futures_v1",
    asset_class="futures",
    regime_mode="strict",
    score_threshold=65,
    short_threshold_bonus=0,     # futures are symmetric — no long bias
    risk_per_trade_mult=0.8,
    allow_shorts=True,
    stop_atr_mult=2.0,
    rr_ratio=2.5,
    trailing_mult=2.0,
    notes="ES/NQ/CL futures: symmetric, session-bound, leveraged.",
)

OPTIONS_PROFILE = AssetProfile(
    name="options_v1",
    asset_class="options",
    regime_mode="permissive",
    score_threshold=70,          # require higher conviction due to theta drag
    short_threshold_bonus=10,
    risk_per_trade_mult=0.5,     # half size — IV and theta amplify losses
    allow_shorts=True,
    stop_atr_mult=2.5,
    rr_ratio=3.0,
    trailing_mult=2.5,
    notes="Options: higher threshold, half size, theta-aware stops.",
)


PROFILES: dict[str, AssetProfile] = {
    "crypto":  CRYPTO_PROFILE,
    "equity":  EQUITY_PROFILE,
    "futures": FUTURES_PROFILE,
    "options": OPTIONS_PROFILE,
}


# ---------------------------------------------------------------------------
# Symbol → asset class detection
# ---------------------------------------------------------------------------

_CRYPTO_SUFFIXES = ("USDT", "USDC", "USD", "BUSD", "DAI", "PERP")
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "DOGE", "LINK", "MATIC"}

_FUTURES_ROOTS = {"ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "ZB", "ZN", "ZF", "6E", "6J"}


def classify_symbol(symbol: str) -> str:
    """
    Map a symbol to an asset class.

    Heuristics (in order):
      1. Obvious crypto suffix (USDT, USD, PERP)
      2. Known futures root (ES, NQ, CL)
      3. Options detection (contains OPT or expiry pattern)
      4. Default: equity
    """
    s = symbol.upper().strip()

    # Options: e.g. "AAPL250117C00150000" or "AAPL_OPT"
    if "_OPT" in s or (len(s) > 15 and any(c in s for c in ("C", "P")) and any(ch.isdigit() for ch in s[-8:])):
        if any(ch.isdigit() for ch in s[-6:]):
            return "options"

    # Crypto
    if any(s.endswith(suf) for suf in _CRYPTO_SUFFIXES):
        return "crypto"
    if s in _CRYPTO_BASES:
        return "crypto"

    # Futures (root symbols, not expiries)
    if s in _FUTURES_ROOTS or s[:2] in _FUTURES_ROOTS:
        return "futures"

    # Default: equity
    return "equity"


def get_profile(symbol: str) -> AssetProfile:
    """Return the AssetProfile for a given symbol."""
    asset_class = classify_symbol(symbol)
    return PROFILES.get(asset_class, EQUITY_PROFILE)
