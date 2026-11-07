"""
====================================================

QuantEngine

Research Intelligence -- vocabulary (Phase 9E)

Deterministic, stable string contracts for recommendation
statuses, categories and evidence-strength values. These are
plain string constants (never enum-imposed onto the JSON surface)
so recommendations survive serialisation and are queryable by
exact string.

Status values are research-assessment states, NOT production
approval. None of them means "approved for production".
====================================================
"""

# ------------------------------------------------------------------
# Recommendation status -- research assessment only, never adoption.
# ------------------------------------------------------------------

OBSERVATION = "OBSERVATION"
HYPOTHESIS = "HYPOTHESIS"
PROMISING = "PROMISING"
INCONCLUSIVE = "INCONCLUSIVE"
REJECTED = "REJECTED"
REQUIRES_OOS = "REQUIRES_OOS"
BLOCKED = "BLOCKED"

RECOMMENDATION_STATUSES = (
    OBSERVATION,
    HYPOTHESIS,
    PROMISING,
    INCONCLUSIVE,
    REJECTED,
    REQUIRES_OOS,
    BLOCKED,
)

# ------------------------------------------------------------------
# Recommendation categories
# ------------------------------------------------------------------

ENTRY_RECOVERY = "ENTRY_RECOVERY"
ENTRY_NOT_REACHED = "ENTRY_NOT_REACHED"
MISSED_CONTINUATION = "MISSED_CONTINUATION"
RR_ANALYSIS = "RR_ANALYSIS"
EXPIRY_ANALYSIS = "EXPIRY_ANALYSIS"
ENTRY_OFFSET_ANALYSIS = "ENTRY_OFFSET_ANALYSIS"
STOP_TARGET_ANALYSIS = "STOP_TARGET_ANALYSIS"
DIRECTIONAL_ANALYSIS = "DIRECTIONAL_ANALYSIS"
SYMBOL_ANALYSIS = "SYMBOL_ANALYSIS"
CONFLUENCE_ANALYSIS = "CONFLUENCE_ANALYSIS"
GENERAL = "GENERAL"

RECOMMENDATION_CATEGORIES = (
    ENTRY_RECOVERY,
    ENTRY_NOT_REACHED,
    MISSED_CONTINUATION,
    RR_ANALYSIS,
    EXPIRY_ANALYSIS,
    ENTRY_OFFSET_ANALYSIS,
    STOP_TARGET_ANALYSIS,
    DIRECTIONAL_ANALYSIS,
    SYMBOL_ANALYSIS,
    CONFLUENCE_ANALYSIS,
    GENERAL,
)

# ------------------------------------------------------------------
# Evidence strength -- deterministic, non-statistical grades.
# ------------------------------------------------------------------

EVIDENCE_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
EVIDENCE_SMALL_SAMPLE = "SMALL_SAMPLE"
EVIDENCE_LIMITED = "LIMITED"
EVIDENCE_MODERATE = "MODERATE"
EVIDENCE_STRONG = "STRONG"

# ------------------------------------------------------------------
# Robustness status indicators (reused 9D vocabulary).
# ------------------------------------------------------------------

ROBUST = "ROBUST"
NON_ROBUST = "NON_ROBUST"
OOS_REQUIRED = "OOS_REQUIRED"
LOSS_EXPANSION = "LOSS_EXPANSION"
DIRECTIONAL_IMBALANCE = "DIRECTIONAL_IMBALANCE"
NO_CLEAR_ADVANTAGE = "NO_CLEAR_ADVANTAGE"

# ------------------------------------------------------------------
# Opportunities that are "unfilled" candidates for recovery.
# ------------------------------------------------------------------

RECOVERABLE_BASELINE_CATEGORIES = (
    "REJECTED",
    "ENTRY_NOT_REACHED",
    "MISSED_CONTINUATION",
    "INVALIDATED",
)