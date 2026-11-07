"""Phase-0 tests for the value-redacting secret scanner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


_ROOT = Path(__file__).resolve().parents[1]
_SCANNER_PATH = _ROOT / "scripts" / "security" / "scan_secrets.py"
_SPEC = importlib.util.spec_from_file_location("phase0_secret_scan", _SCANNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_SCANNER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _SCANNER
_SPEC.loader.exec_module(_SCANNER)


class TestPhase0SecretScanner(unittest.TestCase):
    def test_blank_env_credentials_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "\n".join((
                    "DELTA_API_" + "KEY=",
                    "DELTA_API_" + "SECRET=",
                    "",
                )),
                encoding="utf-8",
            )
            self.assertEqual(_SCANNER.scan_worktree(root), [])

    def test_nonempty_credentials_are_found_without_value(self):
        marker = "phase0-test-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_API_" + "KEY"
            (root / ".env").write_text(
                key_name + "=" + marker + "\n",
                encoding="utf-8",
            )
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertNotIn(marker, repr(findings[0]))

    def test_bom_prefixed_first_line_secret_is_found(self):
        """Phase159 regression: a BOM on line 1 must not hide a credential.

        The r2 self-audit planted a real-looking key in a scratch .env written
        by a tool that prepends a UTF-8 BOM; the ^-anchored rule missed it
        because U+FEFF is not whitespace.  The scanner now decodes with
        utf-8-sig, and this test pins the behavior with the same artifact.
        """
        marker = "phase0-test-bom-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_API_" + "KEY"
            (root / ".env").write_text(
                key_name + "=" + marker + "\n",
                encoding="utf-8-sig",
            )
            self.assertTrue(
                (root / ".env").read_bytes().startswith(b"\xef\xbb\xbf"),
                "the fixture must actually carry a UTF-8 BOM")
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertEqual(findings[0].path, ".env")
        self.assertEqual(findings[0].line, 1)
        self.assertNotIn(marker, repr(findings[0]))

    def test_utf16_bom_first_line_secret_is_found(self):
        """Phase160 regression: the declared UTF-16 boundary must be closed.

        The Phase159 vendor-audit handoff declared that UTF-16 members were
        invisible to the content rules (bytes were decoded as UTF-8, so
        UTF-16 text arrived NUL-interleaved and no rule could match).
        Decoding is now content-based (scripts/security/text_decode.py); this
        test pins the closed boundary with a BOM'd UTF-16 ``.env``.
        """
        marker = "phase160-test-utf16-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_API_" + "KEY"
            (root / ".env").write_bytes(
                (key_name + "=" + marker + "\n").encode("utf-16"))
            self.assertEqual((root / ".env").read_bytes()[:2], b"\xff\xfe",
                             "the fixture must actually carry a UTF-16LE BOM")
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertEqual(findings[0].path, ".env")
        self.assertEqual(findings[0].line, 1)
        self.assertNotIn(marker, repr(findings[0]))

    def test_bomless_utf16_le_secret_is_found(self):
        """Phase160: BOM-less UTF-16 LE must not slip through either."""
        marker = "phase160-test-utf16le-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_API_" + "KEY"
            (root / ".env").write_bytes(
                (key_name + "=" + marker + "\n").encode("utf-16-le"))
            self.assertFalse(
                (root / ".env").read_bytes().startswith(b"\xff\xfe"),
                "the fixture must be BOM-less")
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertEqual(findings[0].path, ".env")
        self.assertEqual(findings[0].line, 1)
        self.assertNotIn(marker, repr(findings[0]))

    def test_bomless_utf16_be_secret_is_found(self):
        """Phase160: BOM-less UTF-16 BE is sniffed by its NUL parity."""
        marker = "phase160-test-utf16be-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_API_" + "KEY"
            (root / ".env").write_bytes(
                (key_name + "=" + marker + "\n").encode("utf-16-be"))
            self.assertFalse(
                (root / ".env").read_bytes().startswith(b"\xfe\xff"),
                "the fixture must be BOM-less")
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertEqual(findings[0].path, ".env")
        self.assertEqual(findings[0].line, 1)
        self.assertNotIn(marker, repr(findings[0]))

    def test_utf32_bom_secret_is_found(self):
        """Phase160: UTF-32 BOM'd files are closed alongside the UTF-16 class.

        Misread as UTF-16 a UTF-32 file would present as NUL-interleaved text
        that no rule can match, so the decoder must claim it first.
        """
        marker = "phase160-test-utf32-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_API_" + "KEY"
            (root / ".env").write_bytes(
                (key_name + "=" + marker + "\n").encode("utf-32"))
            self.assertEqual((root / ".env").read_bytes()[:4], b"\xff\xfe\x00\x00",
                             "the fixture must actually carry a UTF-32LE BOM")
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertEqual(findings[0].path, ".env")
        self.assertEqual(findings[0].line, 1)
        self.assertNotIn(marker, repr(findings[0]))

    def test_binary_member_is_not_scanned_as_garbage(self):
        """Phase160: binary members are not scanned as mangled text here.

        They must instead be declared as an opaque class; an undeclared one
        fails the privacy scan (scan_privacy.py rule E, pinned by the privacy
        contract tests).
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.txt").write_bytes(bytes(range(256)) * 4)
            self.assertEqual(_SCANNER.scan_worktree(root), [])

    def test_current_worktree_has_no_detected_secret_material(self):
        # Worktree must not leak secrets in source, fixtures, or tracked files.
        # Operator-local runtime configuration (the root untracked `.env`) is
        # returned by `scan_worktree_with_local_policy` as an *explicit*
        # second bucket (Phase193B): it is excluded from release packaging by
        # policy and surfaced here by name -- never filtered in silence.
        scoped, local = _SCANNER.scan_worktree_with_local_policy(_ROOT)
        self.assertEqual(scoped, [])
        # Anything in the local bucket must be exactly the operator-local
        # policy set; nested `.env.*` files would appear in `scoped` above.
        for finding in local:
            self.assertIn(finding.path, _SCANNER.operator_local_files(_ROOT))

    def test_main_fails_closed_on_root_env_credentials(self):
        """Phase193B regression: `main()` must fail on a root `.env` secret.

        The Phase187 exemption (`f.path != ".env"` in `main`) let a
        credential-bearing root `.env` pass `scan_secrets.py` as PASS while
        the history gate flagged the same values.  This pins the closed
        bypass at the CLI boundary: a non-empty root `.env` findings list
        reaches the emitted findings with exit code 1.
        """
        marker = "phase193b-root-env-cli-secret"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_name = "DELTA_INDIA_TESTNET_API_" + "KEY"
            (root / ".env").write_text(
                key_name + "=" + marker + "\n", encoding="utf-8")
            exit_code = _SCANNER.main(["--root", str(root)])
        self.assertEqual(exit_code, 1)

    def test_main_passes_when_no_secret_anywhere(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "DELTA_INDIA_TESTNET_API_" + "KEY=\n"
                "DELTA_INDIA_TESTNET_API_" + "SECRET=\n",
                encoding="utf-8")
            exit_code = _SCANNER.main(["--root", str(root)])
        self.assertEqual(exit_code, 0)

    def test_nested_env_files_are_never_exempt(self):
        """A nested `.env` (e.g. `core/.env`) is flagged like the root one."""
        marker = "phase193b-nested-env-secret"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "core").mkdir()
            # Blank files do not indicator-match; nested ones with values do.
            self.assertEqual(_SCANNER.scan_worktree(root), [])
            key_name = "DELTA_" + "API_SECRET"
            (root / "core" / ".env").write_text(
                key_name + "=" + marker + "\n", encoding="utf-8")
            findings = _SCANNER.scan_worktree(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, "core/.env")
        self.assertEqual(findings[0].rule, "non_empty_known_secret")
        self.assertNotIn(marker, repr(findings[0]))

    def test_hist_scanner_flags_credential_history_canary(self):
        """`scan_env_history` reports the commit that plants a credential."""
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "t@t.invalid"],
                           cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "t"],
                           cwd=root, check=True)
            key_name = "DELTA_" + "API_KEY"
            (root / ".env").write_text("# blank operator template\n" + key_name + "=\n",
                                       encoding="utf-8")
            subprocess.run(["git", "add", ".env"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "safe baseline"],
                           cwd=root, check=True)
            leak_name = "DELTA_INDIA_TESTNET_API_" + "KEY"
            (root / ".env").write_text(
                leak_name + "=" + "phase193b-history-canary-v\n",
                encoding="utf-8")
            subprocess.run(["git", "add", ".env"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "operator fill"],
                           cwd=root, check=True)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                  check=True, capture_output=True,
                                  text=True).stdout.strip()
            unsafe = _SCANNER.scan_env_history(root)
        self.assertEqual(len(unsafe), 1)
        self.assertEqual(unsafe[0], head)
        # The leak value must never appear in the scanner output surface.
        self.assertNotIn("phase193b-history-canary-v", str(unsafe))


if __name__ == "__main__":
    unittest.main()
