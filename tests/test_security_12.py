"""
====================================================

QuantEngine

Phase 12 -- security hygiene regression tests.

Proves (stdlib only, never printing secret values):

  1. `.env` is not tracked by git;
  2. `logs/engine.log` is not tracked by git;
  3. `.env.example` ships keys/placeholders only (the
     credential entries are empty);
  4. the startup safety banner and safety snapshot never
     contain credential material, even when fake
     credentials are configured;
  5. LIVE remains disabled by default and conflicting
     modes fail closed.

Git-based checks skip cleanly when git is unavailable.
SECRET VALUES ARE NEVER ASSERTED ON AND NEVER PRINTED --
only their ABSENCE from tracked files and outputs.

====================================================
"""

import os
import subprocess
import unittest
from unittest import mock


def git_tracked(path):
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--", path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__ + "/..")),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


class TestSecretHygiene(unittest.TestCase):

    def test_env_not_tracked(self):
        tracked = git_tracked(".env")
        if tracked is None:
            self.skipTest("git unavailable")
        self.assertEqual(tracked, "")

    def test_engine_log_not_tracked(self):
        tracked = git_tracked("logs/engine.log")
        if tracked is None:
            self.skipTest("git unavailable")
        self.assertEqual(tracked, "")

    def test_env_example_has_no_secret_values(self):
        root = os.path.dirname(os.path.abspath(__file__ + "/.."))
        with open(os.path.join(root, ".env.example"),
                  encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        values = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip()
        self.assertIn("DELTA_API_KEY", values)
        self.assertIn("DELTA_API_SECRET", values)
        # Keys/placeholders only: credential entries empty.
        self.assertEqual(values["DELTA_API_KEY"], "")
        self.assertEqual(values["DELTA_API_SECRET"], "")

    def test_banner_and_snapshot_exclude_credentials(self):
        from core.execution.live_safety_gate import (
            ExecutionMode,
            LiveSafetyGate,
        )
        marker_key = "AK12TESTKEY"
        marker_secret = "SK12TESTSECRET"
        inputs = LiveSafetyGate.from_settings(
            mode=ExecutionMode.PAPER,
            api_key=marker_key,
            api_secret=marker_secret,
        )
        decision = LiveSafetyGate.decide(**inputs)
        banner = "\n".join(
            LiveSafetyGate.format_banner(decision))
        snapshot = repr(LiveSafetyGate.describe(decision))
        for output in (banner, snapshot):
            self.assertNotIn(marker_key, output)
            self.assertNotIn(marker_secret, output)

    def test_live_disabled_by_default(self):
        from config.settings import Settings
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in ("ALLOW_LIVE", "LIVE_EXECUTE",
                        "LIVE_MODE"):
                os.environ.pop(key, None)
            fresh = Settings()
        self.assertFalse(fresh.ALLOW_LIVE)
        self.assertFalse(fresh.LIVE_EXECUTE)
        self.assertFalse(fresh.LIVE_MODE)
        self.assertTrue(fresh.PAPER_MODE)

    def test_conflicting_modes_fail_closed(self):
        from core.execution.live_safety_gate import (
            ConfigurationError,
            ExecutionMode,
        )
        with self.assertRaises(ConfigurationError):
            ExecutionMode.resolve(
                paper_mode=True, live_mode=True,
                execution_mode="")


if __name__ == "__main__":
    unittest.main()
