"""11G-A D3 seal tests (11G-specific; never touches D3 content)."""

import unittest
from pathlib import Path

from research.phase11g import datasets as D

PHASE11G = Path("research/phase11g")


class TestD3Seal(unittest.TestCase):
    def test_blocked_before_io(self):
        with self.assertRaises(D.SealedHoldoutError):
            D.assert_not_holdout("research/phase11f/data/universe_D3_BTC.json")
        with self.assertRaises(D.SealedHoldoutError):
            D.load_holdout()

    def test_counters_zero_read_hash_load(self):
        self.assertEqual(D.D3_ACCESS["read"], 0)
        self.assertEqual(D.D3_ACCESS["hash"], 0)
        self.assertEqual(D.D3_ACCESS["load"], 0)

    def test_no_d3_content_access_in_sources(self):
        for path in list((PHASE11G / "features").glob("*.py")) + \
                   list((PHASE11G / "validation").glob("*.py")) + \
                   [PHASE11G / "datasets.py"]:
            for line in path.read_text().splitlines():
                if "D3" in line:
                    self.assertNotIn("open(", line, path.name)
                    self.assertNotIn("read_text", line, path.name)
                    self.assertNotIn("read_bytes", line, path.name)
                    self.assertNotIn("json.load", line, path.name)

    def test_datasets_metadata_only(self):
        for did in D.all_ids():
            desc = D.describe(did)
            for key in ("dataset_id", "symbol", "timeframe", "start_timestamp",
                        "end_timestamp", "bar_count", "source", "sha256",
                        "data_fields", "measurement_class", "lineage_status"):
                self.assertIn(key, desc)
            self.assertIsNone(desc["sha256"])  # unfilled until Stage B
            self.assertIn("lineage_status", desc)

    def test_content_hash_not_used_by_stage_a(self):
        import pathlib
        for name in pathlib.Path("research/phase11g/tests").glob("test_*.py"):
            if name.name.startswith("test_data_"):
                continue  # 11G-E provenance tests legitimately hash
            if name.name == "test_d3_seal.py":
                continue
            src = name.read_text()
            self.assertNotIn("content_hash", src, name.name)


if __name__ == "__main__":
    unittest.main()
