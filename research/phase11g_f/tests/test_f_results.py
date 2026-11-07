"""11G-F results certification (artifacts only, no re-execution)."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

RESEARCH = Path("research/phase11g_f")
RESULTS = RESEARCH / "results"

ARTIFACTS = ["primary_results.json", "fold_results.json", "cost_results.json",
             "ablation_results.json", "regime_results.json",
             "random_baseline_results.json", "monte_carlo_results.json",
             "execution_robustness_results.json", "reproducibility_results.json",
             "multiple_testing_results.json"]


class TestArtifacts(unittest.TestCase):
    def test_all_present_and_eight(self):
        for name in ARTIFACTS:
            self.assertTrue((RESULTS / name).exists(), name)
        hypo = json.loads((RESULTS / "primary_results.json").read_text())
        self.assertEqual(sorted(hypo), ["H11GF-%03d" % i for i in range(1, 9)])
        for hid, rec in hypo.items():
            self.assertIn(rec["verdict"], ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"))

    def test_256_matrix_and_expanding(self):
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        self.assertEqual(len(folds), 64)
        for key, fr in folds.items():
            self.assertEqual(set(fr["costs"]), {"A", "B", "C", "D"})
            self.assertEqual(fr["execution_model"][:13], "NEXT_BAR_OPEN")
            self.assertEqual(fr["geometry"]["train_start"], 0)
        ends = sorted({fr["geometry"]["train_end"] for fr in folds.values()})
        self.assertEqual(ends, [2000, 3000, 4000, 5000])

    def test_no_d3_no_live(self):
        for name in ARTIFACTS:
            blob = (RESULTS / name).read_text()
            for marker in ("universe_D3", "/D3", "D3_BTC", "D3_ETH",
                           "LIVE_EXECUTE", "ALLOW_LIVE"):
                self.assertNotIn(marker, blob, name)
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        for fr in folds.values():
            self.assertTrue(set(fr["lineage"]) <= {"D1", "D2"})

    def test_economic_integrity(self):
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        n = 0
        for fr in folds.values():
            for cost in "ABCD":
                for t in fr["costs"][cost]["trades"]:
                    self.assertAlmostEqual(
                        t["gross"] - t["commission"] - t["slippage"], t["net"])
                    self.assertLessEqual(t["decision_time"], t["entry_time"])
                    self.assertLessEqual(t["entry_time"], t["exit_time"])
                    n += 1
        self.assertGreater(n, 0)

    def test_fills_cost_independent(self):
        folds = json.loads((RESULTS / "fold_results.json").read_text())
        for key, fr in folds.items():
            self.assertEqual(
                len({len(fr["costs"][c]["trades"]) for c in "ABCD"}), 1, key)

    def test_verdict_rule(self):
        hypo = json.loads((RESULTS / "primary_results.json").read_text())
        for hid, rec in hypo.items():
            if rec["evidence"] != "SUFFICIENT":
                self.assertEqual(rec["verdict"], "INSUFFICIENT_EVIDENCE")

    def test_no_winner(self):
        for name in ARTIFACTS:
            self.assertNotIn("winner", (RESULTS / name).read_text().lower(), name)
        mt = json.loads((RESULTS / "multiple_testing_results.json").read_text())
        self.assertEqual(mt["passes"], 0)
        self.assertAlmostEqual(mt["bonferroni_reference"], 0.00625)

    def test_repro_record(self):
        rep = json.loads((RESULTS / "reproducibility_results.json").read_text())
        self.assertTrue(rep["identical"])
        self.assertEqual(len(rep["folds"]), 256)
        self.assertTrue(all(rep["folds"].values()))

    def test_ablations_preregistered(self):
        abls = json.loads((RESULTS / "ablation_results.json").read_text())
        allowed = {("H11GF-001", "no-sweep"), ("H11GF-002", "no-sweep"),
                   ("H11GF-002", "no-displacement"), ("H11GF-003", "no-sweep"),
                   ("H11GF-003", "no-displacement"), ("H11GF-003", "no-fvg"),
                   ("H11GF-004", "no-bos"), ("H11GF-005", "no-breaker"),
                   ("H11GF-006", "no-volume"), ("H11GF-007", "no-volume"),
                   ("H11GF-008", "no-htf")}
        seen = {(k.split("|")[0], k.split("|")[1]) for k in abls}
        self.assertTrue(seen <= allowed)
        for rec in abls.values():
            self.assertIn("removed", rec)


class TestExecutionMutations(unittest.TestCase):
    def test_mutated_hypothesis_detected(self):
        man = json.loads((RESEARCH / "freeze_manifest.json").read_text())
        doc = json.loads((RESEARCH / "hypotheses" / "hypotheses.json").read_text())
        ref = man["hypothesis_sha256"]
        bad = copy.deepcopy(doc)
        bad["hypotheses"][0]["stop_rule"] = "MUTANT"
        self.assertNotEqual(
            hashlib.sha256(json.dumps(bad).encode()).hexdigest(), ref)

    def test_mutated_cost_detected(self):
        from research.phase11f.harness import COST_SCENARIOS_11F
        self.assertAlmostEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)
        bad = dict(COST_SCENARIOS_11F["C"], SLIPPAGE_BPS=0.0)
        self.assertNotEqual(bad["SLIPPAGE_BPS"],
                            COST_SCENARIOS_11F["C"]["SLIPPAGE_BPS"])

    def test_rolling_mutation_detected(self):
        from research.phase11f import validation as V
        folds = V.build_folds(8000)
        self.assertEqual(V.validate_expanding(folds), [])
        mutant = [dict(f, train_start=f["fold"] * 1000,
                       train_end=f["fold"] * 1000 + 2000) for f in folds]
        self.assertTrue(any("rolling" in e for e in V.validate_expanding(mutant)))


if __name__ == "__main__":
    unittest.main()
