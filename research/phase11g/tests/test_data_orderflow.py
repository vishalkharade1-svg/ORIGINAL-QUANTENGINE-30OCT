"""11G-E order-flow truth + book tests (SYNTHETIC-labeled inputs only)."""

import unittest

from research.phase11g.data import synthetic as SYN
from research.phase11g.events import canonical as EV
from research.phase11g.normalization import normalize as NZ
from research.phase11g.orderflow import book as BK
from research.phase11g.orderflow import truth as TR


def _trades(n=120):
    rows = SYN.synthetic_trades(n=n)
    return NZ.normalize_trades(rows, "X", "synthetic-fixture", provenance="REAL")


class TestTruth(unittest.TestCase):
    def test_classify_matrix(self):
        self.assertEqual(TR.classify("delta", "trades"), "REAL")
        self.assertEqual(TR.classify("cvd", "trades"), "REAL")
        self.assertEqual(TR.classify("footprint", "trades"), "REAL")
        self.assertEqual(TR.classify("absorption", "trades"), "REAL")
        self.assertEqual(TR.classify("imbalance", "quotes"), "REAL")
        self.assertEqual(TR.classify("spread", "quotes"), "REAL")
        self.assertEqual(TR.classify("depth_imbalance", "book"), "REAL")
        self.assertEqual(TR.classify("delta", "ohlcv"), "PROXY")
        self.assertEqual(TR.classify("delta", None), "UNAVAILABLE")
        self.assertEqual(TR.classify("spread", "ohlcv"), "UNAVAILABLE")
        with self.assertRaises(ValueError):
            TR.classify("magic", "trades")

    def test_require_trades_refuses_candles(self):
        with self.assertRaises(TR.UnavailableData):
            TR.require_trades([])
        with self.assertRaises(TR.UnavailableData):
            TR.footprint_for_bar(
                [EV.CandleEvent(symbol="X", event_timestamp=1, source="s")], 0, 10)

    def test_footprint_cvd(self):
        evts = _trades()
        t0 = evts[0].event_timestamp
        fp = TR.footprint_for_bar(evts, t0, t0 + 30)
        self.assertEqual(fp["provenance"], "REAL")
        self.assertAlmostEqual(fp["bar_delta"],
                               sum(l["delta"] for l in fp["levels"].values()))
        self.assertAlmostEqual(fp["bar_volume"],
                               sum(l["total"] for l in fp["levels"].values()))
        self.assertGreaterEqual(fp["n_trades"], 0)
        cvd = TR.cumulative_delta([fp, fp])
        self.assertEqual(cvd[1], 2 * fp["bar_delta"])

    def test_diagonal_and_absorption(self):
        lv = {100.0: {"buy": 9.0, "sell": 1.0}, 100.5: {"buy": 1.0, "sell": 1.0}}
        hits = TR.diagonal_imbalance(lv, ratio=3.0)
        self.assertIn((100.0, "bullish"), hits)
        evts = _trades()
        t0 = evts[0].event_timestamp
        absorb = TR.absorption_candidates(evts, t0, t0 + 60)
        self.assertIn("high_volume", absorb)

    def test_synthetic_label_present(self):
        rows = SYN.synthetic_trades(n=5)
        self.assertTrue(all(r["synthetic"] is True for r in rows))
        self.assertEqual(SYN.SYNTHETIC, "SYNTHETIC")
        self.assertEqual(SYN.synthetic_trades(n=5), SYN.synthetic_trades(n=5))


class TestBook(unittest.TestCase):
    def _feed(self, book, updates):
        for u in updates:
            if u["kind"] == "snapshot":
                book.apply(EV.BookSnapshotEvent(
                    symbol="X", event_timestamp=u["time"], sequence=u["sequence"],
                    bids=u["bids"], asks=u["asks"], source="syn"))
            else:
                book.apply(EV.BookDeltaEvent(
                    symbol="X", event_timestamp=u["time"], sequence=u["sequence"],
                    side=u["side"], price=u["price"], quantity=u["quantity"],
                    source="syn"))

    def test_reconstruction(self):
        book = BK.BookState()
        self._feed(book, SYN.synthetic_book_updates())
        snap = book.snapshot()
        self.assertAlmostEqual(snap["best_bid"], 99.5)
        self.assertAlmostEqual(snap["best_ask"], 100.0)
        self.assertEqual(book.rejections, [])

    def test_duplicate_out_of_order_missing(self):
        book = BK.BookState()
        self._feed(book, SYN.synthetic_book_updates())
        n_ok = len(book.rejections)
        book.apply(EV.BookDeltaEvent(symbol="X", event_timestamp=1004, sequence=4,
                                     side="bid", price=99.0, quantity=1.0, source="s"))
        book.apply(EV.BookDeltaEvent(symbol="X", event_timestamp=1000, sequence=5,
                                     side="bid", price=99.0, quantity=1.0, source="s"))
        book.apply(EV.BookDeltaEvent(symbol="X", event_timestamp=1006, sequence=9,
                                     side="bid", price=99.0, quantity=1.0, source="s"))
        reasons = {r for x in book.rejections[n_ok:] for r in x["reason"]}
        self.assertIn("duplicate-update", reasons)
        self.assertIn("stale-book", reasons)
        self.assertIn("missing-update", reasons)

    def test_crossed_rejected_unapplied(self):
        book = BK.BookState()
        self._feed(book, SYN.synthetic_book_updates())
        before = book.snapshot()
        ok = book.apply(EV.BookDeltaEvent(symbol="X", event_timestamp=1005, sequence=5,
                                          side="bid", price=200.0, quantity=1.0,
                                          source="s"))
        self.assertFalse(ok)
        self.assertEqual(book.snapshot(), before)
        self.assertIn("crossed-book", book.rejections[-1]["reason"])

    def test_malformed_rejected(self):
        book = BK.BookState()
        ok = book.apply(EV.BookDeltaEvent(symbol="X", event_timestamp=1, sequence=1,
                                          side="bid", price=-3.0, quantity=1.0,
                                          source="s"))
        self.assertFalse(ok)

    def test_deterministic_twice(self):
        def run():
            b = BK.BookState()
            self._feed(b, SYN.synthetic_book_updates())
            return b.snapshot()
        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()
