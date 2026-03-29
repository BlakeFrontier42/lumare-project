"""
scoring_engine.py - Master Conviction Scorer

Combines all 5 signal engines (trend, momentum, structure, flow, macro)
into a single 0-100 conviction score with regime-adaptive weighting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol

from backend.core.regime_engine import RegimeState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols for sub-engines (duck-typed interface)
# ---------------------------------------------------------------------------

class SignalEngine(Protocol):
    """Expected interface for each of the 5 signal sub-engines."""

    def score(
        self, market_data: dict[str, Any], direction: str
    ) -> dict[str, Any]:
        """
        Return a dict with at minimum:
            - score: float (0-100 raw sub-score)
            - signals: list[str] (human-readable signal descriptions)
            - confidence: float (0.0-1.0)
        """
        ...


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class TradeEligibility(str, Enum):
    NO_TRADE = "NO_TRADE"        # < 70
    STANDARD = "STANDARD"        # 70-84
    ELEVATED = "ELEVATED"        # 85+


@dataclass
class ComponentScore:
    """Score from a single sub-engine."""
    engine_name: str
    raw_score: float       # 0-100 before regime weighting
    weight: float          # regime-adjusted weight
    weighted_score: float  # raw * weight (before normalisation)
    signals: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class ScoringResult:
    """Complete scoring output."""
    total_score: float                        # 0-100 normalised
    component_scores: dict[str, ComponentScore]
    regime: RegimeState
    direction: str                            # "long" or "short"
    confidence: float                         # aggregate 0-1
    signals_active: list[str]                 # all triggered signals
    trade_eligible: bool
    eligibility_tier: TradeEligibility
    explanation: str                          # human-readable summary
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_score": round(self.total_score, 2),
            "component_scores": {
                name: {
                    "raw_score": round(cs.raw_score, 2),
                    "weight": round(cs.weight, 3),
                    "weighted_score": round(cs.weighted_score, 2),
                    "signals": cs.signals,
                    "confidence": round(cs.confidence, 3),
                }
                for name, cs in self.component_scores.items()
            },
            "regime": self.regime.value,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "signals_active": self.signals_active,
            "trade_eligible": self.trade_eligible,
            "eligibility_tier": self.eligibility_tier.value,
            "explanation": self.explanation,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Regime-adaptive weight tables
# ---------------------------------------------------------------------------

ENGINE_NAMES = ["trend", "momentum", "structure", "flow", "macro"]

REGIME_WEIGHTS: dict[RegimeState, dict[str, float]] = {
    RegimeState.TREND: {
        "trend": 1.3, "momentum": 1.2, "structure": 0.8, "flow": 0.9, "macro": 0.8,
    },
    RegimeState.RANGE: {
        "trend": 0.5, "momentum": 1.0, "structure": 1.5, "flow": 1.0, "macro": 1.0,
    },
    RegimeState.EXPANSION: {
        "trend": 1.0, "momentum": 1.2, "structure": 1.2, "flow": 1.0, "macro": 0.6,
    },
    RegimeState.RISK_OFF: {
        "trend": 0.7, "momentum": 0.7, "structure": 1.0, "flow": 1.3, "macro": 1.3,
    },
    RegimeState.RISK_ON: {
        "trend": 1.0, "momentum": 1.0, "structure": 1.0, "flow": 1.0, "macro": 1.0,
    },
    RegimeState.CHAOTIC: {
        # Small non-zero weights avoid division-by-zero in normalisation.
        # CHAOTIC regime forces NO_TRADE regardless of score (see line 268).
        "trend": 0.1, "momentum": 0.1, "structure": 0.1, "flow": 0.1, "macro": 0.1,
    },
}

# NOTE: In live trading with all 5 data feeds active, threshold should be 70.
# In backtest mode (flow/macro neutralised at 50), effective ceiling is ~80,
# so 65 filters for only the highest-conviction signals.
TRADE_THRESHOLD = 65
ELEVATED_THRESHOLD = 78


# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------

class ScoringEngine:
    """
    Master conviction scorer.

    Combines the five signal sub-engines into a normalised 0-100 score
    with regime-adaptive weighting and full explainability.
    """

    def __init__(
        self,
        trend_engine: SignalEngine,
        momentum_engine: SignalEngine,
        structure_engine: SignalEngine,
        flow_engine: SignalEngine,
        macro_engine: SignalEngine,
        settings=None,
    ) -> None:
        self._engines: dict[str, SignalEngine] = {
            "trend": trend_engine,
            "momentum": momentum_engine,
            "structure": structure_engine,
            "flow": flow_engine,
            "macro": macro_engine,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        market_data: dict[str, Any],
        regime: RegimeState,
        direction: str,
    ) -> ScoringResult:
        """
        Produce the master conviction score.

        Parameters
        ----------
        market_data : dict
            All market data required by sub-engines.
        regime : RegimeState
            Current confirmed market regime.
        direction : str
            Trade direction: ``"long"`` or ``"short"``.

        Returns
        -------
        ScoringResult
        """
        direction = direction.lower()
        if direction not in ("long", "short"):
            raise ValueError(f"direction must be 'long' or 'short', got '{direction}'")

        weights = self._get_weights(regime)

        # -- Collect raw scores from each sub-engine --
        component_scores: dict[str, ComponentScore] = {}
        all_signals: list[str] = []
        confidences: list[float] = []

        for name in ENGINE_NAMES:
            engine = self._engines[name]
            w = weights[name]

            try:
                result = engine.score(market_data, direction)
                raw = float(max(0.0, min(100.0, result.get("score", 0))))
                sigs = result.get("signals", [])
                conf = float(result.get("confidence", 0.5))
            except Exception as exc:
                logger.warning(
                    "Sub-engine '%s' raised %s: %s — using 0 score",
                    name, type(exc).__name__, exc,
                )
                raw = 0.0
                sigs = []
                conf = 0.0

            weighted = raw * w
            component_scores[name] = ComponentScore(
                engine_name=name,
                raw_score=raw,
                weight=w,
                weighted_score=weighted,
                signals=sigs,
                confidence=conf,
            )
            all_signals.extend(sigs)
            if w > 0:
                confidences.append(conf)

        # -- Rebalance weights to exclude neutral engines --
        # DISABLED for A/B testing: rebalancing changes score distribution.
        # rebalanced = self._rebalance_weights(weights, component_scores)
        rebalanced = dict(weights)  # use raw regime weights

        # Recompute weighted scores with rebalanced weights
        for name, cs in component_scores.items():
            cs.weight = rebalanced[name]
            cs.weighted_score = cs.raw_score * cs.weight

        # -- Normalise to 0-100 --
        total_weighted = sum(cs.weighted_score for cs in component_scores.values())
        total_weight = sum(rebalanced.values())

        if total_weight > 0:
            total_score = (total_weighted / total_weight)
        else:
            # CHAOTIC or all engines neutral
            total_score = 0.0

        total_score = max(0.0, min(100.0, total_score))

        # -- Per-engine debug log (sampled, not every bar) --
        if logger.isEnabledFor(10):  # DEBUG level
            parts = " | ".join(
                f"{n}={cs.raw_score:.0f}(w={cs.weight})"
                for n, cs in component_scores.items()
            )
            logger.debug("Scores [{}] {}: {} → total={:.1f}", direction, parts, total_score)

        # -- Aggregate confidence --
        if confidences:
            aggregate_confidence = sum(confidences) / len(confidences)
        else:
            aggregate_confidence = 0.0

        # -- Eligibility --
        if total_score < TRADE_THRESHOLD:
            tier = TradeEligibility.NO_TRADE
            eligible = False
        elif total_score < ELEVATED_THRESHOLD:
            tier = TradeEligibility.STANDARD
            eligible = True
        else:
            tier = TradeEligibility.ELEVATED
            eligible = True

        # Force no-trade in CHAOTIC regime regardless of score
        if regime == RegimeState.CHAOTIC:
            eligible = False
            tier = TradeEligibility.NO_TRADE

        explanation = self._build_explanation(
            total_score, component_scores, regime, direction, tier,
        )

        return ScoringResult(
            total_score=total_score,
            component_scores=component_scores,
            regime=regime,
            direction=direction,
            confidence=aggregate_confidence,
            signals_active=all_signals,
            trade_eligible=eligible,
            eligibility_tier=tier,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _get_weights(regime: RegimeState) -> dict[str, float]:
        return dict(REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS[RegimeState.RISK_ON]))

    @staticmethod
    def _rebalance_weights(
        weights: dict[str, float],
        component_scores: dict[str, ComponentScore],
    ) -> dict[str, float]:
        """
        Dynamic weight redistribution for engines returning neutral/unavailable data.

        When an engine reports low confidence (<0.4) AND a neutral-ish score (40-60),
        it's likely returning a hardcoded neutral value (no real data). In that case,
        redistribute its weight proportionally to engines that ARE producing real signals.

        This prevents neutralized engines from dragging the composite score toward 50
        and ensures the threshold remains meaningful regardless of how many data feeds
        are active.

        Example: If flow and macro are neutral, their combined weight (2.0 in RISK_ON)
        gets redistributed to trend, momentum, and structure — so the effective ceiling
        rises from ~80 back to 100.
        """
        rebalanced = dict(weights)
        neutral_weight = 0.0
        active_engines = []

        for name, cs in component_scores.items():
            is_neutral = (
                cs.confidence <= 0.4
                and 35.0 <= cs.raw_score <= 65.0
            )
            if is_neutral:
                neutral_weight += rebalanced[name]
                rebalanced[name] = 0.0
                logger.debug(
                    "Engine '%s' detected as neutral (score=%.1f, conf=%.2f) — weight zeroed",
                    name, cs.raw_score, cs.confidence,
                )
            else:
                active_engines.append(name)

        # Redistribute neutral weight proportionally to active engines
        if active_engines and neutral_weight > 0:
            active_total = sum(rebalanced[n] for n in active_engines)
            if active_total > 0:
                for name in active_engines:
                    share = rebalanced[name] / active_total
                    rebalanced[name] += neutral_weight * share

        return rebalanced

    @staticmethod
    def _build_explanation(
        total_score: float,
        components: dict[str, ComponentScore],
        regime: RegimeState,
        direction: str,
        tier: TradeEligibility,
    ) -> str:
        lines = [
            f"Master Score: {total_score:.1f}/100 | Regime: {regime.value} | "
            f"Direction: {direction.upper()} | Tier: {tier.value}",
            "",
        ]

        # Sort components by weighted contribution descending
        ranked = sorted(
            components.values(),
            key=lambda c: c.weighted_score,
            reverse=True,
        )

        for cs in ranked:
            bar_len = int(cs.raw_score / 5)
            bar = "#" * bar_len + "-" * (20 - bar_len)
            lines.append(
                f"  {cs.engine_name:<12} raw={cs.raw_score:5.1f}  "
                f"wt={cs.weight:.2f}  [{bar}]  "
                f"conf={cs.confidence:.2f}"
            )
            if cs.signals:
                for sig in cs.signals:
                    lines.append(f"    -> {sig}")

        lines.append("")

        # Top-level verdict
        if tier == TradeEligibility.NO_TRADE:
            lines.append("VERDICT: Score below threshold - NO TRADE.")
        elif tier == TradeEligibility.STANDARD:
            lines.append("VERDICT: Standard conviction - proceed with normal sizing.")
        else:
            lines.append("VERDICT: Elevated conviction - eligible for enhanced sizing.")

        # Highlight dominant engine
        if ranked and ranked[0].weighted_score > 0:
            lines.append(
                f"Primary driver: {ranked[0].engine_name} "
                f"(weighted {ranked[0].weighted_score:.1f})"
            )

        return "\n".join(lines)
