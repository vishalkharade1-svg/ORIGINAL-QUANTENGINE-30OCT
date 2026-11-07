"""Phase154: release manifest + provenance contract (deterministic, offline).

Fails if a required release file is omitted from the manifest, a manifest
hash is wrong, or provenance names the wrong release. Stdlib only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_manifest.py"
_SPEC = importlib.util.spec_from_file_location("phase154_manifest", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)


class TestReleaseManifest154(unittest.TestCase):
    def test_manifest_verifies_clean(self):
        problems = _MOD.verify(ROOT, ROOT / "BUILD_MANIFEST.sha256")
        self.assertEqual(problems, [])

    def test_required_files_covered(self):
        covered = set()
        for line in (ROOT / "BUILD_MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                _, p = line.split(None, 1)
                covered.add(p.strip())
        for rel in (
            "README.md",
            "IMPLEMENTATION_STATE.md",
            "NEXT_ACTIONS.md",
            "requirements.txt",
            "core/risk/trading_policy.py",
            "core/exchanges/delta/delta_auth.py",
            "scripts/generate_manifest.py",
            "tests/test_secret_scan_phase0.py",
        ):
            self.assertIn(rel, covered, rel)
        # Research evidence ZIPs are required assets, not excludable clutter.
        zips = [c for c in covered if c.endswith(".zip")]
        self.assertGreaterEqual(len(zips), 10)

    def test_manifest_hashes_match_bytes(self):
        checked = 0
        for line in (ROOT / "BUILD_MANIFEST.sha256").read_text(encoding="utf-8").splitlines()[:50]:
            line = line.strip()
            if not line:
                continue
            h, p = line.split(None, 1)
            actual = hashlib.sha256((ROOT / p.strip()).read_bytes()).hexdigest()
            self.assertEqual(actual, h, p)
            checked += 1
        self.assertGreater(checked, 0)

    def test_provenance_names_phase154_release(self):
        doc = json.loads((ROOT / "reports" / "PHASE154_PROVENANCE.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["phase"], 154)
        self.assertIn("QuantEngine_PHASE154", doc["output_archive"])
        self.assertEqual(doc["input_archive"]["sha256"],
                         "eb7c3ba10b74bb00e1bff0b58d523799facbcb024e20ce61cc19af6729b91e86")

    def test_kilo_exclusion_is_narrow_and_does_not_conceal_project_files(self):
        """R-06: .kilo exclusion is narrow, exact, and never conceals project files."""
        self.assertIn(".kilo", _MOD.SKIP_PARTS)
        pkged = _MOD.package_files(ROOT)
        for p in pkged:
            self.assertNotIn(".kilo", Path(p).parts, f".kilo tooling path packaged: {p}")
        test_path = Path("core/analytics/kilo_metric.py")
        self.assertFalse(any(part in _MOD.SKIP_PARTS for part in test_path.parts))
        self.assertIn("scripts/generate_manifest.py", pkged)
        self.assertIn("core/risk/trading_policy.py", pkged)


if __name__ == "__main__":
    unittest.main()

