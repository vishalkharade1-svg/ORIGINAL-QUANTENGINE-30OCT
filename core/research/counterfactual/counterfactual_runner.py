"""
====================================================

QuantEngine

Counterfactual Simulation -- runner (Phase 9C)

Batches deterministic counterfactual simulations over many
OpportunityRecords, and integrates natively with the frozen Phase
9B ParameterGrid so every generated configuration is evaluated
independently (no blending, no shared mutable experiment state).

Each result preserves: original opportunity identity + exact
counterfactual config + counterfactual result + deterministic
experiment id.

The runner only READS opportunities + candles. It never writes the
production ledger, portfolio, journal, or any execution state.
====================================================
"""

from core.research.counterfactual.opportunity_simulator import OpportunitySimulator
from core.research.counterfactual.counterfactual_config import CounterfactualConfig


class CounterfactualRunner:
    """Run one or many counterfactual configs over opportunities."""

    def __init__(self, candles, baseline_id="baseline"):
        self.simulator = OpportunitySimulator()
        self.candles = candles
        self.baseline_id = baseline_id

    # -------------------------------------------------

    def run_config(self, opportunities, config, experiment_id=None):
        """Evaluate `config` against each opportunity, independently.
        Returns a list of CounterfactualOutcome (one per opportunity,
        same order)."""
        experiment_id = experiment_id or config.experiment_id()
        return [
            self.simulator.simulate(
                record, config, self.candles, experiment_id=experiment_id
            )
            for record in opportunities
        ]

    def run_configs(self, opportunities, configs):
        """Evaluate many configs independently. Returns a dict
        {experiment_id: [outcome, ...]} -- never blended."""
        results = {}
        for config in configs:
            exp_id = config.experiment_id()
            results[exp_id] = self.run_config(
                opportunities, config, experiment_id=exp_id
            )
        return results

    # -------------------------------------------------

    def grid(self, opportunities, base_config, **overrides):
        """Native Phase 9B ParameterGrid integration. `base_config` is
        a CounterfactualConfig; `overrides` are grid keys (e.g.
        rr=[...], expiry_bars=[...]). Returns a list of
        (CounterfactualConfig, [outcome, ...]) for every combination,
        evaluated independently, in deterministic order."""
        from core.research.lab.parameter_grid import ParameterGrid

        grid = ParameterGrid(self.candles, baseline_id=self.baseline_id)
        combos = list(grid.combos(base_config.to_config(), **overrides))
        results = []
        for cfg in combos:
            cf_config = CounterfactualConfig(
                params=dict(cfg.to_params()),
                outcome_bars=base_config.outcome_bars,
                baseline_id=self.baseline_id,
            )
            outcomes = self.run_config(opportunities, cf_config)
            results.append((cf_config, outcomes))
        return results
