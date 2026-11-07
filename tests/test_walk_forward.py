"""
====================================================

QuantEngine

Walk-Forward Tester Tests

Run with:

    python -m unittest tests.test_walk_forward -v

Proves the rolling out-of-sample evaluation over the
canonical Backtester:

    1. Fold carving: train immediately precedes a never-seen
       test window; folds advance by `step`.
    2. Candidate selection: the best train-window config is
       picked by the in-sample metric and used to run the test
       window (out of sample).
    3. No candidates -> plain windowed runs, no selection.
    4. Aggregate: total OOS trades and net OOS profit are the
       sums over the test windows.
    5. Same engine state is never shared between folds (each
       fold is a fresh engine via the runner).
    6. Guard checks: bad train/test sizes and unknown metrics
       raise immediately.

Stdlib only -- no network, real strategy internals replaced
by a parametric fake pipeline whose tp_pct decides win/hold.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from core.backtesting.trade_simulator import TradeSimulator

from backtesting.backtester import Backtester

from core.validation.walk_forward import WalkForwardTester


class Candle:

    def __init__(self, high, low, close, timestamp, symbol="TEST"):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = symbol
        self.timeframe = "1m"


class FakeEventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


class ParamPipeline:

    def __init__(self, symbol, tp_pct, stop_pct):
        self.symbol = symbol
        self.tp_pct = tp_pct
        self.stop_pct = stop_pct
        self.reset()

    def reset(self):
        self.context = PipelineContext()
        self.context.market = MarketState(symbol=self.symbol, timeframe="1m")

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.context.order = OrderIntent(
            direction="BULLISH",
            entry=100.0,
            stop_loss=100.0 - self.stop_pct,
            take_profit=100.0 + self.tp_pct,
            quantity=1.0,
            symbol=self.symbol,
            valid=True,
            risk_amount=1.0,
            position_value=100.0,
        )
        self.context.execution_signal = None


# Phase 12 micro-economics (entry 100.0): stop 99.5 /
# TP 103.0 is exactly 6.0:1, the inclusive gate boundary.
# Entry bars touch 100 without hitting 99.5 or 103; win
# bars reach 103 without breaching 99.5.
def entry_candle(ts):
    return Candle(high=100.3, low=99.7, close=100.0, timestamp=ts)


def win_candle(ts):
    return Candle(high=103.5, low=100.0, close=100.0, timestamp=ts)


def candle_series(pairs):
    candles = []
    ts = 0
    for _ in range(pairs):
        candles.append(entry_candle(ts))
        ts += 1
        candles.append(win_candle(ts))
        ts += 1
    return candles


def make_runner():
    def runner(bars, config=None):
        # Phase 12: scripted legacy-path orders must clear
        # the mandatory gates (TP 3.0 / stop 0.5 -> exactly
        # 6.0:1).
        cfg = config or {}
        tp_pct = float(cfg.get("tp_pct", 3.0))
        stop_pct = float(cfg.get("stop_pct", 0.5))
        pipeline = ParamPipeline("TEST", tp_pct, stop_pct)
        engine = Backtester(
            pipeline,
            FakeEventBus(pipeline),
            TradeSimulator(),
        )
        engine.run(bars)
        return engine.account, engine.trades

    return runner


WIN = {"tp_pct": 3.0}

HOLD = {"tp_pct": 20.0}


class TestWalkForwardTester(unittest.TestCase):

    maxDiff = None

    def test_folds_advance_by_test_size(self):
        history = candle_series(8)
        result = WalkForwardTester(
            runner=make_runner(),
            history=history,
            train_size=4,
            test_size=4,
        ).run()

        self.assertEqual(result.fold_count, 3)
        self.assertEqual(
            [f.train_range for f in result.folds],
            [(0, 4), (4, 8), (8, 12)],
        )
        self.assertEqual(
            [f.test_range for f in result.folds],
            [(4, 8), (8, 12), (12, 16)],
        )

    def test_candidate_selection_and_out_of_sample(self):
        history = candle_series(8)
        result = WalkForwardTester(
            runner=make_runner(),
            history=history,
            train_size=4,
            test_size=4,
            candidates=[WIN, HOLD],
        ).run()

        # tp 3.0 wins its train window (2 wins -> +6.0);
        # tp 20.0 never closes (0 trades -> 0.0). WIN always
        # selected and its outcome is measured once per test
        # window (2 wins -> +6.0).
        for fold in result.folds:
            self.assertEqual(fold.best_config, WIN)
            self.assertAlmostEqual(fold.in_sample.net_profit, 6.0, places=6)
            self.assertAlmostEqual(fold.oos_net_profit, 6.0, places=6)
            self.assertEqual(fold.oos_trades, 2)

        self.assertEqual(result.total_trades, 6)
        self.assertAlmostEqual(result.net_profit, 18.0, places=6)

    def test_no_candidates_runs_plain_windows(self):
        history = candle_series(6)
        result = WalkForwardTester(
            runner=make_runner(),
            history=history,
            train_size=4,
            test_size=4,
        ).run()

        self.assertEqual(result.fold_count, 2)
        for fold in result.folds:
            self.assertIsNone(fold.best_config)
            self.assertAlmostEqual(fold.oos_net_profit, 6.0, places=6)
            self.assertEqual(fold.oos_trades, 2)

        self.assertEqual(result.total_trades, 4)
        self.assertAlmostEqual(result.net_profit, 12.0, places=6)

    def test_overlapping_step(self):
        history = candle_series(6)
        result = WalkForwardTester(
            runner=make_runner(),
            history=history,
            train_size=4,
            test_size=4,
            step=2,
        ).run()

        self.assertEqual(
            [f.test_range for f in result.folds],
            [(4, 8), (6, 10), (8, 12)],
        )

    def test_guards(self):
        with self.assertRaises(ValueError):
            WalkForwardTester(
                runner=make_runner(),
                history=candle_series(2),
                train_size=0,
                test_size=4,
            )
        with self.assertRaises(ValueError):
            WalkForwardTester(
                runner=make_runner(),
                history=candle_series(2),
                train_size=4,
                test_size=4,
                metric="bogus",
            )


if __name__ == "__main__":
    unittest.main()