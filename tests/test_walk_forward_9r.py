"""
Phase 9R-1 — Walk-forward disjoint test windows, purge/embargo.

Requirements:
- OOS test windows must be explicit, disjoint (no overlap) unless documented
- Purge + embargo supported
- Chronological, no lookahead
"""

import unittest
from dataclasses import dataclass

from core.research.ml.split import walk_forward


@dataclass
class Item:
    decision_bar: int
    timestamp: int = 0


class TestWalkForwardDisjoint(unittest.TestCase):

    def test_test_windows_are_disjoint(self):
        items = [Item(decision_bar=i) for i in range(100)]
        wf = walk_forward(items, train_size=0.5, step=0.2)
        # Collect all test indices across folds
        all_test = []
        for f in wf.folds:
            all_test.extend(f.test.indices)
        # No index should appear in more than one test fold
        self.assertEqual(len(all_test), len(set(all_test)), msg="Test windows must be disjoint")

    def test_test_windows_no_overlap_with_train_of_same_fold(self):
        items = [Item(decision_bar=i) for i in range(80)]
        wf = walk_forward(items, train_size=0.5, step=0.2)
        for f in wf.folds:
            train_set = set(f.train.indices)
            test_set = set(f.test.indices)
            self.assertEqual(train_set & test_set, set())

    def test_train_expands(self):
        items = [Item(decision_bar=i) for i in range(60)]
        wf = walk_forward(items, train_size=0.5, step=0.2)
        prev_train_len = -1
        for f in wf.folds:
            self.assertGreater(len(f.train.indices), prev_train_len)
            prev_train_len = len(f.train.indices)

    def test_chronological(self):
        items = [Item(decision_bar=i) for i in range(60)]
        wf = walk_forward(items, train_size=0.5, step=0.2)
        for f in wf.folds:
            if f.train.indices and f.test.indices:
                self.assertLess(max(f.train.indices), min(f.test.indices))

    def test_purge_removes_last_train_bars(self):
        items = [Item(decision_bar=i) for i in range(100)]
        wf_no_purge = walk_forward(items, train_size=0.5, step=0.2, purge_bars=0)
        wf_purge = walk_forward(items, train_size=0.5, step=0.2, purge_bars=5)
        # With purge, train should be 5 shorter in first fold
        self.assertEqual(len(wf_no_purge.folds[0].train.indices) - len(wf_purge.folds[0].train.indices), 5)

    def test_embargo_shifts_test_start(self):
        items = [Item(decision_bar=i) for i in range(100)]
        wf_no_embargo = walk_forward(items, train_size=0.5, step=0.2, embargo_bars=0)
        wf_embargo = walk_forward(items, train_size=0.5, step=0.2, embargo_bars=3)
        # Test window should start 3 later
        self.assertEqual(wf_embargo.folds[0].test.indices[0] - wf_no_embargo.folds[0].test.indices[0], 3)
        self.assertEqual(len(wf_embargo.folds[0].test.indices), len(wf_no_embargo.folds[0].test.indices) - 3)

    def test_no_lookahead_across_folds(self):
        # Future fold's train should not include earlier test's future
        items = [Item(decision_bar=i) for i in range(100)]
        wf = walk_forward(items, train_size=0.4, step=0.2)
        # All train indices across folds should be prefixes of sorted items, never include indices >= test start of same fold
        for f in wf.folds:
            self.assertTrue(all(t < min(f.test.indices) for t in f.train.indices))
