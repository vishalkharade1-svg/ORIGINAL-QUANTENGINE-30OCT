"""Phase-3 prefix-invariance tests for confirmed swing output."""

import unittest

from core.history.candle import Candle
from core.market_structure.causal_audit import audit_confirmed_swing_prefixes


def bars(prices):
    return [Candle(i * 60, price, price + 0.2, price - 0.2, price, 1.0) for i, price in enumerate(prices)]


class TestSwingPrefixInvariance(unittest.TestCase):
    def test_confirmed_pivots_are_stable_across_later_prefixes(self):
        # Alternating extrema ensure distinct confirmed highs/lows rather than
        # a same-kind replacement policy obscuring the causal assertion.
        prices = [10, 11, 12, 9, 8, 9, 13, 14, 13, 9, 7, 8, 12, 13, 12]
        self.assertEqual(audit_confirmed_swing_prefixes(bars(prices), left=1, right=1), [])

    def test_unconfirmed_tail_is_not_claimed_as_a_pivot(self):
        prices = [10, 11, 9, 10, 12]
        # The final high cannot be confirmed without the next bar. The audit
        # considers only confirmed values and therefore has no false failure.
        self.assertEqual(audit_confirmed_swing_prefixes(bars(prices), left=1, right=1), [])


if __name__ == "__main__":
    unittest.main()
