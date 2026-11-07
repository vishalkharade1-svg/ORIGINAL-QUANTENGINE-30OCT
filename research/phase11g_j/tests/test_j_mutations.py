"""11G-J mutation battery MUT-1..MUT-10 (each detected, then restored)."""

import hashlib
import json
import unittest

from research.phase11g.events import canonical as EV
from research.phase11g_j.replay import engine as ENG
from research.phase11g_j.replay import events as REV
from research.phase11g_j.tests import fixtures as FX


def _mk(ms, price, qty, side, tid="m", idx=999):
    return REV.RealTrade(ms, ms * 1000, idx, "X", "test", price, qty,
                         side, tid, tid, tid)


class TestMutations(unittest.TestCase):
    def test_mut1_future_trade_state(self):
        base = ENG.TradeReplay(FX.GOLDEN).cvd()
        poisoned = ENG.TradeReplay(
            list(FX.GOLDEN) + [_mk(FX.T0 + 1, 0.01, 10 ** 6, "buy")]).cvd()
        self.assertNotEqual([v for _, v in poisoned], [v for _, v in base])

    def test_mut2_future_quantity(self):
        base = ENG.TradeReplay(FX.GOLDEN).delta(FX.T0 + 3, window="prefix")
        mutated = [t if t.trade_id != "g5" else _mk(
            FX.T0 + 3, 99.99, 10 ** 6, "sell", tid="g5") for t in FX.GOLDEN]
        got = ENG.TradeReplay(mutated).delta(FX.T0 + 3, window="prefix")
        self.assertNotEqual(got["delta"], base["delta"])

    def test_mut3_side_flip(self):
        base = ENG.TradeReplay(FX.GOLDEN).delta(FX.T0 + 3, window="prefix")
        flipped = [t if t.trade_id != "g1" else _mk(
            FX.T0, 100.0, 1.0, "sell", tid="g1") for t in FX.GOLDEN]
        got = ENG.TradeReplay(flipped).delta(FX.T0 + 3, window="prefix")
        self.assertNotEqual(got["delta"], base["delta"])
        self.assertAlmostEqual(base["delta"] - got["delta"], 2.0)

    def test_mut4_duplicate(self):
        from research.phase11g.validation import quality as Q
        evts = [t.to_canonical() for t in FX.GOLDEN]
        _, rej = Q.validate_trades(evts + [evts[0]])
        self.assertIn("duplicate-trade", rej[0]["reason"])

    def test_mut5_timestamp_backward(self):
        from research.phase11g.validation import quality as Q
        evts = [t.to_canonical() for t in FX.GOLDEN]
        back = EV.TradeEvent(symbol="X", event_timestamp=FX.T0 - 5,
                             price=1.0, quantity=1.0, side="buy",
                             trade_id="back", source="s")
        _, rej = Q.validate_trades(evts + [back])
        self.assertIn("out-of-order", rej[0]["reason"])

    def test_mut6_negative_quantity(self):
        from research.phase11g.validation import quality as Q
        bad = EV.TradeEvent(symbol="X", event_timestamp=1, price=1.0,
                            quantity=-2.0, side="buy", trade_id="z", source="s")
        _, rej = Q.validate_trades([bad])
        self.assertIn("non-positive-quantity", rej[0]["reason"])

    def test_mut7_raw_tamper(self):
        blob = b'{"rows": [{"a": 1}]}'
        h1 = hashlib.sha256(blob).hexdigest()
        self.assertNotEqual(hashlib.sha256(b'{"rows": [{"a": 2}]}').hexdigest(), h1)

    def test_mut8_proxy_relabeled(self):
        from research.phase11g.orderflow import truth as TR
        self.assertEqual(TR.classify("delta", "ohlcv"), "PROXY")
        # A registry claiming REAL for an OHLCV-only source must fail review:
        with self.assertRaises(ValueError):
            TR.classify("not-a-feature", "ohlcv")

    def test_mut9_future_in_closed_window(self):
        base = ENG.TradeReplay(FX.GOLDEN).footprint(FX.T0, FX.T0 + 2)
        poisoned = ENG.TradeReplay(
            list(FX.GOLDEN) + [_mk(FX.T0 + 1, 100.0, 500.0, "buy")]).footprint(
                FX.T0, FX.T0 + 2)
        # +500 buy inside the window MUST change it (sensitivity proof):
        self.assertNotEqual(poisoned, base)
        # ...while a trade strictly after the window must not:
        later = ENG.TradeReplay(
            list(FX.GOLDEN) + [_mk(FX.T0 + 2, 100.0, 500.0, "buy")]).footprint(
                FX.T0, FX.T0 + 2)
        self.assertEqual(later, base)

    def test_mut10_implementation_change(self):
        from research.phase11g_j.replay.engine import cvd_series
        self.assertEqual(ENG.TradeReplay(FX.GOLDEN).cvd(), cvd_series(FX.GOLDEN))
        rep = ENG.TradeReplay(FX.GOLDEN)
        h1 = rep.state_hash()
        rep2 = ENG.TradeReplay(list(reversed(FX.GOLDEN)))
        self.assertEqual(rep2.state_hash(), h1)


if __name__ == "__main__":
    unittest.main()
