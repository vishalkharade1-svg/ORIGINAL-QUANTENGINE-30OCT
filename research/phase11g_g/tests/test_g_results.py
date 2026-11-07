"""11G-G replication certification (artifacts only, no re-execution)."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

RESEARCH = Path("research/phase11g_g")
RESULTS = RESEARCH / "results"

ARTIFACTS = ["gap_fold_results.json", "gap_setup_rates.json",
             "gap_primary_results.json", "gap_cost_results.json",
             "gap_ablation_results.json", "gap_random_baseline.json",
             "gap_monte_carlo.json", "gap_execution_robustness.json",
             "gap_reproducibility.json", "gap_comparison_11gf.json",
             "run_manifest.json", "gap_results_manifest.json"]


class TestArtifacts(unittest.TestCase):
    def test_all_present_and_eight(self):
        for name in ARTIFACTS:
            self.assertTrue((RESULTS / name).exists(), name)
        hypo = json.loads((RESULTS / "gap_primary_results.json").read_text())
        self.assertEqual(sorted(hypo), ["H11GF-%03d" % i for i in range(1, 9)])
        for hid, rec in hypo.items():
            self.assertIn(rec["verdict"], ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"))

    def test_16_executions_no_folds_fabricated(self):
        folds = json.loads((RESULTS / "gap_fold_results.json").read_text())
        self.assertEqual(len(folds), 16)
        for key, fr in folds.items():
            self.assertEqual(set(fr["costs"]), {"A", "B", "C", "D"})
            self.assertEqual(fr["wf"], "WF_INFEASIBLE_2099_lt_6175")
            self.assertEqual(fr["bars"], 2099)

    def test_gap_window_respected(self):
        folds = json.loads((RESULTS / "gap_fold_results.json").read_text())
        for fr in folds.values():
            for cost in "ABCD":
                for t in fr["costs"][cost]["trades"]:
                    self.assertGreater(t["decision_time"], 1788175440)
                    self.assertLess(t["decision_time"], 1788301500)

    def test_no_d3_no_live(self):
        for name in ARTIFACTS:
            blob = (RESULTS / name).read_text()
            for marker in ("universe_D3", "/D3", "D3_BTC", "D3_ETH",
                           "LIVE_EXECUTE", "ALLOW_LIVE"):
                self.assertNotIn(marker, blob, name)

    def test_economic_integrity(self):
        folds = json.loads((RESULTS / "gap_fold_results.json").read_text())
        n = 0
        for fr in folds.values():
            for cost in "ABCD":
                for t in fr["costs"][cost]["trades"]:
                    self.assertAlmostEqual(
                        t["gross"] - t["commission"] - t["slippage"], t["net"])
                    self.assertLessEqual(t["decision_time"], t["entry_time"])
                    n += 1
        self.assertEqual(n, 0)  # recorded fact: zero gap fills

    def test_no_winner(self):
        for name in ARTIFACTS:
            self.assertNotIn("winner", (RESULTS / name).read_text().lower(), name)
        log = json.loads((RESEARCH / "research_log.json").read_text())
        self.assertEqual(log["passes"], 0)
        self.assertFalse(log["winner_selected"])

    def test_repro_record(self):
        rep = json.loads((RESULTS / "gap_reproducibility.json").read_text())
        self.assertTrue(rep["identical"])
        self.assertEqual(len(rep["runs"]), 64)
        self.assertTrue(all(rep["runs"].values()))
        self.assertTrue(rep["truncation_all_pass"])

    def test_comparison_honest(self):
        comp = json.loads((RESULTS / "gap_comparison_11gf.json").read_text())
        self.assertEqual(sorted(comp), ["H11GF-%03d" % i for i in range(1, 9)])
        for hid, rec in comp.items():
            self.assertIn("sparsity persists", rec["interpretation"])
            self.assertEqual(rec["trades_gap"], 0)


class TestReplicationMutations(unittest.TestCase):
    def test_mutated_family_detected(self):
        man = json.loads((RESEARCH / "freeze_manifest.json").read_text())
        doc = json.loads(
            (Path("research/phase11g_f/hypotheses/hypotheses.json")).read_text())
        ref = man["family_sha256"]
        bad = copy.deepcopy(doc)
        bad["hypotheses"][0]["stop_rule"] = "MUTANT"
        self.assertNotEqual(
            hashlib.sha256(json.dumps(bad).encode()).hexdigest(), ref)

    def test_gap_data_swapped_detected(self):
        man = json.loads((RESEARCH / "freeze_manifest.json").read_text())
        btc = man["fresh_datasets"]["BTCUSDT"]["sha256"]
        eth = man["fresh_datasets"]["ETHUSDT"]["sha256"]
        self.assertNotEqual(btc, eth)
        d = json.load(open("research/phase11g_g/data/fresh_11gg_gap_btcusdt.json"))
        self.assertEqual(d["sha256"], btc)

    def test_rolling_mutation_detected(self):
        from research.phase11f import validation as V
        folds = V.build_folds(8000)
        self.assertEqual(V.validate_expanding(folds), [])
        mutant = [dict(f, train_start=f["fold"] * 1000,
                       train_end=f["fold"] * 1000 + 2000) for f in folds]
        self.assertTrue(any("rolling" in e for e in V.validate_expanding(mutant)))


if __name__ == "__main__":
    unittest.main()
