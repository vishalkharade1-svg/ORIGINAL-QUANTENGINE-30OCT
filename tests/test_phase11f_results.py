"""Phase 11F-4 results meta-tests (artifacts only, no re-execution).

Verifies the recorded evidence is complete, consistent, D3-free,
and winner-free. Never runs hypotheses, never opens D3.
"""

import json
import unittest
from pathlib import Path

RESEARCH = Path("research/phase11f")
RESULTS = RESEARCH / "results"

ARTIFACTS = ["hypothesis_results.json", "fold_results.json",
             "cost_results.json", "regime_results.json",
             "random_baseline_results.json", "monte_carlo_results.json",
             "ablation_results.json", "execution_results.json",
             "multiple_testing_results.json", "reproducibility.json"]


class TestArtifactsExist(unittest.TestCase):
    def test_all_ten_present(self):
        for name in ARTIFACTS:
            self.assertTrue((RESULTS / name).exists(), name)

    def test_eight_hypotheses_recorded(self):
        hypo = json.loads((RESULTS / "hypothesis_results.json").read_text())
        self.assertEqual(sorted(hypo), ["H11F-%03d" % i for i in range(1, 9)])
        for hid, rec in hypo.items():
            self.assertIn(rec["verdict"], ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"))
            for field in ("n_pooled", "n_folds", "active_folds", "metrics_C", "evidence"):
                self.assertIn(field, rec)


class TestNoD3Anywhere(unittest.TestCase):
    def test_artifacts_contain_no_d3(self):
        for name in ARTIFACTS:
            blob = (RESULTS / name).read_text()
            self.assertNotIn("D3", blob, name)
            self.assertNotIn("oos_fresh", blob, name)

    def test_fold_lineage_d1_d2_only(self):
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        for key, fr in folds.items():
            for tier in fr["lineage"]:
                self.assertIn(tier, ("D1", "D2"), key)

    def test_runner_never_reads_d3(self):
        for line in (RESEARCH / "run_research.py").read_text().splitlines():
            if "D3" in line:
                self.assertNotIn("open(", line)
                self.assertNotIn("read_text", line)
                self.assertNotIn("candles", line)


class TestLogMatchesArtifacts(unittest.TestCase):
    def test_verdicts_and_counts_agree(self):
        log = json.loads((RESEARCH / "research_log.json").read_text())
        hypo = json.loads((RESULTS / "hypothesis_results.json").read_text())
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        for entry in log["entries"]:
            hid = entry["id"]
            self.assertEqual(entry["status"], hypo[hid]["verdict"])
            self.assertEqual(entry["result"]["verdict"], hypo[hid]["verdict"])
            self.assertEqual(entry["result"]["n_pooled"], hypo[hid]["n_pooled"])
            n_c = sum(len(folds["%s|%s|F%d" % (hid, s, f)]["costs"]["C"]["trades"])
                      for s in ("BTCUSDT", "ETHUSDT") for f in range(4))
            self.assertEqual(entry["result"]["n_pooled"], n_c)

    def test_registration_history_preserved(self):
        log = json.loads((RESEARCH / "research_log.json").read_text())
        hyps = json.loads((RESEARCH / "hypotheses.json").read_text())
        by_id = {h["hypothesis_id"]: h for h in hyps["hypotheses"]}
        for entry in log["entries"]:
            h = by_id[entry["id"]]
            from research.phase11f.contracts import sha256_canonical
            self.assertEqual(entry["hypothesis_hash"], sha256_canonical(h))
            self.assertEqual(entry["registration_timestamp"], "2026-09-07T00:00:00Z")
            self.assertGreaterEqual(entry["variants_tested"], 1)


class TestEconomicIntegrity(unittest.TestCase):
    def test_every_trade_balances(self):
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        n = 0
        for fr in folds.values():
            for cost in ("A", "B", "C", "D"):
                for t in fr["costs"][cost]["trades"]:
                    self.assertAlmostEqual(
                        t["gross"] - t["commission"] - t["slippage"], t["net"])
                    n += 1
        self.assertGreater(n, 100)

    def test_fills_cost_independent(self):
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        for key, fr in folds.items():
            counts = {len(fr["costs"][c]["trades"]) for c in "ABCD"}
            self.assertEqual(len(counts), 1, key)

    def test_verdict_rule_applied(self):
        hypo = json.loads((RESULTS / "hypothesis_results.json").read_text())
        for hid, rec in hypo.items():
            if rec["evidence"] != "SUFFICIENT":
                self.assertEqual(rec["verdict"], "INSUFFICIENT_EVIDENCE")
            elif rec["metrics_C"]["net"] > 0:
                self.assertEqual(rec["verdict"], "PASS")
            else:
                self.assertEqual(rec["verdict"], "FAIL")


class TestNoWinner(unittest.TestCase):
    def test_no_selection_artifact(self):
        for name in ARTIFACTS:
            blob = (RESULTS / name).read_text().lower()
            self.assertNotIn("winner", blob, name)
        mt = json.loads((RESULTS / "multiple_testing_results.json").read_text())
        self.assertEqual(mt["passes"], 0)
        self.assertAlmostEqual(mt["bonferroni_reference"], 0.00625)

    def test_ablations_preregistered_only(self):
        abls = json.loads((RESULTS / "ablation_results.json").read_text())
        allowed = {("H11F-002", "no-sweep"), ("H11F-002", "no-fvg"),
                   ("H11F-005", "no-sweep"), ("H11F-007", "no-trend"),
                   ("H11F-007", "no-fvg")}
        seen = {(k.split("|")[0], k.split("|")[1]) for k in abls}
        self.assertTrue(seen <= allowed)
        for rec in abls.values():
            self.assertIsNotNone(rec["removed"])


class TestReproducibilityRecord(unittest.TestCase):
    def test_repeat_identical(self):
        rep = json.loads((RESULTS / "reproducibility.json").read_text())
        self.assertTrue(rep["identical"])
        self.assertEqual(len(rep["folds"]), 256)
        self.assertTrue(all(rep["folds"].values()))
        self.assertTrue(all(rep["metrics"].values()))


if __name__ == "__main__":
    unittest.main()
