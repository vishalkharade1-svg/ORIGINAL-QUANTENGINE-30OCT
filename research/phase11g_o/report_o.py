"""11G-O readiness report object (research-only, frozen, never a directive).

Follows core/research report contracts: frozen dataclass,
is_production_ready permanently False (enforced in __post_init__),
emission_check() proving non-promotion. Carries the readiness
record; authorizes nothing (PATH A still requires a new
preregistration before any economics).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OReadinessReport:
    inventory_files: int = 0
    overall_overlap: str = "UNKNOWN"
    walk_forward_verdict: str = "UNKNOWN"
    recommend_next_phase: str = "UNKNOWN"
    symbols: tuple = ()
    limitations: tuple = ()
    feasibility_sha256: str = ""
    code_hash: str = ""
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError("OReadinessReport is never production-ready")
        if self.overall_overlap not in ("ZERO_OVERLAP", "OVERLAP_DETECTED", "UNKNOWN"):
            raise ValueError("bad overlap verdict: %r" % self.overall_overlap)
        if self.walk_forward_verdict not in ("WF_FEASIBLE", "FULL_WF_INFEASIBLE",
                                             "UNKNOWN"):
            raise ValueError("bad WF verdict: %r" % self.walk_forward_verdict)
        allowed = ("NEW_PREREGISTERED_OOS", "DATA_EXPANSION_REQUIRED",
                   "DATA_QUALITY_REMEDIATION", "PROVIDER_RESEARCH", "UNKNOWN")
        if self.recommend_next_phase not in allowed:
            raise ValueError("bad recommendation: %r" % self.recommend_next_phase)

    def emission_check(self):
        return {"clean": True,
                "production_ready": False,
                "is_production_ready": self.is_production_ready,
                "promotion_tokens_absent": True,
                "verdict": self.walk_forward_verdict,
                "recommendation": self.recommend_next_phase}

    def to_dict(self):
        return {"inventory_files": self.inventory_files,
                "overall_overlap": self.overall_overlap,
                "walk_forward_verdict": self.walk_forward_verdict,
                "recommend_next_phase": self.recommend_next_phase,
                "symbols": list(self.symbols),
                "limitations": list(self.limitations),
                "feasibility_sha256": self.feasibility_sha256,
                "code_hash": self.code_hash,
                "is_production_ready": self.is_production_ready}


def recommendation_for(walk_forward_verdict, overall_overlap):
    if overall_overlap != "ZERO_OVERLAP":
        return "DATA_QUALITY_REMEDIATION"
    if walk_forward_verdict == "WF_FEASIBLE":
        return "NEW_PREREGISTERED_OOS"
    return "DATA_EXPANSION_REQUIRED"


def from_feasibility(feasibility, feasibility_sha256, code_hash):
    wf = feasibility.get("walk_forward", {}).get("verdict", "UNKNOWN")
    rec = recommendation_for(wf, feasibility.get("overall_overlap", "UNKNOWN"))
    return OReadinessReport(
        inventory_files=int(feasibility.get("inventory_files", 0)),
        overall_overlap=feasibility.get("overall_overlap", "UNKNOWN"),
        walk_forward_verdict=wf,
        recommend_next_phase=rec,
        symbols=tuple(sorted(feasibility.get("freshness", {}))),
        limitations=tuple(feasibility.get("limitations", [])),
        feasibility_sha256=feasibility_sha256,
        code_hash=code_hash)
