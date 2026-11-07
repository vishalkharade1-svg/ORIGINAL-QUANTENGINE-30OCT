"""11G-K causality tests (spec timestamp rules vs certified engine).

Each hypothesis's availability chain is exercised on synthetic trade
bars + synthetic 1m candles using ONLY certified calls. No economics.
"""

import unittest

from research.phase11g_j.replay import engine as ENG
from research.phase11g_j.replay.events import RealTrade


def _trades(n=120, start=1000, step_ms=5000, side_cycle=("buy", "sell")):
    out = []
    for i in range(n):
        out.append(RealTrade(start + i * step_ms, (start + i * step_ms) * 1000,
                             i, "X", "test", 100.0 + (i % 7) * 0.1, 1.0,
                             side_cycle[i % len(side_cycle)], "t%d" % i,
                             "t%d" % i, "t%d" % i))
    return out


def _bars(n=120, start=1000):
    return [{"time": start + i * 60, "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.0 + (1 if i % 2 else -1) * 0.2,
             "volume": 10.0} for i in range(n)]


class TestCausality11GK(unittest.TestCase):
    def test_imbalance_prefix_only(self):
        rev = ENG.TradeReplay(_trades())
        t = 1000 + 60 * 5000
        ref = rev.delta(t, window="5m")
        late = list(_trades()) + [RealTrade(t + 1, (t + 1) * 1000, 999, "X",
                                            "test", 1.0, 10 ** 6, "buy",
                                            "late", "late", "late")]
        got = ENG.TradeReplay(late).delta(t, window="5m")
        self.assertEqual(got, ref)

    def test_cvd_prefix_only(self):
        rev = ENG.TradeReplay(_trades())
        ref = rev.cvd(end_ms=1000 + 50 * 5000)
        extra = list(_trades()) + [RealTrade(10 ** 12, 10 ** 15, 999, "X",
                                             "test", 1.0, 1.0, "buy",
                                             "far", "far", "far")]
        got = ENG.TradeReplay(extra).cvd(end_ms=1000 + 50 * 5000)
        self.assertEqual(got, ref)

    def test_footprint_window_isolation(self):
        rev = ENG.TradeReplay(_trades())
        ref = rev.footprint(1000, 1000 + 60000)
        more = list(_trades()) + [RealTrade(1000 + 120000, 10 ** 14, 999, "X",
                                            "test", 500.0, 9.0, "sell",
                                            "w", "w", "w")]
        got = ENG.TradeReplay(more).footprint(1000, 1000 + 60000)
        self.assertEqual(got, ref)

    def test_structure_past_only(self):
        from research.phase11f import features as F11
        b = _bars()
        ref = F11.atr14(b[:80])[79]
        wild = b[:80] + [dict(x, high=9999.0, low=0.01) for x in b[80:]]
        self.assertEqual(F11.atr14(wild)[79], ref)

    def test_decision_before_entry_ordering(self):
        # Contract invariant spot-check: hypothesis JSONs all define
        # decision_time = signal bar close, entry_time = next bar open.
        import json
        from pathlib import Path
        for p in sorted(Path("research/phase11g_k/hypotheses").glob("*.json")):
            doc = json.loads(p.read_text())
            self.assertIn("next bar open", doc["entry"]["rule"].lower(), p.stem)
            self.assertIn("NEXT_BAR_OPEN", doc["execution_model"])


if __name__ == "__main__":
    unittest.main()
