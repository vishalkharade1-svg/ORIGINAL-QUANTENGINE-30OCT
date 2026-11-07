"""Phase 11F-3 walk-forward tests (geometry, isolation, purge/embargo).

Pure index arithmetic on synthetic dataset lengths — no market data,
no hypothesis execution, no D3. Mutants overlap/remove regions and
must be detected; restoration passes clean.
"""

import unittest

from research.phase11f import validation as V


class TestWalkForwardSpecFrozen(unittest.TestCase):
    def test_spec_values(self):
        spec = V.WALK_FORWARD_SPEC
        self.assertEqual(spec["design"], "expanding-origin chronological folds")
        self.assertEqual(spec["train_min_bars"], 2000)
        self.assertEqual(spec["test_bars"], 1000)
        self.assertEqual(spec["purge_bars"], 150)
        self.assertEqual(spec["embargo_bars"], 25)
        self.assertEqual(spec["step_bars"], 1000)
        self.assertEqual(spec["n_folds"], 4)
        self.assertIn("train_end + purge + embargo <= test_start", spec["invariant"])

    def test_default_plan_builds_and_validates(self):
        folds = V.build_folds(8000)
        self.assertEqual(len(folds), 4)
        self.assertEqual(V.validate_folds(folds), [])
        # First fold geometry is hand-checkable.
        f0 = folds[0]
        self.assertEqual((f0["train_start"], f0["train_end"]), (0, 2000))
        self.assertEqual((f0["purge_start"], f0["purge_end"]), (2000, 2150))
        self.assertEqual((f0["embargo_start"], f0["embargo_end"]), (2150, 2175))
        self.assertEqual((f0["test_start"], f0["test_end"]), (2175, 3175))

    def test_infeasible_plan_raises_not_truncates(self):
        with self.assertRaises(ValueError):
            V.build_folds(2500)


class TestFoldIsolation(unittest.TestCase):
    def test_train_never_contains_test_bars(self):
        for folds in (V.build_folds(8000), V.build_folds(12000, n_folds=3)):
            for f in folds:
                self.assertTrue(
                    set(range(f["train_start"], f["train_end"])).isdisjoint(
                        range(f["test_start"], f["test_end"])))

    def test_purge_and_embargo_excluded(self):
        folds = V.build_folds(8000)
        for f in folds:
            test = set(range(f["test_start"], f["test_end"]))
            self.assertTrue(test.isdisjoint(range(f["purge_start"], f["purge_end"])))
            self.assertTrue(test.isdisjoint(range(f["embargo_start"], f["embargo_end"])))
            train = set(range(f["train_start"], f["train_end"]))
            self.assertTrue(train.isdisjoint(range(f["purge_start"], f["purge_end"])))

    def test_tests_chronological_and_disjoint(self):
        folds = V.build_folds(12000, n_folds=4)
        prev_end = -1
        for f in folds:
            self.assertGreaterEqual(f["test_start"], prev_end)
            prev_end = f["test_end"]

    def test_future_folds_cannot_affect_earlier(self):
        early = V.build_folds(8000)
        # Rebuilding with a longer dataset must not move earlier folds.
        late = V.build_folds(20000, n_folds=4)
        self.assertEqual(early, late)


class TestMutWFOverlap(unittest.TestCase):
    def test_mut_wf_1_train_test_overlap_detected(self):
        folds = V.build_folds(8000)
        mutant = [dict(f) for f in folds]
        mutant[1]["train_end"] = mutant[1]["test_end"]  # MUT-WF-1
        errors = V.validate_folds(mutant)
        self.assertTrue(any("overlaps test" in e for e in errors))
        self.assertEqual(V.validate_folds(folds), [])

    def test_mut_wf_2_purge_removal_detected(self):
        folds = V.build_folds(8000)
        mutant = [dict(f) for f in folds]
        f = mutant[0]
        f["purge_start"] = f["purge_end"] = f["train_end"]  # MUT-WF-2
        f["embargo_start"] = f["embargo_end"] = f["train_end"]
        f["test_start"] = f["train_end"]
        errors = V.validate_folds(mutant)
        self.assertTrue(errors)
        self.assertEqual(V.validate_folds(folds), [])

    def test_mut_wf_3_embargo_removal_detected(self):
        folds = V.build_folds(8000)
        mutant = [dict(f) for f in folds]
        f = mutant[2]
        f["embargo_start"] = f["embargo_end"] = f["purge_end"]  # MUT-WF-3
        f["test_start"] = f["purge_end"]
        errors = V.validate_folds(mutant)
        self.assertTrue(errors)
        self.assertEqual(V.validate_folds(folds), [])

    def test_mut_wf_5_future_fold_contamination_detected(self):
        folds = V.build_folds(12000, n_folds=4)
        mutant = [dict(f) for f in folds]
        # MUT-WF-5: shift fold 0's test into fold 2's test range.
        mutant[0]["test_start"] = mutant[2]["test_start"]
        mutant[0]["test_end"] = mutant[2]["test_end"]
        errors = V.validate_folds(mutant)
        self.assertTrue(any("earlier test" in e or "chronological" in e
                            for e in errors))
        self.assertEqual(V.validate_folds(folds), [])


class TestValidationDeterminism(unittest.TestCase):
    def test_three_runs_identical(self):
        import hashlib
        import json
        runs = []
        for _ in range(3):
            folds = V.build_folds(8000)
            plan = {"spec": V.WALK_FORWARD_SPEC, "folds": folds,
                    "evidence": V.MIN_EVIDENCE, "oos": V.OOS_RULES,
                    "costs": V.cost_scenarios_frozen()}
            blob = json.dumps(plan, sort_keys=True)
            runs.append((folds, hashlib.sha256(blob.encode()).hexdigest()))
        self.assertEqual(runs[0][0], runs[1][0])
        self.assertEqual(runs[1][0], runs[2][0])
        self.assertEqual(len({r[1] for r in runs}), 1)

    def test_cost_and_metric_determinism(self):
        first = V.apply_cost_sequence(10.0, 500.0, "C")
        for _ in range(3):
            self.assertEqual(V.apply_cost_sequence(10.0, 500.0, "C"), first)
        self.assertEqual(V.bh_reject([0.01, 0.04, 0.03, 0.20], 0.10),
                         V.bh_reject([0.01, 0.04, 0.03, 0.20], 0.10))


if __name__ == "__main__":
    unittest.main()
