"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- report

Frozen ConditionalMlReport: the deterministic, research-only output
of a ConditionalMlEngine run. It carries the fixed alternative grid,
every discovery surface (recovery / entry-selection / interactions /
transitions / symbols / calibration), the GLOBAL multiple-testing
guard, robustness and limitations -- nothing is hidden.

is_production_ready is permanently False (enforced in __post_init__).
emission_check proves the NEVER_EMITTED promotion tokens are absent
from the serialized report.
====================================================
"""

from dataclasses import dataclass, field

from core.research.discovery.constants import NEVER_EMITTED
from core.research.conditional_ml.types import (
    RecoveryFinding, AlternativeEvidence, EntrySelection, InteractionFinding,
    TransitionFinding, SymbolBehaviour, CalibrationBin, CalibrationSummary,
)
from core.research.regime.regime_types import (
    short_id,
    stable_json,
)


@dataclass(frozen=True)
class ConditionalMlReport:
    """Deterministic research output of one 9L run."""

    report_id: str = ""
    phase: str = "9L"
    symbol: str = "UNKNOWN"
    dataset_shape: dict = field(default_factory=dict)
    recovery: tuple = ()
    entry_selection: tuple = ()
    interactions: tuple = ()
    transitions: tuple = ()
    symbols: tuple = ()
    calibration: tuple = ()
    multiple_testing: dict = field(default_factory=dict)
    robustness: dict = field(default_factory=dict)
    limitations: tuple = ()
    research_only: bool = True
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError(
                "conditional ML reports are NEVER production-ready"
            )
        if self.phase != "9L":
            raise ValueError("conditional ML report phase must be 9L")
        if not self.research_only:
            raise ValueError("conditional ML reports must be research-only")
        if not self.report_id:
            object.__setattr__(self, "report_id", self._expected_report_id())
        elif self.report_id != self._expected_report_id():
            raise ValueError("report_id does not match canonical report content")

    def _identity_payload(self):
        return {
            "phase": self.phase,
            "symbol": self.symbol,
            "dataset_shape": self.dataset_shape,
            "recovery": [f.to_dict() for f in self.recovery],
            "entry_selection": [f.to_dict() for f in self.entry_selection],
            "interactions": [f.to_dict() for f in self.interactions],
            "transitions": [f.to_dict() for f in self.transitions],
            "symbols": [f.to_dict() for f in self.symbols],
            "calibration": [f.to_dict() for f in self.calibration],
            "multiple_testing": self.multiple_testing,
            "robustness": self.robustness,
            "limitations": self.limitations,
            "research_only": self.research_only,
            "is_production_ready": self.is_production_ready,
        }

    def _expected_report_id(self):
        return short_id("L", self.symbol, stable_json(self._identity_payload()))

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        required=("report_id","phase","symbol","dataset_shape","recovery",
                  "entry_selection","interactions","transitions","symbols",
                  "calibration","multiple_testing","robustness","limitations",
                  "research_only","is_production_ready")
        missing=[k for k in required if k not in payload]
        if missing:
            raise ValueError("missing persisted fields: %s" % ", ".join(missing))
        def rows(name):
            v=payload[name]
            if not isinstance(v,(list,tuple)):
                raise ValueError("%s must be a list/tuple" % name)
            return v
        recovery=tuple(RecoveryFinding(**dict(x)) for x in rows("recovery"))
        entries=[]
        for x in rows("entry_selection"):
            d=dict(x); alts=tuple(AlternativeEvidence(**dict(a)) for a in d.pop("alternatives",[])); d["alternatives"]=alts; entries.append(EntrySelection(**d))
        interactions=tuple(InteractionFinding(**dict(x)) for x in rows("interactions"))
        transitions=tuple(TransitionFinding(**dict(x)) for x in rows("transitions"))
        symbols=tuple(SymbolBehaviour(**dict(x)) for x in rows("symbols"))
        calibration=[]
        for x in rows("calibration"):
            d=dict(x); bins=[]
            for b in d.pop("bins",[]):
                b=dict(b); b["bin_index"]=b.pop("bin", b.get("bin_index",0)); bins.append(CalibrationBin(**b))
            d["bins"]=tuple(bins); calibration.append(CalibrationSummary(**d))
        return cls(report_id=payload["report_id"], phase=payload["phase"],
                    symbol=payload["symbol"], dataset_shape=dict(payload["dataset_shape"]),
                    recovery=recovery, entry_selection=tuple(entries),
                    interactions=interactions, transitions=transitions, symbols=symbols,
                    calibration=tuple(calibration), multiple_testing=dict(payload["multiple_testing"]),
                    robustness=dict(payload["robustness"]), limitations=tuple(payload["limitations"]),
                    research_only=payload["research_only"],
                    is_production_ready=payload["is_production_ready"])

    # -------------------------------------------------

    def emission_check(self):
        blob = stable_json(self.to_dict())
        present = [tok for tok in NEVER_EMITTED if tok in blob]
        return {
            "clean": not present,
            "never_emitted": list(NEVER_EMITTED),
            "present": present,
        }

    def overview(self):
        mt = self.multiple_testing or {}
        return {
            "report_id": self.report_id,
            "phase": self.phase,
            "opportunities": (self.dataset_shape or {}).get(
                "opportunities", 0),
            "recovery_findings": len(self.recovery),
            "entry_selection_cells": len(self.entry_selection),
            "interaction_findings": len(self.interactions),
            "transition_buckets": len(self.transitions),
            "symbol_cells": len(self.symbols),
            "calibration_surfaces": len(self.calibration),
            "total_hypotheses": mt.get("total_hypotheses", 0),
            "corrected_alpha": mt.get("corrected_alpha"),
            "n_survive_familywise": mt.get("n_survive", 0),
            "is_production_ready": self.is_production_ready,
        }

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "phase": self.phase,
            "symbol": self.symbol,
            "dataset_shape": dict(self.dataset_shape),
            "recovery": [f.to_dict() for f in self.recovery],
            "entry_selection": [f.to_dict() for f in self.entry_selection],
            "interactions": [f.to_dict() for f in self.interactions],
            "transitions": [f.to_dict() for f in self.transitions],
            "symbols": [f.to_dict() for f in self.symbols],
            "calibration": [c.to_dict() for c in self.calibration],
            "multiple_testing": {
                k: (dict(v) if isinstance(v, dict) else v)
                for k, v in self.multiple_testing.items()
            },
            "robustness": dict(self.robustness),
            "limitations": list(self.limitations),
            "research_only": self.research_only,
            "is_production_ready": self.is_production_ready,
        }

    # -------------------------------------------------

    def render(self):
        lines = []
        lines.append("=" * 60)
        lines.append("Conditional ML / Opportunity Discovery (Phase 9L)")
        lines.append("=" * 60)
        lines.append("report      : %s" % self.report_id)
        lines.append("opportunities: %s" % (self.dataset_shape or {}).get(
            "opportunities", 0))
        lines.append("phase       : research-only, NEVER production-ready")
        lines.append("")
        mt = self.multiple_testing or {}
        lines.append("Fixed alternative grid: %s" % (
            ", ".join((self.robustness or {}).get(
                "alternatives_grid", ()))))
        lines.append("Hypotheses family: %d (corrected alpha %s, %d survive)" % (
            mt.get("total_hypotheses", 0),
            mt.get("corrected_alpha"),
            mt.get("n_survive", 0)))
        lines.append("")
        lines.append("Recovery probability (missed/rejected):")
        for f in self.recovery:
            lines.append("  %-20s %-10s n=%-3d p=%-6s E[R]=%-6s dd=%-6s loss=%-6s [%s]" % (
                f.alternative, f.regime, f.n,
                "%.3f" % f.p_recovery if f.p_recovery is not None else "n/a",
                "%.3f" % f.expected_r if f.expected_r is not None else "n/a",
                "%.3f" % f.expected_drawdown
                if f.expected_drawdown is not None else "n/a",
                "%.3f" % f.loss_probability
                if f.loss_probability is not None else "n/a",
                f.status))
        lines.append("")
        lines.append("Entry-model selection (conditional per cell):")
        for e in self.entry_selection:
            lines.append("  %-14s selected=%s [%s] famw=%s" % (
                e.cell_id, e.selected, e.status, e.survives_familywise))
        lines.append("")
        lines.append("Regime-conditional interactions: %d tested, %d supported" % (
            len(self.interactions),
            sum(1 for i in self.interactions
                if i.status == "INTERACTION_SUPPORTED")))
        lines.append("")
        lines.append("Regime transitions (generated -> filled):")
        for t in self.transitions:
            lines.append("  %-10s -> %-10s n=%-3d avgR=%-6s [%s]" % (
                t.generated_regime, t.filled_regime, t.n,
                "%.3f" % t.avg_r if t.avg_r is not None else "n/a",
                t.status))
        lines.append("")
        lines.append("Symbol segmentation:")
        for s in self.symbols:
            lines.append("  %-10s %-10s n=%-3d avgR=%-6s justified=%s" % (
                s.symbol, s.regime, s.n,
                "%.3f" % s.avg_r if s.avg_r is not None else "n/a",
                s.justified))
        lines.append("")
        lines.append("Confidence / calibration (OOS):")
        for c in self.calibration:
            lines.append("  %-22s n=%-3d ece=%-6s brier=%-6s [%s]" % (
                c.surface, c.oos_n,
                "%.4f" % c.ece if c.ece is not None else "n/a",
                "%.4f" % c.brier if c.brier is not None else "n/a",
                c.status))
        lines.append("")
        lines.append("Limitations:")
        for l in self.limitations:
            lines.append("  - %s" % l)
        lines.append("")
        lines.append("emission_check: %s" % self.emission_check())
        return "\n".join(lines)