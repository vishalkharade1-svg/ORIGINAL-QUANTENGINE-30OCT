"""The declared pins and the recorded evidence environment must agree.

Phase132 recorded a drift -- httpx 0.28.1 installed against a 0.27.2 pin --
and it stayed recorded, unresolved, for many phases. It was not cosmetic:
Phase134 found that httpx 0.28 had removed the ``content`` kwarg from
``Client.delete()``, which silently broke order cancellation. The pin
described a version that nothing was running.

That is the defect class this contract closes. ``requirements.txt`` is what a
reproducer installs; the release record's ``verification_environment`` is what
the evidence was actually produced under. They must name exactly the same
versions. Drift then fails a test instead of sitting in a report as a note.

The record is read from the highest-numbered ``reports/PHASE*_RELEASE_GATES.json``,
so the contract advances with the release and never needs re-pointing by hand.
It deliberately fails if that record omits its environment: a release that does
not say what it ran on cannot be checked, and the Phase157 self-audit found
exactly that omission once already.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PIN_LINE = re.compile(r"^([A-Za-z0-9_.\-]+)==(\S+)$")
_GATES_NAME = re.compile(r"PHASE(\d+)_RELEASE_GATES\.json$")


def latest_release_record() -> tuple[int, Path]:
    """The highest-numbered release gates file, by phase number."""
    found = []
    for path in (ROOT / "reports").glob("PHASE*_RELEASE_GATES.json"):
        match = _GATES_NAME.search(path.name)
        if match:
            found.append((int(match.group(1)), path))
    if not found:
        raise AssertionError("no release gates file found under reports/")
    return max(found, key=lambda item: item[0])


def declared_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _PIN_LINE.match(line)
        if match:
            pins[match.group(1).lower()] = match.group(2)
    return pins


def recorded_environment() -> dict:
    phase, path = latest_release_record()
    doc = json.loads(path.read_text(encoding="utf-8"))
    env = doc.get("verification_environment")
    if not isinstance(env, dict):
        raise AssertionError(
            "%s (phase %d) has no verification_environment block: a release "
            "that does not state what it ran on cannot be checked"
            % (path.name, phase))
    return env


class TestDependencyPinContract(unittest.TestCase):
    def test_release_record_names_interpreter_and_runner(self):
        env = recorded_environment()
        for key in ("python", "pytest", "platform"):
            self.assertIsInstance(env.get(key), str, "missing %s" % key)
            self.assertTrue(env[key].strip(), "empty %s" % key)

    def test_release_record_names_its_dependency_set(self):
        deps = recorded_environment().get("dependencies")
        self.assertIsInstance(deps, dict, "missing dependencies map")
        self.assertTrue(deps, "empty dependencies map")

    def test_declared_pins_match_the_recorded_evidence_environment(self):
        pins = declared_pins()
        deps = {k.lower(): v for k, v in recorded_environment()["dependencies"].items()}
        phase, path = latest_release_record()
        self.assertEqual(
            sorted(pins), sorted(deps),
            "requirements.txt and %s (phase %d) name different packages"
            % (path.name, phase))
        drifted = {k: (pins[k], deps[k]) for k in pins if pins[k] != deps[k]}
        self.assertEqual(
            drifted, {},
            "requirements.txt disagrees with the recorded evidence "
            "environment (declared, recorded): %s" % drifted)

    def test_httpx_pin_is_not_below_the_recorded_evidence_version(self):
        """The specific drift this contract exists for, named explicitly."""
        pins = declared_pins()
        deps = {k.lower(): v for k, v in recorded_environment()["dependencies"].items()}
        self.assertIn("httpx", pins)
        self.assertEqual(pins["httpx"], deps["httpx"])


if __name__ == "__main__":
    unittest.main()
