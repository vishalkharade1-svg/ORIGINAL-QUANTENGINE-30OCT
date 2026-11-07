"""Phase158 post-audit repair: snapshot neutrality and authentic byte pins.

The independent audit of the first Phase158 build found two defects of one
class -- platform-dependent file bytes:

* running tests physically rewrote ``data/runtime/risk_policy_overrides.json``
  (text-mode persistence converts LF to CRLF on Windows).  The Phase131
  packaging manifest pins the file's authentic bytes as LF, so every
  Windows-side save re-drifted it; the audit platform (LF conventions) saw a
  hash change, and on the build platform the rewrite was byte-identical and
  therefore invisible.
* ``BUILD_MANIFEST.sha256`` was written with platform newline translation, so
  its bytes differed between the shipped file (CRLF on Windows) and a
  byte-for-byte regeneration on a platform using LF.

This module pins the repairs:

* the runtime policy file carries its authentic LF bytes (Phase131 pin), and
  policy persistence writes LF explicitly on every platform;
* the manifest is LF-only and its file bytes equal a fresh generation exactly;
* the thirteen sealed research artifacts the suite rebuilds in place still
  match BOTH records that pin them (the Phase131 packaging manifest and the
  Phase154 archive inventory); those rebuilds are byte-identical on the build
  platform, and ``tests/conftest.py`` restores them byte-exactly if another
  platform's newline conventions make a rebuild differ.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

POLICY = ROOT / "data" / "runtime" / "risk_policy_overrides.json"
POLICY_PIN = "a2b9f5c69f8e3ed4c915d2f52fcef6b4f2a992e75e663c49297a7ac0f35aab44"
MANIFEST = ROOT / "BUILD_MANIFEST.sha256"
PHASE131_MANIFEST = ROOT / "MANIFEST_SHA256_PHASE131.txt"
PHASE154_INVENTORY = ROOT / "reports" / "PHASE154_ARCHIVE_INTEGRITY.json"

#: Sealed research artifacts rebuilt in place by their change-detector tests.
#: (Line-ending conventions differ per artifact -- the pins are the authority,
#: not a convention, which is why the guard restores recorded bytes.)
SEALED_REBUILT_ARTIFACTS = (
    "research/phase11g_n/feasibility.json",
    "research/phase11g_o/feasibility_o.json",
    "research/phase11g_p/readiness_p.json",
    "research/phase11g_q/trigger_q.json",
    "research/phase11g_r/readiness_r.json",
    "research/phase11g_s/readiness_s.json",
    "research/phase11g_t/readiness_t.json",
    "research/phase11g_u/readiness_u.json",
    "research/results/phase33_oos_readiness_snapshot.json",
    "research/results/phase35_symbol_coverage.json",
    "research/results/phase36_provenance_symbol_coverage.json",
    "research/results/phase37_multi_symbol_oos_manifest.json",
    "research/results/phase48_discovery_capture.json",
)

_spec = importlib.util.spec_from_file_location(
    "phase158_snapshot_neutrality_manifest",
    ROOT / "scripts" / "generate_manifest.py")
assert _spec is not None and _spec.loader is not None
gm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gm)


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _phase131_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in PHASE131_MANIFEST.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            pins[parts[1]] = parts[0]
    return pins


class TestSnapshotNeutrality(unittest.TestCase):
    def test_runtime_policy_file_is_the_authentic_lf_form(self):
        blob = POLICY.read_bytes()
        self.assertEqual(
            _sha256(blob), POLICY_PIN,
            "the runtime policy file no longer carries the bytes the Phase131 "
            "packaging manifest pins; it must not be re-drifted by a save")
        self.assertNotIn(
            b"\r", blob,
            "the runtime policy file must carry LF bytes: a CRLF form is the "
            "post-Phase131 drift the audit found")
        self.assertEqual(
            _phase131_pins()["data/runtime/risk_policy_overrides.json"],
            POLICY_PIN,
            "the test pin and the Phase131 manifest disagree about authenticity")

    def test_policy_persistence_is_platform_independent(self):
        from core.risk.trading_policy import TradingPolicyManager
        values = {"min_rr": 2.0, "max_rr": 8.0, "trailing_enabled": True,
                  "trailing_activation_r": 1.0, "trailing_distance_r": 0.5,
                  "auto_exit_on_opposite_signal": True}
        with tempfile.TemporaryDirectory() as td:
            first_path = Path(td) / "policy.json"
            manager = TradingPolicyManager(first_path)
            manager.set_instrument("BTCUSDT", values)
            first = first_path.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            second_path = Path(td) / "policy.json"
            manager = TradingPolicyManager(second_path)
            manager.set_instrument("BTCUSDT", values)
            second = second_path.read_bytes()
        self.assertNotIn(
            b"\r", first,
            "policy persistence must write LF bytes on every platform; a "
            "text-mode write translates them on Windows")
        self.assertTrue(first.endswith(b"\n"), "persisted JSON must end with a newline")
        self.assertEqual(
            first, second,
            "identical policy state must serialise to identical bytes")

    def test_manifest_is_lf_only_and_reproduces_byte_for_byte(self):
        blob = MANIFEST.read_bytes()
        self.assertNotIn(
            b"\r", blob,
            "the manifest must be LF-only: a CRLF file cannot be reproduced "
            "byte-for-byte by a regeneration on a platform using LF")
        self.assertEqual(
            blob, gm.generate(ROOT).encode("utf-8"),
            "the manifest file's bytes must equal a fresh generation exactly")

    def test_sealed_rebuilt_artifacts_match_their_recorded_bytes(self):
        pins = _phase131_pins()
        inventory = {member["path"]: member["sha256"] for member in json.loads(
            PHASE154_INVENTORY.read_text(encoding="utf-8"))["members"]}
        for rel in SEALED_REBUILT_ARTIFACTS:
            with self.subTest(artifact=rel):
                actual = _sha256((ROOT / rel).read_bytes())
                self.assertEqual(
                    actual, pins[rel],
                    "the Phase131 packaging manifest pins different bytes")
                self.assertEqual(
                    actual, inventory[rel],
                    "the Phase154 archive inventory pins different bytes")


if __name__ == "__main__":
    unittest.main()
