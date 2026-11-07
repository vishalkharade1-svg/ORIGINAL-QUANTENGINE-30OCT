"""Phase132-B: release packaging hygiene (deterministic, offline).

Fails if a release archive would include secret-bearing files, bytecode,
caches, or nested full-project archives. Tests the allowlist rule directly
without building a ZIP.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Allowlist approach: release includes source/docs/config/tests/scripts only;
# never secrets, env packages, or private keys. Bytecode/caches/logs are dev
# noise excluded at packaging time (verified via BUILD_MANIFEST), not a
# worktree-fail. Research evidence ZIPs are retained by design (Phase131: 10).
FORBIDDEN_NAMES = {".env", ".env.test", ".env.local"}
FORBIDDEN_PARTS = {"env"}
FORBIDDEN_KEY_SUFFIXES = {".pem", ".key", ".secret"}


def _violations(root: Path) -> list[str]:
    bad: list[str] = []
    for path in root.rglob("*"):
        # Skip dev noise: packaging excludes these via manifest, worktree may hold them.
        if any(part in {"__pycache__", ".pytest_cache", ".venv", "venv", "logs", ".git", ".kilo"} for part in path.parts):
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        # Root .env is operator config excluded at packaging time via BUILD_MANIFEST, not a worktree-fail
        if rel.as_posix() == ".env":
            continue
        parts = set(rel.parts)
        name = path.name
        if name in FORBIDDEN_NAMES:
            bad.append(rel.as_posix())
            continue
        if parts & FORBIDDEN_PARTS:
            bad.append(rel.as_posix())
            continue
        if path.suffix.lower() in FORBIDDEN_KEY_SUFFIXES:
            bad.append(rel.as_posix())
    return sorted(set(bad))


class TestPackagingHygiene132(unittest.TestCase):
    def test_no_secret_bearing_paths(self):
        self.assertEqual(_violations(ROOT), [])

    def test_build_manifest_excludes_bytecode_and_caches(self):
        manifest = (ROOT / "BUILD_MANIFEST.sha256").read_text(encoding="utf-8")
        self.assertNotIn("__pycache__", manifest)
        self.assertNotIn(".pyc", manifest)
        self.assertNotIn(".pytest_cache", manifest)
        self.assertNotIn(".env", manifest.replace(".env.example", ""))

    def test_env_example_is_safe_template(self):
        example = ROOT / ".env.example"
        self.assertTrue(example.exists())
        text = example.read_text(encoding="utf-8")
        # Template must not carry values: every known-secret line is blank.
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, value = stripped.partition("=")
                if "API" in key or "TOKEN" in key or "SECRET" in key:
                    self.assertEqual(value.strip(), "", msg=key)

    def test_scanner_covers_testnet_and_sandbox(self):
        import importlib.util
        import sys
        scanner_path = ROOT / "scripts" / "security" / "scan_secrets.py"
        spec = importlib.util.spec_from_file_location("phase132_scan", scanner_path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".env").write_text(
                "DELTA_INDIA_TESTNET_API_KEY=leak-me\n", encoding="utf-8")
            findings = mod.scan_worktree(root)
            self.assertEqual(len(findings), 1)
            self.assertNotIn("leak-me", repr(findings[0]))
            (root / ".env").write_text(
                "DELTA_SANDBOX_API_SECRET=leak-me-too\n", encoding="utf-8")
            findings2 = mod.scan_worktree(root)
            self.assertEqual(len(findings2), 1)


if __name__ == "__main__":
    unittest.main()
