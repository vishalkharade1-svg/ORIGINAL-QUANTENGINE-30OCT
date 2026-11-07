"""
====================================================

QuantEngine

Delta Contract Loader (Universe) Contract Tests

Run with:

    python -m unittest tests.test_delta_loader -v

Proves the DeltaContractLoader serves the FULL Delta
product universe -- perpetual futures, option calls/puts
(including binary variants) and tokenized spot -- with
option/underlying metadata preserved, and that a
contract_types whitelist restores the old perpetual-only
behavior. Product fixtures mirror the REAL /v2/products
schema (lowercase contract_type values, underlying_asset
as an asset dict, strike_price only on options).

Stdlib only -- DeltaProducts is stubbed (no network).

====================================================
"""

import unittest
from unittest import mock

from core.exchanges.delta.delta_contract_loader import DeltaContractLoader
from core.exchanges.delta.delta_products import DeltaProducts

BTC = {
    "id": 2,
    "name": "Bitcoin",
    "symbol": "BTC",
    "precision": 8,
}


def product(
    symbol,
    contract_type,
    strike_price=None,
    underlying=BTC,
):
    return {
        "symbol": symbol,
        "contract_type": contract_type,
        "strike_price": strike_price,
        "underlying_asset": underlying,
        "tick_size": None,
        "contract_value": 1,
        "minimum_order_size": 0.01,
        "maximum_leverage": 100,
        "maker_commission_rate": 0.0005,
        "taker_commission_rate": 0.001,
        "price_precision": 2,
        "contract_value_precision": 3,
    }


PERP = product("BTCUSD", "perpetual_futures")

CALL = product("C-BTC-63000-280826", "call_options", strike_price=63000)

PUT = product("P-BTC-81000-300826", "put_options", strike_price=81000)

BINARY = product(
    "B-BTC-79500-040926", "binary_call_options", strike_price=79500
)

TOKEN = product("AAPL.", "spot", underlying={"id": 9, "symbol": "AAPL"})

ALL = [PERP, CALL, PUT, BINARY, TOKEN]


class TestDeltaContractLoaderUniverse(unittest.TestCase):

    def _load(self, products, **kwargs):
        with mock.patch.object(
            DeltaProducts,
            "download",
            return_value={"result": products},
        ):
            return DeltaContractLoader().load(**kwargs)

    def test_default_loads_every_product_type(self):
        registry = self._load(ALL)

        self.assertEqual(len(registry.all()), 5)
        for symbol in (
            "BTCUSD",
            "C-BTC-63000-280826",
            "P-BTC-81000-300826",
            "B-BTC-79500-040926",
            "AAPL.",
        ):
            self.assertTrue(registry.exists(symbol))

    def test_perpetuals_only_whitelist_restores_old_behavior(self):
        registry = self._load(
            ALL, contract_types=("perpetual_futures",)
        )

        self.assertEqual(len(registry.all()), 1)
        self.assertTrue(registry.exists("BTCUSD"))
        self.assertFalse(registry.exists("AAPL."))

    def test_option_metadata_is_preserved(self):
        registry = self._load(ALL)

        call = registry.get("C-BTC-63000-280826")
        self.assertEqual(call.contract_type, "call_options")
        self.assertEqual(call.option_type, "call")
        self.assertEqual(call.strike_price, 63000.0)
        self.assertEqual(call.underlying_asset, "BTC")
        self.assertEqual(call.expiry_time, 0)

        put = registry.get("P-BTC-81000-300826")
        self.assertEqual(put.contract_type, "put_options")
        self.assertEqual(put.option_type, "put")
        self.assertEqual(put.strike_price, 81000.0)

    def test_binary_and_token_products_are_loaded(self):
        registry = self._load(ALL)

        binary = registry.get("B-BTC-79500-040926")
        self.assertEqual(binary.contract_type, "binary_call_options")
        self.assertEqual(binary.option_type, "call")
        self.assertEqual(binary.strike_price, 79500.0)

        token = registry.get("AAPL.")
        self.assertEqual(token.contract_type, "spot")
        self.assertEqual(token.underlying_asset, "AAPL")
        self.assertEqual(token.strike_price, 0.0)

    def test_perp_defaults_for_option_fields(self):
        registry = self._load(ALL)

        perp = registry.get("BTCUSD")
        self.assertEqual(perp.option_type, "")
        self.assertEqual(perp.strike_price, 0.0)
        self.assertEqual(perp.expiry_time, 0)
        self.assertEqual(perp.underlying_asset, "BTC")


if __name__ == "__main__":
    unittest.main()