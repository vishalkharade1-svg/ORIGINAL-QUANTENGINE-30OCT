"""Phase-18 genuine multi-period OOS validation (research-only)."""

from core.research.oos_validation.execution import run_frozen_oos
from core.research.oos_validation.periods import (
    split_bars,
    validate_freshness,
)
from core.research.oos_validation.report import (
    aggregate_results,
    classify_period,
    decide_final,
)

__all__ = [
    "aggregate_results",
    "classify_period",
    "decide_final",
    "run_frozen_oos",
    "split_bars",
    "validate_freshness",
]
