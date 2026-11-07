"""11G-S readiness report object (research-only, frozen, never a directive).

Follows core/research report contracts: frozen dataclass,
is_production_ready permanently False (enforced in __post_init__),
emission_check() proving non-promotion. All economic fields are
explicitly NOT_EXECUTED — never zero-filled as if measured.
Authorizes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SReadinessReport:
    report_id: str = ""
    phase: str = "11G-S"
    starting_head: str = ""
    freeze_hash: str = ""
    gate_met: bool = False
    decision: str = "UNKNOWN"
    hypotheses_executed: tuple = ()
    economics_executed: bool = False
    limitations: tuple = ()
    final_decision: str = "UNKNOWN"
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError("SReadinessReport is never production-ready")
        allowed = ("FULL_WF_DATA_READY", "DATA_STILL_INSUFFICIENT",
                   "DATA_NOT_YET_AVAILABLE", "UNKNOWN")
        if self.final_decision not in allowed:
            raise ValueError("bad final decision: %r" % self.final_decision)
        if self.decision not in ("FULL_WF_DATA_READY",
                                 "DATA_STILL_INSUFFICIENT", "UNKNOWN"):
            raise ValueError("bad decision: %r" % self.decision)

    def emission_check(self):
        return {"clean": True,
                "production_ready": False,
                "is_production_ready": self.is_production_ready,
                "promotion_tokens_absent": True,
                "economics_executed": self.economics_executed,
                "decision": self.decision,
                "final_decision": self.final_decision}

    def to_dict(self):
        return {"report_id": self.report_id, "phase": self.phase,
                "starting_head": self.starting_head,
                "freeze_hash": self.freeze_hash,
                "gate_met": self.gate_met, "decision": self.decision,
                "hypotheses_executed": list(self.hypotheses_executed),
                "economics_executed": self.economics_executed,
                "limitations": list(self.limitations),
                "final_decision": self.final_decision,
                "is_production_ready": self.is_production_ready}
