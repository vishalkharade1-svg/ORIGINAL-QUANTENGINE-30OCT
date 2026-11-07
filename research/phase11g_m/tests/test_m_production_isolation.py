"""11G-M production isolation: prod clean, LIVE off, no order-submission tokens."""

import os
import subprocess
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

MDIR = BASE_DIR / "research" / "phase11g_m"


class TestProductionIsolation(unittest.TestCase):
    def test_no_production_paths(self):
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "core/", "config/", "data/",
             "execution/", "risk/", "backtesting/", "main.py"],
            capture_output=True, text=True, cwd=str(BASE_DIR)).stdout.strip()
        self.assertEqual(out, "")

    def test_live_disabled(self):
        self.assertNotIn(os.getenv("ALLOW_LIVE", "").lower(), ("1", "true"))
        self.assertNotIn(os.getenv("LIVE_EXECUTE", "").lower(), ("1", "true"))

    def test_no_order_submission_tokens(self):
        # Token fragments are concatenated so this file never contains
        # the banned literals itself (same guard as the D3 seal scan).
        toks = ("submit" + "_order", "place" + "_order", "live" + "_execute",
                "paper" + "_trade", "shadow" + "_trade", "send" + "_order",
                "create" + "_order")
        for path in MDIR.rglob("*.py"):
            code = path.read_text()
            for tok in toks:
                self.assertNotIn(tok, code, "%s: %s" % (path.name, tok))


if __name__ == "__main__":
    unittest.main()
