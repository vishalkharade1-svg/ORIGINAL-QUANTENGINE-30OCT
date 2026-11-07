"""Delta contract loader smoke tests (Phase 11D: offline by default).

Importing this module performs ZERO network I/O. The live
/demo path (real /v2/products download) runs only when the
file is executed directly as a script AND the operator opts
in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_contract_loader.py
"""

import os
import unittest
from unittest import mock

from core.exchanges.delta.delta_contract_loader import DeltaContractLoader
from core.exchanges.delta.delta_products import DeltaProducts


def _product(symbol="BTCUSDT", product_id=27):
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


class TestContractLoaderSmoke(unittest.TestCase):
    """Offline loader smoke: stubbed transport, no network."""

    def test_stubbed_load_registers_contracts(self):
        with mock.patch.object(
            DeltaProducts,
            "download",
            return_value={
                "result": [
                    _product("BTCUSDT", 27),
                    _product("ETHUSDT", 31),
                ]
            },
        ):
            registry = DeltaContractLoader().load()

        self.assertEqual(len(registry.all()), 2)
        self.assertTrue(registry.exists("BTCUSDT"))
        self.assertEqual(registry.get("ETHUSDT").product_id, 31)


def _live_demo():
    """Manual operator demo: real network download + printout."""

    loader = DeltaContractLoader()

    registry = loader.load()

    print()

    print("=" * 60)
    print("PERPETUAL CONTRACTS")
    print("=" * 60)

    print("Loaded :", len(registry.all()))

    print()

    for contract in registry.all()[:10]:
        print(contract.symbol, contract.contract_type)


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
