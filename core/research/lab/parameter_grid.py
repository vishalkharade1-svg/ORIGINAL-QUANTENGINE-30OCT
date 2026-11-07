"""
====================================================

QuantEngine

Research Lab -- parameter grid (Phase 9B)

A THIN orchestration layer that deterministically generates the
Cartesian product of explicitly supplied parameter ranges and runs
every configuration as an independent experiment.

It contains NO trading / entry / breakout / risk / PnL / indicator
logic -- that all lives in the experiment runner. It only answers:

    "What happened under each explicitly specified configuration?"

It does NOT rank, optimize, or select configurations. Automatic
optimization is deferred to a later research/AI layer.

Guarantees:
   * caller insertion order is preserved for override keys
   * base_config is never mutated
   * every combination gets a fresh ExperimentConfig
   * every experiment gets a deterministic, non-random experiment id
   * no cross-experiment shared mutable state
====================================================
"""

from itertools import product

from core.research.lab.experiment_config import ExperimentConfig
from core.research.lab.experiment_runner import (
    ExperimentRunner,
    experiment_id_for,
)

# Public research-grid keys that map to ExperimentConfig fields.
# Kept deliberately small; unknown keys fail loudly.
_FIELD_ALIASES = {
    "expiry_bars": "expiry",
}


class ParameterGrid:
    """Deterministic Cartesian parameter sweep."""

    def __init__(self, candles, baseline_id="baseline"):
        self.runner = ExperimentRunner(
            candles,
            baseline_id=baseline_id,
        )

    def combos(self, base_config, **overrides):
        """
        Yield one fresh ExperimentConfig per Cartesian combination.

        Override keys may be canonical ExperimentConfig field names
        or explicitly supported research aliases.

        Caller insertion order is preserved.
        """

        keys = list(overrides.keys())

        # No overrides means exactly one baseline configuration.
        if not keys:
            yield ExperimentConfig(**base_config.to_params())
            return

        ranges = [overrides[key] for key in keys]

        # itertools.product naturally gives zero combinations when
        # any supplied range is empty.
        for values in product(*ranges):
            params = base_config.to_params()

            for key, value in zip(keys, values):
                field = _FIELD_ALIASES.get(key, key)

                if field not in params:
                    raise KeyError(
                        f"Unknown ExperimentConfig parameter: {key!r}"
                    )

                params[field] = value

            yield ExperimentConfig(**params)

    def sweep(self, opportunities, base_config, **overrides):
        """
        Run every parameter combination independently.

        Returns exactly one ExperimentResult per generated configuration.
        """
        results = []

        for config in self.combos(base_config, **overrides):
            experiment_id = experiment_id_for(
                config,
                self.runner.baseline_id,
            )

            result = self.runner.run(
                opportunities,
                config,
                experiment_id=experiment_id,
            )

            results.append(result)

        return results
