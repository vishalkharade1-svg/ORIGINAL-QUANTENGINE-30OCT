"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- public surface

Fuses the frozen 9G statistical/ML foundation with the frozen 9K
regime framework into one evidence system that asks, per decision
point:

   given THIS setup, at THIS decision bar, in THIS market regime +
   confluence context, what is the probability that each candidate
   entry/management alternative produces an economically useful
   outcome?

It is deliberately NOT an automatic ML optimizer:
   * a FIXED, bounded grid of candidate alternatives (the production-
     supported entry models) is evaluated independently by 9C -- no
     100k-combination searches,
   * the pipeline is generate -> filter -> temporal split -> outcome
     probability -> recovery probability -> entry-model selection ->
     within-regime feature interactions -> regime transition
     detection -> symbol segmentation -> OOS calibration -> GLOBAL
     strict multiple-testing correction -> robustness -> economic
     significance -> minimum sample -> limitations -> frozen finding,

   * every discovery is ASSOCIATION evidence plus its calibration,
     never a signal and never an execution directive,

   * boundaries: research-only imports, no random / uuid / datetime,
     no lookahead, deterministic, is_production_ready permanently
     False.

Discovery surfaces (9L.1-9L.7):
   recovery        -- P(recovery) + E[R]/drawdown/loss/MAE + regime
                      dependency for missed/rejected setups,
   entry selection -- conditional entry-model selection per
                      (regime, confluence) context,
   interactions    -- bounded regime-conditional 2-way / 3-way
                      feature interactions,
   transitions     -- generated-regime vs fill-regime tracking,
   symbols         -- symbol-specific behaviour gated by sample size,
   calibration     -- OOS confidence / calibration (ECE, Brier,
                      slope) -- an 80% claim must hold near 80%,
   multiple-test   -- stricter GLOBAL familywise guard.
====================================================
"""

from core.research.conditional_ml.types import (
    UNAVAILABLE,
    ENTRY_SELECTION_SUPPORTED,
    ENTRY_SELECTION_INCONCLUSIVE,
    RECOVERY_SUPPORTED,
    RECOVERY_INCONCLUSIVE,
    INTERACTION_SUPPORTED,
    INTERACTION_INCONCLUSIVE,
    TRANSITION_STABLE,
    TRANSITION_CHANGED,
    TRANSITION_INCONCLUSIVE,
    SYMBOL_JUSTIFIED,
    SYMBOL_NOT_JUSTIFIED,
    CALIBRATED,
    CALIBRATION_GAP,
    CANDIDATE_ALTERNATIVES,
    OpportunityContext,
    RecoveryFinding,
    AlternativeEvidence,
    EntrySelection,
    InteractionFinding,
    TransitionFinding,
    SymbolBehaviour,
    CalibrationBin,
    CalibrationSummary,
)
from core.research.conditional_ml.contexts import (
    build_contexts,
    context_for_record,
)
from core.research.conditional_ml.probabilities import OutcomeModel
from core.research.conditional_ml.guards import (
    required_min_n,
    familywise_alpha,
    holm_survives,
)
from core.research.conditional_ml.recovery import recovery_probabilities
from core.research.conditional_ml.entries import entry_selection
from core.research.conditional_ml.interactions import interaction_analysis
from core.research.conditional_ml.transitions import transitions
from core.research.conditional_ml.symbols import symbol_behaviour
from core.research.conditional_ml.calibration import calibration_summary
from core.research.conditional_ml.engine import (
    ConditionalMlEngine,
    DEFAULT_GATES,
)
from core.research.conditional_ml.report import ConditionalMlReport

__all__ = [
    "UNAVAILABLE",
    "ENTRY_SELECTION_SUPPORTED",
    "ENTRY_SELECTION_INCONCLUSIVE",
    "RECOVERY_SUPPORTED",
    "RECOVERY_INCONCLUSIVE",
    "INTERACTION_SUPPORTED",
    "INTERACTION_INCONCLUSIVE",
    "TRANSITION_STABLE",
    "TRANSITION_CHANGED",
    "TRANSITION_INCONCLUSIVE",
    "SYMBOL_JUSTIFIED",
    "SYMBOL_NOT_JUSTIFIED",
    "CALIBRATED",
    "CALIBRATION_GAP",
    "CANDIDATE_ALTERNATIVES",
    "OpportunityContext",
    "RecoveryFinding",
    "AlternativeEvidence",
    "EntrySelection",
    "InteractionFinding",
    "TransitionFinding",
    "SymbolBehaviour",
    "CalibrationBin",
    "CalibrationSummary",
    "build_contexts",
    "context_for_record",
    "OutcomeModel",
    "required_min_n",
    "familywise_alpha",
    "holm_survives",
    "recovery_probabilities",
    "entry_selection",
    "interaction_analysis",
    "transitions",
    "symbol_behaviour",
    "calibration_summary",
    "ConditionalMlEngine",
    "DEFAULT_GATES",
    "ConditionalMlReport",
]