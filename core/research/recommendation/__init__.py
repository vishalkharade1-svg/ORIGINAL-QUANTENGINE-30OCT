"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N)

Research-only, deterministic readback layer that consumes the frozen
9M (OOS), 9L (conditional ML) and 9K (regime) reports and, for every
consumed discovery, emits a RecommendationFinding answering WHAT was
discovered, WHY it might have worked, WHERE it worked, WHERE it failed,
HOW robust it is, and WHAT should be investigated -- always with the
locked INVESTIGATE_FURTHER directive. Never a strategy change, never a
deployment.

Public surface:

   * RecommendationEngine -- readback conductor (consumes the frozen 9M
     OosReport + optional 9L/9K reports)
   * build_finding       -- one finding's evidence chain
   * recommend_status    -- conservative 9M final_status -> 9N mapping
   * RecommendationReport-- research-only report (never emitted)
====================================================================
"""

from core.research.recommendation.constants import (
    ORIGINS,
    READBACK_QUESTIONS,
    RECOMMENDATION_DIRECTIVE,
    RECOMMENDATION_DIRECTIVE_TEXT,
    RECOMMENDATION_STATUSES,
    REVIEW_CONSUMES,
    REVIEW_PROTOCOL_FROZEN,
    ROBUSTNESS_LEVELS,
    SEVEN_E_NO_GO,
)
from core.research.recommendation.engine import RecommendationEngine
from core.research.recommendation.evidence import build_finding, to_recommendation
from core.research.recommendation.ladder import recommend_status
from core.research.recommendation.report import (
    NEVER_EMITTED,
    RecommendationReport,
    build_report,
)
from core.research.recommendation.types import (
    AncillaryReadback,
    EvidenceSummary,
    HypothesisReadback,
    OosReadback,
    ReadbackAnswers,
    Recommendation,
    RecommendationFinding,
    RecommendationStatistics,
    ReviewOverview,
)

__all__ = [
    "RecommendationEngine",
    "RecommendationReport",
    "RecommendationFinding",
    "Recommendation",
    "EvidenceSummary",
    "RecommendationStatistics",
    "OosReadback",
    "HypothesisReadback",
    "AncillaryReadback",
    "ReadbackAnswers",
    "ReviewOverview",
    "build_finding",
    "build_report",
    "to_recommendation",
    "recommend_status",
    "NEVER_EMITTED",
    "RECOMMENDATION_STATUSES",
    "RECOMMENDATION_DIRECTIVE",
    "RECOMMENDATION_DIRECTIVE_TEXT",
    "READBACK_QUESTIONS",
    "ORIGINS",
    "ROBUSTNESS_LEVELS",
    "SEVEN_E_NO_GO",
    "REVIEW_CONSUMES",
    "REVIEW_PROTOCOL_FROZEN",
]
