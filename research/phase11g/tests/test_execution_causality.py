"""11G-C execution causality (fixed-slice equivalence + NBO mechanics).

Proves the fixed-slice candidate view is output-identical to growing
prefixes (the performance optimization changes nothing), and that NBO
fills occur at the next open with exact accounting. Synthetic bars.
"""

import unittest

from research.phase11g import candidates as G
from research.phase11g import execution as EX
from research.phase11g.tests.test_feature_contracts import bars


class TestFixedSliceEquivalence(unittest.TestCase):
    def test_all_candidates_truncation_proof(self):
        b = bars(150)
        by_id = {c.id: c for c in G.ALL}
        for hid in sorted(by_id):
            for idx in (30, 80, 120, 149):
                a = by_id[hid]()
                full = a.signals(idx, b, None) or []
                c = by_id[hid]()
                trunc = c.signals(idx, b[:idx + 1], None) or []
                self.assertEqual(full, trunc, "%s @ %d" % (hid, idx))

    def test_sequential_fixed_equals_growing(self):
        b = bars(120)
        by_id = {c.id: c for c in G.ALL}
        for hid in sorted(by_id):
            ia, ib = by_id[hid](), by_id[hid]()
            for idx in range(len(b)):
                self.assertEqual(ia.signals(idx, b, None) or [],
                                 ib.signals(idx, b[:idx + 1], None) or [],
                                 "%s @ %d" % (hid, idx))


class TestNBOMechanics(unittest.TestCase):
    def test_fill_at_next_open(self):
        b = []
        for i in range(60):
            c = 100.0 if i < 12 else 100.0 + (i - 11) * 1.0
            b.append({"time": 1787000000 + 60 * i, "open": c, "high": c + 0.5,
                      "low": c - 0.5, "close": c, "volume": 10.0})

        class One:
            id = "NBO-PROBE"

            def signals(self, idx, bars_, ctx):
                if idx == 10:
                    return [{"direction": "BULLISH", "entry": 100.0,
                             "stop": 95.0, "take_profit": 105.0,
                             "setup_id": "NBO-10", "confidence": 80.0}]
                return []

        out = EX.run_candidate(b, One(), "BTCUSDT", cost_key="A")
        self.assertEqual(out["n_signals"], 1)
        self.assertEqual(len(out["orders"]), 1)
        self.assertEqual(out["orders"][0]["entry_execution"], "NEXT_BAR_OPEN")
        self.assertEqual(len(out["trades"]), 1)
        t = out["trades"][0]
        self.assertEqual(t["entry_time"], b[11]["time"])
        self.assertAlmostEqual(t["entry"], b[11]["open"])
        self.assertAlmostEqual(t["gross"] - t["commission"] - t["slippage"], t["net"])

    def test_cost_channels_match_freeze(self):
        from research.phase11f.harness import COST_SCENARIOS_11F
        self.assertEqual(set(COST_SCENARIOS_11F), {"A", "B", "C", "D"})
        self.assertAlmostEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)


if __name__ == "__main__":
    unittest.main()
