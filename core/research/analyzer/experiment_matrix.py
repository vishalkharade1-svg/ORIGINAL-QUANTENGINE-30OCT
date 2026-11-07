"""
====================================================

QuantEngine

Research Analyzer -- experiment matrix (Phase 9D)

Deterministic expression of research dimensions into a set of
independent CounterfactualConfigs, evaluated independently via the
frozen 9C runner. It composes (not reimplements) the frozen 9B
ParameterGrid for the experiment-field dimensions and crosses them
with the 9C-only outcome horizon.

Guarantees (identical spirit to 9B/9C):
   * caller insertion order is preserved for override keys
   * base config is frozen and never mutated
   * every combination gets a fresh independent CounterfactualConfig
   * every config gets a deterministic experiment id (9B hash scheme)
   * empty ranges yield zero combinations deterministically
   * no overrides yields exactly the baseline configuration
   * unknown parameters fail loudly (via ExperimentConfig contract)
   * experiments share no mutable state and are never blended

No ranking / optimization: the matrix only reports what happened
under each explicitly specified configuration.
====================================================
"""

from core.research.lab.parameter_grid import ParameterGrid
from core.research.counterfactual.counterfactual_config import (
    CounterfactualConfig,
)
from core.research.counterfactual.counterfactual_runner import (
    CounterfactualRunner,
)


class ExperimentMatrix:
    """Express research dimensions as deterministic configs."""

    def __init__(self, candles, baseline_id="baseline"):
        self.candles = candles
        self.baseline_id = baseline_id

    # -------------------------------------------------

    def spec(self, base_config, **overrides):
        """Deterministic list of CounterfactualConfig combinations.

        override keys are ExperimentConfig fields (plus the
        `expiry_bars` alias and the 9C-only `outcome_bars`); the
        `outcome_bars` options are crossed with the experiment-field
        combinations that ParameterGrid produces.
        """
        if not isinstance(base_config, CounterfactualConfig):
            raise TypeError(
                "base_config must be a CounterfactualConfig, got "
                f"{type(base_config).__name__}"
            )

        exp_override = {k: v for k, v in overrides.items() if k != "outcome_bars"}
        outcome_options = list(overrides.get(
            "outcome_bars", [None]
        )) if "outcome_bars" in overrides else [base_config.outcome_bars]

        grid = ParameterGrid(self.candles, baseline_id=self.baseline_id)
        combos = []

        for exp_cfg in grid.combos(base_config.to_config(), **exp_override):
            for horizon in outcome_options:
                combos.append(CounterfactualConfig(
                    params=dict(exp_cfg.to_params()),
                    outcome_bars=horizon,
                    baseline_id=self.baseline_id,
                ))
        return combos

    # -------------------------------------------------

    def run(self, opportunities, base_config, **overrides):
        """Evaluate every combination independently.

        Returns [(CounterfactualConfig, [CounterfactualOutcome])] in
        the deterministic spec order. The runner only reads; outcomes
        are COUNTERFACTUAL and never touch any ledger.
        """
        runner = CounterfactualRunner(self.candles, baseline_id=self.baseline_id)
        return [
            (config, runner.run_config(opportunities, config))
            for config in self.spec(base_config, **overrides)
        ]