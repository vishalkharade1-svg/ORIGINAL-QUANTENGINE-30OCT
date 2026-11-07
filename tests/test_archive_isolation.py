"""Regression test proving active modules do not import archived duplicate implementations."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestArchiveIsolation(unittest.TestCase):
    def test_no_active_python_module_imports_from_archive(self):
        """Phase 162 Phase 2: active modules must never import from _archive/."""
        active_py_files = [
            p for p in ROOT.rglob("*.py")
            if not p.as_posix().startswith((ROOT / "_archive").as_posix())
            and not any(part.startswith((".", "_phase")) for part in p.parts)
        ]
        violations = []
        for p in active_py_files:
            rel = p.relative_to(ROOT).as_posix()
            try:
                content = p.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                tree = ast.parse(content, filename=rel)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if parts[0] == "_archive":
                            violations.append((rel, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        parts = node.module.split(".")
                        if parts[0] == "_archive":
                            violations.append((rel, node.module))

        self.assertEqual(
            violations, [],
            f"Active modules must not import from _archive/: {violations}"
        )


if __name__ == "__main__":
    unittest.main()
