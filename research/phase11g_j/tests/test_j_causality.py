"""11G-J causality tests (prefix/future-mutation/deletion/sensitivity)."""

import unittest

from research.phase11g_j.replay import engine as ENG
from research.phase11g_j.tests import fixtures as FX


class TestCausality(unittest.TestCase):
    def test_prefix_append_invariance(self):
        base = ENG.TradeReplay(FX.GOLDEN)
        ref = base.delta(FX.T0 + 3, window="prefix")
        extra = list(FX.GOLDEN) + [self._mk(FX.T0 + 100, 50.0, 99.0, "buy")]
        got = ENG.TradeReplay(extra).delta(FX.T0 + 3, window="prefix")
        self.assertEqual(got, ref)

    def test_future_mutation_no_effect(self):
        base = ENG.TradeReplay(FX.GOLDEN)
        ref = base.cvd(end_ms=FX.T0 + 2)
        mutated = [t if t.trade_id != "g5" else self._mk(
            FX.T0 + 3, 999.0, 999.0, "sell", tid="g5") for t in FX.GOLDEN]
        got = ENG.TradeReplay(mutated).cvd(end_ms=FX.T0 + 2)
        self.assertEqual(got, ref)

    def test_future_deletion_no_effect(self):
        base = ENG.TradeReplay(FX.GOLDEN)
        ref = base.cvd(end_ms=FX.T0 + 2)
        pruned = [t for t in FX.GOLDEN if t.event_ms <= FX.T0 + 2]
        got = ENG.TradeReplay(pruned).cvd(end_ms=FX.T0 + 2)
        self.assertEqual(got, ref)

    def test_historical_mutation_detected(self):
        base = ENG.TradeReplay(FX.GOLDEN)
        ref = base.cvd()
        mutated = [self._mk(FX.T0, 100.0, 500.0, "buy", tid="g1")] + list(FX.GOLDEN[1:])
        got = ENG.TradeReplay(mutated).cvd()
        self.assertNotEqual(got, ref)

    def test_footprint_window_isolation(self):
        base = ENG.TradeReplay(FX.GOLDEN)
        ref = base.footprint(FX.T0, FX.T0 + 2)
        later = list(FX.GOLDEN) + [self._mk(FX.T0 + 50, 200.0, 5.0, "sell")]
        got = ENG.TradeReplay(later).footprint(FX.T0, FX.T0 + 2)
        self.assertEqual(got, ref)

    @staticmethod
    def _mk(ms, price, qty, side, tid="m"):
        from research.phase11g_j.replay.events import RealTrade
        return RealTrade(ms, ms * 1000, 999, "X", "test", price, qty,
                         side, tid, tid, tid)


if __name__ == "__main__":
    unittest.main()
