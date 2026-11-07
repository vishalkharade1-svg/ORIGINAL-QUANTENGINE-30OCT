"""Delta contract lookup smoke tests (Phase 11D: offline by default).

Importing this module performs ZERO network I/O. The live
demo path (real /v2/products download) runs only when the
file is executed directly as a script AND the operator opts
in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_delta_contract.py
"""

import os
import unittest
from unittest import mock

from core.exchanges.delta.delta_contract_loader import DeltaContractLoader
from core.exchanges.delta.delta_products import DeltaProducts


class TestDeltaContractSmoke(unittest.TestCase):
    """Offline contract lookup: stubbed transport, no network."""

    def test_stubbed_contract_lookup(self):
        with mock.patch.object(
            DeltaProducts,
            "download",
            return_value={
                "result": [
                    {
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
                ]
            },
        ):
            registry = DeltaContractLoader().load()

        contract = registry.get("BTCUSDT")
        self.assertIsNotNone(contract)
        self.assertEqual(contract.product_id, 27)


def _live_demo():
    """Manual operator demo: real network download + printout."""

    loader = DeltaContractLoader()

    registry = loader.load()

    contract = registry.get("BTCUSDT")

    print()

    print("=" * 60)

    print("DELTA CONTRACT")

    print("=" * 60)

    print(contract)


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
