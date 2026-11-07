"""11G-J determinism, quality, seal, provenance tests (no network)."""

import unittest
from pathlib import Path

from research.phase11g_j.replay import engine as ENG
from research.phase11g_j.tests import fixtures as FX

J = Path("research/phase11g_j")


class TestDeterminism(unittest.TestCase):
    def test_replay_twice_identical(self):
        a = ENG.TradeReplay(FX.GOLDEN)
        b = ENG.TradeReplay(list(FX.GOLDEN))
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertEqual(a.cvd(), b.cvd())
        self.assertEqual(a.delta(FX.T0 + 3, window="prefix"),
                         b.delta(FX.T0 + 3, window="prefix"))

    def test_no_uncontrolled_randomness(self):
        for rel in ("replay/events.py", "replay/engine.py", "replay/load.py"):
            src = (J / rel).read_text()
            for token in ("random.", "os.urandom", "uuid", "time.time()",
                          "datetime.now"):
                self.assertNotIn(token, src, rel)


class TestQuality11GJ(unittest.TestCase):
    def test_golden_clean(self):
        from research.phase11g.validation import quality as Q
        evts = [t.to_canonical() for t in FX.GOLDEN]
        accepted, rejected = Q.validate_trades(evts)
        self.assertEqual(len(accepted), 5)
        self.assertEqual(rejected, [])

    def test_gap_semantics(self):
        from research.phase11g.validation import quality as Q
        # Absence of trades is not a gap: sparse minutes compare fine.
        self.assertEqual(Q.detect_gaps([0, 60, 120], 60), [])
        self.assertEqual(Q.detect_gaps([0, 180], 60),
                         [{"after": 0, "missing": 2}])

    def test_malformed_rejected(self):
        from research.phase11g.events import canonical as EV
        from research.phase11g.validation import quality as Q
        bad = EV.TradeEvent(symbol="", event_timestamp=None, price=0.0,
                            quantity=-1.0, side="sideways", trade_id="z",
                            source="s")
        _, rejected = Q.validate_trades([bad])
        reasons = set(rejected[0]["reason"])
        self.assertTrue({"missing-timestamp", "impossible-price",
                         "non-positive-quantity"} <= reasons)


class TestSeal11GJ(unittest.TestCase):
    def test_d3_counters_zero(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})

    def test_no_d3_io_in_new_modules(self):
        for rel in ("replay/events.py", "replay/engine.py", "replay/load.py"):
            for line in (J / rel).read_text().splitlines():
                if "D3" in line:
                    self.assertNotIn("open(", line, rel)

    def test_production_isolation(self):
        for rel in ("replay/events.py", "replay/engine.py", "replay/load.py"):
            src = (J / rel).read_text()
            for token in ("place_order", "submit_order", "ALLOW_LIVE",
                          "LIVE_EXECUTE", "DELTA_API_KEY"):
                self.assertNotIn(token, src, rel)

    def test_live_still_disabled(self):
        from config.settings import settings
        self.assertFalse(settings.ALLOW_LIVE)
        self.assertFalse(settings.LIVE_EXECUTE)


if __name__ == "__main__":
    unittest.main()
