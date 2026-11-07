"""Phase193B regression: packaging must refuse credential-bearing members.

Closes the Phase193B finding that ``scripts/generate_manifest.py`` excluded
only three literal file names (``.env``/``.env.test``/``.env.local``), so a
nested ``.env.backup``, ``prod.key``, ``cert.pem`` or ``identity.secrets``
would ship silently in a release tree while the docstring claimed wider
protection.  The refusal is now a rule over names and suffixes at any depth,
and strict verification fails closed on it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "phase193b_generate_manifest", ROOT / "scripts" / "generate_manifest.py")
assert _spec is not None and _spec.loader is not None
manifest_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = manifest_mod
_spec.loader.exec_module(manifest_mod)


def _tree_with_secret_members() -> tuple[Path, list[str]]:
    root = Path(tempfile.mkdtemp())
    planted = [
        ".env",
        "ops/.env.backup",
        "ops/.env.prod",
        "certs/server.pem",
        "certs/prod.key",
        "ops/identity.secrets",
        "ops/reporter.p12",
        "ops/wallet.pfx",
        "ops/client.keystore",
    ]
    for rel in planted:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("placeholder\n", encoding="utf-8")
    (root / ".env.example").write_text(
        "DELTA_" + "API_KEY=\n", encoding="utf-8")
    (root / "KEEP.txt").write_text("legit\n", encoding="utf-8")
    return root, planted


class TestPackagingRefusesSecrets(unittest.TestCase):
    def test_secret_bearing_rule_flags_each_variant(self):
        for rel in (".env", "ops/.env.backup", "ops/.env.prod",
                    "certs/server.pem", "certs/prod.key",
                    "ops/identity.secrets", "ops/reporter.p12",
                    "ops/wallet.pfx", "ops/client.keystore"):
            with self.subTest(rel=rel):
                self.assertTrue(manifest_mod.is_secret_bearing_name(rel))

    def test_template_is_allowed(self):
        self.assertFalse(manifest_mod.is_secret_bearing_name(".env.example"))

    def test_prohibited_members_lists_all_planted_files(self):
        root, planted = _tree_with_secret_members()
        found = manifest_mod.prohibited_members(root)
        got, expected = set(found), set(planted)
        self.assertLessEqual(expected, got)

    def test_package_files_never_cover_secret_members(self):
        root, planted = _tree_with_secret_members()
        covered = manifest_mod.package_files(root)
        for rel in planted:
            with self.subTest(rel=rel):
                self.assertNotIn(rel, covered)
        self.assertIn(".env.example", covered)
        self.assertIn("KEEP.txt", covered)

    def test_verify_strict_fails_on_planted_secrets(self):
        root, planted = _tree_with_secret_members()
        write_to = root / manifest_mod.MANIFEST_NAME
        text = manifest_mod.generate(root)
        write_to.write_text(text, encoding="utf-8", newline="\n")
        problems = manifest_mod.verify(root, write_to, strict=True)
        refusals = {p.split(":")[0] for p in problems if p.startswith("prohibited:")}
        self.assertIn("prohibited", refusals)

    def test_verify_normal_reports_exclusions_as_warnings(self):
        root, planted = _tree_with_secret_members()
        write_to = root / manifest_mod.MANIFEST_NAME
        write_to.write_text(manifest_mod.generate(root),
                            encoding="utf-8", newline="\n")
        problems = manifest_mod.verify(root, write_to, strict=False)
        self.assertEqual([p for p in problems if not p.startswith("prohibited:")], [])


class TestZipPackagingPolicy(unittest.TestCase):
    def test_scan_detects_secret_planted_inside_generated_zip(self):
        """A release ZIP with a planted .env must be detectable by the scan."""
        marker = "phase193b-zip-canary"
        with tempfile.TemporaryDirectory() as directory:
            zip_path = Path(directory) / "bundle.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("inner/.env",
                            "DELTA_" + "API_KEY=" + marker + "\n")
                zf.writestr("inner/README.txt", "legit\n")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(Path(directory) / "extracted")
            import importlib.util as iu
            spec = iu.spec_from_file_location(
                "phase193b_zip_scan",
                ROOT / "scripts" / "security" / "scan_secrets.py")
            mod = iu.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            findings = mod.scan_worktree(Path(directory) / "extracted")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "inner/.env")
        self.assertNotIn(marker, repr(findings[0]))


class TestStagedScanCoversRemovedWorktreeCopies(unittest.TestCase):
    def test_scan_staged_finds_secret_after_worktree_removal(self):
        marker = "phase193b-staged-canary"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "t@t.invalid"],
                           cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "t"],
                           cwd=root, check=True)
            (root / "notes.txt").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"],
                           cwd=root, check=True)
            secret_rel = "ops/.env.backup"
            (root / "ops").mkdir()
            (root / secret_rel).write_text(
                "DELTA_INDIA_TESTNET_API_" + "SECRET=" + marker + "\n",
                encoding="utf-8")
            subprocess.run(["git", "add", secret_rel], cwd=root, check=True)
            # Remove the worktree copy: the staged blob is the only exposure.
            (root / secret_rel).unlink()
            import importlib.util as iu
            spec = iu.spec_from_file_location(
                "phase193b_staged_scan",
                ROOT / "scripts" / "security" / "scan_secrets.py")
            mod = iu.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            findings = mod.scan_staged(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, secret_rel)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertNotIn(marker, repr(findings[0]))


if __name__ == "__main__":
    unittest.main()
