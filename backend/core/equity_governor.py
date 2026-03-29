"""
equity_governor.py — Equity Curve Protection
Meta-level risk management: treats the equity curve itself as a signal.

RULES:
- Equity below 20-day MA: reduce all position sizes by 25%
- Equity below 50-day MA: reduce all position sizes by 50%
- New all-time high: normal sizing (1.0x)
- Recovery mode: gradual ramp from 0.5x back to 1.0x over 20 bars
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from loguru import logger


@dataclass
class GovernorState:
    """Current state of the equity governor."""
    size_modifier: float          # 0.5, 0.75, or 1.0
    is_in_recovery: bool
    recovery_multiplier: float
    equity_vs_20ma: float
    equity_vs_50ma: float
    current_equity: float
    all_time_high: float
    drawdown_from_ath: float
    regime: str                   # NORMAL, CAUTION, DEFENSIVE, RECOVERY
    reason: str


class EquityGovernor:
    """
    Monitors the equity curve and adjusts position sizing.
    Meta-risk layer that sits above the risk engine.
    """

    def __init__(self, ma_short: int = 20, ma_long: int = 50, recovery_ramp_bars: int = 20):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.recovery_ramp_bars = recovery_ramp_bars

        self._ath: float = 0.0
        self._bars_since_recovery: int = 0
        self._was_in_drawdown: bool = False
        self._previous_modifier: float = 1.0

    def evaluate(self, equity_curve: pd.Series) -> GovernorState:
        """Evaluate equity curve and return position sizing guidance."""
        if equity_curve is None or len(equity_curve) < 2:
            return GovernorState(
                size_modifier=1.0, is_in_recovery=False, recovery_multiplier=1.0,
                equity_vs_20ma=1.0, equity_vs_50ma=1.0,
                current_equity=float(equity_curve.iloc[-1]) if len(equity_curve) > 0 else 0,
                all_time_high=0, drawdown_from_ath=0, regime="NORMAL",
                reason="Insufficient data",
            )

        current = float(equity_curve.iloc[-1])
        self._ath = max(self._ath, float(equity_curve.max()))
        dd = (current - self._ath) / self._ath if self._ath > 0 else 0.0

        ma20 = float(equity_curve.iloc[-self.ma_short:].mean()) if len(equity_curve) >= self.ma_short else None
        ma50 = float(equity_curve.iloc[-self.ma_long:].mean()) if len(equity_curve) >= self.ma_long else None

        eq_vs_20 = current / ma20 if ma20 and ma20 > 0 else 1.0
        eq_vs_50 = current / ma50 if ma50 and ma50 > 0 else 1.0

        # Classification
        if current >= self._ath * 0.99:
            regime, modifier, reason = "NORMAL", 1.0, "At or near ATH"
            self._was_in_drawdown = False
            self._bars_since_recovery = 0
        elif ma50 and current < ma50:
            regime, modifier = "DEFENSIVE", 0.5
            reason = f"Below 50-MA (eq/MA50={eq_vs_50:.3f})"
            self._was_in_drawdown = True
        elif ma20 and current < ma20:
            regime, modifier = "CAUTION", 0.75
            reason = f"Below 20-MA (eq/MA20={eq_vs_20:.3f})"
            self._was_in_drawdown = True
        elif self._was_in_drawdown:
            regime = "RECOVERY"
            self._bars_since_recovery += 1
            progress = min(self._bars_since_recovery / self.recovery_ramp_bars, 1.0)
            modifier = 0.5 + 0.5 * progress
            reason = f"Recovery ramp: {progress:.0%} complete"
        else:
            regime, modifier, reason = "NORMAL", 1.0, "Above both MAs"

        # Smooth transitions (allow immediate reductions, gradual increases)
        if modifier > self._previous_modifier:
            modifier = min(modifier, self._previous_modifier + 0.25)
        self._previous_modifier = modifier

        return GovernorState(
            size_modifier=round(modifier, 4),
            is_in_recovery=(regime == "RECOVERY"),
            recovery_multiplier=round(modifier, 4) if regime == "RECOVERY" else 1.0,
            equity_vs_20ma=round(eq_vs_20, 4),
            equity_vs_50ma=round(eq_vs_50, 4),
            current_equity=current,
            all_time_high=self._ath,
            drawdown_from_ath=round(dd, 4),
            regime=regime,
            reason=reason,
        )

    def get_size_modifier(self, equity_curve: pd.Series) -> float:
        return self.evaluate(equity_curve).size_modifier

    def reset(self):
        self._ath = 0.0
        self._bars_since_recovery = 0
        self._was_in_drawdown = False
        self._previous_modifier = 1.0
