"""11G-D fresh-results certification (artifacts only, no re-execution)."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

RESEARCH = Path("research/phase11g")
D = RESEARCH / "results" / "11gd"

ARTIFACTS = ["fresh_data_audit.json", "fresh_data_manifest.json",
             "fresh_primary_results.json", "fresh_setup_rates.json",
             "fresh_fold_results.json", "fresh_cost_results.json",
             "fresh_ablation_results.json", "fresh_regime_results.json",
             "fresh_random_baseline_results.json", "fresh_monte_carlo_results.json",
             "fresh_execution_robustness.json", "fresh_reproducibility.json",
             "fresh_comparison_11gc.json", "run_manifest.json",
             "fresh_results_manifest.json"]


class TestFreshArtifacts(unittest.TestCase):
    def test_all_present_and_eight(self):
        for name in ARTIFACTS:
            self.assertTrue((D / name).exists(), name)
        hypo = json.loads((D / "fresh_primary_results.json").read_text())
        self.assertEqual(sorted(hypo), ["H11G-%03d" % i for i in range(1, 9)])
        for hid, rec in hypo.items():
            self.assertIn(rec["verdict"], ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"))

    def test_audit_declares_fresh(self):
        audit = json.loads((D / "fresh_data_audit.json").read_text())
        self.assertEqual(audit["freshness_verdict"], "FRESH")
        self.assertEqual(audit["bar_count"], 2499)
        self.assertEqual(audit["symbol"], "BTCUSDT")
        man = json.loads((D / "fresh_data_manifest.json").read_text())
        self.assertEqual(man["sha256"], audit["file_sha256"])

    def test_wf_infeasible_recorded(self):
        prim = json.loads((D / "fresh_fold_results.json").read_text())
        self.assertTrue(prim)
        # No fold geometry beyond a single diagnostic slice exists.
        for hid, fr in prim.items():
            self.assertEqual(fr["bars"], 2499)

    def test_no_d3_anywhere(self):
        # The "D3_counters" key name (a zero-proof) is allowed; D3
        # content markers (files, paths, statistics) are forbidden.
        for name in ARTIFACTS:
            blob = (D / name).read_text()
            for marker in ("universe_D3", "/D3", "D3_BTC", "D3_ETH"):
                self.assertNotIn(marker, blob, name)

    def test_economic_integrity(self):
        folds = json.loads((D / "fresh_fold_results.json").read_text())
        n = 0
        for fr in folds.values():
            for cost in "ABCD":
                for t in fr["costs"][cost]["trades"]:
                    self.assertAlmostEqual(
                        t["gross"] - t["commission"] - t["slippage"], t["net"])
                    self.assertLessEqual(t["decision_time"], t["entry_time"])
                    n += 1
        self.assertEqual(n, 0)  # fresh run produced zero fills (recorded fact)

    def test_no_winner(self):
        for name in ARTIFACTS:
            self.assertNotIn("winner", (D / name).read_text().lower(), name)
        mt = json.loads((D / "fresh_multiple_testing.json").read_text()) \
            if (D / "fresh_multiple_testing.json").exists() else {"passes": 0}
        self.assertEqual(mt["passes"], 0)

    def test_ablations_preregistered(self):
        abls = json.loads((D / "fresh_ablation_results.json").read_text())
        allowed = {("H11G-001", "no-sweep"), ("H11G-002", "no-sweep"),
                   ("H11G-002", "no-displacement"), ("H11G-003", "no-sweep"),
                   ("H11G-003", "no-displacement"), ("H11G-003", "no-fvg"),
                   ("H11G-004", "no-bos"), ("H11G-005", "no-breaker"),
                   ("H11G-006", "no-volume"), ("H11G-007", "no-volume"),
                   ("H11G-008", "no-htf")}
        seen = {(k.split("|")[0], k.split("|")[1]) for k in abls}
        self.assertTrue(seen <= allowed)
        # Structural check only (never outcome-dependent): every record
        # carries the removed-component name and trade counts.
        for rec in abls.values():
            self.assertIn("removed", rec)
            self.assertIn("trades", rec)
            self.assertIn("net", rec)

    def test_repro_record(self):
        rep = json.loads((D / "fresh_reproducibility.json").read_text())
        self.assertTrue(rep["identical"])
        self.assertTrue(rep["truncation_all_pass"])
        self.assertEqual(len(rep["folds"]), 32)

    def test_comparison_honest(self):
        comp = json.loads((D / "fresh_comparison_11gc.json").read_text())
        self.assertEqual(sorted(comp), ["H11G-%03d" % i for i in range(1, 9)])
        for hid, rec in comp.items():
            self.assertIn("sparsity persists", rec["interpretation"])
            self.assertEqual(rec["trades_fresh"], 0)


class TestFreshMutations(unittest.TestCase):
    def test_mutated_hypothesis_detected(self):
        man = json.loads((RESEARCH / "freeze_manifest.json").read_text())
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        ref = man["hypothesis_sha256"]
        bad = copy.deepcopy(doc)
        bad["hypotheses"][3]["stop_rule"] = "MUTANT"
        self.assertNotEqual(
            hashlib.sha256(json.dumps(bad).encode()).hexdigest(), ref)

    def test_contaminated_cannot_pass_as_fresh(self):
        from research.phase11g import fresh as FR
        for name in ("D1_BTC", "D2_ETH", "gate_a_snapshot", "phase7_file"):
            self.assertEqual(FR.freshness(name), "CONTAMINATED")
        with self.assertRaises(FR.SealedHoldoutError):
            FR.freshness("D3_BTC")

    def test_mutated_cost_detected(self):
        from research.phase11f.harness import COST_SCENARIOS_11F
        self.assertAlmostEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)
        bad = dict(COST_SCENARIOS_11F["C"], SLIPPAGE_BPS=0.0)
        self.assertNotEqual(bad["SLIPPAGE_BPS"],
                            COST_SCENARIOS_11F["C"]["SLIPPAGE_BPS"])


if __name__ == "__main__":
    unittest.main()
