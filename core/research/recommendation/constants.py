"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N) -- constants

Closed, conservative review vocabulary and the frozen readback rules.

9N is a READBACK layer, not a decision system and not an optimizer:
it consumes the frozen research reports already produced by 9M (OOS),
9L (conditional ML) and 9K (regime) and re-states WHAT was discovered,
WHY it might have worked, WHERE it worked, WHERE it failed, HOW robust
it is, and WHAT should be investigated next -- always as an
INVESTIGATE FURTHER directive, never as a "change the strategy" or
"deploy now" directive.

The recommendation vocabulary is deliberately small and conservative:
a finding may hold exactly one of the 8 review statuses. The highest
possible recommendation is ROBUST_RESEARCH_FINDING (research-only -- it
is never a production go).
====================================================================
"""

# ------------------------------------------------------------------
# Closed recommendation vocabulary (Section 5 of the 9N spec).
# Ordered from most severe / least evidence to most supported.
# ------------------------------------------------------------------
RECOMMENDATION_STATUSES = (
    "7E_BLOCKED",             # frozen 7E directional NO-GO -- never review
    "NO_EVIDENCE",            # no eligible OOS evidence at all
    "INCONCLUSIVE",           # nothing settled; cannot conclude
    "REJECTED",               # repeated adverse OOS evidence
    "REQUIRES_MORE_OOS",      # positive but too few settled periods
    "CONDITIONAL",            # robust evidence scoped to a claimed
                              #   regime/conjunction cell -- never promoted
                              #   into a universal finding
    "PROMISING",              # robust unconditional evidence, not yet the
                              #   fully-provenanced top tier
    "ROBUST_RESEARCH_FINDING",# full survival + provenance + consistency
                              #   for an unconditional claim (research only)
)

# The frozen 7E directional safety boundary.
SEVEN_E_NO_GO = "7E-NO-GO"

# The single readback directive. 9N NEVER emits a strategy change.
RECOMMENDATION_DIRECTIVE = "INVESTIGATE_FURTHER"
RECOMMENDATION_DIRECTIVE_TEXT = (
    "Undertake further research-only OOS / mechanism investigation of "
    "this discovery. This is NOT a strategy-change, a deployment order, "
    "or any production consideration."
)

# The five readback questions every finding answers.
READBACK_QUESTIONS = (
    "what_discovered",
    "why_it_worked",
    "where_it_worked",
    "where_it_failed",
    "how_robust",
)

# Closed limitations vocabulary (mirrors the shared research evidence
# vocabulary where available; a 9N report never manufactures evidence).
LIMITATIONS = (
    "NO_OOS_SURVIVORS",
    "INSUFFICIENT_SAMPLE",
    "REGIME_DATA_UNAVAILABLE",
    "SYMBOL_DATA_UNAVAILABLE",
    "ORDERFLOW_DATA_UNAVAILABLE",
    "DIRECTIONAL_EVIDENCE_UNAVAILABLE",
    "MULTIPLE_TESTING_NOT_SURVIVED",
    "CONDITIONAL_ONLY",
)

# Production-directive tokens. build_report rejects any input whose
# STRUCTURED token fields (status / directive / candidate_id /
# hypothesis_id / oos_report_id / baseline_reference) contain one of
# these -- a production instruction must never masquerade as a research
# recommendation. Ordinary words inside explanatory prose (title /
# rationale) are NOT scanned.
PRODUCTION_DIRECTIVES = (
    "PROMOTE",
    "DEPLOY",
    "ENABLE",
    "TRADE",
    "LIVE",
    "PAPER",
    "EXECUTE",
    "PRODUCTION_READY",
)

# Answers to the "why / where" questions are drawn from a closed set of
# narrative tags (never free prose), so the readback stays deterministic
# and machine-checkable.
WHY_NARRATIVES = (
    "OOS survival consistent with the discovery premise",
    "economic delta positive across multiple periods",
    "baseline counterfactual outperformed by the candidate",
    "recovery captured missed baselines",
    "sign and magnitude stable over the trailing periods",
)

WHERE_NARRATIVES = (
    "scoped to the claimed symbol",
    "scoped to the claimed direction",
    "scoped to the claimed regime cell",
    "degraded outside the claimed cell",
    "no scope narrowing observed",
)

# Recommendation status ranks (index into RECOMMENDATION_STATUSES).
_RANK = {s: i for i, s in enumerate(RECOMMENDATION_STATUSES)}

# Origins of the discovery being read back (mirrors the frozen 9M grid).
ORIGINS = ("9J", "9K", "9L")

# Robustness tier vocabulary (mirrors 9M).
ROBUSTNESS_LEVELS = ("LOW", "MEDIUM", "HIGH")

# ------------------------------------------------------------------
# Frozen readback review defaults
# ------------------------------------------------------------------

# A finding becomes a PROMISING / CONDITIONAL / ROBUST tier only when
# it clears the review's minimum settled evidence. These are readback
# ceilings (a review never re-derives OOS numbers), not new validation.
MIN_REVIEWED_PERIODS = 1
REVIEW_ALPHA = 0.05
REVIEW_PROTOCOL_FROZEN = True

# The review never re-simulates; it aggregates evidence already frozen
# by the 9M / 9L / 9K reports.
REVIEW_CONSUMES = ("9M", "9L", "9K")
REVIEW_MODIFIES_NOTHING = True
