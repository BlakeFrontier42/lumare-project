"""
Risk / Policy Engine — Pre-execution gate.

Every request passes through policy checks BEFORE any adapter runs.
Trade-category requests get additional checks before execution.

Rules are deterministic. No LLM involved. Fully auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.orchestrator.schemas import (
    IntentCategory,
    PolicyDecision,
    Severity,
)
from backend.orchestrator.memory import MemoryEngine


@dataclass
class PolicyRule:
    name: str
    description: str
    categories: List[IntentCategory]  # Which intents this rule applies to
    enabled: bool = True


class PolicyEngine:
    """
    Evaluates a set of deterministic rules against each request.
    Returns allow/block with reasoning.
    """

    def __init__(self, memory: MemoryEngine, settings: Any = None):
        self.memory = memory
        self.settings = settings
        self._rules = self._build_rules()

    def _build_rules(self) -> List[PolicyRule]:
        return [
            PolicyRule(
                name="drawdown_circuit_breaker",
                description="Block new trades if portfolio drawdown exceeds threshold",
                categories=[IntentCategory.TRADE],
            ),
            PolicyRule(
                name="daily_loss_cap",
                description="Block trades if daily loss cap is hit",
                categories=[IntentCategory.TRADE],
            ),
            PolicyRule(
                name="max_portfolio_heat",
                description="Block trades if total portfolio heat exceeds limit",
                categories=[IntentCategory.TRADE],
            ),
            PolicyRule(
                name="correlated_position_limit",
                description="Warn if adding correlated positions beyond limit",
                categories=[IntentCategory.TRADE],
            ),
            PolicyRule(
                name="no_martingale",
                description="Block averaging down into losing positions",
                categories=[IntentCategory.TRADE],
            ),
            PolicyRule(
                name="leverage_sanity",
                description="Block excessive leverage requests",
                categories=[IntentCategory.TRADE],
            ),
            PolicyRule(
                name="rate_limit",
                description="Throttle rapid-fire requests",
                categories=[
                    IntentCategory.TRADE, IntentCategory.RESEARCH,
                    IntentCategory.QUANT, IntentCategory.GENERAL,
                ],
            ),
            PolicyRule(
                name="symbol_validation",
                description="Ensure requested symbols are in the tradable universe",
                categories=[IntentCategory.TRADE, IntentCategory.RESEARCH],
            ),
        ]

    def evaluate(
        self,
        category: IntentCategory,
        user_id: str,
        symbols: List[str] = None,
        context: Dict[str, Any] = None,
    ) -> PolicyDecision:
        """
        Run all applicable rules. Returns first blocking rule or all-clear.
        """
        context = context or {}
        symbols = symbols or []
        checks_run = []
        warnings = []

        for rule in self._rules:
            if not rule.enabled:
                continue
            if category not in rule.categories:
                continue

            checks_run.append(rule.name)
            result = self._evaluate_rule(rule, user_id, symbols, context)

            if result is not None:
                allowed, severity, reason = result
                if not allowed:
                    logger.warning(
                        f"Policy BLOCKED: {rule.name} | user={user_id} | {reason}"
                    )
                    return PolicyDecision(
                        allowed=False,
                        reason=reason,
                        severity=severity,
                        checks_run=checks_run,
                        blocked_by=rule.name,
                    )
                if severity == Severity.WARNING:
                    warnings.append(reason)

        # All passed
        decision = PolicyDecision(
            allowed=True,
            checks_run=checks_run,
            severity=Severity.WARNING if warnings else Severity.INFO,
            reason="; ".join(warnings) if warnings else None,
        )
        return decision

    def _evaluate_rule(
        self,
        rule: PolicyRule,
        user_id: str,
        symbols: List[str],
        context: Dict[str, Any],
    ) -> Optional[tuple]:
        """
        Evaluate a single rule.
        Returns None if rule doesn't apply, or (allowed, severity, reason).
        """
        method = getattr(self, f"_check_{rule.name}", None)
        if method is None:
            return None
        return method(user_id, symbols, context)

    # ─── Rule Implementations ─────────────────────────────

    def _check_drawdown_circuit_breaker(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        dd = ctx.get("drawdown_pct", 0)
        threshold = -0.15  # -15%
        if self.settings and hasattr(self.settings, "risk"):
            threshold = self.settings.risk.drawdown_shutdown_threshold
        if dd <= threshold:
            return (False, Severity.CRITICAL,
                    f"Drawdown {dd:.1%} exceeds shutdown threshold {threshold:.1%}")
        if dd <= threshold * 0.8:  # -12% warn
            return (True, Severity.WARNING,
                    f"Drawdown {dd:.1%} approaching shutdown threshold")
        return None

    def _check_daily_loss_cap(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        daily_loss = ctx.get("daily_loss_pct", 0)
        cap = -0.04  # -4%
        if self.settings and hasattr(self.settings, "risk"):
            cap = -abs(self.settings.risk.daily_loss_cap)
        if daily_loss <= cap:
            return (False, Severity.CRITICAL,
                    f"Daily loss {daily_loss:.1%} exceeds cap {cap:.1%}")
        return None

    def _check_max_portfolio_heat(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        heat = ctx.get("portfolio_heat", 0)
        max_heat = 0.20
        if self.settings and hasattr(self.settings, "risk"):
            max_heat = self.settings.risk.max_portfolio_heat
        if heat >= max_heat:
            return (False, Severity.BLOCKED,
                    f"Portfolio heat {heat:.1%} at maximum {max_heat:.1%}")
        if heat >= max_heat * 0.8:
            return (True, Severity.WARNING,
                    f"Portfolio heat {heat:.1%} approaching limit {max_heat:.1%}")
        return None

    def _check_correlated_position_limit(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        correlated_count = ctx.get("correlated_positions", 0)
        max_corr = 3
        if self.settings and hasattr(self.settings, "risk"):
            max_corr = self.settings.risk.max_correlated_positions
        if correlated_count >= max_corr:
            return (True, Severity.WARNING,
                    f"{correlated_count} correlated positions (limit: {max_corr})")
        return None

    def _check_no_martingale(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        if ctx.get("is_averaging_down", False):
            no_avg = True
            if self.settings and hasattr(self.settings, "risk"):
                no_avg = self.settings.risk.no_averaging_down
            if no_avg:
                return (False, Severity.BLOCKED,
                        "Averaging down into losing position is blocked by policy")
        return None

    def _check_leverage_sanity(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        requested_lev = ctx.get("requested_leverage", 1)
        max_lev = 8.0
        if self.settings and hasattr(self.settings, "leverage"):
            max_lev = self.settings.leverage.absolute_max_leverage
        if requested_lev > max_lev:
            return (False, Severity.CRITICAL,
                    f"Requested leverage {requested_lev}x exceeds max {max_lev}x")
        if requested_lev > max_lev * 0.75:
            return (True, Severity.WARNING,
                    f"Leverage {requested_lev}x is high (max: {max_lev}x)")
        return None

    def _check_rate_limit(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        # Check recent decision count from memory
        recent = self.memory.get_decision_history(user_id, limit=10)
        if len(recent) >= 10:
            first = recent[-1].get("created_at", "")
            if first:
                try:
                    first_dt = datetime.fromisoformat(first)
                    now = datetime.now(timezone.utc)
                    if first_dt.tzinfo is None:
                        first_dt = first_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now - first_dt).total_seconds()
                    if elapsed < 10:  # 10 requests in <10 seconds
                        return (False, Severity.WARNING,
                                "Rate limit: too many requests, please slow down")
                except (ValueError, TypeError):
                    pass
        return None

    def _check_symbol_validation(
        self, user_id: str, symbols: List[str], ctx: Dict
    ) -> Optional[tuple]:
        # Import here to avoid circular dep
        from backend.orchestrator.classifier import _KNOWN_SYMBOLS
        unknown = [s for s in symbols if s not in _KNOWN_SYMBOLS]
        if unknown:
            return (True, Severity.WARNING,
                    f"Unknown symbols: {', '.join(unknown)} — data may be unavailable")
        return None
