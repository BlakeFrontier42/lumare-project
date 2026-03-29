"""
regime_engine.py - 6-State Market Regime Classifier

Global filter that determines what trading strategies are allowed.
States: RISK_ON, RISK_OFF, RANGE, TREND, EXPANSION, CHAOTIC
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RegimeState(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    RANGE = "RANGE"
    TREND = "TREND"
    EXPANSION = "EXPANSION"
    CHAOTIC = "CHAOTIC"


@dataclass
class RegimeResult:
    """Result of a regime classification."""
    state: RegimeState
    confidence: float  # 0.0 - 1.0
    transition_from: Optional[RegimeState]
    contributing_factors: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pending_transition: Optional[RegimeState] = None
    bars_confirming: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "confidence": round(self.confidence, 4),
            "transition_from": self.transition_from.value if self.transition_from else None,
            "contributing_factors": self.contributing_factors,
            "timestamp": self.timestamp.isoformat(),
            "pending_transition": self.pending_transition.value if self.pending_transition else None,
            "bars_confirming": self.bars_confirming,
        }


# ---------------------------------------------------------------------------
# Strategy / sizing tables
# ---------------------------------------------------------------------------

ALLOWED_STRATEGIES: dict[RegimeState, list[str]] = {
    RegimeState.RISK_ON: [
        "trend_following", "momentum", "breakout", "mean_reversion",
        "swing", "position",
    ],
    RegimeState.RISK_OFF: [
        "mean_reversion", "hedging", "defensive", "short_selling",
    ],
    RegimeState.RANGE: [
        "mean_reversion", "grid", "scalping", "range_bound",
    ],
    RegimeState.TREND: [
        "trend_following", "momentum", "breakout", "swing", "position",
    ],
    RegimeState.EXPANSION: [
        "breakout", "momentum", "trend_following", "aggressive_momentum",
    ],
    RegimeState.CHAOTIC: [],  # no trading
}

POSITION_SIZE_MODIFIERS: dict[RegimeState, float] = {
    RegimeState.RISK_ON: 1.0,
    RegimeState.RISK_OFF: 0.5,
    RegimeState.RANGE: 0.75,
    RegimeState.TREND: 1.0,
    RegimeState.EXPANSION: 1.15,
    RegimeState.CHAOTIC: 0.0,
}

# Default weights when scoring each state (used in fallback weighted scoring)
STATE_SCORE_FEATURES = {
    RegimeState.CHAOTIC:   {"vol_pct": 1.2, "atr_pct": 1.0, "adx": -0.3, "vol_ratio": 0.2, "macro_stress": 0.5},
    RegimeState.RISK_OFF:  {"vol_pct": 0.8, "atr_pct": 0.3, "adx": -0.1, "vol_ratio": 0.1, "macro_stress": 1.0},
    RegimeState.EXPANSION: {"vol_pct": -0.3, "atr_pct": 0.3, "adx": 0.8, "vol_ratio": 1.0, "macro_stress": -0.3},
    RegimeState.TREND:     {"vol_pct": -0.2, "atr_pct": 0.2, "adx": 1.0, "vol_ratio": 0.3, "macro_stress": -0.2},
    RegimeState.RANGE:     {"vol_pct": -0.5, "atr_pct": -0.4, "adx": -1.0, "vol_ratio": -0.3, "macro_stress": -0.1},
    RegimeState.RISK_ON:   {"vol_pct": -0.4, "atr_pct": -0.2, "adx": 0.2, "vol_ratio": 0.2, "macro_stress": -0.8},
}


class RegimeClassifier:
    """
    6-state market regime classifier.

    Requires ``market_data_dict`` with keys:
        - vol_percentile:  30-day realised vol percentile (0-100)
        - atr_percentile:  30-day ATR percentile from 4H candles (0-100)
        - adx:             14-period ADX from 4H candles
        - volume_ratio:    current volume / 20-period avg volume
        - breakout_detected: bool
        - macro_stress:    bool  (yield-curve inversion, etc.)
        - macro_liquidity_expanding: bool (M2 growth positive, etc.)
        - fed_funds_trend: str  ("rising", "falling", "stable")
        - m2_growth:       float (annualised %)
        - yield_curve:     float (10y - 2y spread)
    """

    DEFAULT_CONFIRMATION_BARS = 3

    def __init__(
        self,
        confirmation_bars: int = DEFAULT_CONFIRMATION_BARS,
        max_history: int = 500,
    ) -> None:
        self.confirmation_bars = confirmation_bars
        self.max_history = max_history

        # Current confirmed regime
        self._current_state: RegimeState = RegimeState.RISK_ON
        self._current_confidence: float = 0.5

        # Transition tracking
        self._pending_state: Optional[RegimeState] = None
        self._pending_bars: int = 0

        # History ring buffer
        self._history: list[RegimeResult] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, market_data: dict[str, Any]) -> RegimeResult:
        """Classify the current market regime from the provided data."""
        validated = self._validate_inputs(market_data)

        raw_state, confidence, factors = self._decision_tree(validated)

        # --- Transition confirmation logic ---
        previous_state = self._current_state
        transition_from: Optional[RegimeState] = None

        if raw_state != self._current_state:
            if self._pending_state == raw_state:
                self._pending_bars += 1
            else:
                # New candidate
                self._pending_state = raw_state
                self._pending_bars = 1

            if self._pending_bars >= self.confirmation_bars:
                # Confirmed transition
                transition_from = self._current_state
                self._current_state = raw_state
                self._current_confidence = confidence
                self._pending_state = None
                self._pending_bars = 0
                logger.info(
                    "Regime transition confirmed: %s -> %s (confidence=%.2f)",
                    transition_from.value, raw_state.value, confidence,
                )
            else:
                # Not yet confirmed - keep old state, note pending
                confidence = self._current_confidence
                factors["pending_transition"] = raw_state.value
                factors["bars_confirming"] = self._pending_bars
        else:
            # Same state - reset any pending transition
            self._pending_state = None
            self._pending_bars = 0
            self._current_confidence = confidence

        result = RegimeResult(
            state=self._current_state,
            confidence=confidence,
            transition_from=transition_from,
            contributing_factors=factors,
            pending_transition=self._pending_state,
            bars_confirming=self._pending_bars,
        )

        self._append_history(result)
        return result

    @property
    def current_regime(self) -> RegimeState:
        return self._current_state

    @property
    def history(self) -> list[RegimeResult]:
        return list(self._history)

    @staticmethod
    def get_allowed_strategies(regime: RegimeState) -> list[str]:
        """Return list of strategy types allowed under the given regime."""
        return list(ALLOWED_STRATEGIES.get(regime, []))

    @staticmethod
    def get_position_size_modifier(regime: RegimeState) -> float:
        """Return the position-size multiplier for the given regime."""
        return POSITION_SIZE_MODIFIERS.get(regime, 1.0)

    # ------------------------------------------------------------------
    # Decision tree
    # ------------------------------------------------------------------

    def _decision_tree(
        self, data: dict[str, Any]
    ) -> tuple[RegimeState, float, dict[str, Any]]:
        """
        Walk the decision tree and return (state, confidence, factors).
        """
        vol_pct: float = data["vol_percentile"]
        atr_pct: float = data["atr_percentile"]
        adx: float = data["adx"]
        vol_ratio: float = data["volume_ratio"]
        breakout: bool = data["breakout_detected"]
        macro_stress: bool = data["macro_stress"]
        macro_liq: bool = data["macro_liquidity_expanding"]

        factors: dict[str, Any] = {
            "vol_percentile": vol_pct,
            "atr_percentile": atr_pct,
            "adx": adx,
            "volume_ratio": vol_ratio,
            "breakout_detected": breakout,
            "macro_stress": macro_stress,
            "macro_liquidity_expanding": macro_liq,
            "rule_matched": "",
        }

        # Rule 1: CHAOTIC
        if vol_pct > 90 and atr_pct > 80:
            confidence = self._chaotic_confidence(vol_pct, atr_pct)
            factors["rule_matched"] = "rule_1_chaotic"
            return RegimeState.CHAOTIC, confidence, factors

        # Rule 2: RISK_OFF
        if vol_pct > 75 and macro_stress:
            confidence = self._risk_off_confidence(vol_pct, macro_stress)
            factors["rule_matched"] = "rule_2_risk_off"
            return RegimeState.RISK_OFF, confidence, factors

        # Rule 3: TREND / EXPANSION
        if adx > 25 and vol_pct < 75:
            if vol_ratio > 1.5 and breakout:
                confidence = self._expansion_confidence(adx, vol_ratio, vol_pct)
                factors["rule_matched"] = "rule_3a_expansion"
                return RegimeState.EXPANSION, confidence, factors
            else:
                confidence = self._trend_confidence(adx, vol_pct)
                factors["rule_matched"] = "rule_3b_trend"
                return RegimeState.TREND, confidence, factors

        # Rule 4: RANGE
        if adx < 15 and vol_pct < 50:
            confidence = self._range_confidence(adx, vol_pct)
            factors["rule_matched"] = "rule_4_range"
            return RegimeState.RANGE, confidence, factors

        # Rule 5: RISK_ON
        if macro_liq and vol_pct < 60:
            confidence = self._risk_on_confidence(vol_pct, macro_liq)
            factors["rule_matched"] = "rule_5_risk_on"
            return RegimeState.RISK_ON, confidence, factors

        # Rule 6: Default - weighted scoring
        state, confidence = self._weighted_fallback(data)
        factors["rule_matched"] = "rule_6_weighted_fallback"
        return state, confidence, factors

    # ------------------------------------------------------------------
    # Confidence scorers per rule
    # ------------------------------------------------------------------

    @staticmethod
    def _chaotic_confidence(vol_pct: float, atr_pct: float) -> float:
        """Higher vol/atr = higher confidence it is truly chaotic."""
        score = 0.5 + 0.25 * ((vol_pct - 90) / 10) + 0.25 * ((atr_pct - 80) / 20)
        return max(0.5, min(1.0, score))

    @staticmethod
    def _risk_off_confidence(vol_pct: float, macro_stress: bool) -> float:
        base = 0.6
        if macro_stress:
            base += 0.15
        base += 0.25 * ((vol_pct - 75) / 25)
        return max(0.5, min(1.0, base))

    @staticmethod
    def _expansion_confidence(adx: float, vol_ratio: float, vol_pct: float) -> float:
        base = 0.55
        base += 0.15 * min((adx - 25) / 25, 1.0)
        base += 0.15 * min((vol_ratio - 1.5) / 1.5, 1.0)
        base += 0.1 * (1.0 - vol_pct / 100)
        return max(0.5, min(1.0, base))

    @staticmethod
    def _trend_confidence(adx: float, vol_pct: float) -> float:
        base = 0.55
        base += 0.25 * min((adx - 25) / 25, 1.0)
        base += 0.15 * (1.0 - vol_pct / 75)
        return max(0.5, min(1.0, base))

    @staticmethod
    def _range_confidence(adx: float, vol_pct: float) -> float:
        base = 0.55
        base += 0.25 * max(0, (15 - adx) / 15)
        base += 0.15 * max(0, (50 - vol_pct) / 50)
        return max(0.5, min(1.0, base))

    @staticmethod
    def _risk_on_confidence(vol_pct: float, macro_liq: bool) -> float:
        base = 0.55
        if macro_liq:
            base += 0.2
        base += 0.15 * max(0, (60 - vol_pct) / 60)
        return max(0.5, min(1.0, base))

    # ------------------------------------------------------------------
    # Weighted fallback scoring (Rule 6)
    # ------------------------------------------------------------------

    def _weighted_fallback(
        self, data: dict[str, Any]
    ) -> tuple[RegimeState, float]:
        """Score every regime and pick the highest."""
        feature_vec = {
            "vol_pct": data["vol_percentile"] / 100,
            "atr_pct": data["atr_percentile"] / 100,
            "adx": data["adx"] / 50,  # normalise to ~0-1
            "vol_ratio": min(data["volume_ratio"] / 3.0, 1.0),
            "macro_stress": 1.0 if data["macro_stress"] else 0.0,
        }

        scores: dict[RegimeState, float] = {}
        for state, weights in STATE_SCORE_FEATURES.items():
            s = sum(weights[k] * feature_vec[k] for k in weights)
            scores[state] = s

        # Softmax-ish normalisation for confidence
        best_state = max(scores, key=lambda st: scores[st])
        best_score = scores[best_state]
        score_range = max(scores.values()) - min(scores.values())
        if score_range > 0:
            confidence = 0.4 + 0.4 * (
                (best_score - min(scores.values())) / score_range
            )
        else:
            confidence = 0.4

        return best_state, max(0.3, min(0.85, confidence))

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(data: dict[str, Any]) -> dict[str, Any]:
        required_keys = [
            "vol_percentile", "atr_percentile", "adx", "volume_ratio",
            "breakout_detected", "macro_stress", "macro_liquidity_expanding",
        ]
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValueError(f"Missing required market data keys: {missing}")

        validated = dict(data)
        validated["vol_percentile"] = float(max(0, min(100, data["vol_percentile"])))
        validated["atr_percentile"] = float(max(0, min(100, data["atr_percentile"])))
        validated["adx"] = float(max(0, min(100, data["adx"])))
        validated["volume_ratio"] = float(max(0, data["volume_ratio"]))
        validated["breakout_detected"] = bool(data["breakout_detected"])
        validated["macro_stress"] = bool(data["macro_stress"])
        validated["macro_liquidity_expanding"] = bool(data["macro_liquidity_expanding"])
        return validated

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _append_history(self, result: RegimeResult) -> None:
        self._history.append(result)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

    def get_regime_duration(self) -> int:
        """How many bars the current regime has been active."""
        count = 0
        for r in reversed(self._history):
            if r.state == self._current_state:
                count += 1
            else:
                break
        return count

    def get_transition_count(self, lookback: int = 100) -> int:
        """Count regime transitions in the last *lookback* results."""
        recent = self._history[-lookback:]
        transitions = 0
        for i in range(1, len(recent)):
            if recent[i].state != recent[i - 1].state:
                transitions += 1
        return transitions

    def reset(self) -> None:
        """Reset classifier to initial state."""
        self._current_state = RegimeState.RISK_ON
        self._current_confidence = 0.5
        self._pending_state = None
        self._pending_bars = 0
        self._history.clear()
        logger.info("RegimeClassifier reset to initial state.")
