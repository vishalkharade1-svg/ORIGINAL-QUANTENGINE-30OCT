"""Phase158 regression: the build manifest must be complete, exact, deterministic.

``BUILD_MANIFEST.sha256`` is the release's file-level integrity record: it is
what a recipient checks after extraction.  It is only meaningful if it (a)
covers every regular file that ships, (b) hashes the bytes that actually ship,
(c) contains no duplicate or malformed lines, and (d) reproduces byte-for-byte
when regenerated.  Anything else leaves a hole an auditor cannot see through.

The negative controls at the end run against throwaway trees and prove the
verifier really reports each failure mode -- a verifier that cannot fail is not
a verifier.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_manifest.py"

_spec = importlib.util.spec_from_file_location("generate_manifest_contract", SCRIPT)
gm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gm)

MANIFEST = ROOT / "BUILD_MANIFEST.sha256"

REQUIRED_COVERAGE_PREFIXES = [
    "tests/",
    "scripts/",
    "config/",
    "core/",
    "research/captures/",
    "data/history/",
    "docs/",
]

EXCLUDED_PATH_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", ".git", "logs",
                       "_phase154_extract", ".kilo"}
EXCLUDED_NAMES = {".env", ".env.test", ".env.local"}


def _entries(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, rel = line.partition("  ")
        out.append((digest.strip(), rel.strip()))
    return out


class TestManifestCompleteness(unittest.TestCase):
    def setUp(self):
        self.text = MANIFEST.read_text(encoding="utf-8")
        self.entries = _entries(self.text)
        self.listed = [rel for _, rel in self.entries]

    def test_manifest_covers_every_packaged_file_exactly_once(self):
        actual = gm.package_files(ROOT)
        duplicates = sorted({rel for rel in self.listed if self.listed.count(rel) > 1})
        self.assertEqual(duplicates, [], "duplicate manifest paths")
        self.assertEqual(sorted(set(self.listed)), sorted(set(actual)),
                         "manifest does not cover exactly the packaged files")
        self.assertEqual(len(self.listed), len(actual),
                         "manifest has duplicate lines for packaged files")

    def test_every_listed_hash_matches_the_file_bytes(self):
        mismatched = [rel for digest, rel in self.entries
                      if (ROOT / rel).exists() and gm.digest(ROOT, rel) != digest]
        missing = [rel for _, rel in self.entries if not (ROOT / rel).exists()]
        self.assertEqual(missing, [], "manifest lists files that do not exist")
        self.assertEqual(mismatched, [], "manifest hashes do not match the bytes")

    def test_manifest_reproduces_byte_for_byte(self):
        self.assertEqual(gm.generate(ROOT), self.text,
                         "regenerating the manifest does not reproduce it exactly; "
                         "either a file changed after the manifest was written or "
                         "generation is not deterministic")
        blob = MANIFEST.read_bytes()
        self.assertEqual(blob, gm.generate(ROOT).encode("utf-8"),
                         "the manifest file's *bytes* must equal a fresh "
                         "generation: a platform newline translation makes a "
                         "byte-for-byte audit fail on platforms with other "
                         "newline conventions (the audit's F-03)")
        self.assertNotIn(b"\r", blob, "the manifest must be LF-only")

    def test_generate_stdout_is_byte_identical(self):
        """The auditor's own reproduction (`generate > file` + diff) must match.

        A text-mode stdout translated "\\n" to CRLF on Windows, so a captured
        regeneration differed from the shipped file even though both were
        "generated".  The script now writes UTF-8 bytes to stdout.buffer.
        """
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", "."],
            cwd=str(ROOT), capture_output=True, check=True)
        self.assertEqual(completed.stdout, MANIFEST.read_bytes(),
                         "`generate_manifest.py > file` must reproduce the "
                         "manifest's bytes exactly")

    def test_builder_packs_an_lf_byte_reproducible_manifest(self):
        """scripts/build_release.py must pack the same bytes this test checks.

        The builder regenerates the manifest itself at pack time, in text mode:
        a Windows build then shipped a CRLF manifest that a platform using LF
        conventions could not reproduce byte-for-byte (the audit's F-03).  This
        runs the real builder against a throwaway tree and reads the manifest
        member out of the archive it produced.
        """
        builder = ROOT / "scripts" / "build_release.py"
        with tempfile.TemporaryDirectory() as tmp, \
                tempfile.TemporaryDirectory() as out_tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copy2(SCRIPT, root / "scripts" / SCRIPT.name)
            shutil.copy2(builder, root / "scripts" / builder.name)
            (root / "a.txt").write_bytes(b"alpha\n")
            (root / "b.txt").write_bytes(b"beta\r\n")
            output = Path(out_tmp) / "out.zip"
            subprocess.run(
                [sys.executable, str(root / "scripts" / builder.name),
                 "--root", str(root), "--output", str(output)],
                capture_output=True, check=True, cwd=str(root))
            with zipfile.ZipFile(output) as archive:
                packed = archive.read(gm.MANIFEST_NAME)
            self.assertNotIn(b"\r", packed,
                             "the builder must pack an LF-only manifest")
            self.assertEqual(packed, gm.generate(root).encode("utf-8"),
                             "the packed manifest must equal a fresh generation")

    def test_verify_reports_no_problems(self):
        self.assertEqual(gm.verify(ROOT, MANIFEST), [])

    def test_manifest_excludes_itself_and_only_documented_categories(self):
        self.assertNotIn(gm.MANIFEST_NAME, self.listed,
                         "the manifest must not list itself")
        offences = []
        for rel in self.listed:
            parts = Path(rel).parts
            if any(part in EXCLUDED_PATH_PARTS for part in parts):
                offences.append(("excluded-part", rel))
            if Path(rel).name in EXCLUDED_NAMES:
                offences.append(("secret-name", rel))
            if Path(rel).suffix.lower() in {".pyc", ".pyo"}:
                offences.append(("bytecode", rel))
            if Path(rel).name.startswith("QuantEngine_") and Path(rel).suffix.lower() == ".zip":
                offences.append(("prior-archive", rel))
        self.assertEqual(offences, [], "manifest covers paths that must not ship")

    def test_required_categories_are_covered(self):
        for prefix in REQUIRED_COVERAGE_PREFIXES:
            with self.subTest(prefix=prefix):
                count = sum(1 for rel in self.listed if rel.startswith(prefix))
                self.assertGreater(count, 0, "no manifest entries under %s" % prefix)

    def test_research_evidence_archives_are_covered(self):
        """Nested research evidence ZIPs are covered; prior build ZIPs are not."""
        nested = [rel for rel in self.listed if rel.lower().endswith(".zip")]
        self.assertTrue(nested, "research evidence ZIPs must be covered by the manifest")
        for rel in nested:
            self.assertTrue(rel.startswith("research/"),
                            "only research evidence archives may be covered: %s" % rel)


class TestManifestVerifierDetectsFailures(unittest.TestCase):
    """Negative controls: each failure mode must be reported, not tolerated."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "a.txt").write_text("alpha\n", encoding="utf-8")
        (self.root / "b.txt").write_text("beta\n", encoding="utf-8")
        (self.root / gm.MANIFEST_NAME).write_text(gm.generate(self.root), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_tree_verifies(self):
        self.assertEqual(gm.verify(self.root, self.root / gm.MANIFEST_NAME), [])

    def test_wrong_hash_is_detected(self):
        (self.root / "b.txt").write_text("tampered\n", encoding="utf-8")
        problems = gm.verify(self.root, self.root / gm.MANIFEST_NAME)
        self.assertIn("mismatch:b.txt", problems)

    def test_missing_file_is_detected(self):
        (self.root / "b.txt").unlink()
        problems = gm.verify(self.root, self.root / gm.MANIFEST_NAME)
        # Phase159: the label must say exactly what happened.  "b.txt" is in
        # the manifest and absent from disk -> "missing:", never the inverted
        # "manifest-extra:" wording (r2 self-audit observation).
        self.assertIn("missing:b.txt", problems)
        self.assertFalse(
            any(p.startswith("manifest-extra:") for p in problems),
            "the inverted manifest-extra label must not be produced: %s" % problems)

    def test_extra_file_is_detected(self):
        (self.root / "c.txt").write_text("gamma\n", encoding="utf-8")
        problems = gm.verify(self.root, self.root / gm.MANIFEST_NAME)
        self.assertIn("uncovered:c.txt", problems)

    def test_duplicate_manifest_line_is_detected(self):
        manifest = self.root / gm.MANIFEST_NAME
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text + text.splitlines()[0] + "\n", encoding="utf-8")
        problems = gm.verify(self.root, manifest)
        self.assertTrue(any(p.startswith("duplicate:") for p in problems),
                        "a duplicated path must be reported: %s" % problems)

    def test_malformed_line_is_detected(self):
        manifest = self.root / gm.MANIFEST_NAME
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(text + "not-a-manifest-line\n", encoding="utf-8")
        problems = gm.verify(self.root, manifest)
        self.assertTrue(any(p.startswith("malformed:") for p in problems),
                        "a malformed line must be reported: %s" % problems)

    def test_generation_is_deterministic_and_sorted(self):
        first = gm.generate(self.root)
        second = gm.generate(self.root)
        self.assertEqual(first, second)
        paths = [rel for _, rel in _entries(first)]
        self.assertEqual(paths, sorted(paths), "manifest entries must be sorted")

    def test_kilo_exclusion_cannot_mask_regular_files(self):
        """R-06: .kilo is excluded, but a similar name like kilo.txt is NOT masked."""
        (self.root / ".kilo").mkdir()
        (self.root / ".kilo" / "tooling.txt").write_text("tooling\n", encoding="utf-8")
        self.assertEqual(gm.verify(self.root, self.root / gm.MANIFEST_NAME), [])
        (self.root / "kilo.txt").write_text("regular file\n", encoding="utf-8")
        problems = gm.verify(self.root, self.root / gm.MANIFEST_NAME)
        self.assertIn("uncovered:kilo.txt", problems)


class TestManifestStdoutRobustness(unittest.TestCase):
    """Phase 162 Phase 7: Prove robust stdout writing under BlockingIOError and partial writes."""

    class MockBlockingBuffer:
        def __init__(self, fail_count=2, max_chunk=16):
            self.fail_count = fail_count
            self.max_chunk = max_chunk
            self.written_chunks = []
            self.flushed = False

        def write(self, data):
            if self.fail_count > 0:
                self.fail_count -= 1
                raise BlockingIOError("Simulated pipe buffer full")
            # Write a partial chunk to test partial write handling
            chunk = bytes(data[:self.max_chunk])
            self.written_chunks.append(chunk)
            return len(chunk)

        def flush(self):
            self.flushed = True

    def test_write_buffer_robust_recovers_from_blocking_io_and_partial_writes(self):
        mock_buf = self.MockBlockingBuffer(fail_count=3, max_chunk=32)
        test_payload = b"abcdefghijklmnopqrstuvwxyz0123456789" * 50
        gm._write_buffer_robust(mock_buf, test_payload)
        reconstructed = b"".join(mock_buf.written_chunks)
        self.assertEqual(reconstructed, test_payload,
                         "All bytes must be written completely without corruption or truncation")
        self.assertTrue(mock_buf.flushed, "Buffer must be flushed upon completion")


if __name__ == "__main__":
    unittest.main()
