"""Phase-16 evidence-readiness helpers + frozen-OOS execution readiness.

Research-only: deterministic preregistration and readiness gates for
the preregistered OOS execution phase. No strategy logic, no
execution, no I/O, no randomness.
"""

from core.research.readiness.sample_math import (
    expected_fills,
    expected_orders,
    oos_span_bars,
    required_bars,
    sample_ladder,
)
from core.research.readiness.scenarios import (
    scenario_combined,
    scenario_conservative_fees,
    scenario_conservative_slippage,
    scenario_funding,
    scenario_structural,
)
from core.research.readiness.preregistration import (
    FrozenPreregistration,
    PreregistrationError,
)
from core.research.readiness.oos_execution_readiness import (
    GateVerdict,
    OOSExecutionReadinessReport,
    ReadinessError,
    evaluate,
    observe_dataset,
    required_fresh_bars,
    required_per_period_bars,
)
from core.research.readiness.monitor import (
    Blocker,
    MonitorError,
    ReadinessSnapshot,
    classify_blockers,
    derive_handoff,
    run_monitor,
    source_status,
)

__all__ = [
    "expected_fills",
    "expected_orders",
    "oos_span_bars",
    "required_bars",
    "sample_ladder",
    "scenario_combined",
    "scenario_conservative_fees",
    "scenario_conservative_slippage",
    "scenario_funding",
    "scenario_structural",
    "FrozenPreregistration",
    "PreregistrationError",
    "GateVerdict",
    "OOSExecutionReadinessReport",
    "ReadinessError",
    "evaluate",
    "observe_dataset",
    "required_fresh_bars",
    "required_per_period_bars",
    "Blocker",
    "MonitorError",
    "ReadinessSnapshot",
    "classify_blockers",
    "derive_handoff",
    "run_monitor",
    "source_status",
    "SelectionPreregistrationError",
    "create_9l_preregistration",
]

from core.research.readiness.selection_preregistration import (
    SelectionPreregistrationError, create_9l_preregistration,
)
