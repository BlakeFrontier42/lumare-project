"""
Unified Structured Response Schema

Every orchestrator output follows this shape regardless of which
engine/adapter produced it. Frontend can render any response block
without knowing which backend path generated it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ─── Block Types ──────────────────────────────────────────

class BlockType(str, Enum):
    """All possible content blocks in a response."""
    TEXT = "text"                    # Narrative / explanation
    CHART = "chart"                  # Chart data payload
    TABLE = "table"                  # Rows + columns
    METRIC = "metric"                # Single key-value metric
    METRICS_GROUP = "metrics_group"  # Group of related metrics
    SIGNAL = "signal"                # Trade signal
    TRADE_PLAN = "trade_plan"        # Full trade plan with levels
    PORTFOLIO = "portfolio"          # Portfolio snapshot
    RISK_ALERT = "risk_alert"        # Risk/policy warning
    CITATION = "citation"            # Source citation from research
    CODE = "code"                    # Quant code / formula output
    ACTION = "action"                # Actionable button / next step
    ERROR = "error"                  # Error block


class IntentCategory(str, Enum):
    RESEARCH = "research"
    TRADE = "trade"
    PORTFOLIO = "portfolio"
    MACRO = "macro"
    MEMORY = "memory"
    RISK = "risk"
    GENERAL = "general"
    QUANT = "quant"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKED = "blocked"


# ─── Request Schema ──────────────────────────────────────

class OrchestratorRequest(BaseModel):
    """Inbound request to the orchestration layer."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default"
    query: str
    context: Dict[str, Any] = Field(default_factory=dict)
    # Optional hints
    symbol: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    category_hint: Optional[IntentCategory] = None
    # Session
    session_id: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─── Response Blocks ─────────────────────────────────────

class ResponseBlock(BaseModel):
    """Single content block inside a response."""
    type: BlockType
    title: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    severity: Optional[Severity] = None
    source: Optional[str] = None  # Which adapter produced this


class PolicyDecision(BaseModel):
    """Result of policy/risk gate evaluation."""
    allowed: bool = True
    reason: Optional[str] = None
    severity: Severity = Severity.INFO
    checks_run: List[str] = Field(default_factory=list)
    blocked_by: Optional[str] = None


class RoutingDecision(BaseModel):
    """How the orchestrator chose to route the request."""
    category: IntentCategory
    confidence: float = Field(ge=0.0, le=1.0)
    adapters_used: List[str] = Field(default_factory=list)
    slm_handled: bool = False
    reasoning: Optional[str] = None


# ─── Unified Response ────────────────────────────────────

class OrchestratorResponse(BaseModel):
    """
    Every orchestrator call returns this shape.
    The frontend iterates `blocks` and renders each by `type`.
    """
    request_id: str
    user_id: str = "default"
    routing: RoutingDecision
    policy: PolicyDecision
    blocks: List[ResponseBlock] = Field(default_factory=list)
    # Memory updates triggered
    memory_writes: List[Dict[str, Any]] = Field(default_factory=list)
    # Timing
    latency_ms: Optional[float] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ─── Convenience constructors ────────────────────────────

def text_block(title: str, body: str, source: str = "orchestrator") -> ResponseBlock:
    return ResponseBlock(type=BlockType.TEXT, title=title, data={"body": body}, source=source)


def metric_block(label: str, value: Any, unit: str = "", status: str = "ok") -> ResponseBlock:
    return ResponseBlock(
        type=BlockType.METRIC,
        data={"label": label, "value": value, "unit": unit, "status": status},
    )


def signal_block(
    symbol: str, direction: str, score: float,
    entry: float = 0, stop: float = 0, targets: list = None,
    source: str = "scoring_engine",
) -> ResponseBlock:
    return ResponseBlock(
        type=BlockType.SIGNAL,
        title=f"{direction.upper()} {symbol}",
        data={
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "entry": entry,
            "stop_loss": stop,
            "targets": targets or [],
        },
        source=source,
    )


def risk_alert_block(message: str, severity: Severity, blocker: str = "") -> ResponseBlock:
    return ResponseBlock(
        type=BlockType.RISK_ALERT,
        title="Risk Alert",
        data={"message": message, "blocker": blocker},
        severity=severity,
    )


def error_block(message: str, detail: str = "") -> ResponseBlock:
    return ResponseBlock(
        type=BlockType.ERROR,
        title="Error",
        data={"message": message, "detail": detail},
        severity=Severity.CRITICAL,
    )
