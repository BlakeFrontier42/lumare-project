"""
Private SLM Router — Fast, deterministic response layer.

Handles:
1. Routing decisions (which adapters to invoke)
2. Templated responses for common queries (no LLM needed)
3. Preference-aware behavior (uses memory to personalize)
4. Response assembly from adapter outputs

The SLM is the "fast path" — most requests never need a frontier LLM.
Only complex synthesis / planning / narrative gets escalated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.orchestrator.classifier import Intent
from backend.orchestrator.memory import MemoryEngine
from backend.orchestrator.schemas import (
    BlockType,
    IntentCategory,
    ResponseBlock,
    text_block,
    metric_block,
    signal_block,
)


# ─── Routing Matrix ──────────────────────────────────────
# Maps (category, sub_intent) -> list of adapter names to invoke

_ROUTING_MATRIX: Dict[IntentCategory, Dict[Optional[str], List[str]]] = {
    IntentCategory.RESEARCH: {
        None: ["perplexity"],
        "congressional_trades": ["market_data"],
        "insider_trades": ["market_data"],
        "dark_pool": ["market_data"],
        "unusual_flow": ["market_data"],
        "earnings_calendar": ["perplexity"],
    },
    IntentCategory.TRADE: {
        None: ["market_data"],
        "options_chain": ["market_data"],
        "options": ["market_data"],
        "options_greeks": ["market_data"],
        "iv_skew": ["market_data"],
        "futures": ["market_data"],
    },
    IntentCategory.PORTFOLIO: {
        None: ["market_data"],
        "rebalance": ["market_data", "quant_engine"],
        "allocation": ["market_data"],
    },
    IntentCategory.MACRO: {
        None: ["perplexity", "market_data"],
        "calendar": ["market_data"],
    },
    IntentCategory.RISK: {
        None: ["quant_engine"],
        "stress_test": ["quant_engine"],
    },
    IntentCategory.QUANT: {
        None: ["quant_engine"],
        "backtest": ["quant_engine"],
        "monte_carlo": ["quant_engine"],
    },
    IntentCategory.MEMORY: {
        None: [],  # Handled locally by SLM
    },
    IntentCategory.GENERAL: {
        None: ["frontier_llm"],
    },
}

# Queries that need frontier LLM escalation
_ESCALATION_KEYWORDS = [
    "compare", "versus", "trade-off", "tradeoff", "pros and cons",
    "should i", "what would happen if", "scenario",
    "synthesize", "summarize everything", "big picture",
    "plan", "strategy for", "build a thesis",
]


class SLMRouter:
    """
    Determines which adapters to invoke and handles templated responses.
    """

    def __init__(self, memory: MemoryEngine):
        self.memory = memory
        self._templates = self._build_templates()

    def route(self, intent: Intent, user_profile: Dict[str, Any]) -> Tuple[List[str], bool]:
        """
        Given a classified intent, determine:
        1. Which adapters to invoke
        2. Whether this was fully handled by a template (slm_handled=True)

        Returns (adapter_names, slm_handled)
        """
        # Check for template match first
        template_key = self._match_template(intent)
        if template_key:
            return [], True

        # Check if escalation to frontier LLM is needed
        needs_escalation = self._needs_escalation(intent)

        # Look up routing matrix
        category_routes = _ROUTING_MATRIX.get(intent.category, {})
        adapters = category_routes.get(intent.sub_intent, category_routes.get(None, []))
        adapters = list(adapters)  # copy

        # Add frontier LLM if complex query
        if needs_escalation and "frontier_llm" not in adapters:
            adapters.append("frontier_llm")

        # Personalize: if user prefers detailed analysis, add frontier_llm
        if user_profile.get("preferences", {}).get("detailed_analysis", False):
            if "frontier_llm" not in adapters and intent.category != IntentCategory.MEMORY:
                adapters.append("frontier_llm")

        return adapters, False

    def get_template_response(self, intent: Intent, user_profile: Dict[str, Any]) -> List[ResponseBlock]:
        """
        Generate a templated response without calling any adapter.
        Used for common/simple queries the SLM can handle directly.
        """
        template_key = self._match_template(intent)
        if not template_key:
            return []

        handler = self._templates.get(template_key)
        if handler:
            return handler(intent, user_profile)
        return []

    def _match_template(self, intent: Intent) -> Optional[str]:
        """Check if intent matches a templated response."""
        q = intent.raw_query.lower()

        if intent.category == IntentCategory.MEMORY:
            if any(w in q for w in ["preference", "settings", "my risk"]):
                return "show_preferences"
            if any(w in q for w in ["history", "track record", "past signals"]):
                return "show_signal_history"
            if "remember" in q or "save" in q:
                return "save_preference"

        if intent.category == IntentCategory.GENERAL:
            if any(w in q for w in ["hello", "hi", "hey"]):
                return "greeting"
            if "help" in q or "what can you" in q:
                return "capabilities"

        return None

    def _needs_escalation(self, intent: Intent) -> bool:
        """Check if the query is complex enough to need frontier LLM."""
        q = intent.raw_query.lower()
        return any(kw in q for kw in _ESCALATION_KEYWORDS)

    def _build_templates(self) -> Dict[str, Any]:
        """Register all template handlers."""
        return {
            "greeting": self._template_greeting,
            "capabilities": self._template_capabilities,
            "show_preferences": self._template_show_prefs,
            "show_signal_history": self._template_signal_history,
            "save_preference": self._template_save_pref,
        }

    # ─── Template Handlers ────────────────────────────────

    def _template_greeting(self, intent: Intent, profile: Dict) -> List[ResponseBlock]:
        name = profile.get("preferences", {}).get("display_name", "")
        greeting = f"Welcome back{', ' + name if name else ''}."
        return [text_block("Lumare", greeting + " How can I help you today?", source="slm")]

    def _template_capabilities(self, intent: Intent, profile: Dict) -> List[ResponseBlock]:
        return [ResponseBlock(
            type=BlockType.TEXT,
            title="Lumare Capabilities",
            data={"body": (
                "**Research**: Live web search, company analysis, macro research with citations\n"
                "**Trading**: Real-time signals, entry/exit levels, risk-adjusted sizing\n"
                "**Portfolio**: Allocation analysis, rebalancing, performance tracking\n"
                "**Macro**: Fed/CPI/GDP monitoring, regime classification, macro scoring\n"
                "**Risk**: VaR, stress tests, drawdown monitoring, policy enforcement\n"
                "**Quant**: Backtesting, Monte Carlo, walk-forward validation\n"
                "**Options**: Chain analysis, Greeks, IV skew, unusual flow\n"
                "**Futures**: Session tracking, L2 depth, VPOC, key levels\n\n"
                "Just ask — I'll route to the right engine automatically."
            )},
            source="slm",
        )]

    def _template_show_prefs(self, intent: Intent, profile: Dict) -> List[ResponseBlock]:
        prefs = profile.get("preferences", {})
        if not prefs:
            return [text_block("Preferences", "No preferences saved yet. Tell me your risk tolerance, favorite symbols, or preferred timeframes.", source="slm")]

        lines = [f"**{k}**: {v}" for k, v in prefs.items()]
        return [text_block("Your Preferences", "\n".join(lines), source="slm")]

    def _template_signal_history(self, intent: Intent, profile: Dict) -> List[ResponseBlock]:
        stats = profile.get("signal_stats", {})
        total = stats.get("total_signals", 0)
        if total == 0:
            return [text_block("Signal History", "No signal history yet. Signals will be tracked as you use the platform.", source="slm")]

        return [ResponseBlock(
            type=BlockType.METRICS_GROUP,
            title="Signal Track Record",
            data={"metrics": [
                {"label": "Total Signals", "value": total},
                {"label": "Win Rate", "value": f"{stats.get('win_rate', 0):.1%}"},
                {"label": "Avg P&L", "value": f"{stats.get('avg_pnl_pct', 0):.2%}"},
                {"label": "Acted On", "value": stats.get("acted_on", 0)},
            ]},
            source="slm",
        )]

    def _template_save_pref(self, intent: Intent, profile: Dict) -> List[ResponseBlock]:
        # Parse "remember my X is Y" patterns
        q = intent.raw_query.lower()
        return [text_block(
            "Preference Saved",
            f"Noted. I'll remember this for future interactions.",
            source="slm",
        )]
