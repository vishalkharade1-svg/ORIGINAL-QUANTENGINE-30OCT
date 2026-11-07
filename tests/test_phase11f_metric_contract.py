"""Phase 11F-3 metric-contract tests (reuse certified semantics).

No second Sharpe/Sortino implementation: all values flow from
research.phase11e.common.trade_metrics (parity-tested vs
PerformanceAnalytics). Mutations (gross-from-net, return
denominator, omitted fees, wrong denominator) must be detected.
Hand-computed expectations only.
"""

import unittest

from research.phase11e.common import trade_metrics as certified
from research.phase11f import metrics as M
from research.phase11f import validation as V


def _trade(net, gross=None, entry=100.0, qty=1.0, comm=0.0, slip=0.0,
           risk=10.0, t_in=1, t_out=2):
    return {"net": net, "gross": net if gross is None else gross,
            "entry": entry, "quantity": qty, "commission": comm,
            "slippage": slip, "risk_amount": risk,
            "exit_time": t_out, "entry_time": t_in}


class TestMetricReuse(unittest.TestCase):
    def test_adapter_equals_certified(self):
        trades = [_trade(8.5, gross=10.0, comm=1.0, slip=0.5, risk=5.0),
                  _trade(-6.0, gross=-5.0, comm=0.5, slip=0.5, risk=5.0)]
        m = M.research_trade_metrics(trades)
        base = certified(trades)
        for key in ("gross_pnl", "fees", "slippage", "net_pnl", "expectancy",
                    "profit_factor", "max_drawdown", "sharpe", "sortino"):
            self.assertAlmostEqual(m[key], base[key], msg=key)
        self.assertAlmostEqual(m["funding"], 0.0)

    def test_field_distinctions_hand_computed(self):
        trades = [_trade(8.5, gross=10.0, comm=1.0, slip=0.5, risk=5.0),
                  _trade(-6.0, gross=-5.0, comm=0.5, slip=0.5, risk=5.0)]
        m = M.research_trade_metrics(trades)
        self.assertAlmostEqual(m["gross_pnl"], 5.0)
        self.assertAlmostEqual(m["fees"], 1.5)
        self.assertAlmostEqual(m["slippage"], 1.0)
        self.assertAlmostEqual(m["funding"], 0.0)
        self.assertAlmostEqual(m["net_pnl"], 2.5)
        self.assertEqual((m["wins"], m["losses"], m["breakevens"]), (1, 1, 0))
        self.assertLess(m["net_consistency_diff"], 1e-9)

    def test_trade_return_semantics_certified(self):
        # Sharpe/Sortino rest on pnl/notional position returns, not
        # raw dollar PnL: scaling quantity must not move Sharpe.
        small = [_trade(1.0, entry=100.0, qty=1.0, risk=1.0),
                 _trade(-0.5, entry=100.0, qty=1.0, risk=1.0)]
        big = [_trade(10.0, entry=100.0, qty=10.0, risk=10.0),
               _trade(-5.0, entry=100.0, qty=10.0, risk=10.0)]
        self.assertAlmostEqual(certified(small)["sharpe"],
                               certified(big)["sharpe"])


class TestMetricMutations(unittest.TestCase):
    def test_mut_metric_1_gross_from_net_detected(self):
        # MUT-METRIC-1: gross fabricated from net (inverts the ledger).
        trades = [_trade(8.5, gross=8.5, comm=1.0, slip=0.5, risk=5.0)]
        m = M.research_trade_metrics(trades)
        # gross(8.5) - fees(1.0) - slip(0.5) = 7.0 != booked net 8.5.
        self.assertGreater(m["net_consistency_diff"], 0.5)
        clean = M.research_trade_metrics(
            [_trade(8.5, gross=10.0, comm=1.0, slip=0.5, risk=5.0)])
        self.assertLess(clean["net_consistency_diff"], 1e-9)

    def test_mut_metric_2_wrong_return_denominator_detected(self):
        # MUT-METRIC-2: dollar-PnL Sharpe substituted for position-return
        # Sharpe. With non-uniform notionals the two must differ; the
        # certified path must follow returns (uniform-notional rescale
        # leaves it unchanged, dollar rescale does not).
        import statistics
        trades = [_trade(20.0, entry=100.0, qty=2.0, risk=10.0),   # r=+0.10
                  _trade(-10.0, entry=100.0, qty=1.0, risk=10.0)]  # r=-0.10
        certified_sharpe = certified(trades)["sharpe"]
        nets = [20.0, -10.0]
        dollar_sharpe = (sum(nets) / len(nets)) / statistics.stdev(nets) * (2 ** 0.5)
        self.assertNotAlmostEqual(certified_sharpe, dollar_sharpe)
        self.assertAlmostEqual(certified_sharpe, 0.0)  # mean return is 0
        rescaled = [_trade(0.10, entry=1.0, qty=1.0, risk=0.1),
                    _trade(-0.10, entry=1.0, qty=1.0, risk=0.1)]
        self.assertAlmostEqual(certified_sharpe, certified(rescaled)["sharpe"])

    def test_fees_omitted_from_net_detected(self):
        trades = [_trade(8.5, gross=10.0, comm=1.0, slip=0.5, risk=5.0)]
        m = M.research_trade_metrics(trades)
        mutant_net = m["gross_pnl"] - m["slippage"]  # fees dropped
        self.assertNotAlmostEqual(mutant_net, m["net_pnl"])

    def test_wrong_denominator_detected(self):
        # Expectancy divides by ALL trades (breakevens included).
        trades = [_trade(10.0, risk=5.0), _trade(-4.0, risk=5.0),
                  _trade(0.0, risk=5.0)]
        m = M.research_trade_metrics(trades)
        self.assertAlmostEqual(m["expectancy"], 2.0)  # 6/3, not 6/2
        self.assertEqual(m["breakevens"], 1)


if __name__ == "__main__":
    unittest.main()
