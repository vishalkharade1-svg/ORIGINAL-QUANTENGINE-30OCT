"""Delta mapper smoke tests (offline by default).

Importing this module performs ZERO network I/O. The live
demo path (map the first real product) runs only when the
file is executed directly as a script AND the operator opts
in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_delta_mapper.py
"""

import os
import unittest

from core.exchanges.delta.delta_mapper import DeltaMapper


def _product():
    return {
        "id": 27,
        "symbol": "BTCUSDT",
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


class TestDeltaMapperSmoke(unittest.TestCase):
    """Offline mapping: fixture dict, no network."""

    def test_maps_product_fields(self):
        contract = DeltaMapper().map(_product())
        self.assertEqual(contract.symbol, "BTCUSDT")
        self.assertEqual(contract.product_id, 27)
        self.assertEqual(contract.contract_type, "perpetual_futures")
        self.assertAlmostEqual(contract.tick_size, 0.5)
        self.assertEqual(contract.price_precision, 1)


def _live_demo():
    """Manual operator demo: map the first live product."""

    from core.exchanges.delta.delta_products import DeltaProducts

    products = DeltaProducts().download()

    mapper = DeltaMapper()

    first = mapper.map(products["result"][0])

    print()

    print("=" * 60)
    print("FIRST CONTRACT")
    print("=" * 60)

    print(first)


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
