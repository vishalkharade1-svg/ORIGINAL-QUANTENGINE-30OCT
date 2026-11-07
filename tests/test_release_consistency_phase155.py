"""Release internal-consistency contract (offline, stdlib only).

Guards the defect class found in Phase154's own output:

  * the worktree must verify clean against BUILD_MANIFEST.sha256;
  * no packaged text artifact may embed the archive's own SHA-256
    (self-reference is unprovable and goes stale the moment the tree
    changes -- exactly how a stale hash shipped in Phase154);
  * the detached hash record must agree with the actual archive bytes.

The archive and its detached record live *outside* the packaged tree, so
this file must behave correctly in two places: the build tree (archive
present -> full cross-check) and an extracted package (no archive -> the
invariant becomes "there must be no orphaned detached record either").
Neither branch is a skip; each asserts a real invariant.

The constants name the CURRENT candidate, so the contract always guards
the artifact being shipped rather than a historical one. They advance
with each rebuild (Phase155 -> ... -> Phase161); superseded archives stay on
disk as historical evidence and are deliberately no longer cross-checked
here, exactly as Phase132/149/153/154 already are.

Phase158 note: the detached record now sits beside the archive in the
delivery directory (ROOT.parent), which is what ``_find`` already covers.
The Phase157 detached record still lives there too, next to its own
historical archive, and is not cross-checked by this file.

Phase161 note: the environment-adoption cycle advances the constants to
this candidate as part of its record set -- routine since Phase160
repaired the lag (REP-160-03 in reports/PHASE160_HARDENING.json). At this
writing the Phase160 deliverable is preserved in ../_phase160_superseded/.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = "QuantEngine_PHASE162_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE162.txt"

_SPEC = importlib.util.spec_from_file_location(
    "phase155_manifest", ROOT / "scripts" / "generate_manifest.py")
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)

_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def _find(name: str):
    for base in (ROOT, ROOT.parent):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


class TestReleaseConsistency155(unittest.TestCase):
    def test_worktree_verifies_against_manifest(self):
        problems = _MOD.verify(ROOT, ROOT / "BUILD_MANIFEST.sha256")
        self.assertEqual(problems, [], problems)

    def test_gates_files_do_not_embed_archive_hash(self):
        for rel in ("reports/PHASE162_RELEASE_GATES.json",
                    "reports/PHASE161_RELEASE_GATES.json",
                    "reports/PHASE160_RELEASE_GATES.json",
                    "reports/PHASE159_RELEASE_GATES.json",
                    "reports/PHASE158_RELEASE_GATES.json",
                    "reports/PHASE157_RELEASE_GATES.json",
                    "reports/PHASE156_RELEASE_GATES.json",
                    "reports/PHASE155_RELEASE_GATES.json",
                    "reports/PHASE154_RELEASE_GATES.json"):
            path = ROOT / rel
            if not path.exists():
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            blob = json.dumps(doc.get("final_archive", {}))
            self.assertIsNone(_HEX64.search(blob),
                              "%s embeds a hash: %s" % (rel, blob))

    def test_archive_and_detached_record_agree(self):
        archive = _find(ARCHIVE_NAME)
        detached = _find(DETACHED_NAME)
        if archive is None:
            # Extracted-package case: no archive here, so a detached hash
            # record would be an orphan. Absence of both is the invariant.
            self.assertIsNone(detached, "orphan detached hash record")
            return
        self.assertIsNotNone(detached, "archive present without detached record")
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        recorded = _HEX64.search(detached.read_text(encoding="utf-8"))
        self.assertIsNotNone(recorded, "no sha256 in detached record")
        self.assertEqual(recorded.group(0), actual,
                         "detached record disagrees with archive bytes")

    def test_no_text_artifact_embeds_own_archive_hash(self):
        archive = _find(ARCHIVE_NAME)
        if archive is None:
            return  # no archive in this tree; nothing to self-reference
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        offenders = []
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT)
            if any(p in {"__pycache__", ".pytest_cache", ".venv", "venv",
                         ".git", "logs"} for p in rel.parts):
                continue
            if any(p in _MOD.SKIP_PARTS for p in rel.parts) or rel.name in _MOD.SKIP_ROOT_NAMES:
                continue
            if not path.is_file() or path.suffix.lower() not in {
                    ".md", ".json", ".txt", ".py", ".sha256"}:
                continue
            if path.name == "BUILD_MANIFEST.sha256":
                continue
            if path.name.startswith("QuantEngine_") and path.suffix.lower() == ".zip":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if actual in text:
                offenders.append(rel.as_posix())
        self.assertEqual(offenders, [],
                         "artifact embeds its own archive hash: %s" % offenders)


if __name__ == "__main__":
    unittest.main()
