"""
====================================================

QuantEngine -- Phase 11A P1 guard tests.

Locks in three audit-identified hardening fixes:

  A. PositionSizer: balance <= 0 -> invalid (the guard
     exists in core/risk/position_sizer.py:59-89; these
     tests pin zero / negative / positive behavior so a
     future edit cannot silently reintroduce a negative
     risk amount).
  B. DeltaOrderExecutor._contract: product_id /
     precision validation -> InvalidContractError (a
     ValueError subclass, so existing ValueError callers
     keep working) BEFORE any transport call.
  C. DeltaContractLoader.load: transport/schema failures
     -> ContractLoadError instead of a bare
     KeyError("result").
  D. LiveSafetyGate.require_decision: only tokens minted
     by decide() whose fields re-evaluate to allowed can
     arm LIVE (forged tokens refused, transport silence
     proven at a counting fake).

Stdlib only (unittest + mock). No network.

====================================================
"""

import unittest
from unittest import mock

from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_contract import DeltaContract
from core.execution.live_safety_gate import (
    ExecutionMode,
    LiveBlockedError,
    LiveSafetyGate,
    SafetyDecision,
)
from core.execution.order_executor import (
    DeltaOrderExecutor,
    InvalidContractError,
)
from core.risk.order_intent import OrderIntent
from core.risk.position_sizer import PositionSizer


def contract(**overrides):
    params = {
        "symbol": "BTCUSDT",
        "exchange": "DELTA",
        "contract_type": "perpetual_futures",
        "tick_size": 0.01,
        "quantity_step": 0.001,
        "min_quantity": 0.00001,
        "max_leverage": 100.0,
        "maker_fee": 0.0005,
        "taker_fee": 0.001,
        "price_precision": 2,
        "quantity_precision": 5,
        "product_id": 2,
        # Phase-9 execution-evidence hardening: the order transport
        # additionally requires explicit verified live-execution
        # evidence.  The default helper supplies synthetic test
        # evidence (matching test_order_executor.py); the gate itself
        # is covered by dedicated negative tests there and in 11C.
        "live_execution_verified": True,
        "live_execution_evidence": "11A synthetic test fixture",
    }
    params.update(overrides)
    return DeltaContract(**params)


class _FakeRest:
    authenticated = True

    def __init__(self):
        self.calls = []

    def post(self, path, payload=None):
        self.calls.append(("post", path, payload))
        return {"result": {"id": "X"}}


class TestSizerNonPositiveBalance(unittest.TestCase):

    def _size(self, balance):
        return PositionSizer().calculate(
            balance=balance,
            entry_price=80000.0,
            stop_price=79500.0,
        )

    def test_zero_balance_invalid(self):
        result = self._size(0)

        self.assertFalse(result.valid)
        self.assertEqual(result.quantity, 0)
        self.assertEqual(result.risk_amount, 0)

    def test_negative_balance_invalid(self):
        result = self._size(-100.0)

        self.assertFalse(result.valid)
        self.assertEqual(result.quantity, 0)
        # A negative risk amount must never be produced.
        self.assertGreaterEqual(result.risk_amount, 0)

    def test_positive_balance_unchanged(self):
        result = self._size(2000.0)

        self.assertTrue(result.valid)
        self.assertGreater(result.quantity, 0)
        self.assertGreater(result.risk_amount, 0)


class TestContractValidation(unittest.TestCase):

    def _executor(self, registry):
        return DeltaOrderExecutor(
            exchange=_FakeRest(),
            registry=registry,
            order_id_factory=lambda i: "QE-TEST",
        )

    def _intent(self):
        return OrderIntent(
            direction="BULLISH",
            entry=80000.0,
            stop_loss=79500.0,
            take_profit=81000.0,
            quantity=0.0623,
            symbol="BTCUSDT",
            valid=True,
        )

    def test_missing_contract_rejected(self):
        executor = self._executor(ContractRegistry())

        with self.assertRaises(InvalidContractError):
            executor.execute(
                self._intent(),
                safety=LiveSafetyGate.test_armed(),
            )

    def test_zero_product_id_rejected(self):
        reg = ContractRegistry()
        reg.add(contract(product_id=0))
        executor = self._executor(reg)

        with self.assertRaises(InvalidContractError):
            executor._contract(self._intent())

    def test_negative_product_id_rejected(self):
        reg = ContractRegistry()
        reg.add(contract(product_id=-5))
        executor = self._executor(reg)

        with self.assertRaises(InvalidContractError):
            executor._contract(self._intent())

    def test_non_numeric_product_id_rejected(self):
        reg = ContractRegistry()
        reg.add(contract(product_id="abc"))
        executor = self._executor(reg)

        with self.assertRaises(InvalidContractError):
            executor._contract(self._intent())

    def test_invalid_precisions_rejected(self):
        for field, bad in (
            ("price_precision", -1),
            ("quantity_precision", -1),
            ("price_precision", 1.5),
            ("price_precision", True),
        ):
            reg = ContractRegistry()
            reg.add(contract(**{field: bad}))
            executor = self._executor(reg)

            with self.assertRaises(
                InvalidContractError, msg="{}={!r}".format(field, bad)
            ):
                executor._contract(self._intent())

    def test_valid_contract_passes(self):
        reg = ContractRegistry()
        reg.add(contract())
        executor = self._executor(reg)

        self.assertIsNotNone(executor._contract(self._intent()))

    def test_invalid_contract_makes_zero_transport_calls(self):
        rest = _FakeRest()
        reg = ContractRegistry()
        reg.add(contract(product_id=0))
        executor = DeltaOrderExecutor(
            exchange=rest,
            registry=reg,
            order_id_factory=lambda i: "QE-TEST",
        )

        with self.assertRaises(InvalidContractError):
            executor.execute(
                self._intent(),
                safety=LiveSafetyGate.test_armed(),
            )

        self.assertEqual(rest.calls, [])

    def test_invalid_contract_error_is_value_error(self):
        # Backward compatibility for ValueError callers.
        self.assertTrue(issubclass(InvalidContractError, ValueError))


class TestContractLoaderErrors(unittest.TestCase):

    def _loader(self):
        from core.exchanges.delta.delta_contract_loader import (
            DeltaContractLoader,
        )

        return DeltaContractLoader()

    def test_transport_failure_wrapped(self):
        from core.exchanges.delta.delta_contract_loader import (
            ContractLoadError,
        )

        instance = mock.Mock()
        instance.download.side_effect = ConnectionError("down")

        with mock.patch(
            "core.exchanges.delta.delta_contract_loader."
            "DeltaProducts",
            return_value=instance,
        ):
            with self.assertRaises(ContractLoadError) as ctx:
                self._loader().load()

        self.assertIn("download failed", str(ctx.exception))

    def test_missing_result_wrapped(self):
        from core.exchanges.delta.delta_contract_loader import (
            ContractLoadError,
        )

        instance = mock.Mock()
        instance.download.return_value = {"nope": []}

        with mock.patch(
            "core.exchanges.delta.delta_contract_loader."
            "DeltaProducts",
            return_value=instance,
        ):
            with self.assertRaises(ContractLoadError) as ctx:
                self._loader().load()

        self.assertIn("'result'", str(ctx.exception))

    def test_non_list_result_wrapped(self):
        from core.exchanges.delta.delta_contract_loader import (
            ContractLoadError,
        )

        instance = mock.Mock()
        instance.download.return_value = {"result": "nope"}

        with mock.patch(
            "core.exchanges.delta.delta_contract_loader."
            "DeltaProducts",
            return_value=instance,
        ):
            with self.assertRaises(ContractLoadError):
                self._loader().load()


class TestForgedDecisionBlocked(unittest.TestCase):
    """require_decision() refuses fabricated/invalid tokens.

    Every negative case asserts BOTH the typed refusal AND
    transport silence (zero posts AND zero deletes) at a
    counting fake. A hand-built SafetyDecision(allowed=True,
    mode="LIVE", ...) must never arm execution or cancel.
    """

    def _fake(self):
        fake = _FakeRest()
        fake.deletes = []
        real_delete = getattr(fake, "delete", None)

        def delete(path, payload=None):
            fake.deletes.append((path, payload))
            return {"result": {"id": "X"}}

        fake.delete = delete
        return fake

    def _executor(self, fake):
        registry = ContractRegistry()
        registry.add(contract())
        return DeltaOrderExecutor(
            exchange=fake,
            registry=registry,
            order_id_factory=lambda i: "QE-TEST",
        )

    def _intent(self):
        return OrderIntent(
            direction="BULLISH",
            entry=80000.0,
            stop_loss=79500.0,
            take_profit=81000.0,
            quantity=0.0623,
            symbol="BTCUSDT",
            valid=True,
        )

    def _posts(self, fake):
        return [c for c in fake.calls if c[0] == "post"]

    def test_fabricated_consistent_token_blocked_silent(self):
        forged = SafetyDecision(
            allowed=True,
            mode="LIVE",
            reason="trust me",
            allow_live=True,
            live_execute=True,
            has_credentials=True,
        )
        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require_decision(forged, component="t")

        fake = self._fake()
        executor = self._executor(fake)
        with self.assertRaises(LiveBlockedError):
            executor.execute(self._intent(), safety=forged)
        with self.assertRaises(LiveBlockedError):
            executor.cancel("order_1", safety=forged)
        self.assertEqual(self._posts(fake), [])
        self.assertEqual(fake.deletes, [])

    def test_fabricated_inconsistent_token_blocked_silent(self):
        forged = SafetyDecision(
            allowed=True,
            mode="LIVE",
            reason="flags off",
            allow_live=False,
            live_execute=False,
            has_credentials=False,
        )
        fake = self._fake()
        executor = self._executor(fake)
        with self.assertRaises(LiveBlockedError):
            LiveSafetyGate.require_decision(forged, component="t")
        with self.assertRaises(LiveBlockedError):
            executor.execute(self._intent(), safety=forged)
        self.assertEqual(self._posts(fake), [])

    def test_replace_edited_token_blocked_silent(self):
        import dataclasses

        armed = LiveSafetyGate.test_armed()
        fake = self._fake()
        executor = self._executor(fake)
        for edited in (
            dataclasses.replace(armed, mode="PAPER"),
            dataclasses.replace(armed, allow_live=False),
            dataclasses.replace(armed, live_execute=False),
            dataclasses.replace(armed, has_credentials=False),
        ):
            with self.assertRaises(
                LiveBlockedError, msg="edited=%r" % (edited,)
            ):
                LiveSafetyGate.require_decision(edited, component="t")
            with self.assertRaises(LiveBlockedError):
                executor.execute(self._intent(), safety=edited)
        self.assertEqual(self._posts(fake), [])

    def test_non_token_blocked_silent(self):
        fake = self._fake()
        executor = self._executor(fake)
        for bad in (None, "LIVE", 42, {"allowed": True}):
            with self.assertRaises(LiveBlockedError):
                LiveSafetyGate.require_decision(bad, component="t")
            with self.assertRaises(LiveBlockedError):
                executor.execute(self._intent(), safety=bad)
        self.assertEqual(self._posts(fake), [])

    def test_cancel_requires_gate(self):
        fake = self._fake()
        executor = self._executor(fake)
        with self.assertRaises(LiveBlockedError):
            executor.cancel("order_1")
        with self.assertRaises(LiveBlockedError):
            executor.cancel(
                "order_1",
                safety=LiveSafetyGate.decide(
                    mode=ExecutionMode.PAPER
                ),
            )
        self.assertEqual(fake.deletes, [])
        result = executor.cancel(
            "order_1", safety=LiveSafetyGate.test_armed(), product_id=84
        )
        self.assertEqual(fake.deletes,
                         [("/v2/orders",
                           {"id": "order_1", "product_id": 84})])
        self.assertIsNotNone(result)

    def test_broker_construction_rejects_forged_token(self):
        from core.live.broker_engine import BrokerEngine

        forged = SafetyDecision(
            allowed=True,
            mode="LIVE",
            reason="trust me",
            allow_live=True,
            live_execute=True,
            has_credentials=True,
        )
        with self.assertRaises(LiveBlockedError):
            BrokerEngine(
                pipeline=None,
                event_bus=None,
                executor=object(),
                dry_run=False,
                safety=forged,
            )

    def test_per_route_recheck_blocks_tampered_safety(self):
        """Post-construction tampering (engine._safety swapped
        for a refused token) is caught by the per-route
        recheck BEFORE the executor — including executors
        that do not support safety tokens themselves."""

        from core.history.candle import Candle
        from core.live.broker_engine import BrokerEngine
        from core.pipeline.pipeline_context import PipelineContext

        class _ScriptedPipeline:
            def __init__(self, order):
                self.context = PipelineContext()
                self._order = order

            def reset(self):
                pass

            def on_candle(self, event):
                self.context.order = self._order

        class _NoSafetyExecutor:
            def __init__(self):
                self.calls = []

            def execute(self, order):
                self.calls.append(order)
                return {"success": True, "response": {}}

            def fetch(self, order_id):
                raise AssertionError("unreachable")

            def cancel(self, order_id):
                raise AssertionError("unreachable")

            def balance(self):
                return {}

            def positions(self):
                return {"result": []}

        executor = _NoSafetyExecutor()
        engine = BrokerEngine(
            _ScriptedPipeline(self._intent()),
            event_bus=None,
            executor=executor,
            dry_run=False,
            safety=LiveSafetyGate.test_armed(),
        )
        engine._safety = LiveSafetyGate.decide(
            mode=ExecutionMode.LIVE,
            allow_live=False,
            live_execute=False,
            has_credentials=False,
        )
        with self.assertRaises(LiveBlockedError):
            engine.run_candle(
                Candle(
                    timestamp=1,
                    open=80000.0,
                    high=80100.0,
                    low=79900.0,
                    close=80050.0,
                    volume=10.0,
                    closed=True,
                    symbol="BTCUSDT",
                )
            )
        self.assertEqual(executor.calls, [])

    def test_armed_token_still_executes_once(self):
        fake = self._fake()
        executor = self._executor(fake)
        result = executor.execute(
            self._intent(), safety=LiveSafetyGate.test_armed()
        )
        self.assertTrue(result["success"])
        orders = [
            c for c in self._posts(fake) if c[1] == "/v2/orders"
        ]
        self.assertEqual(len(orders), 1)


if __name__ == "__main__":
    unittest.main()
