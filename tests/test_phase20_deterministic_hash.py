"""Phase 20 Unit Tests: Deterministic Research & Code Hashing Engine.

Validates cross-platform deterministic code hashing:
1. LF and CRLF equivalence.
2. Isolated CR handling.
3. Strict sensitivity to meaningful source changes (variable names, values, whitespace).
4. Idempotence and determinism under repeated execution.
5. Canonical JSON serialization determinism.
6. Verification against all 8 Phase 11G research generator files and their HEAD pins.
"""

import hashlib
import json
import unittest
from pathlib import Path

from core.research.deterministic_hash import (
    canonical_code_hash,
    canonical_json_bytes,
    compute_canonical_json_hash,
    compute_deterministic_source_hash,
    normalize_line_endings,
    verify_source_hash,
)

ROOT = Path(__file__).resolve().parent.parent


class TestDeterministicHashEngine(unittest.TestCase):
    """Unit tests for the deterministic hashing engine."""

    def test_normalize_line_endings_lf_and_crlf(self):
        lf_bytes = b"def test_func():\n    return 42\n"
        crlf_bytes = b"def test_func():\r\n    return 42\r\n"
        cr_bytes = b"def test_func():\r    return 42\r"

        self.assertEqual(normalize_line_endings(lf_bytes), lf_bytes)
        self.assertEqual(normalize_line_endings(crlf_bytes), lf_bytes)
        self.assertEqual(normalize_line_endings(cr_bytes), lf_bytes)

    def test_compute_hash_lf_crlf_identical(self):
        source_lf = "def compute_alpha(data):\n    # Alpha calculation\n    return data * 1.5\n"
        source_crlf = "def compute_alpha(data):\r\n    # Alpha calculation\r\n    return data * 1.5\r\n"

        hash_lf = compute_deterministic_source_hash(source_lf)
        hash_crlf = compute_deterministic_source_hash(source_crlf)

        self.assertEqual(hash_lf, hash_crlf)
        self.assertEqual(len(hash_lf), 64)

    def test_repeated_execution_determinism(self):
        sample = b"import sys\n\ndef main():\n    print('determinism test')\n"
        first_hash = compute_deterministic_source_hash(sample)
        for _ in range(500):
            self.assertEqual(compute_deterministic_source_hash(sample), first_hash)

    def test_meaningful_source_changes_modify_digest(self):
        base_code = "def score(x):\n    return x + 1\n"
        base_hash = compute_deterministic_source_hash(base_code)

        # 1. Variable name alteration
        c1 = "def score(y):\n    return y + 1\n"
        self.assertNotEqual(compute_deterministic_source_hash(c1), base_hash)

        # 2. Constant value alteration
        c2 = "def score(x):\n    return x + 2\n"
        self.assertNotEqual(compute_deterministic_source_hash(c2), base_hash)

        # 3. Comment addition
        c3 = "def score(x):\n    # added comment\n    return x + 1\n"
        self.assertNotEqual(compute_deterministic_source_hash(c3), base_hash)

        # 4. Syntactic whitespace change (space vs tab or extra space)
        c4 = "def score(x):\n     return x + 1\n"
        self.assertNotEqual(compute_deterministic_source_hash(c4), base_hash)

        # 5. Identifier case change
        c5 = "def Score(x):\n    return x + 1\n"
        self.assertNotEqual(compute_deterministic_source_hash(c5), base_hash)

    def test_utf8_bom_stripping(self):
        bom_code = b"\xef\xbb\xbfdef foo():\n    return 1\n"
        clean_code = b"def foo():\n    return 1\n"
        self.assertEqual(
            compute_deterministic_source_hash(bom_code),
            compute_deterministic_source_hash(clean_code),
        )

    def test_verify_source_hash_helper(self):
        code = "val = 100\n"
        expected = hashlib.sha256(b"val = 100\n").hexdigest()
        self.assertTrue(verify_source_hash(code, expected))
        self.assertTrue(verify_source_hash(code.replace("\n", "\r\n"), expected))
        self.assertFalse(verify_source_hash("val = 200\n", expected))

    def test_canonical_json_ordering_and_hash(self):
        obj1 = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}
        obj2 = {"nested": {"y": 25, "z": 26}, "a": 1, "b": 2}

        bytes1 = canonical_json_bytes(obj1)
        bytes2 = canonical_json_bytes(obj2)
        self.assertEqual(bytes1, bytes2)
        self.assertTrue(bytes1.endswith(b"\n"))

        hash1 = compute_canonical_json_hash(obj1)
        hash2 = compute_canonical_json_hash(obj2)
        self.assertEqual(hash1, hash2)


class TestPhase11GGeneratorsMatchHead(unittest.TestCase):
    """Proves that deterministic hashing matches the canonical HEAD hashes for all 8 Phase 11G generators."""

    EXPECTED_HEAD_HASHES = {
        "research/phase11g_n/analyze.py": "97d8aaa6e1d47a56a2014dbe25e6d41d15548d75401729fe5838ac866e0a9dde",
        "research/phase11g_o/analyze_o.py": "6fb4a308ed7649002d583f5067a17e094b9c82bfac64fb6d9d22c08233ce1d71",
        "research/phase11g_p/analyze_p.py": "f493df6ce4a2164e5dba6de71b191c4a76720e98fc6766424ba14415aae8e1e5",
        "research/phase11g_q/gate.py": "09cc32a9478b807d291061413147657b9d8b7516874bfa66c941d366fb02f59a",
        "research/phase11g_r/gate_r.py": "5a19b1fc8af7656fd8b24b85c6ba3eb46ac938379e02532b1161f60e65e9c930",
        "research/phase11g_s/gate_s.py": "1181d1ce4d67416254877f1b78587be39e2dc1067fc56eee54e7f4f80f3b24fa",
        "research/phase11g_t/monitor.py": "eea445bd832a92a594716e7ce3ab78fc3c8ba3b75f3b3aeaf8226140d16d6355",
        "research/phase11g_u/monitor_u.py": "2e3a731c24959623aaf11b891f1bfcf463bfc51d5102f3974557a5ce7fe5dbad",
    }

    def test_all_phase11g_generators_match_head_canonical_hash(self):
        for rel_path, expected_hash in self.EXPECTED_HEAD_HASHES.items():
            full_path = ROOT / rel_path
            with self.subTest(file=rel_path):
                self.assertTrue(full_path.is_file(), f"File {rel_path} must exist")
                computed = canonical_code_hash(full_path)
                self.assertEqual(
                    computed,
                    expected_hash,
                    f"Deterministic hash for {rel_path} ({computed}) did not match HEAD canonical hash ({expected_hash})",
                )


if __name__ == "__main__":
    unittest.main()
