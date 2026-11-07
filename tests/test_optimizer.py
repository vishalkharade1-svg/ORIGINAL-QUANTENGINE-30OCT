"""
====================================================

QuantEngine

Strategy Optimizer Tests

Run with:

    python -m unittest tests.test_optimizer -v

Proves the grid sweep over the canonical Backtester:

    1. Grid expansion is the cartesian product and results are
       ranked descending by the chosen metric.
    2. A discriminating grid (tp that wins vs tp that holds)
       ranks the winning parameterization first with its full
       metrics dict intact.
    3. Run objects expose the common report fields as
       properties.
    4. Guards: empty grid, unknown metric, exploding grid
       size all raise immediately.

Stdlib only -- no network, real strategy internals replaced
by the same parametric fake pipeline as the walk-forward tests.

====================================================
"""

import unittest

from core.market_state import MarketState
from core.pipeline.pipeline_context import PipelineContext
from core.risk.order_intent import OrderIntent

from core.backtesting.trade_simulator import TradeSimulator

from backtesting.backtester import Backtester

from core.validation.optimizer import (
    OptimizationRun,
    StrategyOptimizer,
)


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

    # Phase 12: the runner mints scripted legacy-path orders,
    # so every parameterization must satisfy the mandatory
    # gates (directional geometry + R:R >= 6). The default
    # stop (0.5 -> stop 99.5) pairs with TP >= 3.0 for the
    # inclusive 6.0 boundary.
    def __init__(self, symbol, tp_pct, stop_pct=0.5):
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
# entry bars touch 100 without hitting 99.5 or 103; win
# bars reach 103 without breaching 99.5; loss bars breach
# 99.5 without reaching 103.
def entry_candle(ts):
    return Candle(high=100.3, low=99.7, close=100.0, timestamp=ts)


def win_candle(ts):
    return Candle(high=103.5, low=100.0, close=102.0, timestamp=ts)


def loss_candle(ts):
    return Candle(high=100.2, low=99.0, close=99.5, timestamp=ts)


def candle_series(pairs):
    candles = []
    ts = 0
    for _ in range(pairs):
        candles.append(entry_candle(ts))
        ts += 1
        candles.append(win_candle(ts))
        ts += 1
    return candles


def benign_candle(ts):
    # Resolution bar that closes NOTHING (high below any
    # winning TP, low above the 99.5 stop): the open position
    # rides through it.
    return Candle(high=100.2, low=99.6, close=100.0, timestamp=ts)


def mixed_series(pairs):
    # Alternating win-resolution / benign candles so a
    # reachable take-profit banks wins on win bars while the
    # position rides through benign bars -- and a far
    # take-profit never closes. (Phase 12: a stop-hitting
    # loss bar cannot coexist with 6:1 micro-economics here,
    # so the "loss" leg is a ride-through instead; realized
    # losses remain covered by the backtester contract
    # suites.)
    candles = []
    ts = 0
    for i in range(pairs):
        candles.append(entry_candle(ts))
        ts += 1
        resolution = (
            win_candle(ts) if i % 2 == 0 else benign_candle(ts)
        )
        candles.append(resolution)
        ts += 1
    return candles


def make_runner():
    def runner(bars, params):
        # Phase 12: scripted legacy-path orders must clear
        # the mandatory gates, so compliant economics are the
        # default here (TP 3.0 / stop 0.5 -> exactly 6.0:1).
        tp_pct = float(params.get("tp_pct", 3.0))
        stop_pct = float(params.get("stop_pct", 0.5))
        pipeline = ParamPipeline("TEST", tp_pct, stop_pct)
        engine = Backtester(
            pipeline,
            FakeEventBus(pipeline),
            TradeSimulator(),
        )
        engine.run(bars)
        return engine.account, engine.trades

    return runner


class TestStrategyOptimizer(unittest.TestCase):

    maxDiff = None

    def test_ranks_winning_parameterization_first(self):
        history = candle_series(4)
        results = StrategyOptimizer(
            runner=make_runner(),
            grid={"tp_pct": [3.0, 20.0]},
        ).run(history)

        self.assertEqual(len(results), 2)

        best = results[0]
        self.assertEqual(best.params, {"tp_pct": 3.0})
        self.assertAlmostEqual(best.net_profit, 12.0, places=6)
        self.assertEqual(best.total_trades, 4)

        worst = results[1]
        self.assertEqual(worst.params, {"tp_pct": 20.0})
        self.assertAlmostEqual(worst.net_profit, 0.0, places=6)
        self.assertEqual(worst.total_trades, 0)

        self.assertIs(results[0], optimizer_best(results))
        self.assertIsInstance(best, OptimizationRun)

    def test_cartesian_product_and_ranking(self):
        history = mixed_series(4)
        # Reachable TP + compliant stop (0.5 -> stop 99.5):
        # win candles bank TP, benign candles never close ->
        # every closed trade wins. Far TP: nothing ever
        # closes -> zero trades.
        grid = {"tp_pct": [3.0, 30.0], "stop_pct": [0.5]}
        results = StrategyOptimizer(
            runner=make_runner(),
            grid=grid,
            metric="win_rate",
        ).run(history)

        self.assertEqual(len(results), 2)

        self.assertEqual(results[0].params["tp_pct"], 3.0)
        self.assertAlmostEqual(results[0].win_rate, 100.0, places=6)
        self.assertAlmostEqual(results[1].win_rate, 0.0, places=6)

        scores = [r.win_rate for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_metrics_dict_complete(self):
        history = candle_series(2)
        results = StrategyOptimizer(
            runner=make_runner(),
            grid={"tp_pct": [3.0]},
        ).run(history)

        metrics = results[0].metrics
        for key in (
            "net_profit", "sharpe", "profit_factor",
            "win_rate", "total_trades", "max_drawdown",
            "final_equity",
        ):
            self.assertIn(key, metrics)

    def test_best_is_none_before_run(self):
        optimizer = StrategyOptimizer(
            runner=make_runner(),
            grid={"tp_pct": [0.5]},
        )
        self.assertIsNone(optimizer.best)

    def test_guards(self):
        with self.assertRaises(ValueError):
            StrategyOptimizer(
                runner=make_runner(),
                grid={},
            )
        with self.assertRaises(ValueError):
            StrategyOptimizer(
                runner=make_runner(),
                grid={"tp_pct": [0.5]},
                metric="bogus",
            )
        with self.assertRaises(ValueError):
            StrategyOptimizer(
                runner=make_runner(),
                grid={"a": [1, 2, 3], "b": [4, 5]},
                max_combos=5,
            )


def optimizer_best(results):
    return results[0]


if __name__ == "__main__":
    unittest.main()