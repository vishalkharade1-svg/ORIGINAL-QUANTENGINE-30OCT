"""Phase 67 funding/holding-period economics invariants."""
import unittest

from core.execution.economics import FundingEvent, FundingSchedule
from core.backtesting.accounting import net_pnl


class TestFundingSchedule(unittest.TestCase):
    def test_only_settlement_events_inside_holding_window_are_charged(self):
        schedule = FundingSchedule([
            FundingEvent(100, 0.001, "delta-fixture"),
            FundingEvent(200, 0.002, "delta-fixture"),
            FundingEvent(300, -0.001, "delta-fixture"),
        ])
        cost, count = schedule.cost(
            entry_time=100, exit_time=300, direction="BULLISH",
            entry=100.0, quantity=2.0,
        )
        # 200 is paid; 300 is a receipt for a long.  Event 100 is excluded
        # because the position was opened at that settlement timestamp.
        self.assertAlmostEqual(cost, 0.4 - 0.2, places=12)
        self.assertEqual(count, 2)

    def test_short_has_opposite_funding_sign(self):
        schedule = FundingSchedule([
            FundingEvent(200, 0.002, "delta-fixture"),
        ])
        cost, count = schedule.cost(
            entry_time=100, exit_time=200, direction="BEARISH",
            entry=100.0, quantity=2.0,
        )
        self.assertAlmostEqual(cost, -0.4, places=12)
        self.assertEqual(count, 1)

    def test_duplicate_settlement_is_rejected(self):
        with self.assertRaises(ValueError):
            FundingSchedule([
                FundingEvent(200, 0.001, "a"),
                FundingEvent(200, 0.002, "b"),
            ])

    def test_funding_is_subtracted_once_from_authoritative_net_pnl(self):
        self.assertAlmostEqual(net_pnl(10.0, 1.0, 0.5, 0.25), 8.25)
        self.assertAlmostEqual(net_pnl(10.0, 1.0, 0.5, -0.25), 8.75)


if __name__ == "__main__":
    unittest.main()

class TestTradeSimulatorFunding(unittest.TestCase):
    def test_closed_trade_books_funding_exactly_once(self):
        from types import SimpleNamespace
        from core.backtesting.trade_simulator import TradeSimulator
        schedule = FundingSchedule([
            FundingEvent(150, 0.001, "delta-fixture"),
            FundingEvent(175, 0.001, "delta-fixture"),
        ])
        sim = TradeSimulator(funding_schedule=schedule)
        setup = SimpleNamespace(
            direction="BULLISH", entry=100.0, stop_loss=90.0,
            take_profit=110.0, exit_mode="FIXED_TARGET",
            trailing_activation_r=0.0, trailing_distance_r=0.0,
            trailing_enabled=False, quantity=1.0, risk_amount=10.0,
            score=0.0, confidence=0.0, symbol="BTCUSD", setup_id="S",
            order_id="O", entry_mode="", canonical_id="",
        )
        trade = sim.open_trade(setup, 100, quantity=1.0)
        self.assertIsNotNone(trade)
        candle = SimpleNamespace(timestamp=200, high=110.0, low=99.0, close=110.0)
        sim.update(candle)
        closed = sim.registry.all()[0]
        self.assertAlmostEqual(closed.funding, 0.2, places=12)
        self.assertEqual(closed.funding_events, 2)
        self.assertAlmostEqual(closed.pnl, 9.8, places=12)

if __name__ == "__main__":
    unittest.main()
