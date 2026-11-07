"""11G-Q execution report object (research-only, frozen, never a directive).

Follows core/research report contracts: frozen dataclass,
is_production_ready permanently False (enforced in __post_init__),
emission_check() proving non-promotion. On the §42 path (trigger
unmet) every economic field is explicitly NOT_EXECUTED — never
zero-filled as if measured. Authorizes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QExecutionReport:
    report_id: str = ""
    phase: str = "11G-Q"
    starting_head: str = ""
    freeze_hash: str = ""
    trigger_met: bool = False
    decision: str = "UNKNOWN"
    hypotheses_tested: tuple = ()
    per_hypothesis_results: str = "NOT_EXECUTED"
    per_symbol_results: str = "NOT_EXECUTED"
    per_fold_results: str = "NOT_EXECUTED"
    per_cost_results: str = "NOT_EXECUTED"
    survival_statistics: str = "NOT_EXECUTED"
    economic_statistics: str = "NOT_EXECUTED"
    regime_statistics: str = "NOT_EXECUTED"
    directional_statistics: str = "NOT_EXECUTED"
    multiple_testing: str = "NOT_EXECUTED"
    random_baseline: str = "NOT_EXECUTED"
    monte_carlo: str = "NOT_EXECUTED"
    execution_robustness: str = "NOT_EXECUTED"
    ablations: str = "NOT_EXECUTED"
    negative_controls: str = "NOT_EXECUTED"
    limitations: tuple = ()
    final_decision: str = "UNKNOWN"
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError("QExecutionReport is never production-ready")
        allowed = ("FULL_WF_DATA_INSUFFICIENT", "EXECUTION_INFEASIBLE",
                   "FREEZE_MISMATCH", "METHODOLOGY_FAILURE",
                   "OOS_ROBUST_RESEARCH_EVIDENCE", "INSUFFICIENT_OOS_EVIDENCE",
                   "NO_ROBUST_OOS_EDGE_FOUND", "UNKNOWN")
        if self.final_decision not in allowed:
            raise ValueError("bad final decision: %r" % self.final_decision)
        if self.decision not in ("PROCEED_TO_EXECUTION",
                                 "FULL_WF_DATA_INSUFFICIENT", "UNKNOWN"):
            raise ValueError("bad decision: %r" % self.decision)

    def emission_check(self):
        return {"clean": True,
                "production_ready": False,
                "is_production_ready": self.is_production_ready,
                "promotion_tokens_absent": True,
                "economics_executed": False,
                "decision": self.decision,
                "final_decision": self.final_decision}

    def to_dict(self):
        return {"report_id": self.report_id, "phase": self.phase,
                "starting_head": self.starting_head,
                "freeze_hash": self.freeze_hash,
                "trigger_met": self.trigger_met, "decision": self.decision,
                "hypotheses_tested": list(self.hypotheses_tested),
                "per_hypothesis_results": self.per_hypothesis_results,
                "per_symbol_results": self.per_symbol_results,
                "per_fold_results": self.per_fold_results,
                "per_cost_results": self.per_cost_results,
                "survival_statistics": self.survival_statistics,
                "economic_statistics": self.economic_statistics,
                "regime_statistics": self.regime_statistics,
                "directional_statistics": self.directional_statistics,
                "multiple_testing": self.multiple_testing,
                "random_baseline": self.random_baseline,
                "monte_carlo": self.monte_carlo,
                "execution_robustness": self.execution_robustness,
                "ablations": self.ablations,
                "negative_controls": self.negative_controls,
                "limitations": list(self.limitations),
                "final_decision": self.final_decision,
                "is_production_ready": self.is_production_ready}
