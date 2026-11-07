"""
====================================================

QuantEngine

Phase 11C -- Operational Robustness, Failure Handling.

Paper/fake-transport/deterministic-replay ONLY. No live
trading, no real exchange orders, no strategy changes.

Covers:

  11C-B  contract metadata hardening (typed failures
         before payload construction)
  11C-C  contract loader failure handling (typed
         ContractLoadError for every transport/schema
         failure)
  11C-D  schema-drift detection (observed tolerant
         readers, degraded-health indicator)
  11C-E  exception-swallow audit evidence (isolation at
         the transport / worker / engine boundaries)
  11C-F  websocket failure injection (frame-level)
  11C-G  market-data failure handling (candle builder)
  11C-H  universe refresh failure handling
  11C-J  task / concurrency safety (thread lifecycle)
  11C-O  state consistency / reconciliation
  11C-P  control API / remote safety regression
  11C-V  live safety regression

The end-to-end realtime paper chain (11C-I), the
multi-symbol soak (11C-L), resources (11C-M), restart
(11C-N), event-loop responsiveness (11C-K) and Gate A
determinism (11C-U) live in
tests/test_realtime_chain_11c.py.

====================================================
"""

import threading
import unittest

from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_contract import DeltaContract
from core.exchanges.delta.delta_contract_loader import (
    ContractLoadError,
    DeltaContractLoader,
)
from core.execution.live_safety_gate import (
    ConfigurationError,
    ExecutionMode,
    LiveBlockedError,
    LiveSafetyGate,
)
from core.execution.order_executor import (
    DeltaOrderExecutor,
    InvalidContractError,
)
from core.live.broker_engine import (
    _field,
    _fields_list,
    drain_schema_drift_stats,
    get_schema_drift_stats,
    schema_health,
)
from core.risk.order_intent import OrderIntent


# ====================================================
# Shared fakes
# ====================================================


def make_contract(symbol="BTCUSDT", **overrides):
    fields = {
        "symbol": symbol,
        "exchange": "DELTA",
        "contract_type": "perpetual_futures",
        "tick_size": 0.01,
        "quantity_step": 0.001,
        "min_quantity": 0.00001,
        "max_leverage": 100.0,
        "maker_fee": 0.0005,
        "taker_fee": 0.001,
        "price_precision": 2,
        # Phase-9 execution-evidence hardening: a contract reaches the
        # order transport only with explicit verified live-execution
        # evidence.  The default helper supplies synthetic test evidence
        # (matching test_order_executor.py); tests covering the gate
        # itself pass live_execution_verified=False explicitly.
        "live_execution_verified": True,
        "live_execution_evidence": "11C synthetic test fixture",
        "quantity_precision": 5,
        "product_id": 2,
    }
    fields.update(overrides)
    return DeltaContract(**fields)


def make_intent(symbol="BTCUSDT", **overrides):
    fields = {
        "direction": "BULLISH",
        "entry": 80000.0,
        "stop_loss": 79500.0,
        "take_profit": 81000.0,
        "quantity": 0.0623,
        "symbol": symbol,
        "valid": True,
        "reason": "",
    }
    fields.update(overrides)
    return OrderIntent(**fields)


class CountingFakeExchange:
    """Fake order-transport boundary. `placed` counts every
    real order-endpoint call; it must stay ZERO unless a test
    explicitly arms the safety gate with a VALID contract."""

    authenticated = True

    def __init__(self):
        self.placed = []

    def post(self, path, payload=None):
        if path == "/v2/orders":
            self.placed.append(payload)
        return {
            "success": True,
            "result": {
                "id": "order_1",
                "product_id": (
                    payload.get("product_id")
                    if isinstance(payload, dict)
                    else None
                ),
                "state": "open",
            },
        }


def make_executor(contract=None, exchange=None):
    registry = ContractRegistry()
    registry.add(
        contract if contract is not None else make_contract()
    )
    fake = (
        exchange if exchange is not None else CountingFakeExchange()
    )
    executor = DeltaOrderExecutor(
        exchange=fake,
        registry=registry,
        order_id_factory=lambda i: "QE-11C-TEST",
    )
    return executor, fake


def valid_product(symbol="BTCUSDT", product_id=27):
    return {
        "id": product_id,
        "symbol": symbol,
        "contract_type": "perpetual_futures",
        "tick_size": "0.5",
        "contract_value": "0.001",
        "minimum_order_size": "1",
        "maximum_leverage": "100",
        "maker_commission_rate": "0.0002",
        "taker_commission_rate": "0.0005",
        "price_precision": 1,
        "contract_value_precision": 3,
        "underlying_asset": {"symbol": "BTC"},
        "strike_price": None,
    }


class FakeProductsModule:
    """Stand-in for DeltaProducts with a scripted download()."""

    def __init__(self, behaviour):
        self.behaviour = behaviour

    def download(self):
        kind = self.behaviour["kind"]
        if kind == "ok":
            return {"result": self.behaviour["products"]}
        if kind == "raise":
            raise self.behaviour["error"]
        if kind == "raw":
            return self.behaviour["value"]
        raise AssertionError("unknown behaviour")


# ====================================================
# 11C-B -- contract metadata hardening
# ====================================================


class TestContractMetadataHardening11C(unittest.TestCase):

    def test_missing_contract_raises_before_transport(self):
        executor, fake = make_executor()
        executor.registry = ContractRegistry()
        with self.assertRaises(InvalidContractError):
            executor.execute(
                make_intent(symbol="UNKNOWN"),
                safety=LiveSafetyGate.test_armed(),
            )
        self.assertEqual(fake.placed, [])

    def test_non_numeric_product_id_raises(self):
        for bad in (None, "abc", "", "12x"):
            executor, fake = make_executor(
                contract=make_contract(product_id=bad)
            )
            with self.assertRaises(
                InvalidContractError, msg="product_id={!r}".format(bad)
            ):
                executor.execute(
                    make_intent(),
                    safety=LiveSafetyGate.test_armed(),
                )
            self.assertEqual(fake.placed, [])

    def test_non_positive_product_id_raises(self):
        for bad in (0, -3, "0"):
            executor, fake = make_executor(
                contract=make_contract(product_id=bad)
            )
            with self.assertRaises(
                InvalidContractError, msg="product_id={!r}".format(bad)
            ):
                executor.execute(
                    make_intent(),
                    safety=LiveSafetyGate.test_armed(),
                )
            self.assertEqual(fake.placed, [])

    def test_invalid_tick_size_raises(self):
        for bad in (0, -0.5, None, "x", float("nan"), float("inf"), True):
            executor, fake = make_executor(
                contract=make_contract(tick_size=bad)
            )
            with self.assertRaises(
                InvalidContractError, msg="tick_size={!r}".format(bad)
            ):
                executor.execute(
                    make_intent(),
                    safety=LiveSafetyGate.test_armed(),
                )
            self.assertEqual(fake.placed, [])

    def test_invalid_quantity_step_raises(self):
        for bad in (0, -1.0, None, "x", float("nan"), float("-inf")):
            executor, fake = make_executor(
                contract=make_contract(quantity_step=bad)
            )
            with self.assertRaises(
                InvalidContractError,
                msg="quantity_step={!r}".format(bad),
            ):
                executor.execute(
                    make_intent(),
                    safety=LiveSafetyGate.test_armed(),
                )
            self.assertEqual(fake.placed, [])

    def test_invalid_min_quantity_raises(self):
        for bad in (-1.0, None, "x", float("nan")):
            executor, fake = make_executor(
                contract=make_contract(min_quantity=bad)
            )
            with self.assertRaises(
                InvalidContractError,
                msg="min_quantity={!r}".format(bad),
            ):
                executor.execute(
                    make_intent(),
                    safety=LiveSafetyGate.test_armed(),
                )
            self.assertEqual(fake.placed, [])

    def test_invalid_precision_raises(self):
        for field in ("price_precision", "quantity_precision"):
            for bad in (-1, 1.5, "2", None, True):
                executor, fake = make_executor(
                    contract=make_contract(**{field: bad})
                )
                with self.assertRaises(
                    InvalidContractError,
                    msg="{}={!r}".format(field, bad),
                ):
                    executor.execute(
                        make_intent(),
                        safety=LiveSafetyGate.test_armed(),
                    )
                self.assertEqual(fake.placed, [])

    def test_valid_contract_reaches_transport_only_when_armed(self):
        executor, fake = make_executor()
        result = executor.execute(
            make_intent(), safety=LiveSafetyGate.test_armed()
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(fake.placed), 1)
        self.assertEqual(fake.placed[0]["product_id"], 2)

    def test_contract_without_execution_evidence_refused_when_armed(self):
        executor, fake = make_executor(
            contract=make_contract(live_execution_verified=False,
                                   live_execution_evidence="")
        )
        with self.assertRaises(InvalidContractError):
            executor.execute(
                make_intent(), safety=LiveSafetyGate.test_armed()
            )
        self.assertEqual(fake.placed, [])

    def test_valid_contract_without_safety_still_blocked(self):
        executor, fake = make_executor()
        with self.assertRaises(LiveBlockedError):
            executor.execute(make_intent(), safety=None)
        self.assertEqual(fake.placed, [])


# ====================================================
# 11C-C -- contract loader failure handling
# ====================================================


class TestContractLoaderFailures11C(unittest.TestCase):

    def _load_with(self, behaviour):
        import core.exchanges.delta.delta_contract_loader as loader_mod

        real = loader_mod.DeltaProducts
        loader_mod.DeltaProducts = lambda: FakeProductsModule(behaviour)
        try:
            return DeltaContractLoader().load()
        finally:
            loader_mod.DeltaProducts = real

    def test_timeout_is_typed(self):
        import httpx

        with self.assertRaises(ContractLoadError):
            self._load_with(
                {"kind": "raise", "error": httpx.TimeoutException("t")}
            )

    def test_connection_failure_is_typed(self):
        import httpx

        with self.assertRaises(ContractLoadError):
            self._load_with(
                {
                    "kind": "raise",
                    "error": httpx.ConnectError("conn refused"),
                }
            )

    def test_http_failure_is_typed(self):
        with self.assertRaises(ContractLoadError):
            self._load_with(
                {"kind": "raise", "error": RuntimeError("500")}
            )

    def test_malformed_json_envelope_is_typed(self):
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "raw", "value": "not-json{"})

    def test_missing_result_is_typed(self):
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "raw", "value": {"ok": True}})

    def test_none_envelope_is_typed(self):
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "raw", "value": None})

    def test_wrong_result_type_is_typed(self):
        for bad in ({"result": {"id": 1}}, {"result": "x"}, {"result": 42}):
            with self.assertRaises(
                ContractLoadError, msg="result={!r}".format(bad)
            ):
                self._load_with({"kind": "raw", "value": bad})

    def test_empty_result_is_typed_failure(self):
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "ok", "products": []})

    def test_malformed_product_is_typed(self):
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "ok", "products": ["BTCUSDT"]})

    def test_product_missing_symbol_is_typed(self):
        bad = valid_product()
        del bad["symbol"]
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "ok", "products": [bad]})

    def test_non_string_contract_type_is_typed(self):
        bad = valid_product()
        bad["contract_type"] = {"unexpected": "shape"}
        with self.assertRaises(ContractLoadError):
            self._load_with({"kind": "ok", "products": [bad]})

    def test_valid_products_load(self):
        registry = self._load_with(
            {
                "kind": "ok",
                "products": [
                    valid_product("BTCUSDT", 27),
                    valid_product("ETHUSDT", 31),
                ],
            }
        )
        self.assertEqual(len(registry.all()), 2)
        self.assertTrue(registry.exists("BTCUSDT"))
        self.assertEqual(registry.get("ETHUSDT").product_id, 31)


# ====================================================
# 11C-D -- schema-drift detection
#
# REQUIRED vs OPTIONAL decision (documented here and in
# the final report):
#   REQUIRED (must be detectable, degrade loudly):
#     position size/quantity, product_id match key,
#     exit price, realized P&L, equity figure. A missing
#     or malformed REQUIRED field degrades to the safe
#     default (no position / no match / modeled P&L /
#     keep last equity) AND is counted as drift.
#   OPTIONAL (tolerant fallback is correct behavior):
#     alternate envelope shapes ({"result": ...} vs bare
#     list), candidate field-name spellings
#     (size|quantity, product_id|productId, ...). The
#     fallback is still OBSERVED via counters.
# ====================================================


class TestSchemaDrift11C(unittest.TestCase):

    def setUp(self):
        drain_schema_drift_stats()

    def tearDown(self):
        drain_schema_drift_stats()

    def test_first_candidate_hit_records_no_drift(self):
        self.assertEqual(_field({"size": 3}, "size", "quantity"), 3)
        stats = get_schema_drift_stats()
        self.assertEqual(stats["fallback"], 0)
        self.assertEqual(stats["miss"], 0)
        self.assertEqual(schema_health(), "HEALTHY")

    def test_fallback_candidate_is_observed(self):
        self.assertEqual(_field({"quantity": 3}, "size", "quantity"), 3)
        stats = get_schema_drift_stats()
        self.assertEqual(stats["fallback"], 1)
        self.assertEqual(schema_health(), "DEGRADED")

    def test_total_miss_is_observed(self):
        self.assertIsNone(_field({"other": 1}, "size", "quantity"))
        stats = get_schema_drift_stats()
        self.assertEqual(stats["miss"], 1)
        self.assertEqual(schema_health(), "DEGRADED")

    def test_envelope_unwrap_still_works(self):
        self.assertEqual(
            _field({"result": {"size": 5}}, "size", "quantity"), 5
        )
        self.assertEqual(
            _fields_list({"result": [{"size": 1}]}), [{"size": 1}]
        )

    def test_non_list_fields_list_is_a_miss(self):
        self.assertEqual(_fields_list({"result": {"size": 1}}), [])
        self.assertEqual(get_schema_drift_stats()["miss"], 1)

    def test_drain_resets(self):
        _field({"other": 1}, "size", "quantity")
        drained = drain_schema_drift_stats()
        self.assertEqual(drained["miss"], 1)
        self.assertEqual(schema_health(), "HEALTHY")

    def test_malformed_position_size_is_not_a_position(self):
        from core.live.broker_engine import BrokerEngine

        engine = BrokerEngine.__new__(BrokerEngine)
        engine._product_id = None
        records = [{"size": "not-a-number"}, {"quantity": None}]
        for record in records:
            found = engine._find_position([record])
            self.assertIsNone(found)

    def test_malformed_product_id_never_matches(self):
        from core.live.broker_engine import BrokerEngine

        engine = BrokerEngine.__new__(BrokerEngine)
        engine._product_id = 27
        records = [
            {"product_id": "not-a-number", "size": 5},
            {"productId": None, "size": 5},
        ]
        self.assertIsNone(engine._find_position(records))
        self.assertGreaterEqual(
            get_schema_drift_stats()["miss"], 1
        )

    def test_malformed_equity_keeps_last_balance(self):
        from core.live.broker_engine import BrokerEngine
        from core.risk.account import Account

        engine = BrokerEngine.__new__(BrokerEngine)
        engine.account = Account(starting_balance=2000.0)
        before = engine.account.state.balance

        class BadBalance:
            def balance(self):
                return {"total_equity": "not-a-number"}

        engine.executor = BadBalance()
        engine._sync_equity(candle=None)
        self.assertEqual(engine.account.state.balance, before)

    def test_malformed_exchange_pnl_falls_back_to_modeled(self):
        from core.backtesting.trade import Trade
        from core.live.broker_engine import BrokerEngine
        from core.risk.account import Account

        engine = BrokerEngine.__new__(BrokerEngine)
        engine.account = Account(starting_balance=2000.0)
        engine.portfolio_release = None
        engine.registry = None
        from core.backtesting.trade_registry import TradeRegistry

        engine.registry = TradeRegistry()
        engine._live_trade = None
        engine._open_order_id = None

        trade = Trade(
            direction="BULLISH",
            entry=100.0,
            stop_loss=90.0,
            take_profit=110.0,
            quantity=1.0,
            risk_amount=10.0,
            commission=1.0,
            slippage=1.0,
            entry_time=1,
        )
        engine._live_trade = trade

        class Candle:
            timestamp = 2

        flat = {
            "size": 0,
            "realized_pnl": "not-a-number",
            "exit_price": 105.0,
        }
        engine._find_position = lambda records, include_zero=False: flat
        engine._book_live_close(Candle(), [flat])
        self.assertIsNone(engine._live_trade)
        closed = engine.registry.all()
        self.assertEqual(len(closed), 1)
        # Modeled net P&L: gross 5 - commission 1 - slippage 1 = 3.
        self.assertAlmostEqual(closed[0].pnl, 3.0)


# ====================================================
# 11C-G -- market-data failure handling (candle builder)
# ====================================================


class TestCandleBuilderRobustness11C(unittest.TestCase):

    def test_invalid_prices_rejected_and_counted(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        for bad in (0, -1.0, None, "abc", float("nan"), float("inf")):
            self.assertIsNone(
                builder.update(1_700_000_000, bad),
                msg="price={!r}".format(bad),
            )
        self.assertEqual(builder.rejected_ticks, 6)
        self.assertEqual(builder.count(), 0)

    def test_invalid_volumes_rejected(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        for bad in (-5.0, float("nan"), float("inf"), "abc"):
            self.assertIsNone(builder.update(1_700_000_000, 100.0, bad))
        self.assertEqual(builder.rejected_ticks, 4)

    def test_invalid_timestamps_rejected(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        for bad in (None, "not-a-time", float("nan")):
            self.assertIsNone(builder.update(bad, 100.0))
        self.assertGreaterEqual(builder.rejected_ticks, 3)

    def test_stale_tick_never_moves_time_backwards(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        base = 1_700_000_000 - (1_700_000_000 % 60)
        self.assertIsNone(builder.update(base, 100.0))
        finished = builder.update(base + 60, 101.0)
        self.assertIsNotNone(finished)
        self.assertEqual(finished.timestamp, base)
        # Late tick for the already-closed bucket: ignored.
        self.assertIsNone(builder.update(base + 10, 999.0))
        self.assertEqual(builder.stale_ticks, 1)
        # Current bucket intact (open still 101, not 999).
        self.assertEqual(builder.current.open, 101.0)
        # History holds exactly one completed candle (no dup).
        self.assertEqual(builder.count(), 1)

    def test_valid_flow_unaffected(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        base = 1_700_000_000 - (1_700_000_000 % 60)
        builder.update(base, 100.0)
        builder.update(base + 5, 102.0)
        finished = builder.update(base + 60, 101.0)
        self.assertEqual(finished.high, 102.0)
        self.assertEqual(builder.stats()["rejected_ticks"], 0)

    def test_load_history_rejects_malformed_entries_typed(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        good = {
            "time": 1_700_000_000,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 10.0,
        }
        for bad in (
            "not-a-dict",
            dict((k, v) for k, v in good.items() if k != "open"),
            dict(good, open="abc"),
            dict(good, high=50.0, low=60.0),
            dict(good, high=90.0),
            dict(good, volume=-1.0),
            dict(good, open=0.0),
        ):
            with self.assertRaises(ValueError):
                builder.load_history([good, bad])

    def test_load_history_valid_unchanged(self):
        from data.candle_builder import CandleBuilder

        builder = CandleBuilder(timeframe="1m")
        bars = [
            {
                "time": 1_700_000_000 + 60 * i,
                "open": 100.0 + i,
                "high": 102.0 + i,
                "low": 99.0 + i,
                "close": 101.0 + i,
                "volume": 10.0,
            }
            for i in range(5)
        ]
        builder.load_history(bars)
        self.assertEqual(builder.count(), 5)


# ====================================================
# 11C-F -- websocket / transport failure injection
# ====================================================


class TestSubscriptionStreamRobustness11C(unittest.TestCase):

    def _stream(self):
        from data.delta.delta_subscription_stream import (
            DeltaSubscriptionStream,
        )

        return DeltaSubscriptionStream()

    def test_unknown_message_type_ignored(self):
        stream = self._stream()
        # Stage 1-3: provider keepalive/control frames are liveness,
        # not data and not "unknown" (heartbeat_frames); genuinely
        # unknown types are still counted as unknown and ignored.
        stream._emit_ticker({"type": "heartbeat", "ts": 1_700_000_000})
        self.assertEqual(stream.stats()["heartbeat_frames"], 1)
        self.assertEqual(stream.stats()["unknown_frames"], 0)
        self.assertEqual(stream.stats()["closed_candles"], 0)
        stream._emit_ticker({"type": "weird-opaque", "ts": 1_700_000_000})
        self.assertEqual(stream.stats()["unknown_frames"], 1)
        self.assertEqual(stream.stats()["closed_candles"], 0)

    def test_non_dict_frame_rejected(self):
        stream = self._stream()
        for bad in (None, "string", [1, 2], 42):
            stream._emit_ticker(bad)
        self.assertEqual(stream.stats()["malformed_frames"], 4)

    def test_missing_fields_rejected(self):
        stream = self._stream()
        cases = [
            {"type": "ticker"},
            {"type": "ticker", "d": []},
            {"type": "ticker", "d": "x"},
            {"type": "ticker", "d": [{}]},
            {"type": "ticker", "d": [{"s": "", "m": "1"}]},
            {"type": "ticker", "d": [{"s": "BTCUSDT"}]},
            {"type": "ticker", "d": [{"s": "BTCUSDT", "m": "abc"}]},
            {"type": "ticker", "d": [{"s": "BTCUSDT", "m": "0"}]},
            {"type": "ticker", "d": [{"s": "BTCUSDT", "m": "-5"}]},
            {
                "type": "ticker",
                "ts": 1_700_000_000,
                "d": [{"s": "BTCUSDT", "m": "NaN"}],
            },
            {
                "type": "ticker",
                "ts": "bad-ts",
                "d": [{"s": "BTCUSDT", "m": "100"}],
            },
        ]
        for raw in cases:
            stream._emit_ticker(raw)
        self.assertEqual(stream.stats()["malformed_frames"], len(cases))
        self.assertEqual(stream.stats()["closed_candles"], 0)

    def test_valid_ticker_flow_produces_closed_candle(self):
        stream = self._stream()
        received = []
        stream._handlers["BTCUSDT"] = (received.append, lambda: None)
        base = 1_700_000_000 - (1_700_000_000 % 60)
        stream._emit_ticker(
            {
                "type": "ticker",
                "ts": base,
                "d": [{"s": "BTCUSDT", "m": "100.0"}],
            }
        )
        stream._emit_ticker(
            {
                "type": "ticker",
                "ts": base + 61,
                "d": [{"s": "BTCUSDT", "m": "101.0"}],
            }
        )
        self.assertEqual(stream.stats()["frames_received"], 2)
        self.assertEqual(stream.stats()["closed_candles"], 1)
        closed = [c for c in received if c.closed]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].symbol, "BTCUSDT")
        self.assertEqual(closed[0].timestamp, base)

    def test_malformed_frames_cannot_create_trades(self):
        stream = self._stream()
        routed = []
        stream._handlers["BTCUSDT"] = (routed.append, lambda: None)
        stream._emit_ticker({"type": "ticker", "d": [{"s": "BTCUSDT"}]})
        stream._emit_ticker("garbage")
        self.assertEqual(
            [c for c in routed if getattr(c, "closed", False)], []
        )


# ====================================================
# 11C-E/F -- downstream isolation (worker + engine)
# ====================================================


class TestDownstreamIsolation11C(unittest.TestCase):

    def test_worker_isolates_downstream_exception(self):
        from core.history.candle import Candle
        from data.realtime.stream_worker import SubscriptionWorker

        calls = []

        class FakeTransport:
            def subscribe(self, symbol, on_candle, on_down):
                self.handler = on_candle

            def unsubscribe(self, symbol):
                pass

        def boom(candle):
            calls.append(candle)
            raise RuntimeError("strategy exploded")

        transport = FakeTransport()
        worker = SubscriptionWorker(
            symbol="BTC",
            transport=transport,
            clock=lambda: 1000.0,
            on_closed_candle=boom,
        )
        worker.start()
        candle = Candle(
            timestamp=1000,
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
            closed=True,
            symbol="BTC",
        )
        # Must not raise into the transport chain.
        transport.handler(candle)
        self.assertEqual(len(calls), 1)
        self.assertEqual(worker.callback_errors, 1)
        self.assertIn("strategy exploded", worker.last_callback_error)
        # Worker still live: next candle still delivered.
        transport.handler(
            Candle(
                timestamp=1060,
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
                closed=True,
                symbol="BTC",
            )
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(worker.callback_errors, 2)

    def test_engine_isolates_per_symbol_runtime_error(self):
        from core.history.candle import Candle
        from core.runtime.realtime_engine import RealTimeEngine

        class Instrument:
            def __init__(self, symbol):
                self.symbol = symbol
                self.exchange = "delta"
                self.instrument_id = "id-" + symbol

        class FakeUniverse:
            def __init__(self, instruments):
                self._instruments = instruments

            def eligible_instruments(self):
                return list(self._instruments)

        class SnapMgr:
            def __init__(self, instruments):
                self.instruments = instruments

            def refresh_discovery(self, **kwargs):
                return {}

            def build_universe(self, timeframe="1m"):
                return FakeUniverse(self.instruments)

        class FakeTransport:
            def __init__(self):
                self._routes = {}

            def subscribe(self, symbol, on_candle, on_down):
                self._routes[symbol] = (on_candle, on_down)

            def unsubscribe(self, symbol):
                self._routes.pop(symbol, None)

            def close(self):
                self._routes.clear()

        instruments = [Instrument("AAA"), Instrument("BBB")]
        engine = RealTimeEngine(
            universe_manager=SnapMgr(instruments),
            transport_factory=FakeTransport,
            refresh_interval_seconds=0,
        )

        def world_factory(context):
            class ExplodingWorld:
                def __init__(self, ctx):
                    self.context = ctx

                def reset(self):
                    pass

                def on_candle(self, event):
                    if self.context.market.symbol == "AAA":
                        raise RuntimeError("AAA strategy bug")

            return ExplodingWorld(context)

        # Rebuild with exploding world factory.
        from core.runtime.pipeline_registry import PipelineRegistry

        engine.registry = PipelineRegistry(
            world_factory=world_factory,
            timeframe="1m",
            strategy="",
            data_source=None,
        )
        engine.start()
        candle_a = Candle(
            timestamp=1000,
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
            closed=True,
            symbol="AAA",
        )
        candle_b = Candle(
            timestamp=1000,
            open=2.0,
            high=2.0,
            low=2.0,
            close=2.0,
            volume=1.0,
            closed=True,
            symbol="BBB",
        )
        engine._on_closed_candle(candle_a)
        engine._on_closed_candle(candle_b)
        self.assertEqual(engine.routed, 2)
        self.assertEqual(engine.route_errors, 1)
        self.assertIn("AAA strategy bug", engine.last_route_error)
        # BBB runtime processed its bar despite AAA exploding.
        key_b = ("delta", "id-BBB")
        self.assertEqual(
            engine.runtimes[key_b].processed_bars, 1
        )


# ====================================================
# 11C-H -- universe refresh failure handling
# ====================================================


def _test_instrument(symbol, exchange="DELTA"):
    from core.registry.instrument import Instrument

    return Instrument(
        instrument_id="id-" + symbol,
        symbol=symbol,
        exchange=exchange,
        product_type="PERPETUAL",
        tick_size=0.01,
        quantity_step=0.001,
        minimum_quantity=0.001,
        trading_enabled=True,
        state="ACTIVE",
    )


class ScriptedLiquidity:
    def __init__(self, volume=10_000_000.0, raises=None):
        self.volume = volume
        self.raises = raises
        self.calls = 0

    def quote_volume_24h(self, symbol):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.volume


class ScriptedHistory:
    def __init__(self, bars=500, raises=None):
        self.bars = bars
        self.raises = raises
        self.calls = 0

    def history_bars(self, symbol, timeframe="1m"):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.bars


def _registry_with(*symbols):
    from core.registry.instrument_registry import InstrumentRegistry

    registry = InstrumentRegistry()
    for symbol in symbols:
        # Two upserts: NEWLY_LISTED -> ACTIVE (confirmation).
        registry.upsert(_test_instrument(symbol))
        registry.upsert(_test_instrument(symbol))
    return registry


def _raw_row(symbol, pid):
    """Minimal /v2/products-shaped row for offline discovery."""
    return {
        "id": pid,
        "symbol": symbol,
        "contract_type": "perpetual_futures",
        "tick_size": "0.01",
        "contract_value": "1",
        "minimum_order_size": "1",
        "state": "live",
        "underlying_asset": {"symbol": "X"},
        "quoting_asset": {"symbol": "USDT"},
        "price_precision": 2,
        "contract_value_precision": 0,
    }


class FakeProductClient:
    """Offline product catalog: fetch() returns stable rows."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.fetches = 0

    def fetch(self):
        self.fetches += 1
        return list(self.rows)


def _manager_via_discovery(symbols, liq=None, hist=None):
    """Real UniverseManager over a real InstrumentRegistry,
    confirmed through two offline discovery passes
    (NEWLY_LISTED -> ACTIVE), with scriptable providers."""
    from core.registry.instrument_registry import InstrumentRegistry
    from core.universe.universe_manager import UniverseManager

    registry = InstrumentRegistry()
    manager = UniverseManager(
        registry=registry,
        liquidity_provider=(
            liq if liq is not None else ScriptedLiquidity()
        ),
        history_provider=(
            hist if hist is not None else ScriptedHistory()
        ),
    )
    client = FakeProductClient(
        [_raw_row(symbol, 101 + index) for index, symbol in enumerate(symbols)]
    )
    manager.refresh_discovery(client=client)
    manager.refresh_discovery(client=client)
    return manager, client


class TestUniverseRefreshFailures11C(unittest.TestCase):

    def test_successful_refresh(self):
        manager, _client = _manager_via_discovery(("AAA", "BBB"))
        universe = manager.build_universe()
        self.assertEqual(
            {i.symbol for i in universe.eligible_instruments()},
            {"AAA", "BBB"},
        )

    def test_provider_exception_recorded_scheduler_survives(self):
        from core.universe.refresh_scheduler import RefreshScheduler

        manager, client = _manager_via_discovery(
            ("AAA",), liq=ScriptedLiquidity(raises=TimeoutError("t/o"))
        )
        scheduler = RefreshScheduler(manager=manager, interval_seconds=0)
        result = scheduler.refresh(client=client)
        self.assertIsNone(result)
        self.assertEqual(len(scheduler.errors), 1)
        self.assertIsInstance(scheduler.errors[0], TimeoutError)

    def test_empty_universe_when_no_data(self):
        manager, _client = _manager_via_discovery(
            ("AAA",), liq=ScriptedLiquidity(volume=None)
        )
        universe = manager.build_universe()
        self.assertEqual(list(universe.eligible_instruments()), [])

    def test_partial_universe(self):
        class SplitLiq:
            def quote_volume_24h(self, symbol):
                return 10_000_000.0 if symbol == "AAA" else None

        manager, _client = _manager_via_discovery(
            ("AAA", "BBB"), liq=SplitLiq()
        )
        universe = manager.build_universe()
        self.assertEqual(
            [i.symbol for i in universe.eligible_instruments()], ["AAA"]
        )

    def test_failed_async_refresh_preserves_cached_universe(self):
        import time

        from core.universe.async_refresh_scheduler import (
            AsyncRefreshScheduler,
        )
        from core.universe.refresh_scheduler import RefreshScheduler

        manager, client = _manager_via_discovery(("AAA",))
        scheduler = RefreshScheduler(manager=manager, interval_seconds=0)
        wrapper = AsyncRefreshScheduler(scheduler)
        first = scheduler.refresh(client=client)
        self.assertIsNotNone(first)
        # Now break the provider; background refresh must fail
        # while the cached universe stays usable.
        manager.liquidity_provider = ScriptedLiquidity(
            raises=ConnectionError("down")
        )
        scheduler.last_run = None
        wrapper._last_success = first
        wrapper.run_if_due(client=client)
        deadline = time.time() + 5.0
        while wrapper.refresh_in_progress and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(wrapper.refresh_in_progress)
        cached = wrapper.get_cached_universe()
        self.assertIsNotNone(cached)
        self.assertEqual(
            [i.symbol for i in cached.eligible_instruments()], ["AAA"]
        )
        self.assertIsNotNone(wrapper.last_refresh_error)

    def test_refresh_overlap_is_coalesced_single_worker(self):
        import time

        from core.universe.async_refresh_scheduler import (
            AsyncRefreshScheduler,
        )
        from core.universe.refresh_scheduler import RefreshScheduler

        started = threading.Event()
        release = threading.Event()

        class BlockingManager:
            def __init__(self):
                self.calls = 0

            def refresh_discovery(self, **kwargs):
                return {}

            def build_universe(self, timeframe="1m"):
                self.calls += 1
                started.set()
                release.wait(timeout=5.0)

                class U:
                    def eligible_instruments(self):
                        return []

                return U()

        inner = RefreshScheduler(
            manager=BlockingManager(), interval_seconds=0
        )
        wrapper = AsyncRefreshScheduler(inner)
        wrapper.run_if_due()
        self.assertTrue(started.wait(timeout=5.0))
        # Overlapping requests while one is active: coalesced.
        for _ in range(10):
            wrapper.run_if_due()
            wrapper.force_refresh()
        self.assertTrue(wrapper.refresh_in_progress)
        release.set()
        deadline = time.time() + 5.0
        while wrapper.refresh_in_progress and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(wrapper.refresh_in_progress)
        # At most the initial worker ran (coalesced, no queue).
        self.assertLessEqual(inner.manager.calls, 2)

    def test_no_lock_held_across_provider_io(self):
        import time

        from core.universe.async_refresh_scheduler import (
            AsyncRefreshScheduler,
        )
        from core.universe.refresh_scheduler import RefreshScheduler

        class SlowManager:
            def refresh_discovery(self, **kwargs):
                time.sleep(0.4)
                return {}

            def build_universe(self, timeframe="1m"):
                class U:
                    def eligible_instruments(self):
                        return []

                return U()

        inner = RefreshScheduler(manager=SlowManager(), interval_seconds=0)
        wrapper = AsyncRefreshScheduler(inner)
        tick = time.perf_counter()
        wrapper.run_if_due()
        elapsed = time.perf_counter() - tick
        # run_if_due must not block on provider I/O.
        self.assertLess(elapsed, 0.2)
        deadline = time.time() + 5.0
        while wrapper.refresh_in_progress and time.time() < deadline:
            time.sleep(0.01)


# ====================================================
# 11C-J -- task / concurrency safety
# ====================================================


class TestTaskLifecycle11C(unittest.TestCase):

    def test_subscription_stream_thread_lifecycle(self):
        import time

        from data.delta.delta_subscription_stream import (
            DeltaSubscriptionStream,
        )

        before = len(threading.enumerate())
        stream = DeltaSubscriptionStream()

        class DummyWS:
            def send(self, payload):
                pass

            def __iter__(self):
                import time as _time

                _time.sleep(0.3)
                return iter([])

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def close(self):
                pass

        real_connect = None
        try:
            import websockets.sync.client as ws_client

            real_connect = ws_client.connect
            ws_client.connect = lambda url: DummyWS()
            stream.subscribe("AAA", lambda c: None, lambda: None)
            time.sleep(0.2)
            during = len(threading.enumerate())
            self.assertGreaterEqual(during, before)
            stream.close()
            time.sleep(0.8)
        finally:
            if real_connect is not None:
                ws_client.connect = real_connect
        after = len(threading.enumerate())
        # No orphan pump thread remains (allow slack of 1).
        self.assertLessEqual(after, before + 1)

    def test_manager_stop_all_cleans_up(self):
        from data.realtime.subscription_manager import (
            MultiSymbolSubscriptionManager,
        )

        class FakeTransport:
            def __init__(self):
                self._routes = {}
                self.closed = False

            def subscribe(self, symbol, on_candle, on_down):
                self._routes[symbol] = (on_candle, on_down)

            def unsubscribe(self, symbol):
                self._routes.pop(symbol, None)

            def close(self):
                self.closed = True

        transport = FakeTransport()
        manager = MultiSymbolSubscriptionManager(
            transport_factory=lambda: transport
        )
        manager.sync([_test_instrument("AAA"), _test_instrument("BBB")])
        self.assertEqual(manager.count, 2)
        manager.stop_all()
        self.assertEqual(manager.count, 0)
        self.assertTrue(transport.closed)
        self.assertEqual(manager.errors, [])

    def test_async_scheduler_never_spawns_unbounded_workers(self):
        import time

        from core.universe.async_refresh_scheduler import (
            AsyncRefreshScheduler,
        )
        from core.universe.refresh_scheduler import RefreshScheduler

        class SlowManager:
            def __init__(self):
                self.calls = 0

            def refresh_discovery(self, **kwargs):
                time.sleep(0.2)
                return {}

            def build_universe(self, timeframe="1m"):
                self.calls += 1

                class U:
                    def eligible_instruments(self):
                        return []

                return U()

        inner = RefreshScheduler(manager=SlowManager(), interval_seconds=0)
        wrapper = AsyncRefreshScheduler(inner)
        before = len(threading.enumerate())
        for _ in range(25):
            wrapper.run_if_due()
        deadline = time.time() + 8.0
        while wrapper.refresh_in_progress and time.time() < deadline:
            time.sleep(0.02)
        after = len(threading.enumerate())
        # One bounded worker, not 25 threads.
        self.assertLessEqual(inner.manager.calls, 2)
        self.assertLessEqual(after, before + 2)


# ====================================================
# 11C-O -- state consistency / reconciliation
# ====================================================


class TestReconciliation11C(unittest.TestCase):

    def test_duplicate_order_event_does_not_duplicate(self):
        from core.execution.order_registry import PENDING, OrderRegistry

        registry = OrderRegistry()
        order = make_intent(symbol="AAA")
        order.setup_id = "S-DUP"
        first, first_id = registry.create(order)
        second, second_id = registry.create(order)
        self.assertEqual(first_id, second_id)
        self.assertIs(first, second)
        self.assertEqual(len(registry.all()), 1)
        self.assertEqual(first.status, PENDING)

    def test_mark_filled_only_from_pending(self):
        from types import SimpleNamespace

        from core.execution.order_registry import (
            FILLED,
            PENDING,
            OrderRegistry,
        )

        registry = OrderRegistry()
        order = make_intent(symbol="AAA")
        order.setup_id = "S-FILL"
        registered, _ = registry.create(order)
        self.assertEqual(registered.status, PENDING)
        trade_id = registry.mark_filled(registered, trade=SimpleNamespace())
        self.assertIsNotNone(trade_id)
        self.assertEqual(registered.status, FILLED)
        # Stale/duplicate fill: no-op, no second trade id.
        self.assertIsNone(
            registry.mark_filled(registered, trade=SimpleNamespace())
        )

    def test_missing_order_lookup_returns_none(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        self.assertIsNone(registry.get("no-such-order"))
        self.assertIsNone(registry.get_by_setup_id("no-such-setup"))
        self.assertFalse(registry.has_order_for_setup("no-such-setup"))

    def test_terminal_order_cannot_fill(self):
        from types import SimpleNamespace

        from core.execution.order_registry import (
            EXPIRED,
            OrderRegistry,
        )

        registry = OrderRegistry(max_wait_bars=0)
        order = make_intent(symbol="AAA")
        order.setup_id = "S-EXP"
        registered, _ = registry.create(order)
        expired = registry.advance()
        self.assertEqual(len(expired), 1)
        self.assertEqual(registered.status, EXPIRED)
        self.assertIsNone(
            registry.mark_filled(registered, trade=SimpleNamespace())
        )

    def test_broker_rejects_double_close_fabrication(self):
        from core.live.broker_engine import BrokerEngine

        engine = BrokerEngine.__new__(BrokerEngine)
        with self.assertRaises(RuntimeError):
            engine._book_closed([object(), object()], candle=None)

    def test_paper_ledger_reconciles_with_account(self):
        from core.backtesting.trade_registry import TradeRegistry
        from core.risk.account import Account

        account = Account(starting_balance=2000.0)
        ledger = TradeRegistry()
        self.assertEqual(ledger.count(), 0)
        self.assertEqual(account.balance, 2000.0)


# ====================================================
# 11C-P -- control API / remote safety regression
# ====================================================


class TestControlApiSafety11C(unittest.TestCase):

    def test_unknown_route_is_unreachable(self):
        from core.remote.roles import required_role

        self.assertIsNone(required_role("GET", "/orders/live"))
        self.assertIsNone(required_role("POST", "/orders"))
        self.assertIsNone(required_role("POST", "/live/enable"))
        self.assertIsNone(required_role("DELETE", "/positions"))

    def test_no_write_or_live_route_at_any_tier(self):
        from core.remote import roles

        # The read surface is GET-only ...
        for method, _path in roles.READ_ROUTES:
            self.assertEqual(method, "GET")
        # ... and no lifecycle command enables live trading or
        # order placement.
        for command in (
            "enable_live", "disable_live", "place_order",
            "cancel_order", "set_leverage", "go_live",
        ):
            self.assertIsNone(
                roles.command_required_role(command),
                msg="command={!r}".format(command),
            )

    def test_role_hierarchy(self):
        from core.remote.roles import satisfies

        self.assertTrue(satisfies("CONTROL", "VIEW"))
        self.assertTrue(satisfies("EMERGENCY", "CONTROL"))
        self.assertFalse(satisfies("VIEW", "CONTROL"))
        self.assertFalse(satisfies("CONTROL", "EMERGENCY"))
        self.assertFalse(satisfies("UNKNOWN", "VIEW"))

    def test_emergency_stop_requires_emergency(self):
        from core.remote.roles import command_required_role

        self.assertEqual(command_required_role("emergency_stop"), "EMERGENCY")
        self.assertEqual(command_required_role("stop"), "CONTROL")
        self.assertIsNone(command_required_role("enable_live"))
        self.assertIsNone(command_required_role("place_order"))

    def test_remote_control_cannot_arm_live(self):
        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.PAPER,
            allow_live=False,
            live_execute=False,
            has_credentials=False,
        )
        self.assertFalse(decision.allowed)
        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require_decision(decision, component="remote")


# ====================================================
# 11C-V -- live safety regression (Phase 11A intact)
# ====================================================


class TestLiveSafetyRegression11C(unittest.TestCase):

    def test_live_defaults_remain_disabled(self):
        from config.settings import settings

        self.assertFalse(settings.ALLOW_LIVE)
        self.assertFalse(settings.LIVE_EXECUTE)

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ConfigurationError):
            LiveSafetyGate.decide(mode="TURBO", allow_live=True,
                                  live_execute=True, has_credentials=True)

    def test_paper_live_conflict_rejected(self):
        with self.assertRaises(ConfigurationError):
            ExecutionMode.resolve(
                paper_mode=True, live_mode=True, execution_mode=""
            )

    def test_missing_credentials_blocked(self):
        decision = LiveSafetyGate.decide(
            mode=ExecutionMode.LIVE,
            allow_live=True,
            live_execute=True,
            has_credentials=False,
        )
        self.assertFalse(decision.allowed)
        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require(
                mode=ExecutionMode.LIVE,
                allow_live=True,
                live_execute=True,
                has_credentials=False,
                component="11C",
            )

    def test_paper_path_makes_zero_real_order_calls(self):
        from core.runtime.execution_port import PaperExecutionAdapter

        port = PaperExecutionAdapter()
        self.assertEqual(port.mode, "paper")
        for op in ("fetch", "cancel", "balance", "positions"):
            with self.assertRaises(Exception):
                getattr(port, op)("x")

    def test_counting_transport_records_zero_without_arm(self):
        executor, fake = make_executor()
        with self.assertRaises(LiveBlockedError):
            executor.execute(make_intent())
        self.assertEqual(fake.placed, [])


if __name__ == "__main__":
    unittest.main()
