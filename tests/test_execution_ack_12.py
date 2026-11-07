"""
====================================================

QuantEngine

Phase 12 -- execution acknowledgement correctness.

Proves the canonical live transition:

    executor.execute() returning
        is NEVER equivalent to
    the exchange confirming FILLED.

Covers (stdlib only, fake transports, never real
settings/credentials):

  order_ack classifier:
    1. explicit filled + quantity evidence -> FILLED
    2. explicit filled label alone -> FILLED
    3. open/working labels -> ACKNOWLEDGED
    4. partial label or short fill quantity -> PARTIAL
    5. zero-fill + filled label -> UNKNOWN
    6. closed-like label without evidence -> UNKNOWN
    7. missing/unrecognized/non-mapping ack -> UNKNOWN
    8. cancelled/expired/rejected labels -> terminal
    9. executor exception -> typed UNKNOWN (never raises)
  BrokerEngine live path (test_armed gate, fake executor):
    10. ack-open place books NOTHING (working mirror only)
    11. visible position confirms the fill exactly once
    12. duplicate sightings never double-book
    13. partial ack is never FILLED and halts routing
    14. unknown ack is never FILLED and halts routing
    15. executor exception clears state, halts, engine lives
    16. dead-on-arrival states clear without halting
    17. fetch-confirmed fill completes the mirror
    18. kill switch blocks live routing
  order ids:
    19. deterministic, setup-bound, sanitized, monotonic
        fallback (no wall clock, no UUID, no randomness).

====================================================
"""

import unittest

from core.execution.order_ack import (
    ACKNOWLEDGED,
    CANCELLED,
    EXPIRED,
    FILLED,
    PARTIAL,
    REJECTED,
    UNKNOWN,
    classify_ack,
    classify_exception,
)
from core.execution.order_executor import (
    DeltaOrderExecutor,
    order_seq_value,
    reset_order_seq,
)


class TestClassifyAck(unittest.TestCase):

    def test_filled_label_with_quantity_evidence(self):
        ack = classify_ack({
            "result": {
                "id": "1",
                "status": "filled",
                "filled_size": 2.0,
                "size": 2.0,
            }
        })
        self.assertEqual(ack.state, FILLED)

    def test_filled_label_alone_is_exchange_authority(self):
        ack = classify_ack({"status": "filled"})
        self.assertEqual(ack.state, FILLED)

    def test_open_labels_acknowledge(self):
        for label in ("open", "pending", "new", "working",
                      "live", "active", "placed"):
            with self.subTest(label=label):
                ack = classify_ack({"status": label})
                self.assertEqual(ack.state, ACKNOWLEDGED)

    def test_partial_label_never_filled(self):
        ack = classify_ack({
            "status": "partially_filled",
            "filled_size": 1.0,
            "size": 2.0,
        })
        self.assertEqual(ack.state, PARTIAL)

    def test_short_quantity_beats_open_label(self):
        ack = classify_ack({
            "status": "open",
            "filled_size": 1.0,
            "size": 2.0,
        })
        self.assertEqual(ack.state, PARTIAL)

    def test_zero_fill_with_filled_label_is_unknown(self):
        ack = classify_ack({
            "status": "filled",
            "filled_size": 0.0,
            "size": 2.0,
        })
        self.assertEqual(ack.state, UNKNOWN)

    def test_closed_without_evidence_is_unknown(self):
        for label in ("closed", "done", "complete", "completed"):
            with self.subTest(label=label):
                ack = classify_ack({"status": label})
                self.assertEqual(ack.state, UNKNOWN)

    def test_missing_status_is_unknown(self):
        self.assertEqual(classify_ack({}).state, UNKNOWN)
        self.assertEqual(classify_ack({"id": "1"}).state, UNKNOWN)
        self.assertEqual(classify_ack(None).state, UNKNOWN)
        self.assertEqual(classify_ack("filled").state, UNKNOWN)

    def test_unrecognized_status_is_unknown(self):
        ack = classify_ack({"status": "mysterious_future_state"})
        self.assertEqual(ack.state, UNKNOWN)

    def test_terminal_labels(self):
        self.assertEqual(
            classify_ack({"status": "cancelled"}).state, CANCELLED)
        self.assertEqual(
            classify_ack({"status": "canceled"}).state, CANCELLED)
        self.assertEqual(
            classify_ack({"status": "expired"}).state, EXPIRED)
        self.assertEqual(
            classify_ack({"status": "rejected"}).state, REJECTED)
        self.assertEqual(
            classify_ack({"status": "failed"}).state, REJECTED)

    def test_exception_maps_to_typed_unknown(self):
        ack = classify_exception(ValueError("boom"))
        self.assertEqual(ack.state, UNKNOWN)
        self.assertIn("ValueError", ack.detail)
        # Never raises, even on hostile input.
        self.assertEqual(classify_exception(None).state, UNKNOWN)


class Candle:

    def __init__(self, high, low, close, timestamp):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


class FakePipeline:

    def __init__(self, script=None):
        self.script = script or {}
        self._idx = 0
        self.reset()

    def reset(self):
        from core.market_state import MarketState
        from core.pipeline.pipeline_context import PipelineContext
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST",
                                          timeframe="1m")
        self._idx = 0

    def on_candle(self, event):
        self.context.add_candle(event.candle)
        self.context.market.timestamp = event.candle.timestamp
        self.context.order = self.script.get(self._idx, None)
        self._idx += 1


class FakeExecutor:

    def __init__(self, ack=None, positions=None, balance=None,
                 fetch=None, explode=None):
        self.calls = []
        self._ack = ack if ack is not None else {
            "result": {"id": "QE-LIVE-1", "status": "open"}}
        self._positions = positions or []
        self._balance = balance if balance is not None else {}
        self._fetch = fetch if fetch is not None else {}
        self._explode = explode

    def execute(self, intent, safety=None):
        self.calls.append(("execute", intent.symbol))
        if self._explode is not None:
            raise self._explode
        return {"success": True, "intent": intent,
                "contract": type("C", (), {"product_id": 2})(),
                "response": dict(self._ack)}

    def fetch(self, order_id):
        self.calls.append(("fetch", order_id))
        return dict(self._fetch)

    def cancel(self, order_id):
        self.calls.append(("cancel", order_id))
        return {}

    def balance(self):
        self.calls.append(("balance",))
        return dict(self._balance)

    def positions(self):
        self.calls.append(("positions",))
        return list(self._positions)


def order(**kwargs):
    # Phase-14 maintenance: gate-compliant economics (gross RR
    # (170-100)/10 = 7.0 >= 6, zero costs so the post-cost layer
    # is vacuous), because BrokerEngine._route now enforces the
    # mandatory geometry + gross-RR + post-cost gates — a hand-fed
    # sub-6 order must never route. Ack-mechanics intent unchanged
    # (no test below depends on TP exits).
    from core.risk.order_intent import OrderIntent
    fields = dict(direction="BULLISH", entry=100.0,
                  stop_loss=90.0, take_profit=170.0,
                  quantity=1.0, commission=0.0, slippage=0.0,
                  confidence=85.0, score=85.0, symbol="TEST",
                  valid=True, setup_id="S-1", order_id="T-ORDER-1")
    fields.update(kwargs)
    return OrderIntent(**fields)


def register(engine, intent):
    registry = engine.pipeline.context.order_registry
    minted, _ = registry.create(intent, bar=0, timestamp=1)
    return minted


SAFE = dict(high=105.0, low=99.0, close=102.0)


def _live_engine(script, executor, **kwargs):
    from core.execution.live_safety_gate import LiveSafetyGate
    from core.live.broker_engine import BrokerEngine
    kwargs.setdefault("safety", LiveSafetyGate.test_armed())
    pipeline = FakePipeline(script)
    engine = BrokerEngine(pipeline, event_bus=None,
                          executor=executor, dry_run=False,
                          **kwargs)
    return engine


class TestBrokerAckTruth(unittest.TestCase):

    def test_ack_open_books_nothing(self):
        executor = FakeExecutor(positions=[])
        engine = _live_engine({0: order()}, executor)
        engine.run_candle(Candle(**SAFE, timestamp=1))

        # Working mirror exists (second fill suppressed) but
        # NOTHING is booked and nothing is confirmed.
        self.assertIsNotNone(engine.current_trade)
        self.assertEqual(engine.registry.count(), 0)
        self.assertEqual(engine._open_order_id, "QE-LIVE-1")
        self.assertEqual(engine._ack_state, ACKNOWLEDGED)
        self.assertFalse(engine._fill_confirmed)
        self.assertFalse(engine.reconciler.halt_new_orders)

    def test_visible_position_confirms_fill(self):
        executor = FakeExecutor(positions=[])
        engine = _live_engine({0: order()}, executor)
        register(engine, engine.pipeline.script[0])
        engine.run_candle(Candle(**SAFE, timestamp=1))
        self.assertFalse(engine._fill_confirmed)

        executor._positions = [{"result": [{
            "product_id": 2, "size": 1.0, "entry_price": 100.0}]}]
        engine.run_candle(Candle(**SAFE, timestamp=2))

        self.assertTrue(engine._fill_confirmed)
        self.assertEqual(engine._ack_state, FILLED)
        registered = engine.pipeline.context.order_registry.get(
            "T-ORDER-1")
        self.assertIsNotNone(registered)
        self.assertEqual(registered.status, "FILLED")

    def test_duplicate_sightings_never_double_book(self):
        executor = FakeExecutor(positions=[])
        engine = _live_engine({0: order()}, executor)
        register(engine, engine.pipeline.script[0])
        engine.run_candle(Candle(**SAFE, timestamp=1))

        executor._positions = [{"result": [{
            "product_id": 2, "size": 1.0, "entry_price": 100.0}]}]
        engine.run_candle(Candle(**SAFE, timestamp=2))
        engine.run_candle(Candle(**SAFE, timestamp=3))
        engine.run_candle(Candle(**SAFE, timestamp=4))

        # Still working (no close), registry untouched by the
        # fill transition itself (booking happens on close).
        self.assertTrue(engine._fill_confirmed)
        self.assertEqual(engine.registry.count(), 0)
        registered = engine.pipeline.context.order_registry.get(
            "T-ORDER-1")
        self.assertEqual(registered.status, "FILLED")

    def test_partial_ack_never_filled_and_halts(self):
        executor = FakeExecutor(
            ack={"result": {"id": "QE-P-1", "status": "open",
                            "filled_size": 0.5, "size": 1.0}},
            positions=[])
        engine = _live_engine({0: order()}, executor)
        engine.run_candle(Candle(**SAFE, timestamp=1))

        self.assertFalse(engine._fill_confirmed)
        self.assertEqual(engine.registry.count(), 0)
        self.assertTrue(engine.reconciler.halt_new_orders)
        self.assertIn("PARTIAL", engine.reconciler.halt_reason)

    def test_unknown_ack_never_filled_and_halts(self):
        executor = FakeExecutor(ack={}, positions=[])
        engine = _live_engine({0: order()}, executor)
        engine.run_candle(Candle(**SAFE, timestamp=1))
        engine.run_candle(Candle(**SAFE, timestamp=2))

        self.assertFalse(engine._fill_confirmed)
        self.assertEqual(engine.registry.count(), 0)
        self.assertTrue(engine.reconciler.halt_new_orders)
        # Halted: the second candle must NOT re-route into a
        # possible duplicate.
        self.assertEqual(
            executor.calls.count(("execute", "TEST")), 1)
        self.assertIsNotNone(engine._last_error)

    def test_executor_exception_clears_and_halts(self):
        executor = FakeExecutor(
            explode=TimeoutError("transport down"), positions=[])
        engine = _live_engine({0: order()}, executor)
        engine.run_candle(Candle(**SAFE, timestamp=1))
        # Engine survives the candle with typed failure state.
        engine.run_candle(Candle(**SAFE, timestamp=2))

        self.assertIsNone(engine.current_trade)
        self.assertIsNone(engine._live_trade)
        self.assertFalse(engine._fill_confirmed)
        self.assertEqual(engine.registry.count(), 0)
        self.assertTrue(engine.reconciler.halt_new_orders)
        self.assertEqual(
            engine.placed[0]["reason"], "EXECUTOR_EXCEPTION")
        self.assertIsNotNone(engine._last_error)

    def test_dead_on_arrival_clears_without_halting(self):
        for label in ("rejected", "cancelled", "expired"):
            with self.subTest(label=label):
                executor = FakeExecutor(
                    ack={"result": {"id": "QE-D-1",
                                    "status": label}},
                    positions=[])
                engine = _live_engine({0: order()}, executor)
                engine.run_candle(Candle(**SAFE, timestamp=1))

                self.assertIsNone(engine.current_trade)
                self.assertIsNone(engine._open_order_id)
                self.assertFalse(engine._fill_confirmed)
                self.assertEqual(engine.registry.count(), 0)
                # A dead order never blocks reuse: no halt.
                self.assertFalse(engine.reconciler.halt_new_orders)

    def test_fetch_confirmed_fill_completes_mirror(self):
        executor = FakeExecutor(
            positions=[],
            fetch={"result": {"id": "QE-LIVE-1",
                              "status": "filled",
                              "filled_size": 1.0, "size": 1.0}})
        engine = _live_engine({0: order()}, executor)
        register(engine, engine.pipeline.script[0])
        engine.run_candle(Candle(**SAFE, timestamp=1))

        # No position yet, but the fetch watch on the same
        # candle already confirms the filled record.
        self.assertTrue(engine._fill_confirmed)
        engine.run_candle(Candle(**SAFE, timestamp=2))

        self.assertTrue(engine._fill_confirmed)
        registered = engine.pipeline.context.order_registry.get(
            "T-ORDER-1")
        self.assertEqual(registered.status, "FILLED")
        self.assertEqual(engine.registry.count(), 0)

    def test_kill_switch_blocks_live_routing(self):
        from core.risk.account import Account
        executor = FakeExecutor(positions=[])
        account = Account(starting_balance=2000.0)
        account.state.kill_switch = True
        engine = _live_engine({0: order()}, executor,
                              account=account)
        engine.run_candle(Candle(**SAFE, timestamp=1))

        self.assertEqual(
            executor.calls.count(("execute", "TEST")), 0)
        self.assertIsNone(engine.current_trade)
        self.assertEqual(engine.registry.count(), 0)


class TestDeterministicClientOrderId(unittest.TestCase):

    def test_setup_bound_and_sanitized(self):
        _made = DeltaOrderExecutor._default_client_order_id
        first = _made(order(order_id="[S-1]-ORDER-3"))
        second = _made(order(order_id="[S-1]-ORDER-3"))
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("QE-"))
        for ch in first[3:]:
            self.assertTrue(ch.isalnum() or ch in "-_.:",
                            msg=f"unsafe char {ch!r}")
        # No wall-clock milliseconds embedded: reruns across
        # time are identical (same input twice above proves it).

    def test_distinct_setups_distinct_ids(self):
        made = DeltaOrderExecutor._default_client_order_id
        self.assertNotEqual(
            made(order(order_id="A-ORDER-1")),
            made(order(order_id="B-ORDER-1")))

    def test_fallback_counter_deterministic(self):
        reset_order_seq(0)
        made = DeltaOrderExecutor._default_client_order_id
        first = made(order(order_id=""))
        second = made(order(order_id=""))
        self.assertEqual(first, "QE-TEST-1")
        self.assertEqual(second, "QE-TEST-2")
        self.assertEqual(order_seq_value(), 2)
        reset_order_seq(0)


if __name__ == "__main__":
    unittest.main()
