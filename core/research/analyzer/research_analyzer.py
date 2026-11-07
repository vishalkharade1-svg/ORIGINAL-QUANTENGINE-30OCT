"""
====================================================

QuantEngine

Research Analyzer -- orchestrator (Phase 9D)

The ANALYZER, not an optimizer. It consumes:

    * OpportunityRecords           (the frozen baseline facts)
    * experiment bundles           ((CounterfactualConfig, outcomes))

-- both read-only -- and assembles a deterministic ResearchReport
answering WHAT HAPPENED, WHAT COULD HAVE HAPPENED, WHY IT WAS
MISSED, and WHICH ALTERNATIVE CONFIGURATION RECOVERED IT, together
with the exact config provenance, metrics, recovery, comparison,
directional breakdown, entry-model comparison and robustness
warnings.

It NEVER simulates anything itself (9C owns simulation), never
mutates inputs, never ranks configurations and never recommends
production changes. Configuration errors (missing provenance,
wrong bundle shape) fail loudly; malformed opportunities are
warned and skipped.
====================================================
"""

from dataclasses import dataclass, field

from core.research.counterfactual.counterfactual_config import (
    CounterfactualConfig,
)
from core.research.analyzer.baseline import baseline_view
from core.research.analyzer.experiment_metrics import (
    metrics_for,
    group_metrics,
    group_sizes,
)
from core.research.analyzer.opportunity_analysis import (
    category_distribution,
    rejected_by_reason,
)
from core.research.analyzer.recovery_analysis import RecoveryReport
from core.research.analyzer.comparison import compare_baseline
from core.research.analyzer.robustness import assess as assess_robustness
from core.research.analyzer.research_report import ResearchReport


@dataclass
class ExperimentAnalysis:
    """One experiment's full analysis (config provenance + facts)."""

    config: object
    experiment_id: str = ""
    metrics: dict = field(default_factory=dict)
    recovery: object = None
    comparison: object = None
    robustness: list = field(default_factory=list)
    directional: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "config": self.config.to_dict() if self.config else {},
            "metrics": self.metrics,
            "recovery": self.recovery.to_dict() if self.recovery else {},
            "comparison": self.comparison.to_dict() if self.comparison else {},
            "robustness": list(self.robustness),
            "directional": self.directional,
        }


class ResearchAnalyzer:
    """Orchestrates the read-only 9D analysis pipeline."""

    # -------------------------------------------------

    def analyze(self, records, experiment_bundles, baseline_id="baseline"):
        """Analyze baseline records against experiment bundles.

        experiment_bundles: iterable of (CounterfactualConfig,
        [CounterfactualOutcome]). Order is preserved; results are
        otherwise deterministic.
        """
        records = list(records)
        bundles = list(experiment_bundles)

        baseline_metrics = metrics_for(baseline_view(r) for r in records)
        population = category_distribution(records)
        rejected = rejected_by_reason(records)

        experiments = [
            self._analyze_experiment(
                records, config, outcomes, baseline_metrics, baseline_id
            )
            for config, outcomes in bundles
        ]

        entry_model_comparison = self._entry_model_comparison(bundles)

        directional = {
            e.experiment_id: e.directional for e in experiments
        }

        warnings = []
        if not records:
            warnings.append("empty opportunity set -- analysis is vacuous")
        if not bundles:
            warnings.append("no experiments supplied -- baseline only")
        for e in experiments:
            warnings.extend(e.robustness)

        return ResearchReport(
            baseline_id=baseline_id,
            baseline_metrics=baseline_metrics,
            population=population,
            experiments=experiments,
            rejected=rejected,
            entry_model_comparison=entry_model_comparison,
            directional=directional,
            warnings=list(dict.fromkeys(warnings)),
        )

    # -------------------------------------------------

    def _analyze_experiment(self, records, config, outcomes,
                            baseline_metrics, baseline_id):
        if not isinstance(config, CounterfactualConfig):
            raise TypeError(
                "each experiment bundle must be "
                "(CounterfactualConfig, [outcome, ...]); got config of "
                f"type {type(config).__name__}"
            )
        exp_id = config.experiment_id()
        metrics = metrics_for(outcomes)
        recovery = RecoveryReport(records, outcomes)

        # Like-for-like baseline: restrict the comparison to the very
        # opportunities this experiment evaluated (outcome identity is
        # always preserved), so incremental fills / wins / losses / R
        # are honest deltas, not population artefacts.
        ids = {getattr(o, "opportunity_id", "") for o in outcomes}
        restricted = [
            r for r in records
            if (getattr(r, "canonical_id", "") or "") in ids
        ]
        restricted_baseline = metrics_for(
            baseline_view(r) for r in restricted
        )
        comparison = compare_baseline(
            exp_id, config, baseline_id, restricted_baseline, metrics
        )
        directional_sizes = group_sizes(outcomes, "direction")
        robustness = assess_robustness(
            comparison,
            experiment_metrics=metrics,
            baseline_metrics=baseline_metrics,
            directional_sizes=directional_sizes,
        )

        direction_grouped = group_metrics(outcomes, "direction").get(
            "direction", {}
        )
        directional = {"ALL": metrics}
        directional.update(direction_grouped)

        return ExperimentAnalysis(
            config=config,
            experiment_id=exp_id,
            metrics=metrics,
            recovery=recovery,
            comparison=comparison,
            robustness=robustness,
            directional=directional,
        )

    # -------------------------------------------------

    def _entry_model_comparison(self, bundles):
        models = {}
        for config, outcomes in bundles:
            model = (config.params or {}).get("entry_model") or "UNKNOWN"
            models.setdefault(model, []).extend(outcomes)
        if len(models) <= 1:
            return {}
        return {
            model: metrics_for(outs) for model, outs in sorted(models.items())
        }

    # -------------------------------------------------

    def analyze_results(self, records, outcomes_by_experiment,
                        configs_by_experiment, baseline_id="baseline"):
        """Convenience: accept 9C run_configs-style dict output plus an
        explicit config map. Exact config provenance is REQUIRED --
        a missing config is an explicit configuration error."""
        missing = set(outcomes_by_experiment) - set(configs_by_experiment)
        if missing:
            raise ValueError(
                "exact config provenance required for every experiment; "
                f"missing configs for: {sorted(missing)}"
            )
        bundles = [
            (configs_by_experiment[exp_id],
             outcomes_by_experiment[exp_id])
            for exp_id in sorted(outcomes_by_experiment)
        ]
        return self.analyze(records, bundles, baseline_id)

    # -------------------------------------------------

    def run_and_analyze(self, records, candles, base_config,
                        baseline_id="baseline", **overrides):
        """End-to-end convenience: build + run the matrix via the
        frozen 9C runner, then analyze. Simulation stays in 9C; the
        analyzer only reads the produced facts."""
        from core.research.analyzer.experiment_matrix import ExperimentMatrix

        matrix = ExperimentMatrix(candles, baseline_id=baseline_id)
        bundles = matrix.run(records, base_config, **overrides)
        return self.analyze(records, bundles, baseline_id)