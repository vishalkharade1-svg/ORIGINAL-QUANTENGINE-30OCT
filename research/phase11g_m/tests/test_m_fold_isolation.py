"""11G-M fold isolation (MUT-M10): L folds re-validated read-only; M has none."""

import json
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import validation as V  # noqa: E402

LRES = BASE_DIR / "research" / "phase11g_l" / "results"
MDIR = BASE_DIR / "research" / "phase11g_m"

FOLDS = [
    {"fold": 0, "train_start": 0, "train_end": 300,
     "purge_start": 300, "purge_end": 450,
     "embargo_start": 450, "embargo_end": 475,
     "test_start": 475, "test_end": 775},
    {"fold": 1, "train_start": 0, "train_end": 600,
     "purge_start": 600, "purge_end": 750,
     "embargo_start": 750, "embargo_end": 775,
     "test_start": 775, "test_end": 1075},
    {"fold": 2, "train_start": 0, "train_end": 900,
     "purge_start": 900, "purge_end": 1050,
     "embargo_start": 1050, "embargo_end": 1075,
     "test_start": 1075, "test_end": 1375},
]


class TestFoldIsolation(unittest.TestCase):
    def test_l_fold_geometry_pinned(self):
        fr = json.loads((LRES / "fold_results.json").read_text())
        geos = {}
        for v in fr.values():
            geos.setdefault(v["fold"], v["geometry"])
        self.assertEqual([geos[k] for k in (0, 1, 2)], FOLDS)
        self.assertEqual(V.validate_folds(FOLDS), [])
        self.assertEqual(V.validate_expanding(FOLDS), [])

    def test_rolling_mutant_trips_expanding(self):
        mutant = [dict(f, train_start=f["fold"] * 300) for f in FOLDS]
        errs = V.validate_expanding(mutant)
        self.assertTrue(any("rolling" in e or "train_start" in e for e in errs))

    def test_gap_shrink_detected(self):
        gaps = [f["test_start"] - f["train_end"] for f in FOLDS]
        self.assertEqual(gaps, [175, 175, 175])

    def test_m_created_no_folds(self):
        hits = [p for p in MDIR.rglob("*")
                if p.is_file() and "tests" not in p.parts
                and ("fold" in p.name.lower() or "folds" in p.name.lower())]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
