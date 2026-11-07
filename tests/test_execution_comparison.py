"""
====================================================

QuantEngine

Phase 5D Execution Comparison Mode Tests

Run with:

    python -m unittest tests.test_execution_comparison -v

Proves the deterministic comparison mode:

    1. The SAME market data executes once per entry model, each
       in a fully independent pipeline / simulator / backtester
       (no blended portfolio, no shared precedent state).
    2. Every row reports the funnel (setups / orders / filled /
       expired / invalidated) plus the EXECUTED-ledger analytics
       (closed / wins / losses / unsettled / win rate / profit
       factor / expectancy / max drawdown) and transaction costs
       from the booked Trade objects.
    3. Markets that never fill report zeros honestly -- a
       measurement run is never warmed up by another model's run.
    4. MARKET_CONFIRMATION is routed through its CANONICAL trigger
       semantics (Phase 5C): a candle that merely TOUCHES the
       reference level but closes below it parks the order instead
       of filling as a LIMIT_RETEST -- the exact research-vs-
       production mismatch Phase 5C forbids.
    5. The report renders one clearly-labelled column per model,
       and the row's mode label equals the model that actually
       executed.

Stdlib only -- no network; the canonical seeded world.

====================================================
"""

import unittest

from config import risk_settings

from core.market_state import MarketState

from core.backtesting.trade_simulator import TradeSimulator

from backtesting.backtester import Backtester

from core.setup.trade_setup_builder import TradeSetupBuilder
from core.setup.decision_engine import DecisionEngine
from core.execution.execution_engine import ExecutionEngine
from core.risk.risk_engine import RiskEngine

from core.execution.entry_model import (
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODE_BREAKOUT_CONTINUATION,
)

from core.validation.execution_comparison import (
    ExecutionComparisonMode,
)

from tests.test_execution_lifecycle import (
    FakeIndicators,
    seeded_world,
)


class Candle:

    def __init__(self, open_, high, low, close, timestamp):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


def miss_candle(ts):
    return Candle(open_=107.0, high=108.0, low=106.0,
                  close=107.5, timestamp=ts)


def break_candle(ts):
    return Candle(open_=108.5, high=113.0, low=109.0,
                  close=111.0, timestamp=ts)


def limit_touch_candle(ts):
    return Candle(open_=109.5, high=112.0, low=110.0,
                  close=111.0, timestamp=ts)


def touch_close_below_candle(ts):
    # Reaches E = 110.0 (low 110.0) but closes BELOW it:
    # LIMIT_RETEST would fill; MARKET_CONFIRMATION must park.
    return Candle(open_=109.8, high=111.0, low=110.0,
                  close=109.5, timestamp=ts)


def open_above_candle(ts):
    # Phase 12: opens AT E = 110.0 (actual RR exactly 6.0)
    # so the NEXT_BAR_OPEN fill survives execution-time
    # revalidation.
    return Candle(open_=110.0, high=115.0, low=110.0,
                  close=113.0, timestamp=ts)


def loss_after_candle(ts):
    return Candle(open_=108.0, high=112.0, low=99.5,
                  close=101.0, timestamp=ts)


class WorldPipeline:

    def __init__(self):
        self.builder = TradeSetupBuilder()
        self.decision = DecisionEngine()
        self.execution = ExecutionEngine()
        self.risk = RiskEngine()
        self.reset()

    def reset(self):
        from core.pipeline.pipeline_context import PipelineContext
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST", timeframe="1m")
        self.context.indicators = FakeIndicators()
        seeded_world(self.context)
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def on_candle(self, event):
        seeded_world(self.context)
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.builder.analyze(self.context)
        self.decision.analyze(self.context)
        self.execution.analyze(self.context)
        self.risk.analyze(self.context)


class EventBus:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def publish(self, event):
        self.pipeline.on_candle(event)


def make_runner():
    """
    Standard Phase 5D runner: mode is routed through the
    comparison tool's ENTRY_MODE / ACTIVE_ENTRY_MODES injection;
    the runner builds a FRESH isolated pipeline + simulator +
    backtester per call.
    """

    def runner(mode, history):
        pipeline = WorldPipeline()
        simulator = TradeSimulator()
        backtester = Backtester(
            pipeline,
            EventBus(pipeline),
            simulator,
        )
        backtester.run(history)
        return backtester

    return runner


def shared_history():
    # The full scripted opportunity set. For every mode the market
    # shows the same bars: the BREAKOUT trigger (bar 3), the open
    # entry bar (bar 4), the resting LIMIT touch (bar 5) and the
    # loss resolution (bar 6).
    return [
        miss_candle(1),
        miss_candle(2),
        break_candle(3),
        open_above_candle(4),
        limit_touch_candle(5),
        loss_after_candle(6),
    ]


class TestExecutionComparison(unittest.TestCase):

    # -------------------------------------------------

    def test_same_data_executes_independently_per_mode(self):
        report = ExecutionComparisonMode(
            runner=make_runner(),
            modes=(
                ENTRY_MODE_LIMIT_RETEST,
                ENTRY_MODE_BREAKOUT_CONTINUATION,
                ENTRY_MODE_MARKET_CONFIRMATION,
            ),
        ).run(shared_history())

        self.assertEqual(report.bars, 6)
        self.assertEqual(len(report.rows), 3)

        limit = report.row(ENTRY_MODE_LIMIT_RETEST)
        breakout = report.row(ENTRY_MODE_BREAKOUT_CONTINUATION)
        market = report.row(ENTRY_MODE_MARKET_CONFIRMATION)

        # Every model saw the identical opportunity set.
        self.assertEqual(limit.setups, 1)
        self.assertEqual(breakout.setups, 1)
        self.assertEqual(market.setups, 1)
        self.assertEqual(limit.orders, 1)
        self.assertEqual(breakout.orders, 1)
        self.assertEqual(market.orders, 1)

        # LIMIT: resting-touch fill on bar 5 (low 110 <= E), then
        # stopped out on bar 6.
        self.assertEqual(limit.filled, 1)
        self.assertEqual(limit.closed_trades, 1)
        self.assertEqual(limit.losses, 1)

        # BREAKOUT: trigger at bar 3 close, fill at bar 4 OPEN,
        # stopped out on bar 6.
        self.assertEqual(breakout.filled, 1)
        self.assertEqual(breakout.closed_trades, 1)
        self.assertEqual(breakout.losses, 1)

        # MARKET_CONFIRMATION: bar 5 reached E AND closed beyond it
        # (close 111 > E 110) -> its own canonical trigger fills,
        # independently of the LIMIT touch.
        self.assertEqual(market.filled, 1)
        self.assertEqual(market.closed_trades, 1)

        # All three booked the identical executed economics.
        self.assertAlmostEqual(limit.net_pnl, breakout.net_pnl, places=6)
        self.assertAlmostEqual(market.net_pnl, limit.net_pnl, places=6)

    # -------------------------------------------------

    def test_market_confirmation_never_degrades_to_limit_fill(self):
        # Bar 2 TOUCHES E = 110.0 but closes 109.5 (below E).
        # LIMIT_RETEST fills on the touch; MARKET_CONFIRMATION's
        # canonical trigger (reached AND close beyond E) fails, so
        # the active-market order stays PARKED -- it must NOT come
        # back as a LIMIT fill.
        history = [
            miss_candle(1),
            touch_close_below_candle(2),
            loss_after_candle(3),
        ]

        report = ExecutionComparisonMode(
            runner=make_runner(),
            modes=(
                ENTRY_MODE_LIMIT_RETEST,
                ENTRY_MODE_MARKET_CONFIRMATION,
            ),
        ).run(history)

        limit = report.row(ENTRY_MODE_LIMIT_RETEST)
        market = report.row(ENTRY_MODE_MARKET_CONFIRMATION)

        self.assertEqual(limit.filled, 1)
        self.assertEqual(market.filled, 0)
        self.assertEqual(market.closed_trades, 0)
        self.assertEqual(market.unsettled, 0)
        self.assertEqual(market.win_rate, 0.0)

    # -------------------------------------------------

    def test_rows_are_isolated_and_labeled_by_routed_mode(self):
        report = ExecutionComparisonMode(
            runner=make_runner(),
            modes=(ENTRY_MODE_LIMIT_RETEST,),
        ).run(shared_history())

        row = report.rows[0]

        self.assertEqual(row.mode, ENTRY_MODE_LIMIT_RETEST)
        self.assertEqual(row.orders, 1)
        self.assertEqual(row.filled, 1)
        self.assertEqual(row.losses, 1)

        # Loss: stop 100.0 from entry 110.0 at the actual-entry
        # quantity (18.5 risk / 10.0 distance) -> -18.50 before
        # costs; the booked ledger matches the account.
        self.assertAlmostEqual(row.net_pnl, -18.5, places=6)
        self.assertAlmostEqual(
            row.final_balance,
            row.starting_balance + row.net_pnl,
            places=6,
        )
        self.assertEqual(row.fees, 0.0)
        self.assertEqual(row.slippage, 0.0)

        ordered = report.row(ENTRY_MODE_LIMIT_RETEST)
        self.assertIs(ordered, row)

    # -------------------------------------------------

    def test_unsettled_is_respected_and_zeros_are_honest(self):
        # Last candle resolves nothing: the BREAKOUT position fills
        # on the final bar and stays OPEN -> unsettled, no closed
        # trade, final equity untouched.
        history = [
            miss_candle(1),
            break_candle(2),
            open_above_candle(3),
        ]

        report = ExecutionComparisonMode(
            runner=make_runner(),
            modes=(ENTRY_MODE_BREAKOUT_CONTINUATION,),
        ).run(history)

        row = report.rows[0]

        self.assertEqual(row.filled, 1)
        self.assertEqual(row.closed_trades, 0)
        self.assertEqual(row.unsettled, 1)
        self.assertEqual(row.wins, 0)
        self.assertEqual(row.losses, 0)
        self.assertAlmostEqual(row.net_pnl, 0.0, places=6)
        self.assertAlmostEqual(
            row.final_balance, row.starting_balance, places=6
        )

    # -------------------------------------------------

    def test_market_confirmation_reports_zero_when_never_triggered(self):
        report = ExecutionComparisonMode(
            runner=make_runner(),
            modes=(ENTRY_MODE_MARKET_CONFIRMATION,),
        ).run([miss_candle(1), miss_candle(2), miss_candle(3)])

        row = report.rows[0]

        self.assertEqual(row.mode, ENTRY_MODE_MARKET_CONFIRMATION)
        # An order is created and honestly parked -- but nothing
        # ever fills without a canonical trigger.
        self.assertEqual(row.orders, 1)
        self.assertEqual(row.filled, 0)
        self.assertEqual(row.closed_trades, 0)
        self.assertEqual(row.unsettled, 0)
        self.assertAlmostEqual(row.net_pnl, 0.0, places=6)

    # -------------------------------------------------

    def test_render_emits_a_labeled_column_per_model(self):
        report = ExecutionComparisonMode(
            runner=make_runner(),
            modes=(
                ENTRY_MODE_LIMIT_RETEST,
                ENTRY_MODE_BREAKOUT_CONTINUATION,
            ),
        ).run(shared_history())

        text = report.render()

        self.assertIn("EXECUTION COMPARISON", text)
        self.assertIn(ENTRY_MODE_LIMIT_RETEST, text)
        self.assertIn(ENTRY_MODE_BREAKOUT_CONTINUATION, text)
        self.assertNotIn(ENTRY_MODE_MARKET_CONFIRMATION, text)


if __name__ == "__main__":
    unittest.main()