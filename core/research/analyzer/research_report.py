"""
====================================================

QuantEngine

Research Analyzer -- research report (Phase 9D)

A deterministic, machine- AND human-readable report of a research
run. It carries exact experiment provenance (experiment_id + the
exact CounterfactualConfig) alongside every metric / comparison /
recovery / robustness section.

Explicit non-claims are always included: the report states the
results are in-sample research facts only, that no configuration is
promoted, and that conclusions require OOS validation -- this is the
ANALYZER-NOT-OPTIMIZER contract.
====================================================
"""

_SECTIONS = (
    "BASELINE",
    "EXPERIMENTS",
    "RECOVERY",
    "REJECTED_OPPORTUNITIES",
    "ENTRY_MODEL_COMPARISON",
    "DIRECTIONAL_BREAKDOWN",
    "METRICS",
    "ROBUSTNESS",
    "WARNINGS",
)


class ResearchReport:
    """Deterministic report container. Assembles from facts the
    analyzer has already computed (never computes anything itself)."""

    def __init__(self, baseline_id="baseline", baseline_metrics=None,
                 population=None, experiments=None, rejected=None,
                 entry_model_comparison=None, directional=None,
                 warnings=None):
        self.baseline_id = baseline_id
        self.baseline_metrics = dict(baseline_metrics or {})
        self.population = dict(population or {})
        self.experiments = experiments or []
        self.rejected = rejected or {}
        self.entry_model_comparison = entry_model_comparison or {}
        self.directional = directional or {}
        self.warnings = list(warnings or [])

    # -------------------------------------------------

    def to_dict(self):
        return {
            "phase": "9D",
            "baseline_id": self.baseline_id,
            "baseline_metrics": self.baseline_metrics,
            "population": self.population,
            "experiments": [e.to_dict() for e in self.experiments],
            "entry_model_comparison": self.entry_model_comparison,
            "directional": self.directional,
            "rejected": self.rejected,
            "robustness_warnings": self.warnings,
            "statement": (
                "In-sample research facts only. No configuration is "
                "promoted, no production change is recommended, no "
                "statistical significance is claimed. Any apparent "
                "improvement requires out-of-sample validation before "
                "production consideration."
            ),
        }

    # -------------------------------------------------

    def render(self):
        """Deterministic human-readable text rendering."""
        lines = [
            "=" * 60,
            f"PHASE 9D RESEARCH REPORT (baseline={self.baseline_id})",
            "=" * 60,
            "",
        ]
        bm = self.baseline_metrics
        lines.append(
            f"BASELINE: {bm.get('opportunities', 0)} opportunities, "
            f"{bm.get('filled', 0)} filled, "
            f"{bm.get('settled', 0)} settled, "
            f"win_rate={bm.get('win_rate', 0.0):.1f}%, "
            f"PF={bm.get('profit_factor', 0.0)}, "
            f"expectancy={bm.get('expectancy', 0.0):.3f}, "
            f"total_R={bm.get('total_R', 0.0):.2f}"
        )
        lines.append(f"population: {self.population}")
        lines.append("")

        for exp in self.experiments:
            d = exp.to_dict()
            lines.append("-" * 60)
            lines.append(f"EXPERIMENT {d['experiment_id']}")
            lines.append(f"  config: {d['config']}")
            m = d["metrics"]
            lines.append(
                f"  evaluated={m.get('evaluated', 0)} filled="
                f"{m.get('filled', 0)} wins={m.get('wins', 0)} "
                f"losses={m.get('losses', 0)} expectancy="
                f"{m.get('expectancy', 0.0):.3f} PF="
                f"{m.get('profit_factor', 0.0)} total_R="
                f"{m.get('total_R', 0.0):.2f}"
            )
            cmp_ = d.get("comparison", {})
            if cmp_:
                lines.append(
                    f"  vs baseline: +{cmp_.get('incremental_fills', 0)} "
                    f"fills, +{cmp_.get('incremental_wins', 0)} wins, "
                    f"+{cmp_.get('incremental_losses', 0)} losses, "
                    f"incremental_R={cmp_.get('incremental_R', 0.0):.2f}, "
                    f"delta_expectancy="
                    f"{cmp_.get('delta_expectancy', 0.0):.3f}"
                )
            rec = d.get("recovery", {})
            if rec:
                lines.append(
                    f"  recovery: {rec.get('recovered', 0)} recovered "
                    f"({rec.get('recovered_wins', 0)} wins / "
                    f"{rec.get('recovered_losses', 0)} losses), "
                    f"recovery_rate={rec.get('recovery_rate', 0.0):.2f}, "
                    f"incremental_R={rec.get('incremental_R', 0.0):.2f}"
                )
            rob = d.get("robustness", [])
            for w in rob:
                lines.append(f"  [warning] {w}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("WARNINGS")
        lines.append("=" * 60)
        for w in self.warnings:
            lines.append(f"- {w}")
        lines.append("")
        lines.append(self.to_dict()["statement"])
        return "\n".join(lines)