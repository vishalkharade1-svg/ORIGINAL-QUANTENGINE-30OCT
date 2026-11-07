"""
Phase 9Q-9 — Position sizing explicit: requested vs actual.
"""
import unittest

from core.risk.position_sizer import PositionSizer


class TestPositionSizingExplicit(unittest.TestCase):

    def test_no_cap_exposes_requested_equals_actual(self):
        sizer = PositionSizer()
        # 11E-Prep H1: MAX_ALLOCATION_PER_TRADE is a NOTIONAL
        # cap (position value <= 500). The old scenario here
        # (PV 1000) is ABOVE the cap, so this test now uses a
        # genuinely below-cap scenario (PV 100) to keep its
        # purpose: no cap => requested == actual.
        ps = sizer.calculate(balance=2000, entry_price=50000, stop_price=40000)
        self.assertTrue(ps.valid)
        self.assertFalse(ps.capped)
        self.assertAlmostEqual(ps.requested_quantity, ps.quantity, places=9)
        self.assertAlmostEqual(ps.requested_risk_amount, ps.risk_amount, places=6)
        self.assertAlmostEqual(ps.requested_position_value, ps.position_value, places=2)
        self.assertEqual(ps.cap_reason, "")

    def test_cap_triggered_records_reason_and_actual_risk(self):
        sizer = PositionSizer()
        # Tight stop → huge qty → notional > allocation 500 → cap
        # balance 2000, risk 1% => risk_amount 20, stop 10 => qty 2, notional 100k => scaled to 500
        ps = sizer.calculate(balance=2000, entry_price=50000, stop_price=49990)
        self.assertTrue(ps.valid)
        self.assertTrue(ps.capped)
        self.assertNotEqual(ps.cap_reason, "")
        self.assertLess(ps.quantity, ps.requested_quantity)
        self.assertLess(ps.position_value, ps.requested_position_value)
        self.assertAlmostEqual(ps.expected_loss, ps.quantity * ps.stop_distance, places=6)
        self.assertAlmostEqual(ps.risk_amount, ps.expected_loss, places=6)
        self.assertLess(ps.actual_risk_percent, ps.requested_risk_percent)

    def test_insufficient_balance_invalid(self):
        sizer = PositionSizer()
        ps = sizer.calculate(balance=0, entry_price=100, stop_price=90)
        self.assertFalse(ps.valid)
        self.assertEqual(ps.quantity, 0)

    def test_zero_stop_distance_invalid(self):
        sizer = PositionSizer()
        ps = sizer.calculate(balance=2000, entry_price=100, stop_price=100)
        self.assertFalse(ps.valid)
        self.assertEqual(ps.reason, "Stop distance must be greater than zero")

    def test_minimum_quantity_and_precision(self):
        sizer = PositionSizer()
        # Very small risk → dust
        ps = sizer.calculate(balance=1, entry_price=50000, stop_price=49999)
        # quantity = 0.01 /1 =0.01 → notional 500 → margin 50 <500 → not capped but qty 0.01 > min
        # Actually with balance 1, risk 0.01 => qty 0.01, should be valid
        self.assertTrue(ps.valid)

    def test_leverage_cap(self):
        sizer = PositionSizer()
        # Allocation is a NOTIONAL cap (11E-Prep H1), so with
        # leverage 1 the same 500-notional bound applies.
        ps = sizer.calculate(balance=10000, entry_price=100, stop_price=90, leverage=1)
        # qty = 100/10=10, notional 1000 >500 => capped to 5
        self.assertTrue(ps.capped)
        self.assertAlmostEqual(ps.quantity, 5.0, places=4)

    def test_actual_risk_exposed_when_not_capped_but_expected_less(self):
        sizer = PositionSizer()
        # Force case where margin not capped but expected_loss < requested due to rounding?
        # This is covered by the second condition in sizer
        ps = sizer.calculate(balance=2000, entry_price=100, stop_price=99.5)
        # Should have actual_risk_percent set
        self.assertIsNotNone(ps.actual_risk_percent)
        self.assertGreaterEqual(ps.actual_risk_percent, 0)
