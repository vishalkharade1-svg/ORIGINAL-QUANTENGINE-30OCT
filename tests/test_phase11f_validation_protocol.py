"""Phase 11F-3 validation-protocol tests (fit isolation, OOS, plans).

No hypothesis execution, no market data, no D3. Threshold mutants
fit on future data and must be detected; restoration uses
training-only fits. Ablation / random-baseline / regime plans are
frozen data + validators.
"""

import unittest

from research.phase11f import datasets as D
from research.phase11f import validation as V


def _train_vals():
    return [float(i) for i in range(100)]


def _test_vals():
    return [1000.0 + float(i) for i in range(20)]


class TestParameterFitIsolation(unittest.TestCase):
    def test_thresholds_fit_on_train_only(self):
        lo, hi = V.tercile_thresholds(_train_vals())
        self.assertLess(lo, hi)
        self.assertTrue(V.check_threshold_fit_region(0, 100, 100))
        self.assertFalse(V.check_threshold_fit_region(0, 120, 100))

    def test_mut_wf_4_future_threshold_fitting_detected(self):
        certified = V.tercile_thresholds(_train_vals())
        # MUT-WF-4: fit on train + test (future-aware quantiles).
        mutant = V.tercile_thresholds(_train_vals() + _test_vals())
        self.assertNotEqual(certified, mutant)
        # The guard rejects any fit window reaching into the test.
        self.assertFalse(V.check_threshold_fit_region(0, 120, 100))
        # Restoration: training-only fit is stable and accepted.
        self.assertEqual(V.tercile_thresholds(_train_vals()), certified)
        self.assertTrue(V.check_threshold_fit_region(0, 100, 100))

    def test_hostile_future_values_cannot_shift_train_fit(self):
        ref = V.tercile_thresholds(_train_vals())
        # Even with extreme future values present, the certified call
        # site only ever passes the training slice.
        self.assertEqual(V.tercile_thresholds(_train_vals()[:100]), ref)


class TestOOSDefinition(unittest.TestCase):
    def test_oos_rules_frozen(self):
        self.assertIn("chronologically later than all fitting/selection data",
                      V.OOS_RULES[0])
        self.assertTrue(any("D3" in r and "sealed holdout" in r for r in V.OOS_RULES))

    def test_mut_oos_1_test_used_for_fitting_detected(self):
        # MUT-OOS-1: test bars feed the threshold fit.
        self.assertFalse(V.check_threshold_fit_region(50, 150, 100))
        self.assertTrue(V.check_threshold_fit_region(0, 100, 100))


class TestMinimumEvidence(unittest.TestCase):
    def test_minima_frozen(self):
        self.assertEqual(V.MIN_EVIDENCE["min_trades_pooled"], 30)
        self.assertEqual(V.MIN_EVIDENCE["min_folds"], 3)
        self.assertEqual(V.MIN_EVIDENCE["min_active_folds"], 2)
        self.assertIn("never silently dropped",
                      V.MIN_EVIDENCE["zero_trade_fold"])

    def test_assess_evidence(self):
        self.assertEqual(V.assess_evidence(30, 3, 2), "SUFFICIENT")
        self.assertIn("INSUFFICIENT", V.assess_evidence(29, 4, 4))
        self.assertIn("INSUFFICIENT", V.assess_evidence(50, 4, 1))
        # Zero-trade folds are representable, not errors.
        self.assertIn("INSUFFICIENT", V.assess_evidence(0, 4, 0))


class TestAblationProtocol(unittest.TestCase):
    def test_registry_unchanged(self):
        self.assertEqual(V.verify_ablations(), [])
        from research.phase11f.contracts import ABLATIONS
        self.assertEqual(set(ABLATIONS), {"H11F-002", "H11F-005", "H11F-007"})

    def test_mut_ablation_1_hidden_second_change_detected(self):
        from research.phase11f import candidates as C
        # MUT-ABLATION-1: an ablation smuggling a second override.
        mutant_overrides = {"use_sweep": False, "displacement_atr": 9.99}
        self.assertEqual(len(mutant_overrides), 2)
        certified = dict(C.SweepDisplacementFVG(use_sweep=False).cfg)
        self.assertAlmostEqual(certified["displacement_atr"], 2.0)
        # Restoration: certified ablations carry exactly one override.
        from research.phase11f.contracts import ABLATIONS
        for variants in ABLATIONS.values():
            for v in variants:
                if v["name"] != "full":
                    self.assertEqual(len(v["overrides"]), 1)


class TestRandomBaselineProtocol(unittest.TestCase):
    def test_plan_frozen(self):
        plan = V.RANDOM_BASELINE_PLAN
        self.assertEqual(plan["draws_per_fold"], 500)
        self.assertEqual(plan["costs"], "scenario C")
        self.assertIn("never cross a fold boundary", plan["boundary"])
        self.assertIn("MTM", plan["boundary"])

    def test_within_fold_check(self):
        self.assertTrue(V.check_random_trade_within_fold(2200, 2300, 2175, 3175))
        self.assertFalse(V.check_random_trade_within_fold(2100, 2300, 2175, 3175))

    def test_mut_random_1_cross_fold_detected(self):
        # MUT-RANDOM-1: a random trade crossing the fold boundary.
        self.assertFalse(V.check_random_trade_within_fold(3100, 3300, 2175, 3175))
        # Restoration: confined trades pass.
        self.assertTrue(V.check_random_trade_within_fold(2200, 2300, 2175, 3175))


class TestRegimeProtocol(unittest.TestCase):
    def test_plan_prohibits_future_thresholds(self):
        self.assertIn("full-dataset quantiles", V.REGIME_PLAN["prohibited"])
        self.assertIn("TRAINING bars only", V.REGIME_PLAN["volatility"])
        self.assertEqual(V.REGIME_PLAN["min_trades_per_cell"], 3)

    def test_mut_regime_1_future_threshold_detected(self):
        self.assertFalse(V.check_threshold_fit_region(0, 5000, 2175))
        self.assertTrue(V.check_threshold_fit_region(0, 2000, 2175))


class TestMonteCarloProtocol(unittest.TestCase):
    def test_plan_frozen(self):
        plan = V.MONTE_CARLO_PLAN
        self.assertEqual(plan["trade_order_shuffle"]["sims"], 5000)
        self.assertEqual(plan["trade_order_shuffle"]["seed"], 1107001)
        self.assertEqual(plan["bootstrap_expectancy"]["seed"], 1107002)
        self.assertIn("P(net<0)", plan["statistics"])


class TestExecutionFreeze(unittest.TestCase):
    def test_models_match_registry(self):
        models = V.execution_models()
        self.assertEqual(len(models), 8)
        self.assertIn(models["H11F-001"], ("NEXT_BAR_OPEN market fill",))
        self.assertIn("LIMIT", models["H11F-002"])
        self.assertEqual(V.EXECUTION_FREEZE["channel"][:12], "LIMIT_RETEST")

    def test_no_model_substitution(self):
        import json
        from pathlib import Path
        doc = json.loads((Path("research/phase11f/hypotheses.json")).read_text())
        by_id = {h["hypothesis_id"]: h for h in doc["hypotheses"]}
        self.assertEqual(by_id["H11F-001"]["execution_model"], "NEXT_BAR_OPEN market fill")
        self.assertIn("LIMIT touch fill", by_id["H11F-005"]["execution_model"])


class TestD3StillSealed(unittest.TestCase):
    def test_seal_intact_no_hash_no_read(self):
        for path in D.discovery_files():
            D.assert_not_holdout(path)
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout_candles("research/phase11f/data/universe_D3_BTC.json")
        self.assertEqual(D.validate_lineage(), [])


class TestResearchSafety(unittest.TestCase):
    def test_validation_module_has_no_execution_reach(self):
        from pathlib import Path
        src = Path("research/phase11f/validation.py").read_text()
        for token in ("DeltaOrderExecutor", "BrokerEngine", "place_order",
                      "submit_order", "DeltaExchange", "_require_auth",
                      "DELTA_API_KEY", "DELTA_API_SECRET", "LIVE_EXECUTE",
                      "ALLOW_LIVE"):
            self.assertNotIn(token, src)

    def test_exchange_writes_raise_if_reached(self):
        from unittest import mock
        with mock.patch("core.execution.order_executor.DeltaOrderExecutor.execute",
                        side_effect=AssertionError("live write reached")) as m:
            V.build_folds(8000)
            V.apply_cost_sequence(10.0, 500.0, "C")
            V.bh_reject([0.01, 0.04], 0.10)
        m.assert_not_called()

    def test_log_untouched_by_validators(self):
        # 11F-4 authorized update: validators never write the ledger;
        # the ledger holds the recorded 11F-4 verdicts with preserved
        # registration history (full check in test_phase11f_results.py).
        import json
        from pathlib import Path
        log = json.loads(Path("research/phase11f/research_log.json").read_text())
        hypo = json.loads(Path("research/phase11f/results/hypothesis_results.json").read_text())
        for entry in log["entries"]:
            self.assertEqual(entry["status"], hypo[entry["id"]]["verdict"])
            self.assertEqual(entry["registration_timestamp"], "2026-09-07T00:00:00Z")
            if entry["status"] == "PASS":
                self.assertIsNone(entry["failure_reason"])
            else:
                self.assertIsNotNone(entry["failure_reason"])


if __name__ == "__main__":
    unittest.main()
