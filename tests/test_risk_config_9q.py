"""
Phase 9Q-8 — Risk config validation + enforcement.
Every param must have type, unit, range, default, and fail-fast on invalid.
"""

import unittest
import importlib

from config import risk_settings


class TestRiskConfigContract(unittest.TestCase):

    def test_pct_ranges_are_fractions_or_percent_points(self):
        # _PCT values are percent points 0-100, fractions 0-1
        self.assertGreaterEqual(risk_settings.MAX_TOTAL_EXPOSURE_PCT, 0)
        self.assertLessEqual(risk_settings.MAX_TOTAL_EXPOSURE_PCT, 100)
        self.assertGreaterEqual(risk_settings.RISK_PER_TRADE, 0)
        self.assertLessEqual(risk_settings.RISK_PER_TRADE, 1)

    def test_amounts_positive(self):
        self.assertGreater(risk_settings.MAX_ALLOCATION_PER_TRADE, 0)
        self.assertGreater(risk_settings.STARTING_BALANCE, 0)

    def test_counts_positive(self):
        self.assertGreater(risk_settings.MAX_WAIT_BARS, 0)
        self.assertGreater(risk_settings.MAX_PENDING_ORDERS, 0)
        self.assertGreater(risk_settings.ENTRY_DELAY_BARS, 0)

    def test_leverage_at_least_one(self):
        self.assertGreaterEqual(risk_settings.LEVERAGE, 1)

    def test_drawdown_fractions(self):
        self.assertGreaterEqual(risk_settings.MAX_DAILY_LOSS, 0)
        self.assertLessEqual(risk_settings.MAX_DAILY_LOSS, 1)
        self.assertGreaterEqual(risk_settings.MAX_WEEKLY_LOSS, 0)
        self.assertLessEqual(risk_settings.MAX_WEEKLY_LOSS, 1)

    def test_capital_floor(self):
        from core.risk.capital import SharedCapital
        cap = SharedCapital(equity=1000, max_deployment_pct=100)
        cap.reserve("R1", 600)
        cap.reserve("R2", 600)  # reserved 1200 > deployment 1000
        # available should be floored at 0, not negative
        self.assertEqual(cap.available_capital, 0.0)
        self.assertGreaterEqual(cap.snapshot()["available_capital"], 0)

    def test_position_size_explicit_capped(self):
        from core.risk.position_sizer import PositionSizer
        sizer = PositionSizer()
        ps = sizer.calculate(balance=2000, entry_price=50000, stop_price=49990)
        self.assertTrue(hasattr(ps, "requested_quantity"))
        self.assertTrue(hasattr(ps, "capped"))
        self.assertTrue(hasattr(ps, "cap_reason"))
        if ps.capped:
            self.assertNotEqual(ps.cap_reason, "")
            self.assertLess(ps.quantity, ps.requested_quantity)

    def test_shared_capital_validation(self):
        from core.risk.capital import SharedCapital
        cap = SharedCapital(equity=0, max_deployment_pct=100)
        # With 0 equity, deployment 0, cannot reserve
        self.assertFalse(cap.can_reserve(100))
        self.assertEqual(cap.last_reason, "insufficient_capital")
