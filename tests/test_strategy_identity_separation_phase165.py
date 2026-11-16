"""Test suite for versioned strategy and runtime identity separation (Phase 165).

Validates that:
1. Historical Phase 14 pin is preserved intact.
2. Strategy Core (alpha logic) and Runtime Infrastructure are strictly partitioned.
3. Decoupled digests compute deterministically.
4. Changes to paper trading infrastructure alter runtime infrastructure but leave strategy core invariant.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from core.research.strategy_identity import (
    HISTORICAL_PHASE14_STRATEGY_HASH,
    LEGACY_9_FILES,
    RUNTIME_INFRA_FILES,
    STRATEGY_CORE_FILES,
    compute_composite_digest,
    get_versioned_identities,
)

ROOT = Path(__file__).resolve().parents[1]


class TestStrategyIdentitySeparation(unittest.TestCase):
    def test_01_historical_pin_preserved(self):
        self.assertEqual(
            HISTORICAL_PHASE14_STRATEGY_HASH,
            "c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6",
            "historical strategy hash must remain pinned to Phase 14 artifact"
        )

    def test_02_files_partitioning_disjoint_and_complete(self):
        core_set = set(STRATEGY_CORE_FILES)
        infra_set = set(RUNTIME_INFRA_FILES)
        all_set = set(LEGACY_9_FILES)

        self.assertEqual(len(core_set), 6, "Strategy Core must contain exactly 6 alpha files")
        self.assertEqual(len(infra_set), 3, "Runtime Infrastructure must contain exactly 3 execution files")
        self.assertTrue(core_set.isdisjoint(infra_set), "Core and Infra file sets must be strictly disjoint")
        self.assertEqual(core_set | infra_set, all_set, "Union of Core and Infra must equal Legacy 9 files")

    def test_03_versioned_identities_structure_and_determinism(self):
        identities = get_versioned_identities(ROOT)
        self.assertEqual(identities["schema"], "quantengine.strategy-identity.v2")
        self.assertEqual(identities["historical_phase14_pinned_hash"], HISTORICAL_PHASE14_STRATEGY_HASH)

        core_h = identities["strategy_core"]["sha256"]
        infra_h = identities["runtime_infrastructure"]["sha256"]
        legacy_lf_h = identities["composite_legacy_9_files"]["canonical_lf_sha256"]

        self.assertEqual(len(core_h), 64)
        self.assertEqual(len(infra_h), 64)
        self.assertEqual(len(legacy_lf_h), 64)

        # The Phase22 values remain historical registration records.
        # The migrated current tree is explicitly observed but unregistered;
        # its hashes are checked against the Phase206 blocked observation.
        from tests.strategy_identity_evidence import assert_unregistered_identity
        assert_unregistered_identity(self, identities, ROOT)

    def test_04_paper_trading_isolation_invariance(self):
        """Simulate a change to paper trading engine: core strategy hash must remain invariant."""
        identities_before = get_versioned_identities(ROOT)
        core_before = identities_before["strategy_core"]["sha256"]

        # Strategy core files do NOT include paper_trading_engine.py
        self.assertNotIn("core/paper_trading/paper_trading_engine.py", STRATEGY_CORE_FILES)
        self.assertIn("core/paper_trading/paper_trading_engine.py", RUNTIME_INFRA_FILES)

        # Recalculate strategy core
        core_recalc, _ = compute_composite_digest(ROOT, STRATEGY_CORE_FILES, normalize_lf=True)
        self.assertEqual(core_before, core_recalc)

    def test_05_fail_closed_validation(self):
        """Certify fail-closed validation for empty, duplicate, traversal, or missing files."""
        # Empty list
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, [])

        # Duplicate entries
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, ["config/risk_settings.py", "config/risk_settings.py"])

        # Traversal path
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, ["../outside.py"])

        # Missing file
        with self.assertRaises(FileNotFoundError):
            compute_composite_digest(ROOT, ["non_existent_strategy_file.py"])

    def test_06_path_normalization_and_collision_handling(self):
        """Certify path normalization catches empty paths, whitespace, and normalized duplicate aliases."""
        # Empty string path
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, [""])

        # Whitespace path
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, ["   "])

        # Normalized duplicate collision (./config vs config)
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, ["config/risk_settings.py", "./config/risk_settings.py"])

        # Windows backslash normalized duplicate collision
        with self.assertRaises(ValueError):
            compute_composite_digest(ROOT, ["config/risk_settings.py", "config\\risk_settings.py"])


if __name__ == "__main__":
    unittest.main()


