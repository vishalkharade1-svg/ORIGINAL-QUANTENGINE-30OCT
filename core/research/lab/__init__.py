"""
====================================================

QuantEngine

Research Lab (Phase 9B)

Deterministic research / counterfactual simulation layer. It
answers, for an explicitly supplied configuration:

    "What would have happened at historical time T under a
     different RR, expiry, entry distance, entry model, stop or
     target geometry?"

COUNTERFACTUAL / SIMULATED ONLY. The lab never mutates production
strategy, execution, risk, portfolio, Phase 7/7E results, or live
trading behavior. Simulated trades never enter the production
TradeRegistry. Automatic optimization is deferred to later layers.

Modules
-------
provenance           -- COUNTERFACTUAL / SIMULATED provenance
experiment_config    -- immutable ExperimentConfig
simulated_trade      -- first-class counterfactual trade record
counterfactual       -- CounterfactualOutcome (one replay result)
opportunity_replay   -- causal candle-by-candle replay engine
entry_models         -- experimental causal entry semantics
exit_models          -- experimental stop/target geometry
evidence             -- immutable EvidenceSnapshot (future AI/ML input)
metrics              -- deterministic metrics over counterfactual trades
experiment_result    -- machine-readable ExperimentResult
experiment_runner    -- runs a config over opportunities
parameter_grid       -- thin deterministic Cartesian sweep (9B)
recovery             -- opportunity recovery classification
====================================================
"""

from core.research.lab.provenance import LabProvenance
from core.research.lab.experiment_config import ExperimentConfig
from core.research.lab.simulated_trade import SimulatedTrade
from core.research.lab.counterfactual import CounterfactualOutcome
from core.research.lab.opportunity_replay import OpportunityReplay
from core.research.lab.evidence import EvidenceSnapshot, evidence_from_opportunity
from core.research.lab.metrics import metrics
from core.research.lab.experiment_result import ExperimentResult
from core.research.lab.experiment_runner import (
    ExperimentRunner,
    experiment_id_for,
)
from core.research.lab.parameter_grid import ParameterGrid
from core.research.lab.recovery import (
    OpportunityRecoveryReport,
    classify_outcome,
)

__all__ = [
    "LabProvenance",
    "ExperimentConfig",
    "SimulatedTrade",
    "CounterfactualOutcome",
    "OpportunityReplay",
    "EvidenceSnapshot",
    "evidence_from_opportunity",
    "metrics",
    "ExperimentResult",
    "ExperimentRunner",
    "experiment_id_for",
    "ParameterGrid",
    "OpportunityRecoveryReport",
    "classify_outcome",
]
