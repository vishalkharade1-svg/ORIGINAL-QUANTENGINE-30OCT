"""Digest re-certification procedure tests (deterministic, offline).

Pins the procedure's canonical construction and its honest BLOCKED
verdict. Stdlib only. Never rewrites pins or artifacts.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "recertify_strategy_digest.py"


def run_report(*args: str) -> dict:
    out = subprocess.run(
        ["python", str(SCRIPT), "--json", *args],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


class TestRecertProcedure(unittest.TestCase):
    def test_report_deterministic_across_runs(self):
        first = run_report()
        second = run_report()
        self.assertEqual(first, second)

    def test_canonical_construction_explicit(self):
        report = run_report()
        self.assertEqual(
            report["schema"], "quantengine.strategy-digest-recertification.v1")
        self.assertEqual(
            report["canonical"]["representation"],
            "bytes with CRLF normalized to LF")
        self.assertEqual(
            report["canonical"]["algorithm"],
            "sha256(per-file) concatenated, sha256 again")
        self.assertEqual(len(report["canonical"]["ordering"]), 9)
        self.assertEqual(len(report["per_file"]), 9)

    def test_current_digest_is_reported_but_not_recertified(self):
        # The current archive is not the historical Phase-4 tree. Validate
        # honest reporting, not equality with an unavailable historical tree.
        report = run_report()
        self.assertRegex(report["canonical_digest"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(
            report["canonical_digest"],
            "9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["matches_recorded"])

    def test_status_blocked_with_reasons_not_recertified(self):
        report = run_report()
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["matches_recorded"])
        self.assertGreaterEqual(len(report["reasons"]), 3)

    def test_procedure_is_read_only(self):
        import ast

        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        writes = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in (
                "open", "exec", "eval",
            ):
                writes.append(getattr(func, "id", "?"))
            if isinstance(func, ast.Attribute) and func.attr in (
                "write", "write_text", "write_bytes",
            ):
                writes.append(func.attr)
        self.assertEqual(writes, [])
        self.assertNotIn("--record", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
