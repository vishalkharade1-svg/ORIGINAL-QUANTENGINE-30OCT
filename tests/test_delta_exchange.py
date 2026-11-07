"""
====================================================

QuantEngine

Delta Exchange Contract Tests

Run with:

    python -m unittest tests.test_delta_exchange -v

Proves the DeltaExchange adapter (previously a
NotImplementedError stub) issues the correct Delta v2
endpoints with the signed client:

- POST /v2/orders         -> place_order
- DELETE /v2/orders + {"id", "product_id"} body -> cancel_order
  (venue-verified: the legacy DELETE /v2/orders/{id} route 404s;
  product scope is mandatory)
- GET  /v2/orders/{id}    -> get_order
- GET  /v2/wallet/balances-> get_balance
- GET  /v2/positions      -> get_positions
- GET  /v2/products       -> get_products (public)

and that private endpoints refuse to run without
DELTA_API_KEY / DELTA_API_SECRET.

Stdlib only -- a recording fake REST client replaces the
network.

====================================================
"""

import unittest
from unittest import mock

from core.exchanges.delta.delta_exchange import DeltaExchange
from core.exchanges.delta.delta_products import DeltaProducts
from core.exchanges.delta.write_authority import offline_test_token


class _FakeRest:

    def __init__(self, authenticated=True):
        self.authenticated = authenticated
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(("get", path, params))
        return {"canned": True, "path": path}

    def post(self, path, payload=None):
        self.calls.append(("post", path, payload))
        return {"canned": True, "path": path, "body": payload}

    def delete(self, path, payload=None):
        self.calls.append(("delete", path, payload))
        return {"canned": True, "path": path}


class TestDeltaExchangeEndpoints(unittest.TestCase):

    def _exchange(self, authenticated=True):
        return DeltaExchange(
            api_key="k" if authenticated else "",
            api_secret="s" if authenticated else "",
            rest=_FakeRest(authenticated=authenticated),
        )

    def test_place_order_posts_to_orders(self):
        exchange = self._exchange()

        payload = {"product_id": 2, "side": "buy"}

        # Offline fake transport: the write carries the explicit
        # tests-only authority (Phase193B boundary).
        response = exchange.place_order(
            payload, authority=offline_test_token())

        self.assertTrue(response["canned"])

        verb, path, sent = exchange.rest.calls[-1]

        self.assertEqual(verb, "post")
        self.assertEqual(path, "/v2/orders")
        self.assertEqual(sent, payload)

    def test_cancel_order_deletes_specific_order(self):
        exchange = self._exchange()

        exchange.cancel_order(
            1234, product_id=84, authority=offline_test_token())

        verb, path, payload = exchange.rest.calls[-1]

        self.assertEqual(verb, "delete")
        self.assertEqual(path, "/v2/orders")
        self.assertEqual(payload, {"id": 1234, "product_id": 84})

    def test_cancel_order_requires_product_scope(self):
        exchange = self._exchange()

        with self.assertRaises(ValueError):
            exchange.cancel_order(
                1234, authority=offline_test_token())

    def test_get_order_gets_specific_order(self):
        exchange = self._exchange()

        exchange.get_order(5678)

        verb, path, params = exchange.rest.calls[-1]

        self.assertEqual(verb, "get")
        self.assertEqual(path, "/v2/orders/5678")
        self.assertIsNone(params)

    def test_get_balance_hits_wallet_balances(self):
        exchange = self._exchange()

        exchange.get_balance()

        verb, path, params = exchange.rest.calls[-1]

        self.assertEqual(verb, "get")
        self.assertEqual(path, "/v2/wallet/balances")

    def test_get_positions_hits_positions(self):
        exchange = self._exchange()

        exchange.get_positions()

        verb, path, params = exchange.rest.calls[-1]

        self.assertEqual(verb, "get")
        self.assertEqual(path, "/v2/positions")

    def test_authenticated_flag_from_rest(self):
        self.assertTrue(self._exchange().authenticated)
        self.assertFalse(
            DeltaExchange(
                api_key="k",
                api_secret="s",
                rest=_FakeRest(authenticated=False),
            )
            .authenticated
        )

    def test_private_endpoints_require_credentials(self):
        exchange = DeltaExchange(
            api_key="",
            api_secret="",
            rest=_FakeRest(authenticated=False),
        )

        for call in (
            lambda: exchange.place_order({"product_id": 1}),
            lambda: exchange.cancel_order(1),
            lambda: exchange.get_order(1),
            lambda: exchange.get_balance(),
            lambda: exchange.get_positions(),
        ):
            with self.assertRaises(RuntimeError):
                call()

        self.assertEqual(exchange.rest.calls, [])


class TestDeltaExchangeProducts(unittest.TestCase):

    def test_get_products_returns_live_payload(self):
        exchange = DeltaExchange(
            api_key="k",
            api_secret="s",
            rest=_FakeRest(),
        )

        with mock.patch.object(
            DeltaProducts,
            "download",
            return_value={"result": []},
        ):
            self.assertEqual(
                exchange.get_products(),
                {"result": []},
            )

    def test_get_product_id_resolves_symbol(self):
        exchange = DeltaExchange(
            api_key="k",
            api_secret="s",
            rest=_FakeRest(),
        )

        products = {
            "result": [
                {"symbol": "BTCUSDT", "id": 2},
                {"symbol": "ETHUSDT", "id": 7},
                {"symbol": "SOL_USDT", "id": 33},
            ]
        }

        self.assertEqual(
            exchange.get_product_id("ETHUSDT", products),
            7,
        )
        self.assertEqual(
            exchange.get_product_id("BTCUSDT", products),
            2,
        )
        self.assertIsNone(
            exchange.get_product_id("DOGEUSDT", products)
        )


if __name__ == "__main__":
    unittest.main()