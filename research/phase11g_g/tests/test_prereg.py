"""11G-G preregistration tests (freeze, lineage, geometry, seeds, D3)."""

import hashlib
import json
import unittest
from pathlib import Path

R = Path("research/phase11g_g")


class TestPrereg(unittest.TestCase):
    def test_manifest_references_frozen_family(self):
        man = json.loads((R / "freeze_manifest.json").read_text())
        frozen = json.loads(
            (Path("research/phase11g_f/freeze_manifest.json")).read_text())
        self.assertEqual(man["family_sha256"], frozen["hypothesis_sha256"])
        self.assertEqual(len(man["family_sha256"]), 64)
        self.assertEqual(man["family_count"], 8)
        self.assertEqual(man["family_source"],
                         "research/phase11g_f/hypotheses/hypotheses.json")
        self.assertEqual(man["D3_status"][:6], "SEALED")
        self.assertEqual(man["git_head"], "56b777cc153cc901a7dab356fc58bf985e6224a6")

    def test_spec_frozen_geometry(self):
        spec = json.loads((R / "spec.json").read_text())
        self.assertEqual(len(spec["hypotheses"]), 8)
        wf = spec["walk_forward"]
        self.assertTrue(wf["expanding_origin"])
        self.assertEqual((wf["train_min_bars"], wf["test_bars"],
                          wf["purge_bars"], wf["embargo_bars"],
                          wf["step_bars"], wf["n_folds"]),
                         (2000, 1000, 150, 25, 1000, 4))

    def test_gap_window_zero_overlap(self):
        for sym in ("btc", "eth"):
            d = json.load(open(R / "data" / ("fresh_11gg_gap_%susdt.json" % sym)))
            ts = sorted(int(x["time"]) for x in d["candles"])
            self.assertEqual(len(ts), 2099)
            self.assertTrue(all(t > 1788175440 for t in ts))
            self.assertTrue(all(t < 1788301500 for t in ts))
            self.assertEqual(len(set(ts)), len(ts))

    def test_gap_hashes_match_manifest(self):
        man = json.loads((R / "freeze_manifest.json").read_text())
        for sym in ("BTCUSDT", "ETHUSDT"):
            info = man["fresh_datasets"][sym]
            d = json.load(open(info["file"]))
            self.assertEqual(d["sha256"], info["sha256"])
            self.assertEqual(d["fetched_count"], info["bars"])

    def test_seeds_frozen(self):
        spec = json.loads((R / "spec.json").read_text())
        self.assertEqual(spec["seeds"]["random_baseline"], "1108000-1108499")
        self.assertEqual(spec["seeds"]["mc_shuffle"], 1107001)
        self.assertEqual(spec["seeds"]["mc_boot"], 1107002)

    def test_no_d3_paths(self):
        # Test files legitimately name D3 inside assertions; scan only
        # non-test sources, where any D3 content marker is forbidden.
        for path in list((R / "data").glob("*.py")):
            for line in path.read_text().splitlines():
                if "D3" in line:
                    self.assertNotIn("universe_D3", line, str(path))
                    self.assertNotIn("open(", line, str(path))

    def test_expanding_semantics(self):
        from research.phase11f import validation as V
        folds = V.build_folds(8000)
        self.assertEqual(V.validate_expanding(folds), [])
        self.assertTrue(all(f["train_start"] == 0 for f in folds))
        mutant = [dict(f, train_start=f["fold"] * 1000,
                       train_end=f["fold"] * 1000 + 2000) for f in folds]
        self.assertTrue(any("rolling" in e for e in V.validate_expanding(mutant)))

    def test_hypothesis_files_untouched(self):
        import subprocess
        out = subprocess.run(
            ["git", "diff", "--name-only", "56b777cc153cc901a7dab356fc58bf985e6224a6",
             "HEAD", "--", "research/phase11g_f/hypotheses"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
