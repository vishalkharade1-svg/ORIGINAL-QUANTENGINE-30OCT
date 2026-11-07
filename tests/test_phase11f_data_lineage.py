"""Phase 11F-1 data-lineage tests (D3 sealed, metadata only).

Never loads D3 candle arrays. All checks operate on tier
metadata, path guards, and recorded hashes.
"""

import hashlib
import json
import unittest
from pathlib import Path

from research.phase11f import contracts as K
from research.phase11f import datasets as D

RESEARCH = Path("research/phase11f")


def _canonical(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class TestDatasetContract(unittest.TestCase):
    def test_tiers_and_contamination_labels(self):
        doc = json.loads((RESEARCH / "datasets.json").read_text())
        self.assertEqual(doc["universe"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(doc["timeframe"], "1m")
        for tier in ("D0_development", "D1_insample", "D2_validation", "D3_holdout"):
            self.assertIn(tier, doc["tiers"])
        self.assertIn("UNTOUCHED", doc["tiers"]["D3_holdout"]["role"])
        self.assertIn("DATA_UNAVAILABLE", doc["orderflow"])
        self.assertIn("PROXY_FEATURE", doc["orderflow"])

    def test_lineage_validator_passes(self):
        self.assertEqual(D.validate_lineage(), [])

    def test_discovery_excludes_holdout_and_validation(self):
        disc = D.discovery_files()
        self.assertTrue(len(disc) > 0)
        for p in disc:
            self.assertNotIn("D3", p)
            self.assertNotIn("oos_fresh", p)
            D.assert_not_holdout(p)

    def test_holdout_sealed(self):
        for h in D.holdout_files():
            self.assertEqual(h["status"], "SEALED_HOLDOUT")
            self.assertTrue(D.is_sealed_holdout(h["path"]))
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout_candles("research/phase11f/data/universe_D3_BTC.json")

    def test_mutation_d3_contamination_blocked(self):
        # Intentionally introduce a D3 path into discovery: the
        # guard must fail (raise), proving D3 cannot leak silently.
        with self.assertRaises(D.SealedHoldoutError):
            D.assert_not_holdout("research/phase11f/data/universe_D3_ETH.json")
        # restoration: a D1 path passes cleanly.
        D.assert_not_holdout("research/phase11f/data/universe_D1_ETH.json")

    def test_manifest_hashes_match_files(self):
        manifest = json.loads((RESEARCH / "freeze_manifest.json").read_text())
        files = manifest["sha256"]
        for name in ("hypotheses.json", "datasets.json", "candidates.py",
                     "features.py", "fibonacci.py", "contracts.py",
                     "metrics.py", "datasets.py", "harness.py"):
            self.assertIn(name, files)
            actual = hashlib.sha256((RESEARCH / name).read_bytes()).hexdigest()
            self.assertEqual(files[name], actual, "stale hash for %s" % name)


class TestResearchLogIntegrity(unittest.TestCase):
    def test_log_fields_and_hashes(self):
        log = json.loads((RESEARCH / "research_log.json").read_text())
        hyps = json.loads((RESEARCH / "hypotheses.json").read_text())
        ds = json.loads((RESEARCH / "datasets.json").read_text())
        self.assertEqual(len(log["entries"]), 8)
        ds_hash = _canonical(ds)
        self.assertEqual(log["dataset_spec_hash"], ds_hash)
        by_id = {h["hypothesis_id"]: h for h in hyps["hypotheses"]}
        for entry in log["entries"]:
            hid = entry["id"]
            self.assertIn(hid, by_id)
            h = by_id[hid]
            self.assertEqual(entry["hypothesis_hash"], _canonical(h))
            param_spec = {"frozen": h["frozen_parameters"],
                          "allowed": h["allowed_research_parameters"],
                          "forbidden": h["forbidden_optimization_dimensions"]}
            self.assertEqual(entry["parameter_spec_hash"], _canonical(param_spec))
            self.assertEqual(entry["dataset_spec_hash"], ds_hash)
            self.assertIn("registration_timestamp", entry)
            self.assertIn("failure_reason", entry)

    def test_no_research_executed(self):
        # 11F-4 authorized update: the ledger now records the executed
        # preregistered variants ONLY — full plus registered ablations
        # (002:3, 005:2, 007:3, others:1). Anything beyond that is
        # an unregistered variant and fails here.
        allowed_counts = {"H11F-001": 1, "H11F-002": 3, "H11F-003": 1,
                          "H11F-004": 1, "H11F-005": 2, "H11F-006": 1,
                          "H11F-007": 3, "H11F-008": 1}
        log = json.loads((RESEARCH / "research_log.json").read_text())
        for entry in log["entries"]:
            self.assertEqual(entry["variants_tested"], allowed_counts[entry["id"]])
            self.assertIn(entry["status"], ("PASS", "FAIL", "INSUFFICIENT_EVIDENCE"))


if __name__ == "__main__":
    unittest.main()
