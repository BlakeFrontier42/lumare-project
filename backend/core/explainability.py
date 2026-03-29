"""
explainability.py — Trade Decision Explainability Layer
No black boxes. Every trade decision is fully transparent.

For every trade, generates:
- Contributing signals with individual scores
- Regime classification reasoning
- Risk adjustment logic
- Confidence score breakdown
- Historical analog comparison
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class SignalContribution:
    """Individual signal contribution to the trade decision."""
    category: str          # trend, momentum, structure, flow, macro
    signal_name: str       # e.g., "MA Alignment", "RSI Divergence"
    score: float           # Raw score contribution
    max_possible: float    # Max possible for this signal
    weight: float          # Weight applied
    weighted_score: float  # Final weighted score
    description: str       # Human-readable explanation
    data_points: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeExplanation:
    """Complete explanation for a trade decision."""
    timestamp: datetime
    symbol: str
    direction: str                              # LONG or SHORT
    decision: str                               # TRADE, NO_TRADE, REJECTED

    # Scores
    total_score: float
    threshold: float
    score_above_threshold: bool

    # Signal breakdown
    signal_contributions: List[SignalContribution]
    top_signals: List[str]                      # Top 3 most influential
    weakest_signals: List[str]                  # Bottom 3

    # Regime
    regime: str
    regime_confidence: float
    regime_impact: str                          # How regime affected the decision

    # Risk
    risk_adjustments: List[str]                 # All risk adjustments applied
    position_size_original: float
    position_size_final: float
    size_reduction_reasons: List[str]
    risk_checks_passed: List[str]
    risk_checks_failed: List[str]

    # Confidence
    overall_confidence: float                   # 0-1
    confidence_factors: Dict[str, float]        # What contributes to confidence

    # Historical context
    historical_analogs: List[Dict]              # Similar past setups
    regime_win_rate: Optional[float] = None     # Win rate in current regime
    similar_score_win_rate: Optional[float] = None

    # Narrative
    narrative: str = ""                         # Full human-readable summary


class ExplainabilityEngine:
    """
    Generates comprehensive explanations for every trade decision.
    Ensures full transparency — no black box trading.
    """

    def __init__(self, storage=None):
        self.storage = storage
        self._trade_history: List[Dict] = []

    def explain_trade(
        self,
        symbol: str,
        direction: str,
        score_result: Dict,
        regime_result: Dict,
        risk_decision: Dict,
        market_data: Dict,
        portfolio_state: Dict,
    ) -> TradeExplanation:
        """
        Generate a complete explanation for a trade decision.
        Called for every trade proposal, whether approved or rejected.
        """
        now = datetime.now(timezone.utc)

        # Parse score components
        component_scores = score_result.get("component_scores", {})
        total_score = score_result.get("total_score", 0)
        threshold = 70  # From settings

        # Build signal contributions
        contributions = self._build_signal_contributions(
            component_scores, score_result, direction
        )

        # Sort by weighted score
        sorted_contribs = sorted(contributions, key=lambda x: x.weighted_score, reverse=True)
        top_3 = [c.signal_name for c in sorted_contribs[:3]]
        bottom_3 = [c.signal_name for c in sorted_contribs[-3:]]

        # Regime impact
        regime_state = regime_result.get("state", "UNKNOWN")
        regime_conf = regime_result.get("confidence", 0.5)
        regime_impact = self._assess_regime_impact(regime_state, direction)

        # Risk adjustments
        risk_approved = risk_decision.get("approved", False)
        risk_adjustments = risk_decision.get("adjustments", [])
        risk_passed = risk_decision.get("checks_passed", [])
        risk_failed = risk_decision.get("checks_failed", [])

        original_size = risk_decision.get("original_size", 0)
        final_size = risk_decision.get("adjusted_size", original_size)
        size_reasons = risk_decision.get("size_reduction_reasons", [])

        # Confidence calculation
        confidence, confidence_factors = self._calculate_confidence(
            total_score, regime_conf, component_scores, len(risk_failed)
        )

        # Historical analogs
        analogs = self._find_historical_analogs(
            total_score, regime_state, direction, component_scores
        )
        regime_wr = self._get_regime_win_rate(regime_state)
        score_wr = self._get_score_range_win_rate(total_score)

        # Decision
        if total_score < threshold:
            decision = "NO_TRADE"
        elif not risk_approved:
            decision = "REJECTED"
        else:
            decision = "TRADE"

        # Generate narrative
        narrative = self._generate_narrative(
            symbol, direction, decision, total_score, threshold,
            top_3, regime_state, regime_impact, risk_adjustments,
            confidence, final_size, analogs
        )

        explanation = TradeExplanation(
            timestamp=now,
            symbol=symbol,
            direction=direction,
            decision=decision,
            total_score=total_score,
            threshold=threshold,
            score_above_threshold=total_score >= threshold,
            signal_contributions=contributions,
            top_signals=top_3,
            weakest_signals=bottom_3,
            regime=regime_state,
            regime_confidence=regime_conf,
            regime_impact=regime_impact,
            risk_adjustments=risk_adjustments,
            position_size_original=original_size,
            position_size_final=final_size,
            size_reduction_reasons=size_reasons,
            risk_checks_passed=risk_passed,
            risk_checks_failed=risk_failed,
            overall_confidence=confidence,
            confidence_factors=confidence_factors,
            historical_analogs=analogs,
            regime_win_rate=regime_wr,
            similar_score_win_rate=score_wr,
            narrative=narrative,
        )

        # Store for future analog comparisons
        self._trade_history.append({
            "timestamp": now.isoformat(),
            "symbol": symbol,
            "direction": direction,
            "decision": decision,
            "score": total_score,
            "regime": regime_state,
            "components": component_scores,
            "confidence": confidence,
        })

        return explanation

    def _build_signal_contributions(
        self, components: Dict, score_result: Dict, direction: str
    ) -> List[SignalContribution]:
        """Build detailed signal contribution list."""
        contributions = []

        signal_details = {
            "trend": {
                "max": 20, "signals": [
                    ("MA Alignment", "Moving average stack alignment across timeframes"),
                    ("ADX Strength", "Trend strength measured by ADX indicator"),
                    ("LinReg Slope", "Linear regression slope normalized by ATR"),
                ]
            },
            "momentum": {
                "max": 20, "signals": [
                    ("RSI Regime", "RSI positioning and divergence detection"),
                    ("MACD Signal", "MACD histogram direction and crossovers"),
                    ("Rate of Change", "ROC momentum confirmation"),
                ]
            },
            "structure": {
                "max": 20, "signals": [
                    ("Liquidity Sweep", "Stop hunt detection above/below key levels"),
                    ("Break of Structure", "Higher high/lower low confirmations"),
                    ("Fair Value Gap", "Three-candle imbalance zones"),
                    ("Displacement", "Institutional momentum candles"),
                ]
            },
            "flow": {
                "max": 20, "signals": [
                    ("Funding Rate", "Funding rate delta analysis"),
                    ("Open Interest", "OI change vs price direction"),
                ]
            },
            "macro": {
                "max": 20, "signals": [
                    ("Volatility", "Realized volatility percentile analysis"),
                    ("Liquidity", "M2 + Fed balance sheet composite"),
                    ("Risk Sentiment", "Credit spreads and breadth indicators"),
                ]
            },
        }

        for category, details in signal_details.items():
            cat_score = components.get(category, 0)
            cat_max = details["max"]
            weight = score_result.get("weights", {}).get(category, 1.0)

            # Distribute category score across sub-signals proportionally
            n_signals = len(details["signals"])
            per_signal = cat_score / max(n_signals, 1)

            for signal_name, description in details["signals"]:
                contributions.append(SignalContribution(
                    category=category,
                    signal_name=signal_name,
                    score=round(per_signal, 2),
                    max_possible=round(cat_max / n_signals, 2),
                    weight=weight,
                    weighted_score=round(per_signal * weight, 2),
                    description=f"{description} ({direction})",
                    data_points={},
                ))

        return contributions

    def _assess_regime_impact(self, regime: str, direction: str) -> str:
        """Assess how the regime affects the trade decision."""
        impacts = {
            "RISK_ON": f"Favorable: all strategies active. {direction} allowed.",
            "RISK_OFF": (f"Restrictive: {'momentum longs BLOCKED' if direction == 'LONG' else 'shorts allowed with caution'}. "
                         "Macro stress detected."),
            "RANGE": f"Range-bound: {'mean-reversion preferred' if direction == 'LONG' else 'mean-reversion shorts favored'}. "
                     "Trend-following discouraged.",
            "TREND": f"Trending: trend-following active. {direction} in trend direction favored.",
            "EXPANSION": f"Breakout: expansion logic active. {direction} breakout setups prioritized.",
            "CHAOTIC": "BLOCKED: extreme volatility detected. NO TRADING allowed.",
        }
        return impacts.get(regime, f"Unknown regime: {regime}")

    def _calculate_confidence(
        self, score: float, regime_conf: float,
        components: Dict, num_risk_failures: int
    ) -> tuple:
        """
        Calculate overall confidence (0-1).

        Confidence factors:
        - Score strength: how far above threshold (30%)
        - Signal agreement: how evenly distributed across categories (25%)
        - Regime clarity: how confident the regime classification is (25%)
        - Risk clearance: fewer risk flags = higher confidence (20%)
        """
        # Score strength (0-1): 70=0, 100=1
        score_factor = min(max((score - 70) / 30, 0), 1.0)

        # Signal agreement: low variance across categories = higher confidence
        if components:
            values = [v for v in components.values() if isinstance(v, (int, float))]
            if values:
                mean_val = np.mean(values)
                std_val = np.std(values) if len(values) > 1 else 0
                agreement_factor = max(0, 1 - (std_val / max(mean_val, 1)))
            else:
                agreement_factor = 0.5
        else:
            agreement_factor = 0.5

        # Regime clarity
        regime_factor = regime_conf

        # Risk clearance
        risk_factor = max(0, 1 - (num_risk_failures * 0.25))

        factors = {
            "score_strength": round(score_factor, 3),
            "signal_agreement": round(agreement_factor, 3),
            "regime_clarity": round(regime_factor, 3),
            "risk_clearance": round(risk_factor, 3),
        }

        overall = (
            0.30 * score_factor
            + 0.25 * agreement_factor
            + 0.25 * regime_factor
            + 0.20 * risk_factor
        )

        return round(overall, 3), factors

    def _find_historical_analogs(
        self, score: float, regime: str, direction: str,
        components: Dict, max_analogs: int = 5
    ) -> List[Dict]:
        """Find similar historical trade setups."""
        analogs = []
        score_tolerance = 10

        for trade in self._trade_history[-500:]:
            # Match criteria: similar score, same regime, same direction
            if (abs(trade["score"] - score) <= score_tolerance
                    and trade["regime"] == regime
                    and trade["direction"] == direction):
                analogs.append({
                    "timestamp": trade["timestamp"],
                    "score": trade["score"],
                    "decision": trade["decision"],
                    "similarity": round(1 - abs(trade["score"] - score) / score_tolerance, 2),
                })

        # Sort by similarity
        analogs.sort(key=lambda x: x["similarity"], reverse=True)
        return analogs[:max_analogs]

    def _get_regime_win_rate(self, regime: str) -> Optional[float]:
        """Get historical win rate for trades in this regime."""
        regime_trades = [t for t in self._trade_history if t["regime"] == regime]
        if len(regime_trades) < 10:
            return None
        wins = len([t for t in regime_trades if t.get("outcome") == "win"])
        return round(wins / len(regime_trades), 3) if regime_trades else None

    def _get_score_range_win_rate(self, score: float) -> Optional[float]:
        """Get win rate for trades in this score range."""
        range_trades = [
            t for t in self._trade_history
            if abs(t["score"] - score) <= 5
        ]
        if len(range_trades) < 10:
            return None
        wins = len([t for t in range_trades if t.get("outcome") == "win"])
        return round(wins / len(range_trades), 3) if range_trades else None

    def _generate_narrative(
        self, symbol: str, direction: str, decision: str,
        score: float, threshold: float, top_signals: List[str],
        regime: str, regime_impact: str, risk_adjustments: List[str],
        confidence: float, final_size: float, analogs: List[Dict]
    ) -> str:
        """Generate a human-readable narrative for the trade decision."""
        lines = []

        # Header
        if decision == "TRADE":
            lines.append(f"TRADE APPROVED: {direction} {symbol}")
        elif decision == "NO_TRADE":
            lines.append(f"NO TRADE: {symbol} {direction} — score {score:.0f} below threshold {threshold}")
        else:
            lines.append(f"TRADE REJECTED: {direction} {symbol} — failed risk checks")

        lines.append("")

        # Score summary
        lines.append(f"Conviction Score: {score:.0f}/100 (threshold: {threshold})")
        lines.append(f"Confidence: {confidence:.0%}")
        lines.append("")

        # Top signals
        lines.append("Primary Drivers:")
        for i, sig in enumerate(top_signals, 1):
            lines.append(f"  {i}. {sig}")
        lines.append("")

        # Regime
        lines.append(f"Market Regime: {regime}")
        lines.append(f"  → {regime_impact}")
        lines.append("")

        # Risk
        if risk_adjustments:
            lines.append("Risk Adjustments:")
            for adj in risk_adjustments:
                lines.append(f"  - {adj}")
            lines.append("")

        if final_size > 0:
            lines.append(f"Position Size: {final_size:.4f}")
            lines.append("")

        # Analogs
        if analogs:
            lines.append(f"Historical Analogs: {len(analogs)} similar setups found")
            for a in analogs[:3]:
                lines.append(f"  - Score {a['score']:.0f}, {a['decision']} (similarity: {a['similarity']:.0%})")

        return "\n".join(lines)

    def format_for_dashboard(self, explanation: TradeExplanation) -> Dict:
        """Format explanation for frontend dashboard display."""
        return {
            "symbol": explanation.symbol,
            "direction": explanation.direction,
            "decision": explanation.decision,
            "score": explanation.total_score,
            "confidence": explanation.overall_confidence,
            "regime": explanation.regime,
            "top_signals": explanation.top_signals,
            "risk_status": "PASSED" if not explanation.risk_checks_failed else "FLAGGED",
            "narrative": explanation.narrative,
            "timestamp": explanation.timestamp.isoformat(),
            "signal_breakdown": [
                {
                    "name": c.signal_name,
                    "category": c.category,
                    "score": c.weighted_score,
                    "max": c.max_possible * c.weight,
                }
                for c in explanation.signal_contributions
            ],
            "confidence_factors": explanation.confidence_factors,
        }
