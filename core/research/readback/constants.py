"""
====================================================================

QuantEngine

Research UX -- Recommendation Readback (Phase 9O) -- constants

Closed, conservative UX vocabulary for explaining WHY each frozen 9N
recommendation exists, what evidence supports it, what failed, what
remains uncertain, and exactly why it is still research-only.

9O is a READBACK / EXPLANATION layer, not a decision system, not an
optimizer and not an execution surface. It consumes ONLY the frozen 9N
RecommendationReport and never reruns research:
   * it never re-simulates OOS, never re-runs conditional ML, never
     re-derives regime;
   * it never selects a strategy, never emits an order, never touches a
     ledger, never changes a parameter;
   * the strongest possible statement it can make is
     VALIDATED_RESEARCH_FINDING -- a research verdict, not a trade.

The central boundary of this phase:

   VALIDATED_RESEARCH_FINDING  (allowed -- a research artifact)
   TRADABLE_STRATEGY           (impossible -- never produced here)

A 9O report therefore carries a research verdict per recommendation
and a global production status of RESEARCH_ONLY. It can never hold a
TRADABLE_STRATEGY verdict: the vocabulary below has no such member and
build_readback rejects any attempt to inject one.
====================================================================
"""

# Closed research-verdict vocabulary, from least to most supported.
# The MAXIMUM any explanation may claim is VALIDATED_RESEARCH_FINDING.
# There is deliberately NO "TRADABLE" or "TRADABLE_STRATEGY" member:
# that statement is impossible at this boundary by construction.
RESEARCH_VERDICTS = (
    "SEVEN_E_BLOCKED",          # frozen 7E directional NO-GO -- never pursue
    "NO_EVIDENCE",              # no eligible OOS evidence at all
    "INCONCLUSIVE",             # nothing settled; cannot conclude
    "REJECTED",                 # repeated adverse OOS evidence
    "REQUIRES_MORE_OOS",        # positive but too few settled periods
    "CONDITIONAL",              # robust evidence scoped to a claimed
                                #   regime/conjunction cell -- never
                                #   universal
    "PROMISING",                # robust unconditional evidence, not yet
                                #   the fully-provenanced top tier
    "VALIDATED_RESEARCH_FINDING",  # full survival + provenance +
                                #   consistency for an unconditional
                                #   claim (research only)
)

# The single production status every 9O report carries.
PRODUCTION_STATUS = "RESEARCH_ONLY"

# A token that must NEVER appear in a serialized 9O report. This phase
# exists to make TRADABLE impossible; the token is checked in
# emission_check against the actual serialized body.
NEVER_EMITTED = ("TRADABLE_STRATEGY", "TRADABLE-GO", "PRODUCTION_READY")

# The evidence aspects a readback explains for each recommendation.
# These mirror the evidence chain in the frozen 9N report (OOS /
# regime / discovery / counterfactual / baseline / metrics / negative /
# limitations / production status).
EXPLANATION_ASPECTS = (
    "status",
    "candidate",
    "hypothesis",
    "oos_evidence",
    "regime_evidence",
    "discovery_evidence",
    "counterfactual_evidence",
    "baseline_comparison",
    "supporting_metrics",
    "negative_evidence",
    "limitations",
    "uncertainty",
    "production_status",
)

# Closed uncertainty roster. An explanation may claim uncertainty only
# from this closed set -- it never invents a new epistemic label.
UNCERTAINTY_ROSTER = (
    "NO_UNCERTAINTY",
    "POSITIVE_TOO_FEW_PERIODS",
    "CONDITIONAL_SCOPE",
    "FAMILYWISE_NOT_SURVIVED",
    "REGIME_DATA_UNAVAILABLE",
    "SYMBOL_DATA_UNAVAILABLE",
    "DIRECTIONAL_EVIDENCE_UNAVAILABLE",
    "NO_OOS_EVIDENCE",
    "REPEATED_REJECTION",
)

# Closed negative-evidence tags (what failed) -- deterministic and
# checkable, drawn from the frozen 9N chain.
NEGATIVE_EVIDENCE_ROSTER = (
    "REJECTED_PERIODS",
    "FAMILYWISE_NOT_SURVIVED",
    "SEVEN_E_NO_GO",
    "NO_OOS_SURVIVORS",
    "REGIME_DATA_UNAVAILABLE",
    "SYMBOL_DATA_UNAVAILABLE",
    "ORDERFLOW_DATA_UNAVAILABLE",
    "DIRECTIONAL_EVIDENCE_UNAVAILABLE",
    "MULTIPLE_TESTING_NOT_SURVIVED",
    "CONDITIONAL_ONLY",
)

# Robustness tier vocabulary (mirrors 9M/9N).
ROBUSTNESS_LEVELS = ("LOW", "MEDIUM", "HIGH")

# The frozen review protocol marker. 9O is additive and research-only.
REVIEW_PROTOCOL_FROZEN = True
REVIEW_CONSUMES = ("9N",)
REVIEW_MODIFIES_NOTHING = True

# Rank index into RESEARCH_VERDICTS (for deterministic ordering).
_RANK = {v: i for i, v in enumerate(RESEARCH_VERDICTS)}
