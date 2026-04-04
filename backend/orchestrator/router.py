"""
Orchestrator — Central request router for Lumare.

Flow:
1. Classify intent (deterministic)
2. Check policy gate (deterministic)
3. Route through SLM (template or adapter selection)
4. Execute adapters in parallel
5. Assemble unified response
6. Write to memory (audit + preferences)

This is the single entry point for all intelligent operations.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from backend.orchestrator.classifier import IntentClassifier, Intent
from backend.orchestrator.memory import MemoryEngine
from backend.orchestrator.policy import PolicyEngine
from backend.orchestrator.slm import SLMRouter
from backend.orchestrator.adapters import AdapterRegistry, BaseAdapter
from backend.orchestrator.learning import LearningEngine, get_learning_engine
from backend.orchestrator.schemas import (
    BlockType,
    IntentCategory,
    OrchestratorRequest,
    OrchestratorResponse,
    PolicyDecision,
    ResponseBlock,
    RoutingDecision,
    Severity,
    error_block,
    risk_alert_block,
)


class Orchestrator:
    """
    Main orchestration engine. Stateless per-request — all state
    lives in MemoryEngine and is loaded per-request for the user.
    """

    def __init__(self, engine: Any = None, settings: Any = None):
        self.memory = MemoryEngine()
        self.classifier = IntentClassifier()
        self.policy = PolicyEngine(self.memory, settings)
        self.slm = SLMRouter(self.memory)
        self.adapters = AdapterRegistry(engine)
        self.settings = settings
        self.learning = get_learning_engine()
        logger.info("Orchestrator initialized — all modules wired (learning engine active)")

    async def process(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """
        Main entry point. Takes a request, returns a unified response.
        Every step is logged for auditability.
        """
        start = time.perf_counter()

        # ── 1. Classify intent ────────────────────────────
        intent = self.classifier.classify(
            query=request.query,
            category_hint=request.category_hint,
        )

        # Merge symbols from intent extraction + explicit request
        all_symbols = list(set(intent.symbols + request.symbols))
        if request.symbol and request.symbol not in all_symbols:
            all_symbols.append(request.symbol)
        intent.symbols = all_symbols

        logger.info(
            f"[{request.request_id[:8]}] Intent: {intent.category.value} "
            f"| conf={intent.confidence:.2f} | symbols={intent.symbols} "
            f"| sub={intent.sub_intent}"
        )

        # ── 2. Load user profile ──────────────────────────
        user_profile = self.memory.get_user_profile(request.user_id)

        # ── 3. Policy gate ────────────────────────────────
        policy_context = {**request.context}
        policy_decision = self.policy.evaluate(
            category=intent.category,
            user_id=request.user_id,
            symbols=intent.symbols,
            context=policy_context,
        )

        if not policy_decision.allowed:
            logger.warning(
                f"[{request.request_id[:8]}] BLOCKED by {policy_decision.blocked_by}: "
                f"{policy_decision.reason}"
            )
            elapsed = (time.perf_counter() - start) * 1000

            # Log the blocked decision
            self.memory.log_decision(
                request_id=request.request_id,
                user_id=request.user_id,
                query=request.query,
                category=intent.category.value,
                confidence=intent.confidence,
                adapters=[],
                policy_ok=False,
                policy_reason=policy_decision.reason or "",
                latency_ms=elapsed,
            )

            return OrchestratorResponse(
                request_id=request.request_id,
                user_id=request.user_id,
                routing=RoutingDecision(
                    category=intent.category,
                    confidence=intent.confidence,
                    adapters_used=[],
                    reasoning=f"Blocked: {policy_decision.reason}",
                ),
                policy=policy_decision,
                blocks=[risk_alert_block(
                    policy_decision.reason or "Request blocked by policy",
                    policy_decision.severity,
                    policy_decision.blocked_by or "",
                )],
                latency_ms=elapsed,
            )

        # ── 4. SLM routing (with adaptive weight priority) ─
        adapter_names, slm_handled = self.slm.route(intent, user_profile)

        # Use adaptive weights to reorder adapters by learned priority.
        # Adapters whose associated engine has a higher adaptive weight
        # are moved earlier in the execution order so their results
        # appear first and dominate in conflict resolution.
        if adapter_names and not slm_handled:
            try:
                regime = request.context.get("regime", "RISK_ON")
                symbol = intent.symbols[0] if intent.symbols else "*"
                adaptive_ws = self.learning.get_weights(
                    regime=regime, symbol=symbol, user_id=request.user_id,
                )
                weights_map = adaptive_ws.get("weights", {})

                # Map adapter names to a sort key: adapters that match an
                # engine name get that engine's weight (higher = earlier).
                # Unknown adapters keep neutral priority (1.0).
                def _adapter_priority(name: str) -> float:
                    for engine_name, w in weights_map.items():
                        if engine_name in name.lower():
                            return -w  # negate so higher weight sorts first
                    return -1.0

                adapter_names = sorted(adapter_names, key=_adapter_priority)
                logger.debug(
                    f"[{request.request_id[:8]}] Adaptive adapter order: "
                    f"{adapter_names} (weights: {weights_map})"
                )
            except Exception as exc:
                logger.warning(f"Adaptive weight sorting skipped: {exc}")

        blocks: List[ResponseBlock] = []

        if slm_handled:
            # Template response — no adapter needed
            blocks = self.slm.get_template_response(intent, user_profile)
            logger.info(f"[{request.request_id[:8]}] SLM handled (template)")
        else:
            # ── 5. Execute adapters in parallel ───────────
            adapter_context = {
                "symbols": intent.symbols,
                "symbol": intent.symbols[0] if intent.symbols else "",
                "sub_intent": intent.sub_intent or "",
                "user_profile": user_profile,
                **request.context,
            }

            tasks = []
            for name in adapter_names:
                adapter = self.adapters.get(name)
                if adapter:
                    tasks.append(self._run_adapter(adapter, request.query, adapter_context))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Adapter error: {result}")
                        blocks.append(error_block(str(result)))
                    elif isinstance(result, list):
                        blocks.extend(result)

        # Add policy warnings as blocks if any
        if policy_decision.reason and policy_decision.severity == Severity.WARNING:
            blocks.insert(0, risk_alert_block(
                policy_decision.reason,
                Severity.WARNING,
            ))

        # ── 6. Memory writes ─────────────────────────────
        elapsed = (time.perf_counter() - start) * 1000
        memory_writes = []

        # Log decision for audit
        self.memory.log_decision(
            request_id=request.request_id,
            user_id=request.user_id,
            query=request.query,
            category=intent.category.value,
            confidence=intent.confidence,
            adapters=adapter_names,
            policy_ok=True,
            response_summary=f"{len(blocks)} blocks",
            latency_ms=elapsed,
        )
        memory_writes.append({"type": "decision_log", "request_id": request.request_id})

        # Log any signal blocks to the adaptive learning engine
        for blk in blocks:
            if blk.type == BlockType.SIGNAL and blk.data:
                try:
                    sig_data = blk.data
                    self.learning.tracker.record_signal(
                        symbol=sig_data.get("symbol", "UNKNOWN"),
                        direction=sig_data.get("direction", "long"),
                        total_score=sig_data.get("score", 0),
                        sub_scores={
                            "trend": sig_data.get("trend_score", 0),
                            "momentum": sig_data.get("momentum_score", 0),
                            "structure": sig_data.get("structure_score", 0),
                            "flow": sig_data.get("flow_score", 0),
                            "macro": sig_data.get("macro_score", 0),
                        },
                        regime=request.context.get("regime", "RISK_ON"),
                        entry_price=sig_data.get("entry", 0),
                        stop_distance=abs(
                            sig_data.get("entry", 0) - sig_data.get("stop_loss", 0)
                        ) if sig_data.get("entry") and sig_data.get("stop_loss") else 0,
                        user_id=request.user_id,
                    )
                    logger.debug(
                        f"[{request.request_id[:8]}] Signal logged to learning engine: "
                        f"{sig_data.get('symbol')} {sig_data.get('direction')}"
                    )
                except Exception as exc:
                    logger.warning(f"Failed to log signal to learning engine: {exc}")

        # Append to session context if session_id provided
        if request.session_id:
            self.memory.append_context(
                request.user_id, request.session_id, "user", request.query
            )
            summary = " | ".join(b.title or b.type.value for b in blocks[:3])
            self.memory.append_context(
                request.user_id, request.session_id, "system", summary
            )

        # ── 7. Assemble response ─────────────────────────
        response = OrchestratorResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            routing=RoutingDecision(
                category=intent.category,
                confidence=intent.confidence,
                adapters_used=adapter_names,
                slm_handled=slm_handled,
            ),
            policy=policy_decision,
            blocks=blocks,
            memory_writes=memory_writes,
            latency_ms=elapsed,
        )

        logger.info(
            f"[{request.request_id[:8]}] Done: {len(blocks)} blocks, "
            f"{elapsed:.0f}ms, adapters={adapter_names}"
        )

        return response

    async def _run_adapter(
        self, adapter: BaseAdapter, query: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        """Run a single adapter with error handling."""
        try:
            return await adapter.execute(query, context)
        except Exception as e:
            logger.error(f"Adapter {adapter.name} failed: {e}")
            return [error_block(f"{adapter.name} failed: {str(e)}")]

    # ─── Convenience methods ──────────────────────────────

    async def quick_query(self, query: str, user_id: str = "default") -> OrchestratorResponse:
        """Shorthand for simple queries."""
        return await self.process(OrchestratorRequest(
            query=query,
            user_id=user_id,
        ))

    def set_user_preference(self, user_id: str, key: str, value: Any) -> None:
        """Direct preference write."""
        self.memory.set_preference(user_id, key, value)

    def get_audit_log(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get decision audit trail."""
        return self.memory.get_decision_history(user_id, limit)
