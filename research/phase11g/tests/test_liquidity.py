"""11G-A liquidity tests (sessions, pools, sweeps)."""

import unittest

from research.phase11g.features import liquidity as L
from research.phase11g.tests.test_feature_contracts import bars


def _two_days():
    out = []
    t0 = 1787000000 // 86400 * 86400
    for d in range(2):
        for m in range(60):
            t = t0 + d * 86400 + m * 60
            out.append({"time": t, "open": 100, "high": 105, "low": 95,
                        "close": 100, "volume": 10.0})
    out[30] = dict(out[30], high=110.0)
    return out


class TestLiquidity(unittest.TestCase):
    def test_prior_session_unavailable_first_day(self):
        sess = L.session_levels(_two_days())
        self.assertFalse(sess[0]["value"]["prior_available"])
        self.assertTrue(sess[60]["value"]["prior_available"])
        self.assertAlmostEqual(sess[60]["value"]["prior_high"], 110.0)

    def test_session_running_uses_prefix_only(self):
        b = _two_days()
        sess = L.session_levels(b)
        self.assertAlmostEqual(sess[59]["value"]["session_volume"], 600.0)
        self.assertAlmostEqual(sess[119]["value"]["session_volume"], 600.0)

    def test_pool_refs_confirmed_only(self):
        b = bars(200)
        for i, r in enumerate(L.reference_pools(b)):
            for ref in r["value"]:
                self.assertLessEqual(ref["confirmed_time"], b[i]["time"])

    def test_sweep_representation_fields(self):
        b = bars(200)
        for r in L.sweep_events(b):
            if r["status"] == "OK":
                v = r["value"]
                for k in ("direction", "level", "extreme", "penetration_atr",
                          "reference_type"):
                    self.assertIn(k, v)
                self.assertGreaterEqual(v["penetration_atr"], 0.0)

    def test_session_sweep_needs_prior(self):
        sess_bars = _two_days()
        n = sum(1 for r in L.session_sweep_events(sess_bars) if r["status"] == "OK")
        self.assertGreaterEqual(n, 0)
        early = L.session_sweep_events(sess_bars[:30])
        self.assertTrue(all(r["status"] != "OK" for r in early))


if __name__ == "__main__":
    unittest.main()
