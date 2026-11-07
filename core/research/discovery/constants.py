"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- closed vocabulary

The classification vocabulary and gate thresholds of the autonomous
discovery pipeline. Every status is a RESEARCH status; the pipeline
NEVER emits a promotion status.

Classification (closed vocabulary):

   REJECTED       -- evidence does not support the hypothesis
                     (no advantage vs the like-for-like baseline,
                     OOS fold did not confirm, or a directional
                     contradiction / loss expansion was found).
                     The rejected evidence is retained, never hidden.
   INCONCLUSIVE   -- the settled population is too small to conclude;
                     the run is retained for later accumulation.
   PROMISING      -- positive in-sample evidence but the robustness /
                     economic gate is not yet clear (9D/9E blockers,
                     economic trade-off flagged); never promoted.
   REQUIRES_OOS   -- in-sample evidence is clear but the chronological
                     OOS fold is missing / too small; OOS can NEVER be
                     bypassed.
   VALIDATED      -- in-sample + chronological OOS evidence is clear.
                     RESEARCH-ONLY validation; it is NEVER a production
                     readiness decision.
   BLOCKED        -- the configuration could not be executed, or the
                     hypothesis carries a 7E NO-GO surface that must
                     stay blocked.

AUTOMATICALLY_DEPLOY (and any promotion token) is deliberately NOT in
the vocabulary. Discovery findings are permanently research-only
(is_production_directive == False).
====================================================
"""

# ------------------------------------------------------------------
# closed classification vocabulary
# ------------------------------------------------------------------
REJECTED = "REJECTED"
INCONCLUSIVE = "INCONCLUSIVE"
PROMISING = "PROMISING"
REQUIRES_OOS = "REQUIRES_OOS"
VALIDATED = "VALIDATED"
BLOCKED = "BLOCKED"

DISCOVERY_STATUSES = (
    REJECTED,
    INCONCLUSIVE,
    PROMISING,
    REQUIRES_OOS,
    VALIDATED,
    BLOCKED,
)

# Promotion tokens that discovery NEVER emits. Tests + the report
# serialize guard assert these never appear in discovery output.
NEVER_EMITTED = ("AUTOMATICALLY_DEPLOY", "PRODUCTION_READY")

# deterministic ranking basis (evidence quality first)
SCORE = {
    VALIDATED: 5.0,
    REQUIRES_OOS: 4.0,
    PROMISING: 3.0,
    INCONCLUSIVE: 1.0,
    REJECTED: 0.0,
    BLOCKED: -1.0,
}

# ------------------------------------------------------------------
# gate thresholds
# ------------------------------------------------------------------
MIN_SETTLED_FOR_CONCLUSION = 30   # settled population to consider VALIDATED
MIN_OOS_SETTLED = 5               # settled OOS fold required to validate
MIN_SETTLED_FOR_PROMISING = 10    # settled population to consider PROMISING +

# 9E robustness/evidence values that keep a discovery gate NOT clear
# (mirrors the 9H robustness-blocker vocabulary).
ROBUST_BLOCKERS = (
    "OOS_REQUIRED",
    "NON_ROBUST",
    "INSUFFICIENT_SAMPLE",
    "LOSS_EXPANSION",
    "INCONCLUSIVE",
    "BLOCKED",
)

RESEARCH_ONLY_DISCLAIMER = (
    "Research-only discovery evidence. These tables are ASSOCIATION "
    "evidence for experimentation planning; they are not a trade "
    "directive and never promote a configuration to production. "
    "Nothing here changes a ledger, an order or a production "
    "strategy/risk state."
)


def gate_score(status):
    """Deterministic score for a discovery status (ranking basis)."""
    return SCORE.get(status, 0.0)