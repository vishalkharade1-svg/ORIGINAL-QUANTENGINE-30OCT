"""
====================================================

Phase 6C -- Multi-Symbol Scanning & Canonical Identity

End-to-end tests for the scanning layer:

    core/identity/            canonical setup identity
    core/scanning/            per-symbol isolated pipelines
                              + multi-symbol scanner

Required behaviour under test:

  * canonical identity is built once at setup creation and
    flows unchanged Setup -> OrderIntent -> Trade;
  * the scanner consumes ONLY the universe's eligible cut
    (never a hardcoded symbol list);
  * one isolated pipeline per instrument -- no shared mutable
    state, no cross-instrument mutation;
  * per-symbol failure isolation (A ok / B raises / C ok);
  * deterministic ordering regardless of universe insertion
    order;
  * an EMPTY universe degrades to a clean empty result.

All tests are offline: a scripted four-engine world (mirror
of the canonical WorldPipeline harness) with FakeIndicators
and per-symbol data sources -- no indicators stack, no
network. ENTRY_MODE is pinned to LIMIT_RETEST for the run,
exactly like tests/test_execution_lifecycle.run_world.

====================================================
"""

import unittest
from unittest import mock

from config import risk_settings

from core.backtesting.trade_simulator import TradeSimulator
from core.execution.entry_mode import ENTRY_MODE_LIMIT_RETEST
from core.execution.execution_engine import ExecutionEngine
from core.identity.instrument_identity import IdentityError
from core.identity.instrument_identity import build_setup_identity
from core.identity.instrument_identity import split_setup_identity
from core.market_state import MarketState
from core.order_blocks.order_block import OrderBlock
from core.order_blocks.order_block_registry import OrderBlockRegistry
from core.fvg.fvg_registry import FVGRegistry
from core.liquidity.liquidity_target import LiquidityTarget
from core.regime.regime_state import RegimeState
from core.risk.risk_engine import RiskEngine
from core.scanning.multi_symbol_scanner import MultiSymbolScanner
from core.scanning.scan_result import ScanStatus
from core.scanning.symbol_pipeline import SymbolPipeline
from core.setup.decision_engine import DecisionEngine
from core.setup.trade_setup_builder import TradeSetupBuilder
from core.trend.trend_state import TrendState
from core.universe.market_universe import MarketUniverse
from core.universe.universe_policy import UniversePolicy


# ==========================================================
# Fixtures
# ==========================================================


class Candle:

    def __init__(self, high, low, close, timestamp, symbol="SYM"):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = symbol
        self.timeframe = "1m"


def ob(direction, high, low, index=5, score=85.0):
    if direction == "BULLISH":
        open_, close = high, low
    else:
        open_, close = low, high
    block = OrderBlock(
        index=index,
        timestamp=1000,
        timeframe="1m",
        direction=direction,
        open=open_,
        high=high,
        low=low,
        close=close,
        strength=score,
        displacement_strength=score,
    )
    block.score = score
    return block


def liquidity_target(price=170.0, side="BUY"):
    return LiquidityTarget(
        side=side,
        price=price,
        timeframe="1m",
        score=90.0,
        probability=90.0,
        distance=13.0,
        strength=0.9,
        reason="test",
        source_pool="pool-1",
    )


def trend(direction="BULLISH"):
    return TrendState(direction=direction)


def regime():
    return RegimeState(
        score=90.0,
        confidence=90.0,
        grade="A",
        regime="TRENDING",
    )


class FakeIndicators:
    """Minimal stand-in for the IndicatorCache (ATR axis only)."""

    def __init__(self, atr=15.0):
        self._atr = atr

    def latest(self, name):
        if name == "ATR_14":
            return self._atr
        return None


def with_scan_patching(fn):
    def wrapper(*args, **kwargs):
        with mock.patch.object(
            risk_settings,
            "ENTRY_MODE",
            ENTRY_MODE_LIMIT_RETEST,
        ), mock.patch.object(
            risk_settings,
            "ACTIVE_ENTRY_MODES",
            (ENTRY_MODE_LIMIT_RETEST,),
        ):
            return fn(*args, **kwargs)
    return wrapper


def _seed_world(context, direction="BULLISH"):
    if direction == "BULLISH":
        block = ob("BULLISH", 110.0, 100.0, index=5)
        target = liquidity_target()
    else:
        # BEARISH block: entry 100 (OB low), stop 110 (OB high),
        # target 40 -- reward 60 on risk 10, rr 6.0, which clears
        # the authoritative config MIN_RISK_REWARD gate. The
        # trend must also match so the Trend Filter passes.
        block = ob("BEARISH", 110.0, 100.0, index=5)
        target = liquidity_target(price=40.0, side="SELL")
    context.order_blocks = OrderBlockRegistry()
    context.order_blocks.add(block)
    context.liquidity_target = target
    context.trend = trend(direction)
    context.regime = regime()
    context.fvgs = FVGRegistry()


class ScanWorld:
    """
    Scripted four-engine world (builder / decision /
    execution / risk) for one instrument. The world is
    re-seeded identically every candle so the same setup is
    re-derived bar after bar -- the canonical duplicate-signal
    scenario. Direction is fixed per world instance so two
    instruments can carry genuinely independent setups.
    """

    def __init__(self, context, direction="BULLISH"):
        self.context = context
        self.direction = direction
        self.builder = TradeSetupBuilder()
        self.decision = DecisionEngine()
        self.execution = ExecutionEngine()
        self.risk = RiskEngine()
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def reset(self):
        for engine in (self.builder, self.decision,
                       self.execution, self.risk):
            engine.reset()

    def on_candle(self, event):
        _seed_world(self.context, self.direction)
        self.context.indicators = FakeIndicators()
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.builder.analyze(self.context)
        self.decision.analyze(self.context)
        self.execution.analyze(self.context)
        self.risk.analyze(self.context)


def direction_for(direction_by_symbol):
    def factory(context):
        return ScanWorld(
            context,
            direction_by_symbol.get(
                context.market.symbol, "BULLISH"
            ),
        )
    return factory


def _bullish_window(symbol):
    return [
        Candle(108.0, 106.0, 107.5, 1000, symbol),   # setup
        Candle(112.0, 109.0, 110.0, 1001, symbol),   # touch fill
        Candle(111.0, 109.0, 110.5, 1002, symbol),   # hold
        Candle(171.0, 170.0, 170.5, 1003, symbol),   # take profit (tp 170)
    ]


def _bearish_window(symbol):
    return [
        Candle(105.0, 102.5, 103.5, 1000, symbol),   # setup
        Candle(104.0, 99.0, 101.0, 1001, symbol),    # touch fill
        Candle(103.0, 100.5, 101.5, 1002, symbol),   # hold
        Candle(44.0, 39.5, 40.0, 1003, symbol),      # take profit (tp 40)
    ]


class DictDataSource:
    """Per-symbol candle source. symbols in 'failing' raise."""

    def __init__(self, windows):
        self.windows = dict(windows)
        self.failing = set()
        self.requested = []

    def fail(self, symbol):
        self.failing.add(symbol)
        return self

    def get_candles(self, symbol, timeframe, limit=None):
        self.requested.append(symbol)
        if symbol in self.failing:
            raise RuntimeError(
                "data unavailable for {}".format(symbol)
            )
        bars = self.windows.get(symbol, [])
        if limit:
            bars = bars[-limit:]
        return list(bars)


def instrument(exchange, instrument_id, symbol, state="ELIGIBLE"):
    from core.registry.instrument import Instrument
    from core.registry.product_types import PRODUCT_STATE_ELIGIBLE
    raw_state = (
        PRODUCT_STATE_ELIGIBLE
        if state == "ELIGIBLE"
        else state
    )
    inst = Instrument(
        instrument_id=str(instrument_id),
        symbol=symbol,
        exchange=exchange,
        state=raw_state,
        tick_size=0.01,
        quantity_step=0.001,
        trading_enabled=True,
    )
    return inst


def policy():
    return UniversePolicy(
        min_quote_volume_24h=100.0,
        min_history_bars=100,
    )


def universe_with(*instruments):
    return MarketUniverse(
        policy=policy(),
        instruments=list(instruments),
        timeframe="1m",
    )


def scanning_helpers():
    btc = instrument("delta", 2, "BTCUSDT")
    eth = instrument("delta", 7, "ETHUSDT")
    sol = instrument("delta", 11, "SOLUSDT")
    return btc, eth, sol


# ==========================================================
# Identity module
# ==========================================================


class TestInstrumentIdentity(unittest.TestCase):

    def test_format_matches_spec(self):
        identity = build_setup_identity(
            exchange="delta",
            instrument_id="27",
            timeframe="1m",
            direction="BULLISH",
            strategy="BREAKOUT_CONTINUATION",
            setup_id="OB-990",
        )
        self.assertEqual(
            identity,
            "delta:27:1m:BULLISH:"
            "BREAKOUT_CONTINUATION:OB-990",
        )

    def test_same_input_same_identity(self):
        args = dict(
            exchange="delta",
            instrument_id="27",
            timeframe="1m",
            direction="BULLISH",
            strategy="BREAKOUT_CONTINUATION",
            setup_id="OB-990",
        )
        self.assertEqual(
            build_setup_identity(**args),
            build_setup_identity(**args),
        )

    def test_identity_diverges_across_instrument_id(self):
        a = build_setup_identity(
            "delta", "2", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        b = build_setup_identity(
            "delta", "7", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        self.assertNotEqual(a, b)

    def test_identity_diverges_across_timeframe(self):
        a = build_setup_identity(
            "delta", "27", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        b = build_setup_identity(
            "delta", "27", "15m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        self.assertNotEqual(a, b)

    def test_identity_diverges_across_direction(self):
        a = build_setup_identity(
            "delta", "27", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        b = build_setup_identity(
            "delta", "27", "1m", "BEARISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        self.assertNotEqual(a, b)

    def test_identity_diverges_across_strategy(self):
        a = build_setup_identity(
            "delta", "27", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        b = build_setup_identity(
            "delta", "27", "1m", "BULLISH",
            "MEAN_REVERSION", "OB-5",
        )
        self.assertNotEqual(a, b)

    def test_identity_diverges_across_setup_id(self):
        a = build_setup_identity(
            "delta", "27", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        b = build_setup_identity(
            "delta", "27", "1m", "BULLISH",
            "BREAKOUT_CONTINUATION", "OB-6",
        )
        self.assertNotEqual(a, b)

    def test_empty_segments_raise(self):
        for empty in ("", None, "  "):
            with self.assertRaises(IdentityError):
                build_setup_identity(
                    exchange=empty,
                    instrument_id="27",
                    timeframe="1m",
                    direction="BULLISH",
                    strategy="BREAKOUT_CONTINUATION",
                    setup_id="OB-5",
                )
            with self.assertRaises(IdentityError):
                build_setup_identity(
                    exchange="delta",
                    instrument_id="27",
                    timeframe="1m",
                    direction="BULLISH",
                    strategy="BREAKOUT_CONTINUATION",
                    setup_id=empty,
                )

    def test_invalid_direction_raises(self):
        with self.assertRaises(IdentityError):
            build_setup_identity(
                "delta", "27", "1m", "LONG",
                "BREAKOUT_CONTINUATION", "OB-5",
            )

    def test_direction_is_normalized_upper(self):
        identity = build_setup_identity(
            "delta", "27", "1m", "bullish",
            "BREAKOUT_CONTINUATION", "OB-5",
        )
        self.assertIn(":BULLISH:", identity)

    def test_split_round_trip_preserves_suffix(self):
        setup_id = "BTCUSDT-1m-BULLISH-OB-5-110.00-100.00-170.00"
        identity = build_setup_identity(
            "delta", "27", "1m", "BEARISH",
            "BREAKOUT_CONTINUATION", setup_id,
        )
        parts = split_setup_identity(identity)
        self.assertEqual(
            parts,
            (
                "delta",
                "27",
                "1m",
                "BEARISH",
                "BREAKOUT_CONTINUATION",
                setup_id,
            ),
        )

    def test_split_malformed_raises(self):
        with self.assertRaises(IdentityError):
            split_setup_identity(
                "delta:27:1m:BULLISH:BREAKOUT_CONTINUATION"
            )


# ==========================================================
# End-to-end identity flow through the scan
# ==========================================================


class TestScanEndToEndIdentityFlow(unittest.TestCase):

    @with_scan_patching
    def _scan(self, instruments, data_source, directions):
        scanner = MultiSymbolScanner(
            data_source=data_source,
            world_factory=direction_for(directions),
            timeframe="1m",
        )
        return scanner.scan(universe_with(*instruments))

    def test_identity_flows_setup_order_trade(self):
        btc, eth, _ = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bullish_window("ETHUSDT"),
            }
        )
        result = self._scan(
            [btc, eth], data, {}
        )
        self.assertEqual(result.successful, 2)
        self.assertEqual(result.failed, 0)

        btc_out = result.for_symbol("BTCUSDT")
        self.assertIsNotNone(btc_out)
        self.assertEqual(btc_out.status, ScanStatus.SUCCESS)
        self.assertTrue(btc_out.setups)
        self.assertTrue(btc_out.orders)
        self.assertTrue(btc_out.trades)

        setup = btc_out.setups[-1]
        order = btc_out.orders[0]
        trade = btc_out.trades[0]

        self.assertTrue(setup.canonical_id)
        self.assertEqual(order.canonical_id, setup.canonical_id)
        self.assertEqual(trade.canonical_id, setup.canonical_id)
        self.assertEqual(
            setup.canonical_id,
            build_setup_identity(
                exchange="delta",
                instrument_id="2",
                timeframe="1m",
                direction=setup.direction,
                strategy=setup.entry_mode,
                setup_id=setup.setup_id,
            ),
        )

    def test_identity_is_namespaced_per_instrument(self):
        btc, eth, _ = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bullish_window("ETHUSDT"),
            }
        )
        result = self._scan([btc, eth], data, {})

        btc_setup = result.for_symbol("BTCUSDT").setups[-1]
        eth_setup = result.for_symbol("ETHUSDT").setups[-1]

        self.assertNotEqual(
            btc_setup.canonical_id, eth_setup.canonical_id
        )
        self.assertTrue(
            btc_setup.canonical_id.startswith("delta:2:1m:")
        )
        self.assertTrue(
            eth_setup.canonical_id.startswith("delta:7:1m:")
        )

    def test_legacy_path_without_exchange_keeps_empty_id(self):
        bare = type(
            "BareInstrument",
            (),
            {"symbol": "LEGACY", "exchange": "",
             "instrument_id": ""},
        )()
        data = DictDataSource(
            {"LEGACY": _bullish_window("LEGACY")}
        )
        pipeline = SymbolPipeline(
            bare,
            timeframe="1m",
            data_source=data,
            world_factory=direction_for({}),
        )
        result = pipeline.run()
        self.assertEqual(result.status, ScanStatus.SUCCESS)
        self.assertTrue(result.setups)
        self.assertEqual(
            result.setups[-1].canonical_id, ""
        )


# ==========================================================
# Universe routing
# ==========================================================


class TestUniverseRouting(unittest.TestCase):

    @with_scan_patching
    def test_scanner_only_scans_eligible_universe_cut(self):
        btc, eth, sol = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bullish_window("ETHUSDT"),
                "SOLUSDT": _bullish_window("SOLUSDT"),
            }
        )
        universe = universe_with(btc, eth)

        scanner = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        )
        result = scanner.scan(universe)

        self.assertEqual(result.scanned, 2)
        self.assertEqual(
            set(result.symbols), {"BTCUSDT", "ETHUSDT"}
        )
        self.assertTrue(
            "SOLUSDT" not in data.requested
        )

    @with_scan_patching
    def test_registry_executable_cut_is_respected(self):
        from core.registry.instrument_registry import InstrumentRegistry
        from core.registry.instrument import Instrument
        from core.registry.product_types import (
            PRODUCT_STATE_ELIGIBLE,
            PRODUCT_STATE_INELIGIBLE,
        )

        btc = Instrument(
            instrument_id="2",
            symbol="BTCUSDT",
            exchange="delta",
            state=PRODUCT_STATE_ELIGIBLE,
        )
        sol = Instrument(
            instrument_id="11",
            symbol="SOLUSDT",
            exchange="delta",
            state=PRODUCT_STATE_INELIGIBLE,
        )
        registry = InstrumentRegistry()
        registry._store(btc)
        registry._store(sol)

        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "SOLUSDT": _bullish_window("SOLUSDT"),
            }
        )
        scanner = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        )
        result = scanner.scan(registry)

        self.assertEqual(result.scanned, 1)
        self.assertEqual(
            set(result.symbols), {"BTCUSDT"}
        )
        self.assertNotIn("SOLUSDT", data.requested)

    @with_scan_patching
    def test_empty_universe_degrades_cleanly(self):
        scanner = MultiSymbolScanner(
            data_source=DictDataSource({}),
            world_factory=direction_for({}),
            timeframe="1m",
        )
        result = scanner.scan(universe_with())

        self.assertEqual(result.scanned, 0)
        self.assertEqual(result.successful, 0)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.symbols, ())
        self.assertEqual(result.setups, ())
        self.assertEqual(result.errors, ())
        self.assertEqual(
            result.summary()["scanned"], 0
        )

    @with_scan_patching
    def test_no_hardcoded_symbols_in_scanner_source(self):
        import pathlib
        source = pathlib.Path(
            __file__
        ).resolve().parent.parent / "core" / "scanning" / \
            "multi_symbol_scanner.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("BTCUSDT", text)
        self.assertNotIn("ETHUSDT", text)
        self.assertNotIn("DEFAULT_SYMBOLS", text)
        self.assertNotIn("DEFAULT_SYMBOL", text)
        self.assertNotIn("SYMBOLS =", text)


# ==========================================================
# Per-instrument state isolation
# ==========================================================


class TestStateIsolation(unittest.TestCase):

    @with_scan_patching
    def test_each_instrument_gets_a_fresh_isolated_world(self):

        btc, eth, _ = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bearish_window("ETHUSDT"),
            }
        )
        result = self._run_scan(
            [btc, eth], data, {"ETHUSDT": "BEARISH"}
        )

        self.assertEqual(result.successful, 2)

        a = result.for_symbol("BTCUSDT")
        b = result.for_symbol("ETHUSDT")

        self.assertIsNot(a.pipeline, b.pipeline)
        self.assertIsNot(
            a.pipeline.context, b.pipeline.context
        )
        self.assertIsNot(a.pipeline.world, b.pipeline.world)
        self.assertIsNot(
            a.pipeline.simulator, b.pipeline.simulator
        )

        a_orders = a.pipeline.context.order_registry.all()
        b_orders = b.pipeline.context.order_registry.all()
        self.assertTrue(a_orders)
        self.assertTrue(b_orders)
        for order in a_orders:
            self.assertNotIn(order, b_orders)
        for order in b_orders:
            self.assertNotIn(order, a_orders)

        self.assertEqual(a_orders[0].direction, "BULLISH")
        self.assertEqual(b_orders[0].direction, "BEARISH")

    @with_scan_patching
    def test_mutating_one_symbols_state_never_reaches_another(self):
        btc, eth, _ = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bullish_window("ETHUSDT"),
            }
        )
        result = self._run_scan([btc, eth], data, {})

        a = result.for_symbol("BTCUSDT")
        b = result.for_symbol("ETHUSDT")

        before_b_orders = list(
            b.pipeline.context.order_registry.all()
        )

        a.pipeline.context.market.mark_price = -9999.0
        a.pipeline.context.market.best_ask = -1.0
        a_orders = a.pipeline.context.order_registry.all()
        a_orders[-1].entry = -1.0

        self.assertEqual(
            b.pipeline.context.market.mark_price, 170.5
        )
        self.assertEqual(
            b.pipeline.context.market.best_ask, 170.5
        )
        after_b_orders = (
            b.pipeline.context.order_registry.all()
        )
        self.assertEqual(
            [o.entry for o in after_b_orders],
            [o.entry for o in before_b_orders],
        )

    @with_scan_patching
    def _run_scan(self, instruments, data, directions):
        scanner = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for(directions),
            timeframe="1m",
        )
        return scanner.scan(universe_with(*instruments))


# ==========================================================
# Failure isolation
# ==========================================================


class TestFailureIsolation(unittest.TestCase):

    @with_scan_patching
    def test_one_symbol_failure_does_not_stop_the_scan(self):
        btc, eth, sol = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bullish_window("ETHUSDT"),
                "SOLUSDT": _bullish_window("SOLUSDT"),
            }
        ).fail("SOLUSDT")

        scanner = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        )
        result = scanner.scan(universe_with(btc, eth, sol))

        self.assertEqual(result.scanned, 3)
        self.assertEqual(result.successful, 2)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.skipped, 0)

        failed = result.for_symbol("SOLUSDT")
        self.assertEqual(failed.status, ScanStatus.FAILED)
        self.assertIn("unavailable", failed.error)

        self.assertTrue(result.for_symbol("BTCUSDT").ok)
        self.assertTrue(result.for_symbol("ETHUSDT").ok)

        self.assertEqual(
            result.errors[0][0], "SOLUSDT"
        )

    @with_scan_patching
    def test_data_pipeline_skips_when_no_data(self):
        btc, eth, _ = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
            }
        )
        scanner = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        )
        result = scanner.scan(universe_with(btc, eth))

        self.assertEqual(result.scanned, 2)
        self.assertEqual(result.successful, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(
            result.for_symbol("ETHUSDT").status,
            ScanStatus.SKIPPED,
        )
        self.assertEqual(
            result.for_symbol("ETHUSDT").error, "NO_DATA"
        )


# ==========================================================
# Determinism
# ==========================================================


class TestDeterminism(unittest.TestCase):

    @with_scan_patching
    def test_result_order_is_independent_of_universe_order(self):
        btc, eth, sol = scanning_helpers()
        data = DictDataSource(
            {
                "BTCUSDT": _bullish_window("BTCUSDT"),
                "ETHUSDT": _bullish_window("ETHUSDT"),
                "SOLUSDT": _bullish_window("SOLUSDT"),
            }
        )
        expected = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

        forward = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        ).scan(universe_with(btc, eth, sol))
        reversed_ = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        ).scan(universe_with(sol, eth, btc))

        self.assertEqual(forward.symbols, expected)
        self.assertEqual(reversed_.symbols, expected)
        self.assertEqual(forward.symbols, reversed_.symbols)
        self.assertEqual(
            forward.setups[0].canonical_id,
            reversed_.setups[0].canonical_id,
        )

    @with_scan_patching
    def test_delta_bs_self_scan_is_repeatable(self):
        btc, _, _ = scanning_helpers()
        data = DictDataSource(
            {"BTCUSDT": _bullish_window("BTCUSDT")}
        )
        first = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        ).scan(universe_with(btc))
        second = MultiSymbolScanner(
            data_source=data,
            world_factory=direction_for({}),
            timeframe="1m",
        ).scan(universe_with(btc))

        self.assertEqual(first.symbols, second.symbols)
        self.assertEqual(
            [o.canonical_id for o in first.orders],
            [o.canonical_id for o in second.orders],
        )
        self.assertEqual(
            [t.canonical_id for t in first.trades],
            [t.canonical_id for t in second.trades],
        )


if __name__ == "__main__":
    unittest.main()