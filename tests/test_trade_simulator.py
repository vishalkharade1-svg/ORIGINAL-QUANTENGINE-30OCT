"""
====================================================

Trade Simulator Test

====================================================
"""

import unittest

from core.backtesting.trade_simulator import TradeSimulator
from core.setup.setup_candidate import SetupCandidate


# -------------------------------------------------
# Fake Candle
# -------------------------------------------------

class Candle:

    def __init__(

        self,

        high,

        low,

        timestamp,

    ):

        self.high = high
        self.low = low
        self.timestamp = timestamp


# -------------------------------------------------
# Buy TP Test
# -------------------------------------------------

def test_buy_take_profit():

    simulator = TradeSimulator()

    setup = SetupCandidate(

        direction="BULLISH",

        entry=100,

        stop_loss=95,

        take_profit=110,

        score=90,

        confidence=90,

    )

    simulator.open_trade(

        setup,

        timestamp="09:15",

    )

    simulator.update(

        Candle(

            high=111,

            low=99,

            timestamp="09:16",

        )

    )

    assert simulator.current_trade is None

    trade = simulator.registry.all()[0]

    assert trade.result == "WIN"

    assert trade.exit_price == 110

    print("Buy TP Test PASSED")


# -------------------------------------------------
# Buy SL Test
# -------------------------------------------------

def test_buy_stop():

    simulator = TradeSimulator()

    setup = SetupCandidate(

        direction="BULLISH",

        entry=100,

        stop_loss=95,

        take_profit=110,

        score=90,

        confidence=90,

    )

    simulator.open_trade(

        setup,

        timestamp="09:15",

    )

    simulator.update(

        Candle(

            high=101,

            low=94,

            timestamp="09:16",

        )

    )

    trade = simulator.registry.all()[0]

    assert trade.result == "LOSS"

    assert trade.exit_price == 95

    print("Buy SL Test PASSED")


# -------------------------------------------------
# Sell TP Test
# -------------------------------------------------

def test_sell_take_profit():

    simulator = TradeSimulator()

    setup = SetupCandidate(

        direction="BEARISH",

        entry=100,

        stop_loss=105,

        take_profit=90,

        score=90,

        confidence=90,

    )

    simulator.open_trade(

        setup,

        timestamp="09:15",

    )

    simulator.update(

        Candle(

            high=102,

            low=89,

            timestamp="09:16",

        )

    )

    trade = simulator.registry.all()[0]

    assert trade.result == "WIN"

    assert trade.exit_price == 90

    print("Sell TP Test PASSED")


# -------------------------------------------------
# Sell SL Test
# -------------------------------------------------

def test_sell_stop():

    simulator = TradeSimulator()

    setup = SetupCandidate(

        direction="BEARISH",

        entry=100,

        stop_loss=105,

        take_profit=90,

        score=90,

        confidence=90,

    )

    simulator.open_trade(

        setup,

        timestamp="09:15",

    )

    simulator.update(

        Candle(

            high=106,

            low=99,

            timestamp="09:16",

        )

    )

    trade = simulator.registry.all()[0]

    assert trade.result == "LOSS"

    assert trade.exit_price == 105

    print("Sell SL Test PASSED")


# -------------------------------------------------
# PnL Test
# -------------------------------------------------

def test_pnl():

    simulator = TradeSimulator()

    setup = SetupCandidate(

        direction="BULLISH",

        entry=100,

        stop_loss=95,

        take_profit=110,

        score=90,

        confidence=90,

    )

    simulator.open_trade(

        setup,

        timestamp="09:15",

    )

    simulator.update(

        Candle(

            high=120,

            low=99,

            timestamp="09:16",

        )

    )

    trade = simulator.registry.all()[0]

    assert trade.pnl == 10

    print("PnL Test PASSED")


# -------------------------------------------------
# Main
# -------------------------------------------------

def main():

    print()

    print("=" * 60)

    print("TRADE SIMULATOR TESTS")

    print("=" * 60)

    test_buy_take_profit()

    test_buy_stop()

    test_sell_take_profit()

    test_sell_stop()

    test_pnl()

    print()

    print("=" * 60)

    print("ALL TRADE SIMULATOR TESTS PASSED")

    print("=" * 60)


class TestExitSignAdversarial(unittest.TestCase):
    """Phase 13 §8: a stop-hit from a valid entry can never
    book a WIN with negative gross, and a target-hit can
    never book a LOSS with positive gross -- in EITHER
    direction, including same-bar SL+TP ambiguity (SL-first
    conservative). Stdlib only."""

    def _trade(self, direction, entry, stop, target,
               high, low):
        simulator = TradeSimulator()
        setup = SetupCandidate(
            direction=direction,
            entry=entry,
            stop_loss=stop,
            take_profit=target,
            score=90,
            confidence=90,
        )
        simulator.open_trade(setup, timestamp="09:15")
        simulator.update(
            Candle(high=high, low=low, timestamp="09:16"))
        trades = simulator.registry.all()
        self.assertEqual(len(trades), 1)
        return trades[0]

    def test_long_stop_hit_is_loss_with_nonpositive_gross(self):
        trade = self._trade("BULLISH", 110.0, 100.0, 170.0,
                            high=112.0, low=99.0)
        self.assertEqual(trade.result, "LOSS")
        self.assertEqual(trade.exit_price, 100.0)
        self.assertLessEqual(trade.pnl, 0.0)

    def test_long_target_hit_is_win_with_nonnegative_gross(self):
        trade = self._trade("BULLISH", 110.0, 100.0, 170.0,
                            high=171.0, low=105.0)
        self.assertEqual(trade.result, "WIN")
        self.assertEqual(trade.exit_price, 170.0)
        self.assertGreaterEqual(trade.pnl, 0.0)

    def test_short_stop_hit_is_loss_with_nonpositive_gross(self):
        trade = self._trade("BEARISH", 100.0, 110.0, 40.0,
                            high=111.0, low=95.0)
        self.assertEqual(trade.result, "LOSS")
        self.assertEqual(trade.exit_price, 110.0)
        self.assertLessEqual(trade.pnl, 0.0)

    def test_short_target_hit_is_win_with_nonnegative_gross(self):
        trade = self._trade("BEARISH", 100.0, 110.0, 40.0,
                            high=105.0, low=39.0)
        self.assertEqual(trade.result, "WIN")
        self.assertEqual(trade.exit_price, 40.0)
        self.assertGreaterEqual(trade.pnl, 0.0)

    def test_same_bar_ambiguity_is_sl_first_loss(self):
        # Bar spans both levels: conservative SL-first.
        # LONG: always a LOSS; SHORT mirror likewise.
        long_trade = self._trade("BULLISH", 110.0, 100.0,
                                 170.0, high=175.0, low=95.0)
        self.assertEqual(long_trade.result, "LOSS")
        self.assertTrue(long_trade.ambiguous)
        short_trade = self._trade("BEARISH", 100.0, 110.0,
                                  40.0, high=115.0, low=35.0)
        self.assertEqual(short_trade.result, "LOSS")
        self.assertTrue(short_trade.ambiguous)


if __name__ == "__main__":

    main()