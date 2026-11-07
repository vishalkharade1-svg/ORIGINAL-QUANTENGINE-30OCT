"""Phase-13 P0: verified-contract enforcement gate (deterministic).

  * tick / quantity-step / minimum / multiplier / precision;
  * unavailable contract -> UNAVAILABLE, legacy pass-through;
  * synthetic terms -> SYNTHETIC, never enforced as venue truth;
  * require_verified() fails closed for verified-semantics ops;
  * audit integration: VERIFIED enforced identically, legacy
    byte-identical (reasons untouched when unused);
  * LONG / SHORT symmetry; oversized / dust / non-finite cases;
  * paper strict-contract construction fails closed; default stays
    explicitly synthetic; env gate flips the default.

Stdlib only. No network. No venue values invented: every numeric
term in these tests is an explicitly attached test term.
"""

from __future__ import annotations

import unittest

from core.risk.contract_gate import (
    SYNTHETIC,
    UNAVAILABLE,
    VERIFIED,
    apply_terms,
    require_verified,
    resolve_terms,
)

TERMS = {"verified": True, "tick_size": 0.5, "quantity_step": 0.25,
         "minimum_quantity": 0.5, "multiplier": 1.0}


def gated_order(**overrides):
    from core.risk.order_intent import OrderIntent

    params = {"direction": "BULLISH", "entry": 100.0, "stop_loss": 90.0,
              "take_profit": 170.0, "quantity": 2.0, "risk_amount": 25.0,
              "confidence": 85.0, "score": 85.0, "symbol": "TEST",
              "valid": True, "contract_terms": dict(TERMS)}
    params.update(overrides)
    return OrderIntent(**params)


class TestResolveTerms(unittest.TestCase):
    def test_missing_means_unavailable(self):
        from core.risk.order_intent import OrderIntent

        order = OrderIntent(direction="BULLISH", entry=100.0)
        terms, status = resolve_terms(order)
        self.assertIsNone(terms)
        self.assertEqual(status, UNAVAILABLE)
        self.assertEqual(resolve_terms(object())[1], UNAVAILABLE)

    def test_synthetic_never_verified(self):
        terms, status = resolve_terms(
            gated_order(contract_terms={"synthetic_fallback": True}))
        self.assertIsNone(terms)
        self.assertEqual(status, SYNTHETIC)

    def test_verified_terms_resolve(self):
        terms, status = resolve_terms(gated_order())
        self.assertEqual(status, VERIFIED)
        self.assertEqual(terms["multiplier"], 1.0)

    def test_incomplete_verified_is_unavailable(self):
        bad = dict(TERMS)
        del bad["multiplier"]
        self.assertEqual(resolve_terms(
            gated_order(contract_terms=bad))[1], UNAVAILABLE)
        bad2 = dict(TERMS, tick_size=float("nan"))
        self.assertEqual(resolve_terms(
            gated_order(contract_terms=bad2))[1], UNAVAILABLE)

    def test_require_verified_fails_closed(self):
        from core.risk.order_intent import OrderIntent

        self.assertEqual(require_verified(gated_order())["tick_size"],
                         0.5)
        with self.assertRaises(ValueError):
            require_verified(OrderIntent(direction="BULLISH",
                                         entry=100.0))
        with self.assertRaises(ValueError):
            require_verified(gated_order(
                contract_terms={"synthetic_fallback": True}))


class TestApplyTerms(unittest.TestCase):
    def test_step_floor_and_minimum(self):
        # 2.3 floored to 2.25 (step 0.25), above minimum 0.5.
        verdict = apply_terms(quantity=2.3, entry=100.0, stop=90.0,
                              risk_amount=0.0, terms=dict(TERMS))
        self.assertTrue(verdict.valid)
        self.assertAlmostEqual(verdict.quantity, 2.25, places=9)
        self.assertAlmostEqual(verdict.position_value, 225.0,
                               places=9)

    def test_below_minimum_refused(self):
        verdict = apply_terms(quantity=0.4, entry=100.0, stop=90.0,
                              risk_amount=0.0, terms=dict(TERMS))
        self.assertFalse(verdict.valid)
        self.assertEqual(verdict.quantity, 0.0)

    def test_dust_refused(self):
        verdict = apply_terms(quantity=1e-9, entry=100.0, stop=90.0,
                              risk_amount=0.0, terms=dict(TERMS))
        self.assertFalse(verdict.valid)

    def test_off_tick_entry_refused(self):
        verdict = apply_terms(quantity=2.0, entry=100.13, stop=90.0,
                              risk_amount=0.0, terms=dict(TERMS))
        self.assertFalse(verdict.valid)

    def test_multiplier_budget_revalidated(self):
        terms = dict(TERMS, multiplier=10.0)
        # 2.0 * 10 * 10 = 200 > budget 20 -> refuse.
        refused = apply_terms(quantity=2.0, entry=100.0, stop=90.0,
                              risk_amount=20.0, terms=terms)
        self.assertFalse(refused.valid)
        # 0.25 * 10 * 10 = 25 > 20 still refuses; budget 300 admits.
        admitted = apply_terms(quantity=0.5, entry=100.0, stop=90.0,
                               risk_amount=300.0, terms=terms)
        self.assertTrue(admitted.valid)
        self.assertAlmostEqual(admitted.quantity, 0.5, places=9)

    def test_no_budget_means_discrete_only(self):
        verdict = apply_terms(quantity=2.0, entry=100.0, stop=90.0,
                              risk_amount=0.0,
                              terms=dict(TERMS, multiplier=1000.0))
        self.assertTrue(verdict.valid)

    def test_non_finite_fails_closed(self):
        for bad in (float("nan"), float("inf"), 0.0, -2.0):
            verdict = apply_terms(quantity=bad, entry=100.0,
                                  stop=90.0, risk_amount=0.0,
                                  terms=dict(TERMS))
            self.assertFalse(verdict.valid, bad)
        self.assertFalse(apply_terms(
            quantity=2.0, entry=float("nan"), stop=90.0,
            risk_amount=0.0, terms=dict(TERMS)).valid)
        self.assertFalse(apply_terms(
            quantity=2.0, entry=100.0, stop=100.0, risk_amount=0.0,
            terms=dict(TERMS)).valid)

    def test_long_short_symmetry(self):
        long_v = apply_terms(quantity=2.0, entry=100.0, stop=90.0,
                             risk_amount=20.0, terms=dict(TERMS))
        short_v = apply_terms(quantity=2.0, entry=100.0, stop=110.0,
                              risk_amount=20.0, terms=dict(TERMS))
        self.assertTrue(long_v.valid)
        self.assertTrue(short_v.valid)
        self.assertAlmostEqual(long_v.quantity, short_v.quantity,
                               places=9)


class TestAuditIntegration(unittest.TestCase):
    def test_legacy_passthrough_byte_identical(self):
        # No terms attached: audit output and reasons identical to
        # the pre-gate path (no reason noise appended).
        from core.risk.order_intent import OrderIntent
        from core.risk.position_manager import PositionManager

        manager = PositionManager()
        order = OrderIntent(direction="BULLISH", entry=100.0,
                            stop_loss=90.0, take_profit=170.0,
                            quantity=2.0, risk_amount=20.0,
                            position_value=200.0, valid=True)
        corrected, reasons = manager.audit(order)
        self.assertEqual(reasons, [])
        self.assertAlmostEqual(corrected.quantity, 2.0, places=9)
        self.assertTrue(corrected.valid)

    def test_synthetic_passthrough_labeled(self):
        from core.risk.position_manager import PositionManager

        manager = PositionManager()
        order = gated_order(contract_terms={"synthetic_fallback": True,
                                            "product_type": "SPOT"})
        corrected, reasons = manager.audit(order)
        self.assertEqual(reasons, [])
        self.assertAlmostEqual(corrected.quantity, 2.0, places=9)

    def test_verified_enforced_through_audit(self):
        from core.risk.position_manager import PositionManager

        manager = PositionManager()
        order = gated_order(quantity=2.3)
        corrected, reasons = manager.audit(order)
        self.assertTrue(corrected.valid)
        self.assertAlmostEqual(corrected.quantity, 2.25, places=9)
        self.assertTrue(any("step" in r for r in reasons))

    def test_verified_violation_invalidates(self):
        from core.risk.position_manager import PositionManager

        manager = PositionManager()
        order = gated_order(quantity=0.4)
        corrected, reasons = manager.audit(order)
        self.assertFalse(corrected.valid)
        self.assertEqual(corrected.quantity, 0.0)
        self.assertTrue(any("minimum" in r for r in reasons))

    def test_execution_equivalence_no_silent_drift(self):
        # What the gate enforces at audit time is what the
        # simulator books: stepped quantity * entry, with risk
        # revalidated — no silent economic drift downstream.
        from core.backtesting.trade_simulator import TradeSimulator

        sim = TradeSimulator()
        trade = sim.open_trade(gated_order(quantity=2.3), 1000)
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.quantity, 2.25, places=9)


class TestPaperStrictContracts(unittest.TestCase):
    def test_default_fallback_is_explicitly_synthetic(self):
        from core.runtime.paper_main import _eligible_instrument

        instrument = _eligible_instrument("BTCUSDT")
        self.assertTrue(instrument.metadata.get("synthetic_fallback"))
        self.assertEqual(instrument.product_type, "SPOT")

    def test_strict_mode_fails_closed(self):
        from core.runtime.paper_main import (
            ContractUnavailableError,
            ExplicitSymbolUniverseManager,
            _eligible_instrument,
        )

        with self.assertRaises(ContractUnavailableError):
            _eligible_instrument("BTCUSDT", strict=True)
        with self.assertRaises(ContractUnavailableError):
            ExplicitSymbolUniverseManager(symbols=["BTCUSDT"],
                                          strict_contracts=True)

    def test_env_gate_flips_default(self):
        import os
        from unittest.mock import patch

        from core.runtime.paper_main import (
            ContractUnavailableError,
            ExplicitSymbolUniverseManager,
        )

        with patch.dict(os.environ,
                        {"QE_REQUIRE_VERIFIED_CONTRACTS": "1"}):
            with self.assertRaises(ContractUnavailableError):
                ExplicitSymbolUniverseManager(symbols=["BTCUSDT"])
        with patch.dict(os.environ,
                        {"QE_REQUIRE_VERIFIED_CONTRACTS": ""}):
            manager = ExplicitSymbolUniverseManager(
                symbols=["BTCUSDT"])
            self.assertEqual(len(manager.instruments), 1)

    def test_synthetic_fallback_refused_by_verified_factory(self):
        # The fabricated fallback carries no verified_* evidence,
        # so the verified contract factory refuses it fail-closed.
        from core.risk.contract_spec_factory import (
            contract_spec_from_instrument,
        )
        from core.runtime.paper_main import _eligible_instrument

        instrument = _eligible_instrument("BTCUSDT")
        availability = contract_spec_from_instrument(instrument)
        self.assertIsNone(availability.spec)


if __name__ == "__main__":
    unittest.main()
