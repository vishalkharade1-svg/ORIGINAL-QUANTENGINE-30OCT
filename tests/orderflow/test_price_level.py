import unittest

from core.orderflow.price_level import PriceLevel


class TestPriceLevel(unittest.TestCase):

    def test_defaults(self):

        level = PriceLevel()

        self.assertEqual(level.price, 0.0)
        self.assertEqual(level.buy_volume, 0.0)
        self.assertEqual(level.sell_volume, 0.0)
        self.assertEqual(level.total_volume, 0.0)
        self.assertEqual(level.delta, 0.0)
        self.assertFalse(level.absorption)
        self.assertFalse(level.exhaustion)
        self.assertFalse(level.stacked_imbalance)


if __name__ == "__main__":
    unittest.main()