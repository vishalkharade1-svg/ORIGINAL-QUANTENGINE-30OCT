"""Runtime boundary certification tests (deterministic, offline).

Covers the internally solvable gaps found in the Phase-6 audit:

* A. End-to-end costed trade hand-calculations (LONG/SHORT, qty>1,
  explicit commission+slippage, exact net) through TradeSimulator.
* D. ML negative controls (unrelated feature shows no edge; permuted
  labels collapse performance) on the deterministic numpy backend.
* D. ML structural pins (no scaler/search/uncontrolled randomness in
  the research ML package; hyperparams fixed and seeded).

Stdlib (+numpy, already a dependency) only. No network. No production
wiring. Fixtures are hand-computed; thresholds carry explicit margin.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Setup:
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    quantity: float = 1.0
    risk_amount: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    symbol: str = "BTCUSDT"
    setup_id: str = "test"
    order_id: str = "ORDER-1"
    entry_mode: str = "LIMIT_RETEST"
    canonical_id: str = "BTCUSDT-1m-BULLISH-OB-1-100-90-120"
    score: float = 80
    confidence: float = 80
    valid: bool = True
    reason: str = ""
    position_value: float = 0.0


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class TestCostedTradeHandCalcs(unittest.TestCase):
    @staticmethod
    def run_closed(setup, candle, *, quantity, commission, slippage):
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        trade = sim.open_trade(
            setup, candle.timestamp - 1000, quantity=quantity,
            commission=commission, slippage=slippage)
        assert trade is not None
        sim.update(candle)
        closed = sim.registry.all()
        assert len(closed) == 1
        return closed[0]

    def test_long_win_exact_net(self):
        # NOTE: setup.quantity takes precedence over the open_trade
        # quantity parameter (existing choke-point semantics); both
        # are set consistently here.
        # Phase-13 maintenance: gate-compliant target (costs 3+2
        # shift the entry to 101.25: 68.75/11.25 = 6.11 >= 6), so
        # the mandatory post-cost R:R gate admits the fill. Exact-net
        # intent unchanged: gross = (170-100)*2 = 140; net = 135.
        setup = Setup(direction="BULLISH", entry=100.0, stop_loss=90.0,
                      take_profit=170.0, quantity=2.0)
        candle = Candle(timestamp=2000, open=100.0, high=172.0,
                        low=98.0, close=171.0)
        trade = self.run_closed(setup, candle, quantity=2.0,
                                commission=3.0, slippage=2.0)
        # gross = (170-100)*2 = 140; net = 140-3-2 = 135.
        self.assertEqual(trade.result, "WIN")
        self.assertAlmostEqual(trade.pnl, 135.0)
        self.assertAlmostEqual(trade.pnl_percent, 67.5)

    def test_short_win_exact_net(self):
        # Phase-13 maintenance: gate-compliant target (entry shifts
        # to 98.75: 68.75/11.25 = 6.11 >= 6). Symmetric with LONG.
        setup = Setup(direction="BEARISH", entry=100.0, stop_loss=110.0,
                      take_profit=30.0, quantity=2.0)
        candle = Candle(timestamp=2000, open=100.0, high=102.0,
                        low=28.0, close=29.0)
        trade = self.run_closed(setup, candle, quantity=2.0,
                                commission=3.0, slippage=2.0)
        # gross = (100-30)*2 = 140; net = 135. Symmetric with LONG.
        self.assertEqual(trade.result, "WIN")
        self.assertAlmostEqual(trade.pnl, 135.0)
        self.assertAlmostEqual(trade.pnl_percent, 67.5)

    def test_long_loss_costs_deepen_loss(self):
        # Phase-13 maintenance: gate-compliant target (170, never
        # touched: candle high 105 < 170); the SL exit math is
        # unchanged.
        setup = Setup(direction="BULLISH", entry=100.0, stop_loss=90.0,
                      take_profit=170.0, quantity=2.0)
        candle = Candle(timestamp=2000, open=100.0, high=105.0,
                        low=85.0, close=95.0)
        trade = self.run_closed(setup, candle, quantity=2.0,
                                commission=3.0, slippage=2.0)
        # gross = (90-100)*2 = -20; net = -25. Costs never subsidize.
        self.assertEqual(trade.result, "LOSS")
        self.assertAlmostEqual(trade.pnl, -25.0)

    def test_costs_applied_once_not_doubled(self):
        # Phase-13 maintenance: gate-compliant target (entry shifts
        # to 102.5: 77.5/12.5 = 6.2 >= 6). Single-subtraction intent
        # unchanged.
        setup = Setup(direction="BULLISH", entry=100.0, stop_loss=90.0,
                      take_profit=180.0)
        candle = Candle(timestamp=2000, open=100.0, high=182.0,
                        low=98.0, close=181.0)
        trade = self.run_closed(setup, candle, quantity=1.0,
                                commission=3.0, slippage=2.0)
        # Single subtraction: 80 - 3 - 2 = 75 (doubled would be 70).
        self.assertAlmostEqual(trade.pnl, 75.0)


class TestMLNegativeControls(unittest.TestCase):
    @staticmethod
    def auc_of(xs, ys, *, train_n=20):
        import numpy as _np

        from core.research.ml.models import SimpleModel, auc

        Xtr, ytr = _np.array(xs[:train_n], float), _np.array(ys[:train_n], int)
        Xte, yte = _np.array(xs[train_n:], float), _np.array(ys[train_n:], int)
        model = SimpleModel(kind="LOGISTIC", backend="numpy").fit(Xtr, ytr)
        assert model.trained
        return auc(yte.tolist(), model.predict_proba(Xte).tolist())

    def test_unrelated_feature_shows_no_edge(self):
        # Deterministic unrelated feature (modular sawtooth of the row
        # index) against balanced alternating labels: chronological
        # split, no shuffle anywhere.
        xs = [[((i * 37) % 11) / 10.0] for i in range(40)]
        ys = [i % 2 for i in range(40)]
        value = self.auc_of(xs, ys)
        self.assertIsNotNone(value)
        self.assertGreater(value, 0.3)
        self.assertLess(value, 0.7)
        self.assertLess(value, 0.8)  # no artificial strong edge

    def test_permuted_labels_collapse_performance(self):
        # Alternating-block feature keeps both classes in each
        # chronological half (a monotone ramp would single-class
        # either half, making AUC undefined).
        xs = [[v] for v in ([-1.5, -0.5, 0.5, 1.5] * 10)]
        ys = [1 if x[0] > 0 else 0 for x in xs]
        honest = self.auc_of(xs, ys, train_n=20)
        self.assertIsNotNone(honest)
        self.assertGreater(honest, 0.9)
        # Deterministic permutation (rotation by one position) breaks
        # the linear mapping: performance must collapse toward baseline.
        # (A pure reversal would keep this periodic pattern separable.)
        collapsed = self.auc_of(xs, ys[1:] + ys[:1], train_n=20)
        self.assertIsNotNone(collapsed)
        self.assertLess(collapsed, honest - 0.3)


class TestMLStructuralPins(unittest.TestCase):
    def test_no_scaler_search_or_randomness_in_ml_package(self):
        root = Path(__file__).resolve().parents[1] / "core" / "research" / "ml"
        banned = ("StandardScaler", "MinMaxScaler", "GridSearch",
                  "RandomizedSearch", "optuna", "np.random", "numpy.random",
                  "datetime.now", "uuid", "time.time")
        hits = []
        for path in sorted(root.glob("*.py")):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                code = line.split("#", 1)[0]
                if "no_shuffle" in code:
                    continue
                for marker in banned:
                    if marker in code:
                        if marker == "random" and "random_state" in code:
                            continue
                        hits.append("%s:%d:%s" % (path.name, number, marker))
        self.assertEqual(hits, [])

    def test_hyperparameters_fixed_and_seeded(self):
        import inspect

        from core.research.ml import models as mm

        self.assertIn("random_state=0", inspect.getsource(mm._sklearn_model))
        tree = mm.NumpyDecisionTree()
        self.assertEqual((tree.max_depth, tree.min_samples), (3, 3))
        logreg = mm.NumpyLogisticRegression()
        self.assertEqual(
            (logreg.learning_rate, logreg.iterations, logreg.l2),
            (0.1, 200, 1e-3),
        )


if __name__ == "__main__":
    unittest.main()
