"""
====================================================

QuantEngine

Delta Order Executor Contract Tests

Run with:

    python -m unittest tests.test_order_executor -v

Proves the DeltaOrderExecutor maps a risk-validated
OrderIntent (RiskEngine -> context.order) into a Delta
/v2/orders payload:

- side derived from direction (BULLISH -> buy, BEARISH ->
  sell);
- product_id and price/quantity precision taken from the
  contract registry;
- GTC limit order at entry, bracket TP/SL attached when the
  intent carries both;
- invalid intents are rejected without touching the exchange.

Stdlib only -- a recording fake exchange replaces the network.

====================================================
"""

import unittest

from core.exchanges.contract_registry import ContractRegistry
from core.exchanges.delta.delta_contract import DeltaContract
from core.execution.order_executor import DeltaOrderExecutor
from core.risk.order_intent import OrderIntent


def contract(
    symbol="BTCUSDT",
    product_id=2,
    price_precision=2,
    quantity_precision=5,
    **overrides,
):
    values = dict(
        symbol=symbol,
        exchange="DELTA",
        contract_type="perpetual_futures",
        tick_size=0.01,
        quantity_step=0.001,
        min_quantity=0.00001,
        max_leverage=100.0,
        maker_fee=0.0005,
        taker_fee=0.001,
        price_precision=price_precision,
        quantity_precision=quantity_precision,
        product_id=product_id,
        live_execution_verified=True,
        live_execution_evidence="test fixture",
    )
    values.update(overrides)
    return DeltaContract(**values)


def intent(
    valid=True,
    direction="BULLISH",
    entry=80000.0,
    stop_loss=79500.0,
    take_profit=81000.0,
    quantity=0.0623,
    symbol="BTCUSDT",
    reason="",
):
    return OrderIntent(
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        quantity=quantity,
        symbol=symbol,
        valid=valid,
        reason=reason,
    )


class _FakeExchange:

    authenticated = True

    def __init__(self):
        self.placed = []

    def post(self, path, payload=None):
        self.placed.append(payload)
        return {
            "success": True,
            "result": {
                "id": "order_1",
                "product_id": payload["product_id"],
                "side": payload["side"],
                "state": "open",
            },
        }


class TestBuildPayload(unittest.TestCase):

    def _executor(self, **kwargs):
        registry = ContractRegistry()
        registry.add(contract())
        return DeltaOrderExecutor(
            exchange=_FakeExchange(),
            registry=registry,
            order_id_factory=lambda i: "QE-TEST",
            **kwargs,
        )

    def test_long_limit_order(self):
        payload = self._executor().build_payload(
            intent(), contract()
        )

        self.assertEqual(payload["product_id"], 2)
        self.assertEqual(payload["order_type"], "limit_order")
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(payload["size"], 0.0623)
        self.assertEqual(payload["limit_price"], "80000.00")
        self.assertEqual(payload["time_in_force"], "gtc")
        self.assertEqual(payload["reduce_only"], False)
        self.assertEqual(payload["post_only"], False)
        self.assertEqual(payload["client_order_id"], "QE-TEST")

    def test_short_maps_to_sell(self):
        payload = self._executor().build_payload(
            intent(direction="BEARISH"), contract()
        )
        self.assertEqual(payload["side"], "sell")

    def test_bracket_fields_attach_tp_and_sl(self):
        payload = self._executor().build_payload(
            intent(), contract()
        )

        self.assertEqual(
            payload["bracket_take_profit_price"], "81000.00"
        )
        self.assertEqual(
            payload["bracket_take_profit_limit_price"], "81000.00"
        )
        self.assertEqual(
            payload["bracket_stop_loss_price"], "79500.00"
        )
        self.assertEqual(
            payload["bracket_stop_loss_limit_price"], "79500.00"
        )

    def test_brackets_omitted_when_no_tp_or_sl(self):
        payload = self._executor().build_payload(
            intent(take_profit=0.0, stop_loss=0.0), contract()
        )

        self.assertNotIn(
            "bracket_take_profit_price", payload
        )
        self.assertNotIn(
            "bracket_stop_loss_price", payload
        )

    def test_brackets_omitted_when_disabled(self):
        payload = self._executor(
            attach_brackets=False
        ).build_payload(intent(), contract())

        self.assertNotIn("bracket_take_profit_price", payload)

    def test_precision_is_applied(self):
        payload = self._executor().build_payload(
            intent(entry=80000.12345, quantity=0.062345),
            contract(price_precision=1, quantity_precision=2),
        )

        self.assertEqual(payload["limit_price"], "80000.1")
        self.assertEqual(payload["size"], 0.06)


class TestExecute(unittest.TestCase):

    def _executor(self):
        registry = ContractRegistry()
        registry.add(contract())
        exchange = _FakeExchange()
        return (
            DeltaOrderExecutor(
                exchange=exchange,
                registry=registry,
                order_id_factory=lambda i: "QE-TEST",
            ),
            exchange,
        )

    def test_execute_places_valid_intent(self):
        from core.execution.live_safety_gate import LiveSafetyGate

        executor, exchange = self._executor()

        result = executor.execute(
            intent(), safety=LiveSafetyGate.test_armed()
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["payload"]["product_id"], 2)
        self.assertEqual(result["response"]["result"]["state"], "open")
        self.assertEqual(exchange.placed, [result["payload"]])

    def test_execute_rejects_invalid_intent(self):
        executor, exchange = self._executor()

        reason = "risk gate rejected"

        result = executor.execute(intent(valid=False, reason=reason))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], reason)
        self.assertEqual(exchange.placed, [])

    def test_execute_raises_without_contract(self):
        empty = ContractRegistry()
        exchange = _FakeExchange()

        executor = DeltaOrderExecutor(
            exchange=exchange,
            registry=empty,
            order_id_factory=lambda i: "QE-TEST",
        )

        with self.assertRaises(ValueError):
            executor.execute(intent())

        self.assertEqual(exchange.placed, [])

    def test_execute_refuses_unverified_execution_contract_after_safety_gate(self):
        from core.execution.live_safety_gate import LiveSafetyGate

        executor, exchange = self._executor()
        unverified = contract(live_execution_verified=False, live_execution_evidence="")
        executor.registry = ContractRegistry()
        executor.registry.add(unverified)
        with self.assertRaisesRegex(ValueError, "verified live execution evidence"):
            executor.execute(intent(), safety=LiveSafetyGate.test_armed())
        self.assertEqual(exchange.placed, [])

    def test_pass_throughs_delegate_to_exchange(self):
        from core.execution.live_safety_gate import LiveSafetyGate

        class _Full:
            authenticated = True

            def get(self, path, params=None):
                return ("get", path)

            def post(self, path, payload=None):
                return ("post", path)

            def delete(self, path, payload=None):
                return ("delete", path, payload)

        registry = ContractRegistry()
        registry.add(contract())

        executor = DeltaOrderExecutor(
            exchange=_Full(),
            registry=registry,
        )

        # Cancel is an exchange WRITE: same LIVE gate as execute.
        # Venue-verified shape carries product scope in the body.
        self.assertEqual(
            executor.cancel(
                1, safety=LiveSafetyGate.test_armed(), product_id=84
            ),
            ("delete", "/v2/orders", {"id": 1, "product_id": 84}),
        )
        with self.assertRaises(ValueError):
            executor.cancel(
                1, safety=LiveSafetyGate.test_armed()
            )
        self.assertEqual(
            executor.fetch(2), ("get", "/v2/orders/2")
        )
        self.assertEqual(
            executor.balance(), ("get", "/v2/wallet/balances")
        )
        self.assertEqual(
            executor.positions(), ("get", "/v2/positions")
        )


if __name__ == "__main__":
    unittest.main()
