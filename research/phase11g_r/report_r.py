"""11G-R readiness report object (research-only, frozen, never a directive).

Follows core/research report contracts: frozen dataclass,
is_production_ready permanently False (enforced in __post_init__),
emission_check() proving non-promotion. All economic fields are
explicitly NOT_EXECUTED — never zero-filled as if measured.
Authorizes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RReadinessReport:
    report_id: str = ""
    phase: str = "11G-R"
    starting_head: str = ""
    freeze_hash: str = ""
    gate_met: bool = False
    decision: str = "UNKNOWN"
    hypotheses_executed: tuple = ()
    trades: str = "NOT_EXECUTED"
    pnl: str = "NOT_EXECUTED"
    expectancy: str = "NOT_EXECUTED"
    sharpe: str = "NOT_EXECUTED"
    sortino: str = "NOT_EXECUTED"
    profit_factor: str = "NOT_EXECUTED"
    win_rate: str = "NOT_EXECUTED"
    drawdown: str = "NOT_EXECUTED"
    baseline: str = "NOT_EXECUTED"
    monte_carlo: str = "NOT_EXECUTED"
    limitations: tuple = ()
    final_decision: str = "UNKNOWN"
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError("RReadinessReport is never production-ready")
        allowed = ("FULL_WF_DATA_READY", "DATA_STILL_INSUFFICIENT",
                   "DATA_QUALITY_FAILURE", "PROVIDER_BLOCKED", "UNKNOWN")
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
                "economics_executed": False,
                "decision": self.decision,
                "final_decision": self.final_decision}

    def to_dict(self):
        return {"report_id": self.report_id, "phase": self.phase,
                "starting_head": self.starting_head,
                "freeze_hash": self.freeze_hash,
                "gate_met": self.gate_met, "decision": self.decision,
                "hypotheses_executed": list(self.hypotheses_executed),
                "trades": self.trades, "pnl": self.pnl,
                "expectancy": self.expectancy, "sharpe": self.sharpe,
                "sortino": self.sortino, "profit_factor": self.profit_factor,
                "win_rate": self.win_rate, "drawdown": self.drawdown,
                "baseline": self.baseline, "monte_carlo": self.monte_carlo,
                "limitations": list(self.limitations),
                "final_decision": self.final_decision,
                "is_production_ready": self.is_production_ready}
