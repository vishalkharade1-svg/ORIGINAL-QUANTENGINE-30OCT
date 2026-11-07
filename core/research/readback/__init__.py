"""
====================================================================

QuantEngine

Research UX -- Recommendation Readback (Phase 9O)

Deterministic, human-usable explanation layer over the frozen 9N
RecommendationReport. For every recommendation it states WHY it exists,
what evidence supports it, what failed, what remains uncertain, and
exactly why it is still research-only. It consumes ONLY the frozen 9N
report and never re-runs research.

The single strongest outcome is a VALIDATED_RESEARCH_FINDING research
verdict. A TRADABLE_STRATEGY is impossible at this boundary by
construction -- the closed verdict vocabulary has no such member and
emission_check verifies the token is absent from the serialized body.

Public surface:

   * explanation engine: explain_report / explain_entry /
     verdict_for_9n_status / build_readback
   * ReadbackEntry     -- one 1:1 explanation for one recommendation
   * ReadbackReport    -- frozen, research-only 9O report (render / to_dict
                          / to_json / emission_check)
   * RESEARCH_VERDICTS / PRODUCTION_STATUS / UNCERTAINTY_ROSTER ...
====================================================================
"""

from core.research.readback.constants import (
    EXPLANATION_ASPECTS,
    NEVER_EMITTED,
    NEGATIVE_EVIDENCE_ROSTER,
    PRODUCTION_STATUS,
    RESEARCH_VERDICTS,
    REVIEW_CONSUMES,
    REVIEW_MODIFIES_NOTHING,
    REVIEW_PROTOCOL_FROZEN,
    ROBUSTNESS_LEVELS,
    UNCERTAINTY_ROSTER,
)
from core.research.readback.explain import (
    build_readback,
    explain_entry,
    explain_report,
    verdict_for_9n_status,
)
from core.research.readback.types import (
    ReadbackEntry,
    ReadbackReport,
)

__all__ = [
    "ReadbackEntry",
    "ReadbackReport",
    "explain_report",
    "explain_entry",
    "build_readback",
    "verdict_for_9n_status",
    "RESEARCH_VERDICTS",
    "PRODUCTION_STATUS",
    "UNCERTAINTY_ROSTER",
    "NEGATIVE_EVIDENCE_ROSTER",
    "EXPLANATION_ASPECTS",
    "ROBUSTNESS_LEVELS",
    "NEVER_EMITTED",
    "REVIEW_CONSUMES",
    "REVIEW_PROTOCOL_FROZEN",
    "REVIEW_MODIFIES_NOTHING",
]
