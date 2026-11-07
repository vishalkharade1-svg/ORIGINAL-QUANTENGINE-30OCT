"""11G-N feasibility report object (research-only, frozen, never a directive).

Convention follows core/research report contracts: frozen dataclass,
is_production_ready permanently False (enforced in __post_init__),
emission_check() proving non-promotion. Carries the feasibility
record; authorizes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NFeasibilityReport:
    dataset_count: int = 0
    overall_overlap: str = "UNKNOWN"
    walk_forward_verdict: str = "UNKNOWN"
    symbols: tuple = ()
    freshness: tuple = ()
    limitations: tuple = ()
    feasibility_sha256: str = ""
    code_hash: str = ""
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError("NFeasibilityReport is never production-ready")
        allowed_overlap = ("ZERO_OVERLAP", "OVERLAP_DETECTED", "UNKNOWN")
        if self.overall_overlap not in allowed_overlap:
            raise ValueError("bad overlap verdict: %r" % self.overall_overlap)
        allowed_wf = ("WF_FEASIBLE", "FULL_WF_INFEASIBLE", "UNKNOWN")
        if self.walk_forward_verdict not in allowed_wf:
            raise ValueError("bad WF verdict: %r" % self.walk_forward_verdict)

    def emission_check(self):
        return {"clean": True,
                "production_ready": False,
                "is_production_ready": self.is_production_ready,
                "promotion_tokens_absent": True,
                "verdict": self.walk_forward_verdict}

    def to_dict(self):
        return {"dataset_count": self.dataset_count,
                "overall_overlap": self.overall_overlap,
                "walk_forward_verdict": self.walk_forward_verdict,
                "symbols": list(self.symbols),
                "freshness": list(self.freshness),
                "limitations": list(self.limitations),
                "feasibility_sha256": self.feasibility_sha256,
                "code_hash": self.code_hash,
                "is_production_ready": self.is_production_ready}


def from_feasibility(feasibility, feasibility_sha256, code_hash):
    return NFeasibilityReport(
        dataset_count=len(feasibility.get("datasets", {})),
        overall_overlap=feasibility.get("overall_overlap", "UNKNOWN"),
        walk_forward_verdict=feasibility.get("walk_forward", {}).get(
            "verdict", "UNKNOWN"),
        symbols=tuple(sorted(feasibility.get("symbols", {}))),
        freshness=tuple(sorted(
            "%s=%s" % (s, v["classification"])
            for s, v in feasibility.get("freshness", {}).items())),
        limitations=tuple(feasibility.get("limitations", [])),
        feasibility_sha256=feasibility_sha256,
        code_hash=code_hash)
