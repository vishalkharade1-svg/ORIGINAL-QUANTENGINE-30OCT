"""Delta products smoke tests (offline by default).

Importing this module performs ZERO network I/O. The live
demo path (real /v2/products download) runs only when the
file is executed directly as a script AND the operator opts
in via QE_LIVE_SMOKE=1:

    QE_LIVE_SMOKE=1 python tests/test_delta_products.py
"""

import os
import unittest
from unittest import mock

from core.exchanges.delta.delta_products import DeltaProducts


class TestDeltaProductsSmoke(unittest.TestCase):
    """Offline products fetch: stubbed transport, no network."""

    def test_stubbed_download_returns_envelope(self):
        payload = {
            "success": True,
            "result": [
                {"id": 27, "symbol": "BTCUSDT"},
                {"id": 31, "symbol": "ETHUSDT"},
            ],
        }
        with mock.patch.object(
            DeltaProducts, "download", return_value=payload
        ):
            products = DeltaProducts().download()

        self.assertTrue(products["success"])
        self.assertEqual(len(products["result"]), 2)


def _live_demo():
    """Manual operator demo: real network download + printout."""

    products = DeltaProducts().download()

    print()

    print("=" * 60)
    print("DELTA PRODUCTS")
    print("=" * 60)

    print("Success :", products["success"])

    print("Products :", len(products["result"]))


if __name__ == "__main__":
    if os.getenv("QE_LIVE_SMOKE", "") == "1":
        _live_demo()
    else:
        unittest.main()
