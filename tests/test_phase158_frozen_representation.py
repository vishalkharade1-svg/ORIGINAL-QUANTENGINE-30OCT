"""Phase158 regression: frozen artifacts keep their mint-time byte representation.

The Phase158 triage found one dominant mechanical defect class: a line-ending
conversion from LF to CRLF that happened after the artifacts were minted (it is
visible in every archive from Phase131 onward, and the Phase131 packaging
manifest records the already-converted bytes).  Because this project's frozen
records were written by tools that hash *raw bytes*, the conversion broke every
byte-level pin even though no content changed:

* ``research/phase11f/freeze_manifest.json`` pins ten of its eleven inputs by
  the exact SHA-256 of the mint-time bytes.  Restoring LF reproduces every one
  of those pins exactly -- proof that only the representation had changed.
  (``research_log.json`` is a separate, documented 11F-4 exception: its ledger
  was lawfully appended after minting, so its pin is stale for a reason that has
  nothing to do with line endings.)
* ``research/results/phase1{4,5,7,8,9}_*.json`` are declared byte-canonical by
  their own determinism tests: the file on disk must equal
  ``json.dumps(obj, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"``,
  which is LF-terminated.  Restoring LF makes all five byte-canonical again.

This test is the regression guard for that class.  It does not re-pin anything:
it asserts the *already recorded* pins, so re-introducing the conversion fails
loudly instead of quietly invalidating frozen evidence.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PHASE11F = ROOT / "research" / "phase11f"

# The one manifest input whose pin is stale for a documented, unrelated reason:
# the 11F-4 authorised ledger append (see test_manifest_hashes_reproduce).
DOCUMENTED_PIN_EXCEPTION = {
    "research_log.json": (
        "the 11F-4 authorised update lawfully appended result halves to the "
        "research ledger after minting, so its recorded hash is stale "
        "independently of any line-ending question"
    ),
}

CANONICAL_JSON_ARTIFACTS = [
    "research/results/phase14_executable_edge_forensics.json",
    "research/results/phase15_evidence_readiness.json",
    "research/results/phase17_oos_feasibility.json",
    "research/results/phase18_oos_validation.json",
    "research/results/phase19_oos_data_extension.json",
]


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


class TestFrozenRepresentationContract(unittest.TestCase):
    def test_phase11f_inputs_match_their_frozen_manifest_bytes(self):
        manifest = json.loads((PHASE11F / "freeze_manifest.json").read_text(encoding="utf-8"))
        checked = 0
        for name, recorded in sorted(manifest["sha256"].items()):
            if name in DOCUMENTED_PIN_EXCEPTION:
                continue
            path = PHASE11F / name
            with self.subTest(entry=name):
                self.assertTrue(path.exists(), "frozen input %s is missing" % name)
                self.assertEqual(
                    _sha256_bytes(path.read_bytes()), recorded,
                    "frozen input %s no longer matches the bytes its manifest "
                    "pins; the file was changed or its line endings were "
                    "converted after minting" % name)
                checked += 1
        self.assertEqual(checked, 10, "expected ten manifest-pinned frozen inputs")

    def test_documented_pin_exception_is_still_documented(self):
        manifest = json.loads((PHASE11F / "freeze_manifest.json").read_text(encoding="utf-8"))
        for name, reason in DOCUMENTED_PIN_EXCEPTION.items():
            self.assertIn(name, manifest["sha256"], "exception names an unlisted file")
            self.assertTrue(reason.strip())

    def test_canonical_json_artifacts_are_byte_canonical(self):
        for rel in CANONICAL_JSON_ARTIFACTS:
            path = ROOT / rel
            with self.subTest(artifact=rel):
                self.assertTrue(path.exists(), "%s is missing" % rel)
                raw = path.read_bytes()
                obj = json.loads(raw.decode("utf-8"))
                canonical = (json.dumps(obj, indent=2, sort_keys=True,
                                        separators=(",", ": ")) + "\n").encode("utf-8")
                self.assertEqual(
                    raw, canonical,
                    "%s is not byte-canonical; the determinism contract in its "
                    "own test suite requires the exact bytes of "
                    "json.dumps(..., indent=2, sort_keys=True) + newline" % rel)

    def test_frozen_artifacts_carry_no_carriage_returns(self):
        names = [name for name in json.loads(
            (PHASE11F / "freeze_manifest.json").read_text(encoding="utf-8"))["sha256"]
            if name not in DOCUMENTED_PIN_EXCEPTION]
        paths = [PHASE11F / name for name in names]
        paths += [ROOT / rel for rel in CANONICAL_JSON_ARTIFACTS]
        offending = [str(p.relative_to(ROOT)) for p in paths
                     if p.exists() and b"\r\n" in p.read_bytes()]
        self.assertEqual(
            offending, [],
            "these frozen artifacts were re-converted to CRLF, which breaks the "
            "raw-byte pins recorded for them")

    def test_the_one_crlf_file_is_the_documented_append_exception(self):
        """research_log.json is CRLF in the tree and its pin matches neither form.

        It cannot be LF-restored like the other ten: its ledger was lawfully
        appended after minting, so no pin identifies mint-time bytes. It is
        therefore left byte-for-byte as it shipped, and documented rather than
        silently re-pinned or silently normalised."""
        for name in DOCUMENTED_PIN_EXCEPTION:
            path = PHASE11F / name
            with self.subTest(entry=name):
                self.assertTrue(path.exists())
                self.assertIn(b"\r\n", path.read_bytes(),
                              "this test documents a CRLF exception; the file is no "
                              "longer CRLF, so the exception should be removed")


if __name__ == "__main__":
    unittest.main()
