import unittest

from core.orderflow.price_ladder import PriceLadder


class TestPriceLadder(unittest.TestCase):

    def test_defaults(self):

        ladder = PriceLadder()

        self.assertEqual(len(ladder.levels), 0)
        self.assertEqual(ladder.total_volume, 0.0)
        self.assertEqual(ladder.total_delta, 0.0)
        self.assertFalse(ladder.balanced)


if __name__ == "__main__":
    unittest.main()