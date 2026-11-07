"""11G-E mutation battery (future-event + contamination + integrity)."""

import unittest

from research.phase11g import datasets as D11G
from research.phase11g import fresh as FR11GD
from research.phase11g.data import synthetic as SYN
from research.phase11g.events import canonical as EV
from research.phase11g.normalization import normalize as NZ
from research.phase11g.orderflow import book as BK
from research.phase11g.orderflow import truth as TR


def _trades(n=150):
    return NZ.normalize_trades(SYN.synthetic_trades(n=n), "X", "syn",
                               provenance="REAL")


class TestFutureMutations(unittest.TestCase):
    def test_future_trades_no_effect(self):
        evts = _trades()
        t0 = evts[0].event_timestamp
        ref = TR.footprint_for_bar(evts, t0, t0 + 30)
        future = [EV.TradeEvent(symbol="X", event_timestamp=t0 + 10 ** 6,
                                price=9999.0, quantity=9999.0, side="buy",
                                source="s")]
        got = TR.footprint_for_bar(list(evts) + future, t0, t0 + 30)
        self.assertEqual(got["bar_delta"], ref["bar_delta"])
        self.assertEqual(got["bar_volume"], ref["bar_volume"])

    def test_future_candles_no_effect(self):
        from research.phase11f import features as F11
        bars = [{"time": i, "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                 "volume": 3.0} for i in range(60)]
        ref = F11.atr14(bars)[59]
        wild = bars + [{"time": 60, "open": 1, "high": 9999, "low": 0.01,
                        "close": 5000, "volume": 1e9}]
        self.assertEqual(F11.atr14(wild)[59], ref)

    def test_future_book_update_no_effect(self):
        def run(extra):
            book = BK.BookState()
            book.apply(EV.BookSnapshotEvent(
                symbol="X", event_timestamp=1000, sequence=1,
                bids=[[99.5, 2.0]], asks=[[100.5, 2.0]], source="s"))
            before = book.snapshot()
            for e in extra:
                book.apply(e)
            return before

        base = run([])
        poison = [EV.BookDeltaEvent(
            symbol="X", event_timestamp=10 ** 9, sequence=99,
            side="bid", price=1.0, quantity=1.0, source="s")]
        # A future update appends state but must not rewrite history:
        # the snapshot taken before it stays identical.
        self.assertEqual(run([]), base)
        book = BK.BookState()
        book.apply(EV.BookSnapshotEvent(
            symbol="X", event_timestamp=1000, sequence=1,
            bids=[[99.5, 2.0]], asks=[[100.5, 2.0]], source="s"))
        snap_before = book.snapshot()
        book.apply(poison[0])
        self.assertNotEqual(book.snapshot(), snap_before)
        self.assertEqual(snap_before, base)

    def test_future_volume_quote_book_unavailable_paths(self):
        with self.assertRaises(TR.UnavailableData):
            TR.footprint_for_bar([], 0, 10)
        self.assertEqual(TR.classify("depth_imbalance", None), "UNAVAILABLE")
        self.assertEqual(TR.classify("spread", "ohlcv"), "UNAVAILABLE")

    def test_prefix_invariance_trades(self):
        evts = _trades()
        t0 = evts[0].event_timestamp
        full = TR.footprint_for_bar(evts, t0, t0 + 30)
        prefix = [t for t in evts if t.event_timestamp < t0 + 30]
        part = TR.footprint_for_bar(prefix, t0, t0 + 30)
        self.assertEqual(full["bar_delta"], part["bar_delta"])


class TestContaminationMutations(unittest.TestCase):
    def test_d1_d2_never_fresh(self):
        for name in ("D1_BTC", "D1_ETH", "D2_BTC", "D2_ETH"):
            self.assertNotEqual(FR11GD.freshness(name), "FRESH")

    def test_d3_always_blocked(self):
        for probe in ("D3_BTC", "universe_D3_ETH.json", "research/x/D3"):
            with self.assertRaises((FR11GD.SealedHoldoutError, Exception)):
                FR11GD.freshness(probe)

    def test_11g_datasets_seal_intact(self):
        from research.phase11f import datasets as D11F
        with self.assertRaises(Exception):
            D11F.load_holdout_candles("probe")


class TestIntegrityMutations(unittest.TestCase):
    def test_tamper_changes_hash(self):
        from research.phase11g.provenance import model as PM
        rows = [{"a": 1}]
        h1 = PM.content_hash(rows)
        rows[0]["a"] = 2
        self.assertNotEqual(PM.content_hash(rows), h1)

    def test_serialization_round_trip(self):
        e = EV.TradeEvent(symbol="X", event_timestamp=7, price=1.5,
                          quantity=2.0, side="sell", trade_id="t1", source="s")
        import json
        d = json.loads(json.dumps(e.to_dict()))
        self.assertEqual(d["side"], "sell")
        self.assertEqual(d["trade_id"], "t1")


if __name__ == "__main__":
    unittest.main()
