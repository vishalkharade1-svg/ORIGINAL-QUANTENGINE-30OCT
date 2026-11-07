"""Phase-7 conservative risk gates: fail-closed, no silent capacity (offline)."""

import unittest

from core.risk.conservative_gates import (
    AUTHORITATIVE_MIN_CONFIDENCE,
    BalanceDivergenceHalt,
    PortfolioExposure,
    check_confidence,
    check_exposure,
    check_leverage,
    check_margin,
)


class TestConservativeRiskGates(unittest.TestCase):
    def test_authoritative_minimum_is_80(self):
        self.assertEqual(AUTHORITATIVE_MIN_CONFIDENCE, 80)
        self.assertTrue(check_confidence(80).allowed)
        self.assertTrue(check_confidence(95).allowed)
        self.assertFalse(check_confidence(79.9).allowed)
        self.assertFalse(check_confidence(70).allowed)
        self.assertFalse(check_confidence(float("nan")).allowed)
        self.assertFalse(check_confidence("high").allowed)

    def test_exposure_defaults_to_conservative_cap(self):
        self.assertTrue(check_exposure(notional=2000.0, equity=2000.0).allowed)
        verdict = check_exposure(notional=2000.01, equity=2000.0)
        self.assertFalse(verdict.allowed)
        # An explicit permissive cap must be passed explicitly, never assumed.
        self.assertTrue(check_exposure(
            notional=2000.01, equity=2000.0,
            max_exposure_pct=25.0).allowed)
        self.assertFalse(
            check_exposure(notional=100.0, equity=0.0).allowed)

    def test_leverage_and_margin_are_explicit(self):
        self.assertTrue(
            check_leverage(notional=20_000.0, equity=2000.0,
                           max_leverage=10.0).allowed)
        self.assertFalse(
            check_leverage(notional=20_001.0, equity=2000.0,
                           max_leverage=10.0).allowed)
        self.assertTrue(
            check_margin(margin_required=500.0, equity=2000.0).allowed)
        self.assertFalse(
            check_margin(margin_required=2000.01, equity=2000.0).allowed)

    def test_balance_divergence_latches_until_operator_resolves(self):
        halt = BalanceDivergenceHalt(tolerance_pct=0.01)
        ok = halt.note_divergence(local_equity=2000.0, exchange_equity=2005.0)
        self.assertTrue(ok.allowed)
        self.assertFalse(halt.halted)
        bad = halt.note_divergence(local_equity=2000.0, exchange_equity=2100.0)
        self.assertFalse(bad.allowed)
        self.assertTrue(halt.halted)
        # A later reconciled reading must NOT auto-clear the halt.
        halt.note_divergence(local_equity=2100.0, exchange_equity=2100.0)
        self.assertTrue(halt.halted)
        halt.resolve(operator="operator-oncall")
        self.assertFalse(halt.halted)
        with self.assertRaises(ValueError):
            halt.resolve(operator="")

    def test_portfolio_exposure_caps_aggregate_notional(self):
        portfolio = PortfolioExposure(max_exposure_pct=1.0)
        self.assertTrue(
            portfolio.reserve("BTCUSDT", 1200.0, 2000.0).allowed)
        verdict = portfolio.reserve("ETHUSDT", 900.0, 2000.0)
        self.assertFalse(verdict.allowed)
        portfolio.release("BTCUSDT")
        self.assertTrue(
            portfolio.reserve("ETHUSDT", 900.0, 2000.0).allowed)


if __name__ == "__main__":
    unittest.main()
