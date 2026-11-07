"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J)

A deterministic, research-only engine that turns accumulated 9I
evidence into EXPLICIT discovery experiments over the frozen 9B/9C
vocabulary. Recovery-first: it asks "which economically valid
opportunities were missed, and which smallest defensible change could
capture them?" -- for entry offset / entry models / expiry /
confirmation / RR / stop gear -- and then executes that change through
the frozen 9C -> 9D -> 9E -> 9G machinery, gates it (REJECTED /
INCONCLUSIVE / PROMISING / REQUIRES_OOS / VALIDATED / BLOCKED), and
returns a deterministic discovery report with full provenance and the
explicit 7E NO-GO preservation block.

Boundaries (enforced + tested):
   * research-only: no execution, no orders, no ledger, no account /
     portfolio, no shared capital, no production strategy/risk /
     market-data surface, no auto-promotion;
   * candidate parameters are limited to the supported 9B/9C schema
     (unsupported parameters fail loudly, never silently invented);
   * confluence is derived ONLY from observed 9F feature snapshots;
   * no lookahead: OOS is the newest chronological fold, features are
     decision-time only;
   * deterministic experiments, ids and schedule -- repeated runs are
     byte-identical; every experiment (incl. rejected/blocked) is
     retained in the report;
   * AI providers are optional (9L) and never bypass these gates.
====================================================
"""

from core.research.discovery.constants import (
    REJECTED,
    INCONCLUSIVE,
    PROMISING,
    REQUIRES_OOS,
    VALIDATED,
    BLOCKED,
    DISCOVERY_STATUSES,
    NEVER_EMITTED,
    SCORE,
    MIN_SETTLED_FOR_CONCLUSION,
    MIN_OOS_SETTLED,
    MIN_SETTLED_FOR_PROMISING,
    ROBUST_BLOCKERS,
    RESEARCH_ONLY_DISCLAIMER,
    gate_score,
)
from core.research.discovery.discovery_types import (
    OpportunityGap,
    DiscoveryHypothesis,
    DiscoveryExperiment,
    DiscoveryFinding,
    EconomicAssessment,
)
from core.research.discovery.candidate_space import (
    validate_overrides,
    vocabulary,
    SUPPORTED_ENTRY_MODELS,
    KNOWN_UNSUPPORTED_ENTRY_MODELS,
)
from core.research.discovery.hypothesis_generator import (
    detect_gaps,
    generate_hypotheses,
    dedup_hypotheses,
)
from core.research.discovery.experiment_scheduler import schedule
from core.research.discovery.baseline_comparator import (
    compare_experiment,
    economic_assessment,
)
from core.research.discovery.recovery_discovery import recovery_findings
from core.research.discovery.confluence_discovery import (
    confluence_findings,
    feature_availability,
)
from core.research.discovery.robustness_filter import (
    DiscoveryGates,
    direction_evidence,
)
from core.research.discovery.discovery_runner import DiscoveryRunner
from core.research.discovery.discovery_report import DiscoveryReport
from core.research.discovery.strategy_discovery import StrategyDiscoveryEngine

__all__ = (
    "REJECTED", "INCONCLUSIVE", "PROMISING", "REQUIRES_OOS",
    "VALIDATED", "BLOCKED",
    "DISCOVERY_STATUSES", "NEVER_EMITTED", "SCORE",
    "MIN_SETTLED_FOR_CONCLUSION", "MIN_OOS_SETTLED",
    "MIN_SETTLED_FOR_PROMISING", "ROBUST_BLOCKERS",
    "RESEARCH_ONLY_DISCLAIMER", "gate_score",
    "OpportunityGap", "DiscoveryHypothesis", "DiscoveryExperiment",
    "DiscoveryFinding", "EconomicAssessment",
    "validate_overrides", "vocabulary",
    "detect_gaps", "generate_hypotheses", "dedup_hypotheses",
    "schedule",
    "compare_experiment", "economic_assessment",
    "recovery_findings", "confluence_findings", "feature_availability",
    "DiscoveryGates", "direction_evidence",
    "DiscoveryRunner", "DiscoveryReport", "StrategyDiscoveryEngine",
)