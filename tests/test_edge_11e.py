"""
====================================================

QuantEngine -- Phase 11E research hypothesis tests.

Validates the 11E research machinery WITHOUT touching
production strategy/risk/execution/safety/config:

  * pre-registered spec conformance (gates, grids, seeds)
  * research metric definitions (hand-computed + parity
    with production PerformanceAnalytics)
  * Monte Carlo / bootstrap determinism
  * break-even arithmetic
  * cost-overlay math

Paper/offline only. Deterministic (fixed seeds).

====================================================
"""

import json
import unittest
from pathlib import Path

RESEARCH = Path("research/phase11e")
SPEC = json.loads((RESEARCH / "spec.json").read_text())

from research.phase11e.common import apply_costs, trade_metrics
from research.phase11e.step4_analysis import (
    bootstrap_mean,
    mc_shuffle,
)
from research.phase11e.step5_regimes import (
    calibration_for_fold,
    classify_fold,
    filter_prior,
    vol_thresholds,
)
from research.phase11e.step7_random_baseline import (
    N_DRAWS,
    TRADE_COST,
    run_all_folds,
    run_fold,
    simulate_fold,
)


def _bars(n=300, start=1787000000, step=60, base=100.0):
    return [
        {"time": start + step * i, "open": base + i,
         "high": base + i + 1.0, "low": base + i - 1.0,
         "close": base + i + 0.5, "volume": 10.0}
        for i in range(n)
    ]


def _trade(net, entry=100.0, qty=1.0, risk=10.0):
    return {
        "net": net, "gross": net, "entry": entry, "quantity": qty,
        "commission": 0.0, "slippage": 0.0, "risk_amount": risk,
        "exit_time": 0, "entry_time": 0,
    }


class TestSpecConformance(unittest.TestCase):
    """The pre-registered spec is complete and frozen."""

    def test_all_gates_defined(self):
        keys = list(SPEC["gates"])
        self.assertEqual(len(keys), 12)
        for i in range(1, 13):
            matches = [k for k in keys if k.split("_")[0] == "E%d" % i]
            self.assertEqual(len(matches), 1)
            self.assertIn("pass", SPEC["gates"][matches[0]])

    def test_sensitivity_grid_frozen(self):
        names = [v["name"] for v in SPEC["sensitivity_grid"]["variants"]]
        self.assertEqual(
            names,
            ["baseline", "wait25", "wait35", "delay2", "width008", "width012"],
        )

    def test_mc_design_matches(self):
        mc = SPEC["monte_carlo"]
        self.assertEqual(mc["trade_order_shuffle"]["sims"], 5000)
        self.assertEqual(mc["trade_order_shuffle"]["seed"], 1107001)
        self.assertEqual(mc["bootstrap_expectancy"]["seed"], 1107002)

    def test_cost_scenarios_match(self):
        from research.phase11e.common import COST_SCENARIOS

        for key, spec in SPEC["costs"].items():
            if not key.startswith(("A_", "B_", "C_", "D_")):
                continue
            self.assertEqual(COST_SCENARIOS[key]["COMMISSION_RATE"], spec["COMMISSION_RATE"])
            self.assertEqual(COST_SCENARIOS[key]["SLIPPAGE_BPS"], spec["SLIPPAGE_BPS"])

    def test_fingerprint_matches_gate_a(self):
        fp = SPEC["frozen_baseline"]["gate_a_fingerprint"]
        self.assertEqual(
            (fp["orders"], fp["fills"], fp["wins"], fp["losses"], fp["breakevens"]),
            (27, 11, 6, 5, 0),
        )
        self.assertAlmostEqual(fp["net_pnl"], 0.117534)


class TestResearchMetrics(unittest.TestCase):
    """Hand-computed metric definitions."""

    def test_expectancy_pf_winrate(self):
        m = trade_metrics([_trade(10.0), _trade(-5.0), _trade(0.0), _trade(20.0)])
        self.assertEqual(m["trades"], 4)
        self.assertEqual((m["wins"], m["losses"], m["breakevens"]), (2, 1, 1))
        self.assertAlmostEqual(m["expectancy"], 6.25)
        self.assertAlmostEqual(m["profit_factor"], 6.0)
        self.assertAlmostEqual(m["win_rate"], 50.0)

    def test_drawdown(self):
        m = trade_metrics([_trade(10.0), _trade(-30.0), _trade(5.0)])
        self.assertAlmostEqual(m["max_drawdown"], 30.0)
        self.assertAlmostEqual(m["net_pnl"], -15.0)

    def test_r_multiples(self):
        m = trade_metrics([_trade(20.0, risk=10.0), _trade(-5.0, risk=10.0)])
        self.assertAlmostEqual(m["avg_r"], 0.75)
        self.assertAlmostEqual(m["median_r"], 2.0)

    def test_production_parity(self):
        from core.analytics.performance import PerformanceAnalytics
        from core.backtesting.trade import Trade
        from core.backtesting.trade_registry import TradeRegistry
        from core.risk.account import Account

        acc = Account(starting_balance=2000.0)
        reg = TradeRegistry()
        for i, pnl in enumerate((10.0, -5.0, 0.0, 20.0)):
            reg.add(Trade(
                direction="BULLISH", entry=100.0, stop_loss=90.0,
                take_profit=110.0, quantity=1.0, risk_amount=10.0,
                commission=0.0, slippage=0.0, entry_time=i,
                exit_time=i, exit_price=100.0 + pnl, status="CLOSED",
                pnl=pnl,
            ))
        rep = PerformanceAnalytics.analyze(acc, reg)
        mine = trade_metrics([_trade(p) for p in (10.0, -5.0, 0.0, 20.0)])
        self.assertAlmostEqual(mine["expectancy"], rep.expectancy, places=9)
        self.assertAlmostEqual(mine["profit_factor"], rep.profit_factor, places=9)
        self.assertAlmostEqual(mine["sharpe"], rep.sharpe, places=9)
        self.assertAlmostEqual(mine["sortino"], rep.sortino, places=9)


class TestMonteCarlo(unittest.TestCase):
    """Determinism + degenerate-distribution behavior."""

    def test_same_seed_identical(self):
        nets = [1.5, -0.5, 2.0, -1.0, 0.5]
        first = mc_shuffle(nets, 500, 1107001)
        second = mc_shuffle(nets, 500, 1107001)
        self.assertEqual(first, second)

    def test_all_negative_set_always_loses(self):
        nets = [-0.5, -0.3, -0.2]
        res = mc_shuffle(nets, 200, 1107001)
        self.assertEqual(res["p_loss"], 1.0)
        self.assertAlmostEqual(res["final_p50"], sum(nets))

    def test_bootstrap_deterministic(self):
        nets = [1.5, -0.5, 2.0, -1.0, 0.5]
        first = bootstrap_mean(nets, 500, 1107002)
        second = bootstrap_mean(nets, 500, 1107002)
        self.assertEqual(first, second)


class TestBreakEvenMath(unittest.TestCase):
    """Break-even arithmetic on synthetic books."""

    def test_negative_edge_needs_subsidy(self):
        trades = [_trade(-0.5), _trade(0.2), _trade(-0.3)]
        n = len(trades)
        edge = sum(t["net"] for t in trades) / n
        self.assertLess(edge, 0.0)
        # No non-negative per-trade cost clears zero.
        self.assertLess(edge - 0.45, 0.0)

    def test_cost_overlay_math(self):
        trades = [_trade(1.0, entry=100.0, qty=5.0)]
        out = apply_costs(trades, "C_moderate")
        # comm = 500*0.0005 = 0.25; slip = 2*500*0.0002 = 0.20
        self.assertAlmostEqual(out[0]["commission"], 0.25)
        self.assertAlmostEqual(out[0]["slippage"], 0.20)
        self.assertAlmostEqual(out[0]["net"], 0.55)


class TestBreakEvenMath(unittest.TestCase):
    """Break-even arithmetic on synthetic books."""

    def test_negative_edge_needs_subsidy(self):
        trades = [_trade(-0.5), _trade(0.2), _trade(-0.3)]
        n = len(trades)
        edge = sum(t["net"] for t in trades) / n
        self.assertLess(edge, 0.0)
        # No non-negative per-trade cost clears zero.
        self.assertLess(edge - 0.45, 0.0)

    def test_cost_overlay_math(self):
        trades = [_trade(1.0, entry=100.0, qty=5.0)]
        out = apply_costs(trades, "C_moderate")
        # comm = 500*0.0005 = 0.25; slip = 2*500*0.0002 = 0.20
        self.assertAlmostEqual(out[0]["commission"], 0.25)
        self.assertAlmostEqual(out[0]["slippage"], 0.20)
        self.assertAlmostEqual(out[0]["net"], 0.55)


class TestCausalRegimes11EClosure(unittest.TestCase):
    """R1-R5: regime thresholds use strictly-prior data only."""

    def _inv(self):
        calib = _bars(300, start=1787000000)
        fold = _bars(120, start=1787018000)
        future = _bars(120, start=1787025200, base=500.0)
        return calib, fold, future

    def test_r1_future_obs_does_not_move_threshold(self):
        calib, _, future = self._inv()
        oos_start = 1787018000
        base = vol_thresholds(filter_prior(calib, oos_start))
        tainted = vol_thresholds(filter_prior(calib + future, oos_start))
        self.assertEqual(base, tainted)

    def test_r2_future_fold_does_not_reclassify_earlier(self):
        calib, fold, future = self._inv()
        inv_min = {"calib": calib, "D2": fold, "D1": [], "D3": []}
        inv_full = {"calib": calib, "D2": fold + future,
                    "D1": future, "D3": future}
        starts = {"F1": fold[0]["time"]}
        cal_a = calibration_for_fold("F1", inv_min, starts)
        cal_b = calibration_for_fold("F1", inv_full, starts)
        self.assertEqual(
            vol_thresholds(cal_a), vol_thresholds(cal_b))
        trades = [{"net": -0.5, "gross": -0.5, "entry": 100.0,
                   "quantity": 1.0, "commission": 0.0, "slippage": 0.0,
                   "risk_amount": 1.0, "entry_time": fold[60]["time"],
                   "exit_time": fold[61]["time"]}]
        cells_a, _ = classify_fold(trades, cal_a, fold)
        cells_b, _ = classify_fold(trades, cal_b, fold)
        self.assertEqual(cells_a.keys(), cells_b.keys())

    def test_r3_filter_drops_oos_and_future(self):
        calib, fold, _ = self._inv()
        kept = filter_prior(calib + fold, fold[0]["time"])
        self.assertTrue(all(b["time"] < fold[0]["time"] for b in kept))
        self.assertEqual(len(kept), len(calib))

    def test_r4_calibration_ignores_later_datasets(self):
        calib, fold, future = self._inv()
        inv = {"calib": calib, "D2": fold,
               "D1": future, "D3": future}
        starts = {"F1": fold[0]["time"]}
        got = calibration_for_fold("F1", inv, starts)
        self.assertEqual(len(got), len(calib))
        self.assertLess(got[-1]["time"], fold[0]["time"])

    def test_r5_thresholds_deterministic(self):
        calib, _, _ = self._inv()
        self.assertEqual(vol_thresholds(calib), vol_thresholds(calib))


class TestCausalRandomBaseline11EClosure(unittest.TestCase):
    """RB1-RB6: per-fold random controls respect fold boundaries."""

    def _fold(self):
        return _bars(300, start=1787000000)

    def test_rb1_deterministic_and_fold_specific(self):
        bars = self._fold()
        other = _bars(300, start=1787100000, base=9000.0)
        first = run_fold(bars, 3, 1108000, 15.5, n_draws=50)
        second = run_fold(bars, 3, 1108000, 15.5, n_draws=50)
        self.assertEqual(first, second)
        third = run_fold(other, 3, 1108000, 15.5, n_draws=50)
        self.assertNotEqual(first, third)

    def test_rb2_future_decoy_cannot_change_fold(self):
        bars = self._fold()
        decoy = _bars(300, start=1787200000, base=500.0)
        fills = {"F1": 3}
        strat = {"F1": [-0.5, -0.2, -0.1]}
        alone = run_all_folds({"F1": bars}, fills, 15.5,
                              n_draws=50, strat_nets=strat)
        with_decoy = run_all_folds(
            {"F1": bars, "DECOY": decoy},
            {"F1": 3, "DECOY": 0}, 15.5,
            n_draws=50, strat_nets=dict(strat, DECOY=[]))
        self.assertEqual(alone["F1"], with_decoy["F1"])

    def test_rb3_exits_never_cross_boundary(self):
        bars = self._fold()
        last = bars[-1]["time"]
        # Entries crowded at the fold tail force MTM exits.
        entries = [(len(bars) - 2, "long"), (len(bars) - 3, "short")]
        trades = simulate_fold(bars, entries, 15.5)
        self.assertTrue(len(trades) > 0)
        self.assertTrue(all(t["exit_ts"] <= last for t in trades))

    def test_rb4_seed_reproducible(self):
        bars = self._fold()
        self.assertEqual(
            run_fold(bars, 3, 1108000, 15.5, n_draws=50),
            run_fold(bars, 3, 1108000, 15.5, n_draws=50),
        )

    def test_rb5_draw_count_exact(self):
        bars = self._fold()
        self.assertEqual(len(run_fold(bars, 3, 1108000, 15.5, n_draws=50)), 50)

    def test_rb6_same_cost_framework(self):
        # Constant-range bars: ATR > 0 but price never touches
        # stop/TP -> MTM at last close -> gross 0, so net must
        # equal exactly minus one scenario-C trade cost.
        bars = [
            {"time": 1787000000 + 60 * i, "open": 100.0, "high": 100.5,
             "low": 99.5, "close": 100.0, "volume": 10.0}
            for i in range(60)
        ]
        trades = simulate_fold(bars, [(20, "long")], 15.5)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["net"], -TRADE_COST, places=9)
        self.assertAlmostEqual(TRADE_COST, 0.45, places=9)


class TestMetricSemantics11EClosure(unittest.TestCase):
    """M1-M6: explicit gross/fees/slippage/net semantics."""

    def _costed(self, gross, pv=500.0):
        comm = pv * 0.0005
        slip = 2 * pv * 0.0002
        return {"net": gross - comm - slip, "gross": gross,
                "entry": 100.0, "quantity": 5.0, "commission": comm,
                "slippage": slip, "risk_amount": 10.0,
                "exit_time": 0, "entry_time": 0}

    def test_m1_zero_cost_gross_equals_net(self):
        m = trade_metrics([_trade(1.5), _trade(-0.5)])
        self.assertAlmostEqual(m["gross_pnl"], m["net_pnl"])
        self.assertEqual(m["fees"], 0.0)
        self.assertEqual(m["slippage"], 0.0)

    def test_m2_fees_reduce_net(self):
        plain = trade_metrics([_trade(1.0, entry=100.0, qty=5.0)])
        costed = trade_metrics([self._costed(1.0)])
        self.assertAlmostEqual(costed["gross_pnl"], 1.0)
        self.assertAlmostEqual(costed["fees"], 0.25)
        self.assertAlmostEqual(costed["net_pnl"], 0.55)
        self.assertLess(costed["net_pnl"], plain["net_pnl"])

    def test_m3_slippage_reduces_net(self):
        costed = trade_metrics([self._costed(1.0)])
        self.assertAlmostEqual(costed["slippage"], 0.20)

    def test_m4_identity_holds(self):
        m = trade_metrics([self._costed(2.0), self._costed(-1.0)])
        self.assertAlmostEqual(
            m["net_pnl"], m["gross_pnl"] - m["fees"] - m["slippage"], places=9)
        self.assertAlmostEqual(m["net_consistency_diff"], 0.0, places=9)

    def test_m5_labels_match_semantics(self):
        m = trade_metrics([self._costed(2.0)])
        for key in ("gross_pnl", "fees", "slippage", "net_pnl"):
            self.assertIn(key, m)
        # Gross excludes costs; net includes them.
        self.assertGreater(m["gross_pnl"], m["net_pnl"])
        self.assertGreaterEqual(m["fees"], 0.0)
        self.assertGreaterEqual(m["slippage"], 0.0)

    def test_m6_production_parity_preserved(self):
        from core.analytics.performance import PerformanceAnalytics
        from core.backtesting.trade import Trade
        from core.backtesting.trade_registry import TradeRegistry
        from core.risk.account import Account

        acc = Account(starting_balance=2000.0)
        reg = TradeRegistry()
        for i, pnl in enumerate((10.0, -5.0, 0.0, 20.0)):
            reg.add(Trade(
                direction="BULLISH", entry=100.0, stop_loss=90.0,
                take_profit=110.0, quantity=1.0, risk_amount=10.0,
                commission=0.0, slippage=0.0, entry_time=i,
                exit_time=i, exit_price=100.0 + pnl, status="CLOSED",
                pnl=pnl,
            ))
        rep = PerformanceAnalytics.analyze(acc, reg)
        mine = trade_metrics([_trade(p) for p in (10.0, -5.0, 0.0, 20.0)])
        self.assertAlmostEqual(mine["net_pnl"], rep.net_profit, places=9)
        self.assertAlmostEqual(mine["gross_pnl"], rep.net_profit, places=9)


if __name__ == "__main__":
    unittest.main()
