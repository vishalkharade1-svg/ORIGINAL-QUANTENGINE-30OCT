"""
====================================================

QuantEngine

Phase 9B -- Deterministic Parameter Experimentation
(ParameterGrid) tests.

Run with:

    python -m unittest tests.test_parameter_grid -v

Proves the ParameterGrid is a thin, deterministic, isolated
Cartesian sweep layer:

   * expiry_bars alias -> ExperimentConfig.expiry
   * canonical fields (rr) work without alias
   * unknown keys raise KeyError loudly
   * deterministic cartesian order (caller insertion order)
   * no overrides -> exactly one baseline config
   * empty range -> zero configs
   * exact cartesian count
   * base_config never mutated (combos + sweep)
   * exact configuration retained in every ExperimentResult
   * deterministic + unique experiment IDs
   * repeatable sweep ordering
   * experiment isolation (no shared mutable state)
   * failure isolation (one bad opportunity never corrupts others)

Stdlib only; offline; deterministic.
====================================================
"""

import unittest

from core.research.lab import (
    ExperimentConfig,
    ExperimentRunner,
    ParameterGrid,
    experiment_id_for,
)
from core.research.journal import OpportunityRecord


def record(canonical, bar=0, direction="BULLISH", terminal="ORDER_NOT_CREATED",
           entry=100.0, stop=98.0, target=104.0, rr=2.0):
    return OpportunityRecord(
        canonical_id=canonical,
        exchange="TESTEX",
        instrument_id=canonical,
        timeframe="1m",
        direction=direction,
        strategy="BREAKOUT_CONTINUATION",
        setup_id=canonical,
        setup={
            "entry": entry, "stop_loss": stop, "take_profit": target,
            "risk_reward": rr, "bar": bar, "rejection_reasons": [],
        },
        order={},
        terminal_outcome=terminal,
    )


class Candle:
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.timestamp = ts


def tiny_candles():
    return [
        Candle(100.0, 101.0, 99.0, 100.0, 0),
        Candle(100.0, 101.0, 99.0, 101.0, 1),
        Candle(101.0, 105.0, 100.0, 104.0, 2),
    ]


class TestCombos(unittest.TestCase):

    def test_expiry_bars_maps_to_expiry(self):
        grid = ParameterGrid(tiny_candles())
        configs = list(grid.combos(ExperimentConfig(), expiry_bars=[5]))
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].expiry, 5)
        self.assertEqual(configs[0].entry_offset_atr, 0.0)

    def test_canonical_field_no_alias(self):
        grid = ParameterGrid(tiny_candles())
        configs = list(grid.combos(ExperimentConfig(), rr=[2.0, 3.0]))
        self.assertEqual([c.rr for c in configs], [2.0, 3.0])

    def test_unknown_key_raises_keyerror(self):
        grid = ParameterGrid(tiny_candles())
        with self.assertRaises(KeyError):
            list(grid.combos(ExperimentConfig(), not_a_real_field=[1, 2]))

    def test_cartesian_order_preserved(self):
        grid = ParameterGrid(tiny_candles())
        configs = list(grid.combos(
            ExperimentConfig(), rr=[2, 3], expiry_bars=[10, 20],
        ))
        self.assertEqual(
            [(c.rr, c.expiry) for c in configs],
            [
                (2, 10),
                (2, 20),
                (3, 10),
                (3, 20),
            ],
        )

    def test_no_overrides_produces_one_baseline(self):
        grid = ParameterGrid(tiny_candles())
        configs = list(grid.combos(ExperimentConfig()))
        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0], ExperimentConfig())

    def test_empty_range_produces_zero(self):
        grid = ParameterGrid(tiny_candles())
        self.assertEqual(len(list(grid.combos(ExperimentConfig(), rr=[]))), 0)

    def test_cartesian_count(self):
        grid = ParameterGrid(tiny_candles())
        configs = list(grid.combos(
            ExperimentConfig(),
            rr=[2, 3],
            expiry_bars=[10, 20, 30],
            entry_offset_atr=[0.0, 0.5],
        ))
        self.assertEqual(len(configs), 2 * 3 * 2)  # 12

    def test_base_config_unchanged_after_combos(self):
        grid = ParameterGrid(tiny_candles())
        base = ExperimentConfig(rr=2.0, expiry=30)
        before = base.to_params()
        list(grid.combos(base, rr=[2, 3], expiry_bars=[10, 20]))
        self.assertEqual(base.to_params(), before)


class TestGridIsolation(unittest.TestCase):

    def test_base_config_unchanged_after_sweep(self):
        grid = ParameterGrid(tiny_candles())
        base = ExperimentConfig(rr=2.0, expiry=30)
        before = base.to_params()
        grid.sweep([record("a"), record("b")], base, rr=[2, 3], expiry_bars=[10, 20])
        self.assertEqual(base.to_params(), before)

    def test_config_propagation_in_results(self):
        grid = ParameterGrid(tiny_candles())
        results = grid.sweep(
            [record("a")], ExperimentConfig(), rr=[2, 3], expiry_bars=[10, 20],
        )
        self.assertEqual(
            [(r.config.rr, r.config.expiry) for r in results],
            [(2, 10), (2, 20), (3, 10), (3, 20)],
        )
        for r in results:
            self.assertEqual(r.config.to_dict(), r.to_dict()["config"])

    def test_experiment_id_deterministic(self):
        grid = ParameterGrid(tiny_candles())
        results = grid.sweep([record("a")], ExperimentConfig(), rr=[2, 3])
        self.assertEqual(results[0].experiment_id, results[0].experiment_id)
        again = grid.sweep([record("a")], ExperimentConfig(), rr=[2, 3])
        self.assertEqual(
            [r.experiment_id for r in results],
            [r.experiment_id for r in again],
        )

    def test_experiment_id_uniqueness(self):
        grid = ParameterGrid(tiny_candles())
        results = grid.sweep(
            [record("a")], ExperimentConfig(), rr=[2, 3], expiry_bars=[10, 20],
        )
        ids = {r.experiment_id for r in results}
        self.assertEqual(len(ids), 4)

    def test_same_config_same_id_function(self):
        cfg = ExperimentConfig(rr=3.0, expiry=20)
        self.assertEqual(
            experiment_id_for(cfg, "baseline"),
            experiment_id_for(cfg, "baseline"),
        )

    def test_insertion_order_deterministic_ordering(self):
        grid = ParameterGrid(tiny_candles())
        c1 = list(grid.combos(ExperimentConfig(), rr=[2, 3], expiry_bars=[10, 20]))
        c2 = list(grid.combos(ExperimentConfig(), rr=[2, 3], expiry_bars=[10, 20]))
        self.assertEqual(
            [(c.rr, c.expiry) for c in c1],
            [(c.rr, c.expiry) for c in c2],
        )

    def test_independent_execution_no_shared_state(self):
        # Fake runner that mutates a shared-lookup dict per call; the
        # grid must pass a FRESH config each time and never reuse or
        # cross-contaminate a prior experiment's state.
        seen = {}

        class FakeRunner:
            baseline_id = "baseline"

            def run(self, opportunities, config, experiment_id=None):
                key = (config.rr, config.expiry)
                seen[key] = seen.get(key, 0) + 1
                return experiment_id

        grid = ParameterGrid(tiny_candles())
        grid.runner = FakeRunner()
        grid.sweep([record("a")], ExperimentConfig(), rr=[2, 3], expiry_bars=[10, 20])
        self.assertEqual(seen, {(2, 10): 1, (2, 20): 1, (3, 10): 1, (3, 20): 1})

    def test_failure_isolation_per_opportunity(self):
        # One malformed opportunity must not abort the experiment nor
        # corrupt a subsequent clean run.
        bad = object()  # not an OpportunityRecord -> replay raises
        good = record("good")
        runner = ExperimentRunner(tiny_candles())
        res = runner.run([bad, good], ExperimentConfig())
        self.assertTrue(any("replay failed" in w for w in res.warnings))
        # the good opportunity still produced a (replayed) outcome
        self.assertEqual(res.metrics["opportunities_evaluated"], 1)
        self.assertIn("good", {getattr(o, "opportunity_id", "") for o in res.outcomes})


class TestLabProvenance(unittest.TestCase):

    def test_simulated_trade_is_counterfactual(self):
        from core.research.lab.counterfactual import CounterfactualOutcome
        from core.research.lab.experiment_config import ExperimentConfig
        cfg = ExperimentConfig()
        out = CounterfactualOutcome(
            experiment_id="exp-x", opportunity_id="o1", config=cfg,
            filled=True, result="WIN", pnl=3.0, r=1.5,
            experimental_rr=2.0,
        )
        trade = out.to_trade()
        self.assertTrue(trade.is_counterfactual)
        self.assertEqual(trade.provenance, "COUNTERFACTUAL")
        self.assertEqual(trade.experimental_rr, 2.0)


if __name__ == "__main__":
    unittest.main()
