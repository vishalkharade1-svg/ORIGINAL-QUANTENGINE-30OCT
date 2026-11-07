"""
====================================================

QuantEngine

Research Intelligence (Phase 9E)

Deterministic, explainable, evidence-backed RESEARCH recommendations
over 9A-9D evidence. This layer is research-only: it never modifies
strategy / execution / risk / portfolio / live-or-paper behaviour,
never promotes or optimises automatically, and neither imports nor
invokes any AI/LLM/ML. It packages evidence for human review and for
a future (9F / 9G) interpretive layer.

Public surface:
    ResearchIntelligence          orchestrator over a 9D ResearchReport
    IntelligenceReport            immutable, deterministic output
    Recommendation                one evidence-backed recommendation
    EvidencePackage               traceable evidence for one experiment
    ConfluenceAnalysis            confluence feature container
    opportunity_recovery_insight  per-category recovery summary
    parameter_insights            per-parameter parameter moves
    directional_breakdown         directional / symbol decomposition
    robustness_status_for         deterministic robustness label
    generate_hypotheses           deterministic candidate hypotheses
    recommendation types          statuses + categories + evidence grades

Boundaries (frozen): production trading engine and Phase 7E NO-GO are
untouched; no auto-promotion; no coined statistical significance.
====================================================
"""

from core.research.intelligence.recommendation_types import (
    RECOMMENDATION_STATUSES,
    RECOMMENDATION_CATEGORIES,
    OBSERVATION, HYPOTHESIS, PROMISING, INCONCLUSIVE, REJECTED,
    REQUIRES_OOS, BLOCKED,
    EVIDENCE_INSUFFICIENT_SAMPLE, EVIDENCE_SMALL_SAMPLE, EVIDENCE_LIMITED,
    EVIDENCE_MODERATE, EVIDENCE_STRONG,
)
from core.research.intelligence.recommendation_types import (
    ROBUST,
    NON_ROBUST,
    OOS_REQUIRED,
    LOSS_EXPANSION,
    DIRECTIONAL_IMBALANCE,
    NO_CLEAR_ADVANTAGE,
)
from core.research.intelligence.recommendation import (
    Recommendation,
    recommendation_id_for,
)
from core.research.intelligence.evidence import (
    EvidencePackage,
    evidence_strength_for,
)
from core.research.intelligence.opportunity_recovery import (
    OpportunityRecoveryInsight,
    opportunity_recovery_insight,
)
from core.research.intelligence.parameter_insights import (
    ParameterInsight,
    parameter_insights,
)
from core.research.intelligence.directional_analysis import (
    directional_breakdown,
    symbol_breakdown,
)
from core.research.intelligence.confluence_analysis import (
    ConfluenceAnalysis,
    ConfluenceFeature,
    confluence_from_features,
    CONFLUENCE_DATA_UNAVAILABLE,
)
from core.research.intelligence.robustness_gate import robustness_status_for
from core.research.intelligence.hypothesis import (
    Hypothesis,
    generate_hypotheses,
)
from core.research.intelligence.research_intelligence import (
    ResearchIntelligence,
    IntelligenceReport,
)

__all__ = [
    "ResearchIntelligence",
    "IntelligenceReport",
    "Recommendation",
    "recommendation_id_for",
    "EvidencePackage",
    "evidence_strength_for",
    "OpportunityRecoveryInsight",
    "opportunity_recovery_insight",
    "ParameterInsight",
    "parameter_insights",
    "directional_breakdown",
    "symbol_breakdown",
    "ConfluenceAnalysis",
    "ConfluenceFeature",
    "confluence_from_features",
    "CONFLUENCE_DATA_UNAVAILABLE",
    "robustness_status_for",
    "Hypothesis",
    "generate_hypotheses",
    "RECOMMENDATION_STATUSES",
    "RECOMMENDATION_CATEGORIES",
    "OBSERVATION", "HYPOTHESIS", "PROMISING", "INCONCLUSIVE",
    "REJECTED", "REQUIRES_OOS", "BLOCKED",
    "EVIDENCE_INSUFFICIENT_SAMPLE", "EVIDENCE_SMALL_SAMPLE",
    "EVIDENCE_LIMITED", "EVIDENCE_MODERATE", "EVIDENCE_STRONG",
    "ROBUST", "NON_ROBUST", "OOS_REQUIRED", "LOSS_EXPANSION",
    "DIRECTIONAL_IMBALANCE", "NO_CLEAR_ADVANTAGE",
]