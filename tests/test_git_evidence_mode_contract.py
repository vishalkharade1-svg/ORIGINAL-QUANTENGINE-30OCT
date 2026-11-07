"""Phase158 regression: the Git evidence-mode contract must not be a loophole.

Three things are asserted here, and all three are needed for the contract to
mean anything:

1. **Mode detection is real.**  ``detect_mode`` must classify a tree and its own
   evidence must agree with the classification.
2. **The guards are wired in and declared.**  Every ``require_git_fact`` call
   found in the test suite must have a matching fact declared in
   ``reports/PHASE161_GIT_EVIDENCE_STATUS.json``, every declared fact must be
   used, and every guarded method must call the guard as its *first* executable
   statement so no git command can run before it (which is what produced the
   silent vacuous passes recorded in the status file).
3. **The guard steps aside in a genuine checkout.**  A throwaway repository is
   created in a temporary directory and the guard is shown to return instead of
   skipping there.  Without this positive control, "archive mode" could be used
   to disable checks arbitrarily.

It also asserts the gate stays blocked in archive mode, so a passing run here
can never be read as proof of Git ancestry.

This module deliberately reaches the contract through the ``evidence_mode``
module object rather than importing ``require_git_fact`` by name: the checks
above locate guards by scanning for *direct* calls to that name, and this file
must not appear to be part of the gated suite.
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:  # package import when pytest loads tests.test_*
    from tests import evidence_mode as em
except ImportError:  # direct execution of this file
    import evidence_mode as em  # type: ignore

TEST_FILES = sorted((ROOT / "tests").glob("test_*.py"))
GUARD_NAME = "require_git_fact"


class _FakeCase:
    """Records the skip reason instead of raising, for control tests.

    Deliberately NOT a ``unittest.TestCase``: pytest collects every TestCase
    subclass in a test module regardless of the ``python_classes`` pattern, and
    this helper is not a test.  It only needs the ``skipTest`` protocol that
    ``require_git_fact`` calls.
    """

    #: None until the guard skips; lets the control assert "did not skip".
    skipped_with = None

    def skipTest(self, reason=None):  # noqa: D102 - mirrors unittest's protocol
        self.skipped_with = reason
        raise unittest.SkipTest(reason)


def _guard_calls() -> dict[str, tuple[str, int]]:
    """Map guard fact id -> (file, line) for every direct require_git_fact call."""
    found: dict[str, tuple[str, int]] = {}
    for path in TEST_FILES:
        src = path.read_text(encoding="utf-8")
        if GUARD_NAME not in src:
            continue
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id != GUARD_NAME:
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                continue
            fact_id = node.args[1].value
            if isinstance(fact_id, str):
                found[fact_id] = (path.name, node.lineno)
    return found


def _first_statement_facts() -> set[str]:
    """Facts whose guard is the first executable statement of its method body."""
    ok: set[str] = set()
    for path in TEST_FILES:
        src = path.read_text(encoding="utf-8")
        if GUARD_NAME not in src:
            continue
        tree = ast.parse(src)
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for item in cls.body:
                if not isinstance(item, ast.FunctionDef) or not item.name.startswith("test_"):
                    continue
                body = list(item.body)
                if body and isinstance(body[0], ast.Expr) and isinstance(
                        getattr(body[0], "value", None), ast.Constant):
                    body = body[1:]  # a docstring executes nothing
                if not body:
                    continue
                first = body[0]
                if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Call):
                    continue
                func = first.value.func
                if (isinstance(func, ast.Name) and func.id == GUARD_NAME
                        and len(first.value.args) >= 2):
                    arg = first.value.args[1]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        ok.add(arg.value)
    return ok


def _make_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    (path / "f.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "f.txt"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.email=t@example.com",
                    "-c", "user.name=t", "commit", "-q", "-m", "x"],
                   check=True, capture_output=True)


class TestGitEvidenceModeDetection(unittest.TestCase):
    def test_mode_is_one_of_two_values_with_consistent_evidence(self):
        mode, evidence = em.detect_mode(ROOT)
        self.assertIn(mode, (em.MODE_GIT_CHECKOUT, em.MODE_SOURCE_ARCHIVE))
        self.assertIn("root", evidence)
        probe = evidence.get("rev_parse_is_inside_work_tree")
        if mode == em.MODE_SOURCE_ARCHIVE:
            if probe is not None:  # git executable was available
                self.assertTrue(
                    probe["returncode"] != 0 or probe["stdout"] != "true",
                    "source-archive mode but rev-parse reported a work tree: %s" % probe)
        else:
            self.assertEqual(probe["returncode"], 0)
            self.assertEqual(probe["stdout"], "true")
            head = evidence["head"]
            self.assertEqual(head["returncode"], 0)
            self.assertEqual(len(head["stdout"]), 40, head["stdout"])

    def test_recorded_mode_is_consistent_with_record(self):
        doc = em.status_document()
        self.assertIsNotNone(doc, "missing %s" % em.STATUS_FILE.name)
        assert doc is not None
        self.assertIn(doc["mode"], (em.MODE_GIT_CHECKOUT, em.MODE_SOURCE_ARCHIVE))
        if doc["mode"] == em.MODE_SOURCE_ARCHIVE:
            self.assertEqual(doc["gate"]["status"], em.STATUS_BLOCKED)
            self.assertIs(doc["gate"]["satisfied"], False)
            bad = [f["id"] for f in doc["facts"] if f["status"] != em.STATUS_BLOCKED]
            self.assertEqual(bad, [], "facts not declared blocked in archive mode")
        else:
            unverified = [f["id"] for f in doc["facts"] if f["status"] != "VERIFIED"]
            self.assertEqual(unverified, [], "checkout mode must record verified facts")

    def test_every_guard_call_is_declared_and_every_declaration_is_used(self):
        doc = em.status_document()
        self.assertIsNotNone(doc)
        assert doc is not None
        declared = {f["id"] for f in doc["facts"]}
        used = set(_guard_calls())
        self.assertGreater(len(used), 0, "no guards found; the scan is broken")
        self.assertEqual(sorted(used - declared), [],
                         "guard call without a declared fact")
        self.assertEqual(sorted(declared - used), [],
                         "declared fact without a guard call")

    def test_guards_precede_any_git_invocation(self):
        used = set(_guard_calls())
        first = _first_statement_facts()
        self.assertEqual(sorted(used - first), [],
                         "these guards are not the first statement of their method, "
                         "so a git command could run before them")

    def test_record_declares_the_vacuous_pass_finding(self):
        doc = em.status_document()
        self.assertIsNotNone(doc)
        assert doc is not None
        vac = doc.get("vacuous_pass_finding")
        self.assertIsNotNone(vac, "the vacuous-pass finding must be recorded")
        self.assertGreater(vac["count"], 0)
        modes = {f["phase157_observation"] for f in doc["facts"]}
        self.assertIn("PASSED_VACUOUSLY", modes)


class TestGuardBehaviourControls(unittest.TestCase):
    """Positive and negative controls for the guard itself."""

    def setUp(self):
        if not em.git_available():
            self.skipTest("git executable unavailable; controls cannot run")

    def test_detect_mode_sees_a_real_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_repo(tmp_path)
            mode, evidence = em.detect_mode(tmp_path)
            self.assertEqual(mode, em.MODE_GIT_CHECKOUT, evidence)

    def test_guard_does_not_skip_in_a_real_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_repo(tmp_path)
            original = em.ROOT
            em.ROOT = tmp_path
            try:
                case = _FakeCase()
                em.require_git_fact(case, "positive.control.fact")
                self.assertIsNone(case.skipped_with,
                                  "guard skipped inside a genuine checkout")
            finally:
                em.ROOT = original

    def test_guard_skips_with_blocked_evidence_in_this_tree(self):
        """The release tree is a source archive, so the guard must declare blocked.

        If this tree *is* a genuine checkout (a developer machine), the negative
        path cannot be exercised here and this test says so rather than
        pretending the contract was checked.
        """
        mode, _ = em.detect_mode(ROOT)
        if mode != em.MODE_SOURCE_ARCHIVE:
            self.skipTest("this tree is a genuine checkout (%s); the archive-mode "
                          "path is exercised against the release archive" % mode)
        case = _FakeCase()
        with self.assertRaises(unittest.SkipTest) as ctx:
            em.require_git_fact(case, "archive.mode.control.fact")
        message = str(ctx.exception)
        self.assertIn("BLOCKED_EVIDENCE", message)
        self.assertIn("archive.mode.control.fact", message)
        self.assertEqual(case.skipped_with, message)


if __name__ == "__main__":
    unittest.main()
