"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M)

Research-only, deterministic re-validation of CONSUMED discoveries
(9J / 9K / 9L) across 6 chronological, non-overlapping out-of-sample
periods, replayed through the frozen 9C counterfactual machinery
against the frozen BREAKOUT_CONTINUATION production baseline.

Public surface:

   * OosValidationEngine -- conductor (see DEFAULT_GATES in engine)
   * partition          -- deterministic chronological OOS partition
   * evaluate_period    -- one-period re-evaluation (frozen containers)
   * OosReport          -- research-only report (never emitted)

The protocol split (6 periods / 50% discovery / 30 opp + 10 trades
per settled period / 60 total trades / 5-of-6 survival / 5-of-6
sign-consistent periods / no shuffle) is protocol, not hyperparameter
(SPLIT_PROTOCOL_FROZEN).
====================================================================
"""

from core.research.oos.constants import (
    ALPHA,
    CANDIDATE_ALTERNATIVES,
    DIRECTIONS,
    DISCOVERY_FRACTION,
    EMBARGO_BARS,
    LOSS_RATE_EXPANSION,
    MIN_OOS_OPPORTUNITIES_PER_PERIOD,
    MIN_OOS_TRADES_PER_PERIOD,
    MIN_SURVIVING_PERIODS,
    MIN_TOTAL_OOS_TRADES,
    OOS_PERIODS,
    OOS_STATUSES,
    PERIOD_STATUSES,
    PURGE_BARS,
    REQUIRED_SIGN_CONSISTENT_PERIODS,
    ROBUSTNESS_LEVELS,
    SEVEN_E_NO_GO,
    SPLIT_PROTOCOL_FROZEN,
)
from core.research.oos.engine import OosValidationEngine
from core.research.oos.oos_types import (
    HypothesisOosResult,
    HypothesisRecord,
    OosPeriodEvidence,
    PeriodBoundary,
)
from core.research.oos.period import (
    OosPartition,
    partition,
)
from core.research.oos.report import (
    NEVER_EMITTED,
    OosReport,
)
from core.research.oos.validator import (
    evaluate_period,
    evaluate_pool,
)
from core.research.oos.intake import DiscoveryBindingError, validate_9l_binding
from core.research.oos.selection import NineLSelection, NineLSelectionError, admit_9l_selection

__all__ = [
    "OosValidationEngine",
    "OosReport",
    "OosPartition",
    "HypothesisRecord",
    "HypothesisOosResult",
    "OosPeriodEvidence",
    "PeriodBoundary",
    "partition",
    "evaluate_period",
    "evaluate_pool",
    "DiscoveryBindingError",
    "validate_9l_binding",
    "NineLSelection",
    "NineLSelectionError",
    "Discovery9LInput",
    "DiscoveryInputError",
    "from_opportunity_records",
    "admit_9l_selection",
    "NEVER_EMITTED",
    "OOS_PERIODS",
    "OOS_STATUSES",
    "PERIOD_STATUSES",
    "DIRECTIONS",
    "ROBUSTNESS_LEVELS",
    "CANDIDATE_ALTERNATIVES",
    "SEVEN_E_NO_GO",
    "DISCOVERY_FRACTION",
    "MIN_OOS_OPPORTUNITIES_PER_PERIOD",
    "MIN_OOS_TRADES_PER_PERIOD",
    "MIN_TOTAL_OOS_TRADES",
    "MIN_SURVIVING_PERIODS",
    "REQUIRED_SIGN_CONSISTENT_PERIODS",
    "PURGE_BARS",
    "EMBARGO_BARS",
    "ALPHA",
    "LOSS_RATE_EXPANSION",
    "SPLIT_PROTOCOL_FROZEN",
]
from core.research.oos.discovery_input import Discovery9LInput, DiscoveryInputError, from_opportunity_records
