"""
====================================================

QuantEngine

Autonomous AI Researcher (Phase 9H)

A provider-neutral, research-only autonomous researcher that
observes 9A-9G evidence, forms hypotheses, designs experiments from
the already-supported 9B/9C vocabulary, executes them through the
frozen 9C/9D/9E/9F/9G machinery, validates out-of-sample, keeps a
research memory, and returns ranked research recommendations --
NEVER orders, NEVER production changes, NEVER auto-promotion.

The built-in NullProvider keeps the engine deterministic and fully
functional with zero external AI. External providers
(OpenAI/Anthropic/OpenRouter/Ollama/future) are optional
interpreters; numeric truth stays in 9B-9G.
====================================================
"""

from core.research.researcher.types import (
    OBSERVATION,
    HYPOTHESIS,
    VALIDATED,
    REJECTED,
    INSUFFICIENT_EVIDENCE,
    BLOCKED,
    PROVIDER_UNAVAILABLE,
    RESEARCH_STATUSES,
    STANDING_LIMITATION,
    EvidenceContext,
    Hypothesis,
    ExperimentResult,
    ResearchRecommendation,
    InvestigationReport,
)
from core.research.researcher.providers import (
    AIProvider,
    NullProvider,
    OpenAIProvider,
    AnthropicProvider,
    OpenRouterProvider,
    OllamaProvider,
    ProviderUnavailable,
    registered_providers,
    available_providers,
)
from core.research.researcher.memory import ResearchMemory
from core.research.researcher.planner import ResearchPlanner
from core.research.researcher.experiments import (
    ExperimentExecutor,
    ExperimentRun,
)
from core.research.researcher.evaluate import EvidenceEvaluator
from core.research.researcher.researcher import (
    AutonomousResearcher,
    build_context,
    DEFAULT_BASE_CONFIG,
)

__all__ = [
    "AutonomousResearcher",
    "build_context",
    "DEFAULT_BASE_CONFIG",
    "EvidenceContext",
    "Hypothesis",
    "ExperimentResult",
    "ExperimentRun",
    "ResearchRecommendation",
    "InvestigationReport",
    "ResearchMemory",
    "ResearchPlanner",
    "ExperimentExecutor",
    "EvidenceEvaluator",
    "AIProvider",
    "NullProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "OpenRouterProvider",
    "OllamaProvider",
    "ProviderUnavailable",
    "registered_providers",
    "available_providers",
    "OBSERVATION",
    "HYPOTHESIS",
    "VALIDATED",
    "REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
    "PROVIDER_UNAVAILABLE",
    "RESEARCH_STATUSES",
    "STANDING_LIMITATION",
]