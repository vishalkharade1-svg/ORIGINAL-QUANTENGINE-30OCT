"""
====================================================

QuantEngine

Monte Carlo Simulator Tests

Run with:

    python -m unittest tests.test_monte_carlo -v

Proves the bootstrap resampling layer over the SHARED closed
trade PnL sequence:

    1. Constant sequence: identical trades give a degenerate
       (exact) distribution -- every simulation lands on the
       same net profit, zero drawdown, survival 1.0.
    2. Determinism: the same seed reproduces the same result.
    3. Mixed sequence: distribution overlays the observed
       ordering, drawdown risk is real, percentiles are
       ordered P25 <= P50 <= P95.
    4. Empty sequence: zeroed but valid; all simulations
       survive on the flat starting balance.
    5. Closed-only view: open trades are excluded from the
       sample set, matching analytics.
    6. Summary form renders.

Stdlib only -- no network, no pipeline.

====================================================
"""

import unittest

from core.backtesting.trade_registry import TradeRegistry

from core.validation.monte_carlo import (
    MonteCarloResult,
    MonteCarloSimulator,
)


def make_trade(pnl, status="CLOSED"):
    from core.backtesting.trade import Trade

    trade = Trade(
        direction="BULLISH",
        entry=100.0,
        quantity=1.0,
        exit_price=100.0 + pnl,
        pnl=pnl,
        pnl_percent=pnl,
        bars_held=1,
        status=status,
        result="WIN" if pnl >= 0 else "LOSS",
    )
    return trade


class TestMonteCarloSimulator(unittest.TestCase):

    maxDiff = None

    def test_constant_sequence_is_exact(self):
        trades = [make_trade(1.0) for _ in range(5)]

        result = MonteCarloSimulator(
            trades,
            starting_balance=100.0,
        ).run(simulations=200, seed=7)

        self.assertEqual(result.simulations, 200)
        self.assertEqual(result.trades_count, 5)
        self.assertAlmostEqual(result.mean_net_profit, 5.0, places=6)
        self.assertAlmostEqual(result.p50_net_profit, 5.0, places=6)
        self.assertAlmostEqual(result.p95_max_drawdown, 0.0, places=6)
        self.assertEqual(result.survival_rate, 1.0)
        self.assertEqual(result.worst_net_profit, 5.0)

    def test_reproducible_with_same_seed(self):
        trades = [
            make_trade(10.0),
            make_trade(-7.0),
            make_trade(4.0),
            make_trade(-3.0),
        ]

        a = MonteCarloSimulator(
            trades, starting_balance=1000.0
        ).run(simulations=500, seed=99)

        b = MonteCarloSimulator(
            trades, starting_balance=1000.0
        ).run(simulations=500, seed=99)

        self.assertEqual(a.samples, b.samples)

        c = MonteCarloSimulator(
            trades, starting_balance=1000.0
        ).run(simulations=500, seed=100)

        self.assertNotEqual(a.samples, c.samples)

    def test_mixed_sequence_distribution(self):
        trades = [
            make_trade(10.0),
            make_trade(-7.0),
            make_trade(4.0),
            make_trade(-3.0),
            make_trade(12.0),
        ]

        result = MonteCarloSimulator(
            trades, starting_balance=1000.0
        ).run(simulations=2000, seed=3)

        self.assertTrue(result.p25_net_profit <= result.p50_net_profit)
        self.assertTrue(result.p50_net_profit <= result.p95_net_profit)
        self.assertGreaterEqual(result.mean_max_drawdown, 0.0)
        self.assertGreaterEqual(result.p95_max_drawdown, 0.0)
        self.assertTrue(0.0 <= result.survival_rate <= 1.0)
        # worst case: every draw picks the largest loss (+ duplicates)
        self.assertGreaterEqual(result.worst_net_profit, -40.0)

    def test_empty_sequence_valid(self):
        result = MonteCarloSimulator(
            [], starting_balance=100.0
        ).run(simulations=50, seed=1)

        self.assertEqual(result.trades_count, 0)
        self.assertAlmostEqual(result.mean_net_profit, 0.0, places=6)
        self.assertEqual(result.survival_rate, 1.0)
        self.assertEqual(len(result.samples), 50)

    def test_closed_only_view(self):
        trades = [
            make_trade(2.0),
            make_trade(-1.0, status="OPEN"),
        ]

        result = MonteCarloSimulator(
            trades, starting_balance=100.0
        ).run(simulations=100, seed=5)

        self.assertEqual(result.trades_count, 1)
        self.assertAlmostEqual(result.mean_net_profit, 2.0, places=6)

    def test_registry_input(self):
        registry = TradeRegistry()
        for trade in (make_trade(1.0), make_trade(1.0)):
            registry.add(trade)

        result = MonteCarloSimulator(
            registry, starting_balance=100.0
        ).run(simulations=50, seed=9)

        self.assertEqual(result.trades_count, 2)
        self.assertAlmostEqual(result.mean_net_profit, 2.0, places=6)

    def test_observation_holdout_ranges(self):
        # Error regimes: exactly one bad sim value.
        with self.assertRaises(ValueError):
            MonteCarloSimulator(
                [make_trade(1.0)]
            ).run(simulations=0)

    def test_summary_renders(self):
        result = MonteCarloSimulator(
            [make_trade(1.0)],
            starting_balance=100.0,
        ).run(simulations=10, seed=2)

        text = result.summary(label="MC DEMO")

        self.assertIn("MC DEMO", text)
        self.assertIn("Simulations", text)
        self.assertIn("Survival rate", text)
        self.assertIsInstance(result, MonteCarloResult)


if __name__ == "__main__":
    unittest.main()