"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- report

Frozen RegimeReport: the deterministic, research-only output of an
OpportunityDiscoveryEngine run. It carries regime segmentation, every
conditional cell and finding (none hidden), feature splits, walk-
forward survival, the multiple-testing guard and robustness coverage.

is_production_ready is permanently False (frozen + enforced in
__post_init__); emission_check proves the NEVER_EMITTED promotion
tokens are absent from the serialized report.
====================================================
"""

from dataclasses import dataclass, field

from core.research.discovery.constants import NEVER_EMITTED
from core.research.regime.regime_types import (
    short_id,
    stable_json,
)


@dataclass(frozen=True)
class RegimeReport:
    """Deterministic research output of one 9K run."""

    report_id: str = ""
    phase: str = "9K"
    symbol: str = "UNKNOWN"
    dataset_shape: dict = field(default_factory=dict)
    cells: tuple = ()
    findings: tuple = ()
    feature_splits: tuple = ()
    walk_forward: dict = field(default_factory=dict)
    multiple_testing: dict = field(default_factory=dict)
    robustness: dict = field(default_factory=dict)
    limitations: tuple = ()
    next_research: tuple = ()
    research_only: bool = True
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError(
                "regime reports are NEVER production-ready"
            )
        if not self.report_id:
            content = {
                "phase": self.phase,
                "symbol": self.symbol,
                "dataset_shape": self.dataset_shape,
                "cells": [c.to_dict() for c in self.cells],
                "findings": [f.to_dict() for f in self.findings],
                "limitations": self.limitations,
            }
            object.__setattr__(
                self, "report_id", short_id("K", self.symbol, stable_json(content))
            )

    # -------------------------------------------------

    def emission_check(self):
        blob = stable_json(self.to_dict())
        present = [tok for tok in NEVER_EMITTED if tok in blob]
        return {
            "clean": not present,
            "never_emitted": list(NEVER_EMITTED),
            "present": present,
        }

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "phase": self.phase,
            "symbol": self.symbol,
            "dataset_shape": dict(self.dataset_shape),
            "cells": [c.to_dict() for c in self.cells],
            "findings": [f.to_dict() for f in self.findings],
            "feature_splits": [s.to_dict() for s in self.feature_splits],
            "walk_forward": {
                k: dict(v) for k, v in self.walk_forward.items()
            },
            "multiple_testing": dict(self.multiple_testing),
            "robustness": dict(self.robustness),
            "limitations": list(self.limitations),
            "next_research": list(self.next_research),
            "research_only": self.research_only,
            "is_production_ready": self.is_production_ready,
        }

    # -------------------------------------------------

    def render(self):
        lines = []
        lines.append("=" * 60)
        lines.append("Regime / Opportunity Discovery Report (Phase 9K)")
        lines.append("=" * 60)
        lines.append("report        : %s" % self.report_id)
        lines.append("symbol        : %s" % self.symbol)
        lines.append("observations  : %s" % self.dataset_shape.get(
            "observations", 0))
        lines.append("phase         : research-only, NEVER production-ready")
        lines.append("")
        lines.append("Segmentation by category:")
        for cat, count in (self.dataset_shape.get("by_category") or {}).items():
            lines.append("  %-22s %d" % (cat, count))
        lines.append("")
        lines.append("Regime coverage:")
        for dim, cov in (self.dataset_shape.get("regime_coverage") or {}).items():
            if not isinstance(cov, dict):
                continue
            lines.append("  %-22s %d/%d (%.0f%%)" % (
                dim, cov.get("available", 0), cov.get("total", 0),
                cov.get("rate", 0.0) * 100.0))
        lines.append("")
        lines.append("Conditional cells (candidate x regime):")
        for c in self.cells:
            lines.append("  %-8s %-14s n=%-3d cand=%s base=%s recov=%d" % (
                c.config_id[:8], "%s=%s" % (c.dimension, c.label),
                c.n,
                "%.3f" % c.expectancy if c.expectancy is not None else "n/a",
                "%.3f" % c.baseline_expectancy
                if c.baseline_expectancy is not None else "n/a",
                c.recovered))
        lines.append("")
        lines.append("Conditional findings:")
        for f in self.findings:
            lines.append("  [%s] %s" % (f.status, f.statement))
        lines.append("")
        lines.append("Walk-forward survival: %d validated" % len(
            self.walk_forward))
        for fid, summ in self.walk_forward.items():
            lines.append("  %s survived=%s validation_n=%d" % (
                fid[:8], summ.get("survived"), summ.get("validation_n", 0)))
        lines.append("")
        mt = self.multiple_testing or {}
        lines.append("Multiple-testing guard: hypotheses=%d corrected_alpha=%s n_survive=%d" % (
            mt.get("n_hypotheses_tested", 0),
            mt.get("corrected_alpha"),
            mt.get("n_survive", 0)))
        lines.append("")
        if self.feature_splits:
            lines.append("Feature splits (observed 9F values only):")
            for s in self.feature_splits:
                lines.append("  %s=%s n=%-3d win=%.3f avg_r=%s" % (
                    s.feature, s.value, s.n,
                    s.win_rate if s.win_rate is not None else -1,
                    "%.3f" % s.avg_r if s.avg_r is not None else "n/a"))
        lines.append("")
        lines.append("Limitations:")
        for l in self.limitations:
            lines.append("  - %s" % l)
        lines.append("")
        lines.append("emission_check: %s" % self.emission_check())
        return "\n".join(lines)