"""11G-A shared builders + contract conformance for all modules."""

import math
import unittest

from research.phase11g.features import (
    breaker as B, confluence as CF, displacement as D, fibonacci as FB,
    fvg as G, liquidity as L, mitigation as M, mtf as T, orderblock as O,
    structure as S, volume as V, wyckoff as W,
)


def bars(n=200, start=1787000000, base=100.0, amp=3.0):
    out, prev = [], base
    for i in range(n):
        c = base + amp * math.sin(i / 5.0)
        out.append({"time": start + 60 * i, "open": prev,
                    "high": max(prev, c) + 0.5, "low": min(prev, c) - 0.5,
                    "close": c, "volume": 10.0 + (i % 7)})
        prev = c
    return out


ALL_SERIES = lambda b: [
    S.swing_series(b), S.trend_state(b), S.bos_events(b), S.choch_events(b),
    S.range_state(b), L.session_levels(b), L.reference_pools(b),
    L.sweep_events(b), L.session_sweep_events(b), D.displacement(b),
    D.consecutive_bars(b), G.fvg_zones(b), O.order_block_series(b, "long"),
    B.breaker_events(b), V.rolling_stats(b), V.volume_regime(b),
    V.expansion(b), W.springs(b), W.upthrusts(b), W.secondary_tests(b),
    W.signs_of_strength(b), FB.retracements(b), FB.extensions(b),
    FB.confluence(b),
]


class TestContractConformance(unittest.TestCase):
    def test_schema_and_timestamp_order(self):
        b = bars()
        n = 0
        for series in ALL_SERIES(b):
            self.assertEqual(len(series), len(b))
            for i, r in enumerate(series):
                n += 1
                self.assertIn(r["status"], ("OK", "INSUFFICIENT_HISTORY", "NO_EVENT"))
                self.assertTrue(r["causal"])
                self.assertIn(r["provenance"], ("REAL", "PROXY", "UNAVAILABLE"))
                if r["status"] == "OK":
                    self.assertIsNotNone(r["availability_time"])
                    self.assertLessEqual(r["availability_time"], b[i]["time"])
                    if r["confirmation_time"] is not None:
                        self.assertGreaterEqual(r["availability_time"],
                                                r["confirmation_time"])
                    if r["formation_time"] is not None and r["confirmation_time"] is not None:
                        self.assertLessEqual(r["formation_time"], r["confirmation_time"])
        self.assertGreater(n, 4000)

    def test_no_scores_or_trades_anywhere(self):
        import json
        b = bars(120)
        blob = json.dumps([r for s in ALL_SERIES(b) for r in s], default=str).lower()
        for token in ("setup_id", "take_profit", "stop_loss", "quantity",
                      "score", "weight"):
            self.assertNotIn(token, blob)


if __name__ == "__main__":
    unittest.main()
