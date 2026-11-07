"""11G-A production-isolation tests (research cannot reach production)."""

import unittest
from pathlib import Path

PHASE11G = Path("research/phase11g")

FORBIDDEN = ("place_order", "submit_order", "cancel_order",
             "DeltaOrderExecutor", "BrokerEngine", "DeltaExchange",
             "ALLOW_LIVE", "LIVE_EXECUTE", "DELTA_API_KEY", "DELTA_API_SECRET",
             "ccxt", ".execute(", "import live", "from core.live")


class TestProductionIsolation(unittest.TestCase):
    def test_no_execution_reach(self):
        for path in list((PHASE11G / "features").glob("*.py")) + \
                   list((PHASE11G / "validation").glob("*.py")) + \
                   [PHASE11G / "datasets.py"]:
            src = path.read_text()
            for token in FORBIDDEN:
                self.assertNotIn(token, src, "%s: %s" % (path.name, token))

    def test_monkeypatched_writes_never_reached(self):
        from unittest import mock
        from research.phase11g.features import structure as S
        from research.phase11g.tests.test_feature_contracts import bars
        with mock.patch("core.execution.order_executor.DeltaOrderExecutor.execute",
                        side_effect=AssertionError("live write")) as m1, \
             mock.patch("core.live.broker_engine.BrokerEngine.__init__",
                        side_effect=AssertionError("broker")) as m2:
            S.trend_state(bars(120))
            S.bos_events(bars(120))
        m1.assert_not_called()
        m2.assert_not_called()

    def test_phase11f_untouched(self):
        import subprocess
        base = "e3e6f4b75bd166529e4c35f59a6a68a53bbc7fbb"
        committed = subprocess.run(
            ["git", "diff", "--name-only", base, "HEAD", "--", "research/phase11f"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(committed, "")
        working = subprocess.run(
            ["git", "status", "--porcelain", "--", "research/phase11f"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(working, "")

    def test_live_still_disabled(self):
        from config.settings import settings
        self.assertFalse(settings.ALLOW_LIVE)
        self.assertFalse(settings.LIVE_EXECUTE)


if __name__ == "__main__":
    unittest.main()
