"""11G-A order-block tests."""

import unittest

from research.phase11g.features import orderblock as O
from research.phase11g.tests.test_feature_contracts import bars


class TestOrderBlock(unittest.TestCase):
    def test_anchor_strictly_before_reference(self):
        b = bars(200)
        for i in (50, 100, 150):
            for d in ("long", "short"):
                r = O.order_block_at(b, i, d)
                if r["status"] == "OK":
                    self.assertLess(r["value"]["anchor_index"], i)
                    self.assertEqual(r["confirmation_time"], b[i]["time"])

    def test_zone_ordered(self):
        b = bars(200)
        r = O.order_block_at(b, 100, "long")
        if r["status"] == "OK":
            lo, hi = r["value"]["zone"]
            self.assertLessEqual(lo, hi)


if __name__ == "__main__":
    unittest.main()
