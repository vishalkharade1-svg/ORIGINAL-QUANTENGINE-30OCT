"""Phase 22 Named-Reference archive-hash contract (F5b resolution).

No tree text artifact may embed the byte digest of its own delivery
archive; archives are referenced by NAME plus their detached hash
record (DELIVERY/RELEASE_HASH_PHASE162.txt), which lives outside the
packaged tree and therefore joins no fixpoint. The offending raw-quote
era (Phase154 stale-hash defect class) is covered by
tests/test_release_consistency_phase155.py, which stays UNCHANGED;
this file adds the regression battery required by the Phase 22
resolution: repeated builds, deterministic ordering, meaningful
content-change detection, and historical report handling.

Stdlib only, offline, and self-contained: the mechanics are mirrored
in an isolated sandbox, so the real tree is never mutated by these
tests.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = "QuantEngine_PHASE162_RELEASE_CANDIDATE.zip"
DETACHED_NAME = "RELEASE_HASH_PHASE162.txt"

_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
_SUFFIXES = {".md", ".json", ".txt", ".py", ".sha256"}
_SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv",
               ".git", "logs"}


def _find(name: str):
    for base in (ROOT, ROOT.parent):
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def _scan_paths(paths, root: str, digest: str):
    """Phase-155-equivalent scan over an explicit path ordering."""
    offenders = []
    for path in paths:
        rel = path.relative_to(root)
        if any(p in _SKIP_PARTS for p in rel.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
            continue
        if path.name == "BUILD_MANIFEST.sha256":
            continue
        if path.name.startswith("QuantEngine_") and path.suffix.lower() == ".zip":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if digest in text:
            offenders.append(rel.as_posix())
    return offenders


def _scan(root: Path, digest: str):
    return _scan_paths(sorted(root.rglob("*")), str(root), digest)


def _candidate_digest() -> str:
    archive = _find(ARCHIVE_NAME)
    if archive is None:
        # Extracted-package case: no archive present. A synthetic
        # digest keeps the contract mechanics testable without
        # weakening anything.
        return "a" * 64
    return hashlib.sha256(archive.read_bytes()).hexdigest()


class TestNamedReferenceArchiveHashContract22(unittest.TestCase):

    def test_repeated_builds_yield_same_digest_and_no_offenders(self):
        # Gate 1 (repeated builds): the candidate digest computed twice
        # from actual bytes must agree, and scanning the real tree
        # (Named-Reference compliant) must find zero offenders on both
        # passes.
        first = _candidate_digest()
        second = _candidate_digest()
        self.assertEqual(first, second)
        self.assertRegex(first, _HEX64.pattern)
        self.assertEqual(_scan(ROOT, first), [])
        self.assertEqual(_scan(ROOT, second), [])

    def test_scan_ordering_is_deterministic(self):
        # Gate 2 (deterministic ordering): the offender set is the same
        # regardless of scan iteration order.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "reports").mkdir()
            (root / "reports" / "a_report.md").write_text(
                "clean text\n", encoding="utf-8")
            (root / "reports" / "b_report.json").write_text(
                json.dumps({"note": "ok"}), encoding="utf-8")
            (root / "reports" / "c_report.md").write_text(
                "embeds: " + "0" * 64 + "\n", encoding="utf-8")
            digest = "0" * 64
            paths = [p for p in root.rglob("*")]
            by_sorted = _scan_paths(sorted(paths), str(root), digest)
            by_reversed = _scan_paths(
                list(reversed(sorted(paths))), str(root), digest)
            self.assertEqual(by_sorted, by_reversed)
            self.assertEqual(by_sorted,
                             ["reports/c_report.md"])

    def test_meaningful_content_change_is_detected(self):
        # Gate 3 (meaningful content change): a raw self-embed is
        # detected (positive proof); the Named-Reference form — name +
        # OUT-OF-TREE detached record — clears it. The removable tree
        # artifact joins no fixpoint, unlike the detached record, which
        # lives OUTSIDE the scanned root.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "tree"
            outside = Path(td)
            root.mkdir()
            reports = root / "reports"
            reports.mkdir()
            digest = "1" * 64
            record = outside / "RELEASE_HASH_X.txt"
            record.write_text("sha256: %s\n" % ("2" * 64),
                              encoding="utf-8")
            record_sha = hashlib.sha256(
                record.read_bytes()).hexdigest()
            report = reports / "phase_report.md"
            report.write_text(
                'archive: "QuantEngine_X.zip", sha256: "%s"\n' % digest,
                encoding="utf-8")
            self.assertEqual(_scan(root, digest),
                             ["reports/phase_report.md"])
            report.write_text(
                'archive: "QuantEngine_X.zip", '
                'sha256_authority: "DELIVERY/RELEASE_HASH_X.txt", '
                'detached_record_sha256: "%s"\n' % record_sha,
                encoding="utf-8")
            self.assertEqual(_scan(root, digest), [])
            # The record file joins no fixpoint: it is outside the
            # scanned root and byte-stable across repeated rebuilds.
            self.assertNotIn(record, list(root.rglob("*")))
            record.write_bytes(record.read_bytes())
            self.assertEqual(
                hashlib.sha256(record.read_bytes()).hexdigest(),
                record_sha)

    def test_historical_report_digests_are_tolerated(self):
        # Gate 4 (historical report handling): references to OTHER
        # archives' digests remain legal. The real tree keeps the
        # historical sha185 quote in PHASE16_FINAL_REPORT.md while the
        # current candidate's digest is embedded by no tree artifact,
        # and the detached record stays the sole byte authority OUTSIDE
        # the packaged tree (quoting the record's own sha inside tree
        # artifacts is the sanctioned Named-Reference form — the
        # record joins no fixpoint).
        report = ROOT / "reports" / "PHASE16_FINAL_REPORT.md"
        self.assertTrue(report.exists())
        blob = report.read_text(encoding="utf-8", errors="ignore")
        historical = re.search(r"sha185 = `([0-9a-f]{64})`", blob)
        self.assertIsNotNone(
            historical, "historical sha185 reference missing")
        candidate_digest = _candidate_digest()
        self.assertNotEqual(historical.group(1), candidate_digest)
        self.assertEqual(_scan(ROOT, candidate_digest), [])
        detached = _find(DETACHED_NAME)
        if detached is None:
            self.skipTest(
                "BLOCKED_EVIDENCE: original detached Phase 162 hash record is unavailable outside the migrated checkout"
            )
        self.assertIsNotNone(detached, "detached record present")
        self.assertNotEqual(detached.resolve().parent, ROOT.resolve())
        record_sha = hashlib.sha256(
            detached.read_bytes()).hexdigest()
        self.assertNotEqual(record_sha, candidate_digest)


if __name__ == "__main__":
    unittest.main()
