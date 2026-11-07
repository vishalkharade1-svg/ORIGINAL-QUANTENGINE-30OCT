"""Phase158 regression: the phase19 extension cache is a verified reconstruction.

Background (recorded in reports/PHASE158_HASH_FAILURE_TRIAGE.json):
``data/history/BTCUSDT_1m_phase19_extension.json`` is gitignored by this
project's own packaging contract, so it shipped in no archive from Phase131
through Phase157.  Ten tests depended on it and failed for that reason alone.

The data itself is not lost.  ``data/history/BTCUSDT_1m_oos_topup.json`` is the
later acquisition that was built *on top of* the phase19 extension, and its own
provenance record states the construction explicitly:

* ``identity_authority``: ``phase19 dataset_hash construction``
* ``merge_authority``:    ``dedupe_merge(first-wins, gaps kept)``
* ``prior_received``:     11899 rows of the topup header

The frozen phase19 artifact committed to the extension's content as
``extended_span.dataset_hash``.  That commitment is a cryptographic claim: any
candidate row set whose canonical hash equals it *is* the extension's content,
to within SHA-256 collision resistance.

This file enforces the derivation, so the reconstruction can never silently
drift from the committed data, and it enforces the disclosure, so the file can
never be mistaken for the original bytes.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXT = ROOT / "data" / "history" / "BTCUSDT_1m_phase19_extension.json"
TOPUP = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
P19 = ROOT / "research" / "results" / "phase19_oos_data_extension.json"
GATE_A_END = 1788601440
ROW_KEYS = ["close", "high", "low", "open", "time", "volume"]


def _rows_ascending(dataset: dict) -> list[dict]:
    return sorted(dataset["raw"], key=lambda row: row["time"])


def _canonical_hash(rows: list[dict]) -> str:
    blob = json.dumps(sorted(rows, key=lambda row: row["time"]),
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


class TestExtensionReconstruction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EXT.exists():
            raise unittest.SkipTest(
                "BLOCKED_EVIDENCE: %s is absent and the reconstruction has not "
                "been applied in this tree" % EXT.name)
        cls.ext = json.loads(EXT.read_text(encoding="utf-8"))
        cls.topup = json.loads(TOPUP.read_text(encoding="utf-8"))
        cls.p19 = json.loads(P19.read_text(encoding="utf-8"))
        cls.span = cls.p19["extended_span"]
        cls.rows = _rows_ascending(cls.ext)
        cls.topup_rows = _rows_ascending(cls.topup)

    def test_content_matches_the_frozen_commitment(self):
        """The reconstructed content must hash to the value the artifact froze."""
        self.assertEqual(_canonical_hash(self.rows), self.span["dataset_hash"])

    def test_rows_are_the_documented_prefix_of_the_topup(self):
        """Verifiable derivation: exactly prior_received leading topup rows.

        The stored topup array is NOT itself time-sorted (it is a raw merge),
        so "leading" is well-defined only in ascending time order -- the same
        qualification the reconstruction disclosure states.  Asserting the
        raw array's order here keeps the sort from being an untested accident.
        """
        n = len(self.rows)
        self.assertEqual(n, self.span["bars"])
        self.assertEqual(n, self.topup["prior_received"])
        self.assertNotEqual(
            self.topup["raw"], self.topup_rows,
            "the stored topup array is time-sorted after all; the ordering "
            "qualification in the disclosure and the derivation must be "
            "re-checked")
        self.assertEqual(self.rows, self.topup_rows[:n])

    def test_span_and_count_match_the_frozen_artifact(self):
        self.assertEqual(self.rows[0]["time"], self.span["start"])
        self.assertEqual(self.rows[-1]["time"], self.span["end"])
        self.assertEqual(len(self.rows), self.span["bars"])
        self.assertEqual(len(self.ext["raw"]), self.span["bars"])

    def test_no_discovery_contamination(self):
        """Every bar is strictly after the gate boundary the artifact records."""
        times = [row["time"] for row in self.rows]
        self.assertTrue(all(t > GATE_A_END for t in times),
                        "a bar at or before the gate boundary would re-introduce "
                        "discovery data")
        self.assertEqual(len(set(times)), len(times), "duplicate timestamps")
        self.assertEqual(times, sorted(times), "rows must be time ordered")

    def test_rows_carry_no_venue_identity(self):
        self.assertEqual(sorted({tuple(sorted(r.keys())) for r in self.rows}),
                         [tuple(ROW_KEYS)])

    def test_reconstruction_is_disclosed_in_the_file(self):
        """A reader must be able to tell this is verified content, not original bytes."""
        block = self.ext.get("reconstruction")
        self.assertIsInstance(block, dict, "missing reconstruction disclosure")
        self.assertEqual(block["phase"], 158)
        self.assertIn("RECONSTRUCTED", block["status"])
        for key in ("why", "how", "verified_by", "not_verified"):
            self.assertTrue(block.get(key), "reconstruction.%s must be stated" % key)
        self.assertIn(self.span["dataset_hash"], block["verified_by"],
                      "the disclosure must name the commitment that verifies it")

    def test_topup_identity_is_unaffected(self):
        """The reconstruction reads the topup; it must not have altered it."""
        self.assertEqual(_canonical_hash(self.topup_rows),
                         self.topup["dataset_identity"])


if __name__ == "__main__":
    unittest.main()
