"""
Lumare Orchestration Layer — Week 3 Core Engine

Routes user intents through classification, policy gating, memory,
and model/tool adapters to produce unified structured responses.
"""

from backend.orchestrator.classifier import IntentClassifier, Intent, IntentCategory
from backend.orchestrator.router import Orchestrator
from backend.orchestrator.memory import MemoryEngine
from backend.orchestrator.policy import PolicyEngine
from backend.orchestrator.slm import SLMRouter
from backend.orchestrator.learning import LearningEngine, get_learning_engine
from backend.orchestrator.schemas import (
    OrchestratorRequest,
    OrchestratorResponse,
    ResponseBlock,
    BlockType,
)

__all__ = [
    "Orchestrator",
    "IntentClassifier",
    "Intent",
    "IntentCategory",
    "MemoryEngine",
    "PolicyEngine",
    "SLMRouter",
    "LearningEngine",
    "get_learning_engine",
    "OrchestratorRequest",
    "OrchestratorResponse",
    "ResponseBlock",
    "BlockType",
]
