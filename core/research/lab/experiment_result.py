"""
====================================================

QuantEngine

Research Lab -- experiment result (Phase 9B)

A machine-readable, deterministic result for one experiment:
experiment_id, baseline_id, config, population, metrics, recovery,
attribution and warnings. JSON-compatible via to_dict().

Scientific boundary: the result reports OBSERVATION / SIMULATION
metrics only. It NEVER asserts "this strategy is superior" -- that
requires out-of-sample validation outside this phase.
====================================================
"""


class ExperimentResult:
    """Deterministic container for one experiment's output."""

    def __init__(self, experiment_id, baseline_id, config, population,
                 metrics, recovery=None, attribution=None, warnings=None,
                 outcomes=None):
        self.experiment_id = experiment_id
        self.baseline_id = baseline_id
        self.config = config
        self.population = population or {}
        self.metrics = metrics or {}
        self.recovery = recovery or {}
        self.attribution = attribution or {}
        self.warnings = warnings or []
        self.outcomes = outcomes or []

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "baseline_id": self.baseline_id,
            "config": self.config.to_dict() if self.config else {},
            "population": self.population,
            "metrics": self.metrics,
            "recovery": self.recovery,
            "attribution": self.attribution,
            "warnings": list(self.warnings),
        }

    def summary(self):
        """Human-readable one-line overview."""
        m = self.metrics
        return (
            f"experiment={self.experiment_id} "
            f"against baseline={self.baseline_id} | "
            f"{m.get('opportunities_evaluated')} opportunities, "
            f"{m.get('settled')} settled, "
            f"win_rate={m.get('win_rate', 0.0):.1f}%, "
            f"PF={_pf(m.get('profit_factor'))}, "
            f"expectancy={m.get('expectancy', 0.0):.3f}, "
            f"total_R={m.get('total_R', 0.0):.2f}"
        )


def _pf(x):
    if x is None or x == float("inf"):
        return "inf"
    return round(x, 2)
