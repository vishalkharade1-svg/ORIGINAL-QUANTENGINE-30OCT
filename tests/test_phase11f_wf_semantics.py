"""Phase 11F-5 walk-forward semantic tests (expanding-origin proof).

These tests assert MEANING, not documentation: any rolling/sliding
implementation must fail them. Synthetic index geometry only — no
market data, no hypotheses, no D3.
"""

import unittest

from research.phase11f import validation as V


def _folds(n=8000):
    return V.build_folds(n)


class TestExpandingSemantics(unittest.TestCase):
    def test_wf_001_all_trains_start_at_zero(self):
        for f in _folds():
            self.assertEqual(f["train_start"], 0, "fold %d" % f["fold"])

    def test_wf_002_train_end_monotonic(self):
        ends = [f["train_end"] for f in _folds()]
        self.assertEqual(ends, [2000, 3000, 4000, 5000])
        self.assertEqual(ends, sorted(ends))
        self.assertEqual(len(set(ends)), 4)

    def test_wf_003_trains_nested(self):
        trains = [(f["train_start"], f["train_end"]) for f in _folds()]
        for (a0, a1), (b0, b1) in zip(trains, trains[1:]):
            self.assertGreaterEqual(a0, b0)
            self.assertLessEqual(a1, b1)

    def test_wf_004_tests_chronological_disjoint(self):
        prev_end = -1
        for f in _folds():
            self.assertGreaterEqual(f["test_start"], prev_end)
            self.assertLess(f["test_start"], f["test_end"])
            prev_end = f["test_end"]

    def test_wf_005_purge_gap_respected(self):
        for f in _folds():
            self.assertEqual(f["purge_start"], f["train_end"])
            self.assertEqual(f["purge_end"] - f["purge_start"], 150)
            self.assertLessEqual(f["train_end"] + 150 + 25, f["test_start"])

    def test_wf_006_embargo_gap_respected(self):
        for f in _folds():
            self.assertEqual(f["embargo_start"], f["purge_end"])
            self.assertEqual(f["embargo_end"] - f["embargo_start"], 25)
            self.assertEqual(f["test_start"], f["embargo_end"])

    def test_wf_007_train_test_overlap_impossible(self):
        for f in _folds():
            self.assertTrue(
                set(range(f["train_start"], f["train_end"])).isdisjoint(
                    range(f["test_start"], f["test_end"])))

    def test_wf_008_tests_never_overlap_prior(self):
        seen = set()
        for f in _folds():
            test = set(range(f["test_start"], f["test_end"]))
            self.assertTrue(test.isdisjoint(seen))
            seen |= test

    def test_wf_009_fit_region_never_touches_test(self):
        for f in _folds():
            self.assertTrue(V.check_threshold_fit_region(
                f["train_start"], f["train_end"], f["test_start"]))
            self.assertFalse(V.check_threshold_fit_region(
                f["train_start"], f["test_end"], f["test_start"]))

    def test_wf_010_construction_deterministic(self):
        self.assertEqual(_folds(), _folds())
        self.assertEqual(V.validate_folds(_folds()), [])
        self.assertEqual(V.validate_expanding(_folds()), [])


class TestRollingMutationDetected(unittest.TestCase):
    def test_rolling_window_mutation_fails(self):
        # Mandatory mutant: train_start = k*step (the 11F-4 defect).
        folds = _folds()
        mutant = []
        for f in folds:
            m = dict(f)
            m["train_start"] = f["fold"] * 1000
            m["train_end"] = m["train_start"] + 2000
            mutant.append(m)
        errors = V.validate_expanding(mutant)
        self.assertTrue(any("rolling" in e for e in errors))
        # The old isolation-only validator CANNOT see this defect
        # (windows still isolate) — proving why semantic tests exist.
        self.assertEqual(V.validate_folds(mutant), [])
        # Restoration passes.
        self.assertEqual(V.validate_expanding(folds), [])

    def test_shrinking_train_detected(self):
        folds = _folds()
        mutant = [dict(f) for f in folds]
        mutant[2]["train_end"] = mutant[1]["train_end"]
        self.assertTrue(V.validate_expanding(mutant))


if __name__ == "__main__":
    unittest.main()
