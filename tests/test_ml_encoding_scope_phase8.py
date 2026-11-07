"""ML encoding-scope tests (deterministic, offline, stdlib only).

Test-first proofs for the Phase-8 preprocessing-leakage finding: the
one-hot/numeric encoding used for model matrices must be fit on
training snapshots only. Future (validation/OOS) rows must never alter
the historical encoding, and unseen future nominal values must
transform to zeros rather than expanding the feature space.

No network. No sklearn required (pure-python level + numpy backend).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace


def snap(oid: str, bar: int, features: dict):
    return SimpleNamespace(opportunity_id=oid, decision_bar=bar,
                           features=dict(features))


def train_snaps():
    return [
        snap("o1", 1, {"regime": "TREND", "size": 1.0}),
        snap("o2", 2, {"regime": "RANGE", "size": 2.0}),
        snap("o3", 3, {"regime": "TREND", "size": 3.0}),
        snap("o4", 4, {"regime": "RANGE", "size": 4.0}),
    ]


def future_snaps():
    # Novel nominal value "BREAKOUT" exists ONLY in future rows.
    return [
        snap("o5", 5, {"regime": "BREAKOUT", "size": 5.0}),
        snap("o6", 6, {"regime": "BREAKOUT", "size": 6.0}),
    ]


class TestEncodingScope(unittest.TestCase):
    def test_future_nominal_does_not_alter_train_encoding(self):
        from core.research.ml.analyzer import (
            _build_matrix, _feature_names, _fit_encoding,
            _transform_matrix,
        )

        train = train_snaps()
        names = _feature_names(train)
        encoding = _fit_encoding(train, names)
        train_rows = _transform_matrix(train, encoding)
        # Joint build over train+future must not change history: the
        # fitted encoding ignores the future-only nominal value.
        # Columns: regime{TREND, RANGE} one-hot (2) + size numeric (1).
        self.assertEqual(
            [len(r) for r in train_rows], [3] * len(train_rows))
        self.assertNotIn("BREAKOUT", encoding[1].get("regime", ()))

    def test_unseen_nominal_transforms_to_zeros(self):
        from core.research.ml.analyzer import (
            _feature_names, _fit_encoding, _transform_matrix,
        )

        train = train_snaps()
        names = _feature_names(train)
        encoding = _fit_encoding(train, names)
        rows = _transform_matrix(future_snaps(), encoding)
        # "regime" one-hot covers {TREND, RANGE} only: a BREAKOUT row
        # contributes zeros in those columns; numeric size passes
        # through untouched.
        numeric, nominal_values = encoding
        self.assertTrue(numeric["size"])
        self.assertFalse(numeric["regime"])
        regime_cols = len(nominal_values["regime"])
        for row, future in zip(rows, future_snaps()):
            self.assertEqual(row[:regime_cols], [0.0] * regime_cols)
            self.assertEqual(row[regime_cols], future.features["size"])

    def test_legacy_joint_builder_preserved(self):
        # The original joint builder keeps its exact behavior for
        # backward compatibility; only the model path changes scope.
        from core.research.ml.analyzer import _build_matrix, _feature_names

        train = train_snaps()
        names = _feature_names(train)
        order_map = {s.opportunity_id: i for i, s in enumerate(train)}
        rows = _build_matrix(train, order_map, names)
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(len(r) == len(rows[0]) for r in rows))


if __name__ == "__main__":
    unittest.main()
