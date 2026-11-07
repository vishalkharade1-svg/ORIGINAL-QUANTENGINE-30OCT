"""
Phase 9S §6 — Strict portfolio-risk semantics.

Canonical: FRACTION 0.03 = 3% (not 0.03%), PERCENTAGE-POINT 3.0 = 3%.
Maximum portfolio risk = equity × fraction.
"""

import unittest

from core.risk.portfolio import PortfolioRiskManager
from core.risk.capital import SharedCapital


class TestPortfolioRiskSemantics(unittest.TestCase):

    def test_fraction_0_03_equals_3_percent(self):
        # 0.03 as fraction → 3% of equity
        mgr = PortfolioRiskManager(max_portfolio_risk=0.03, equity=2000)
        # With 3% cap, max risk = 2000 * 0.03 = 60
        # Try to open a trade with risk 60 → should be allowed
        self.assertTrue(mgr.can_open(trade_risk=60, equity=2000))
        # Risk 61 → should be rejected (exceeds 3%)
        self.assertFalse(mgr.can_open(trade_risk=61, equity=2000))
        self.assertEqual(mgr.last_reason, "max_portfolio_risk")

    def test_percentage_point_3_0_not_3_percent_in_fraction_field(self):
        # Legacy absolute values >1 are allowed for backward compat (e.g., 3.0 treated as absolute 3.0, not 300%)
        # Canonical fraction is 0.03 = 3%, but 3.0 as absolute is still accepted (legacy)
        mgr = PortfolioRiskManager(max_portfolio_risk=3.0, equity=2000)
        # With absolute 3.0, cap = 3.0, so risk 3 → allowed, 3.01 → rejected
        self.assertTrue(mgr.can_open(trade_risk=3.0, equity=2000))
        self.assertFalse(mgr.can_open(trade_risk=3.01, equity=2000))

    def test_maximum_portfolio_risk_equity_times_fraction(self):
        mgr = PortfolioRiskManager(max_portfolio_risk=0.03, equity=2000)
        # Simulate equity 2000, open risk 30, new order risk 20 → total 50 <=60 → allowed
        mgr.register_trade(trade_risk=30, symbol="BTCUSDT", position_value=1000)
        self.assertTrue(mgr.can_open(trade_risk=20, equity=2000))
        # Now try 35 → total 65 >60 → rejected
        self.assertFalse(mgr.can_open(trade_risk=35, equity=2000))

    def test_pct_field_3_0_equals_3_percent(self):
        # _PCT field: 3.0 = 3% (percent points)
        mgr = PortfolioRiskManager(max_total_exposure_pct=3.0, equity=2000)
        # Cap = 2000 * 3.0 /100 = 60
        # Position value 60 → allowed, 61 → rejected
        self.assertTrue(mgr.can_open(trade_risk=10, position_value=60, equity=2000))
        self.assertFalse(mgr.can_open(trade_risk=10, position_value=61, equity=2000))

    def test_invalid_fraction_rejected(self):
        with self.assertRaises(ValueError):
            PortfolioRiskManager(max_portfolio_risk=-1.5)  # negative invalid
        with self.assertRaises(ValueError):
            PortfolioRiskManager(max_total_exposure_pct=150)  # >100 percent invalid
        with self.assertRaises(ValueError):
            PortfolioRiskManager(max_total_exposure_pct=-5)

    def test_capital_fraction_semantics(self):
        cap = SharedCapital(equity=2000, max_deployment_pct=50)
        # Deployment cap = 2000 * 50 /100 = 1000
        self.assertAlmostEqual(cap.deployment_cap, 1000)
        self.assertTrue(cap.can_reserve(1000))
        self.assertFalse(cap.can_reserve(1001))

    def test_equity_times_fraction(self):
        # Explicit: maximum allowed portfolio risk = equity × configured fraction
        for fraction, equity, expected in [(0.03, 2000, 60), (0.01, 5000, 50), (0.05, 1000, 50)]:
            mgr = PortfolioRiskManager(max_portfolio_risk=fraction, equity=equity)
            # The cap is equity * fraction
            # Verify via can_open boundary
            self.assertTrue(mgr.can_open(trade_risk=expected, equity=equity))
            self.assertFalse(mgr.can_open(trade_risk=expected+0.01, equity=equity))
