"""11G-I acquisition/normalization tests (no network; literal micro-samples)."""

import unittest

from research.phase11g.events import canonical as EV
from research.phase11g.normalization import normalize as NZ
from research.phase11g.provenance import model as PM
from research.phase11g.validation import quality as Q
from research.phase11g_i import normalize_binance as NB

# Literal REAL-shaped micro-sample (hand-written, not fetched).
SAMPLE = [
    {"agg_trade_id": 1, "price": "100.5", "quantity": "2.0",
     "first_trade_id": 1, "last_trade_id": 1,
     "transact_time": 1788566400003000, "is_buyer_maker": False},
    {"agg_trade_id": 2, "price": "100.4", "quantity": "1.0",
     "first_trade_id": 2, "last_trade_id": 2,
     "transact_time": 1788566400500000, "is_buyer_maker": True},
]


def _events(rows=None):
    out = []
    for r in (rows if rows is not None else SAMPLE):
        out.append(EV.TradeEvent(
            symbol="BTCUSDT", event_timestamp=NB.parse_timestamp_us(r["transact_time"]),
            price=float(r["price"]), quantity=float(r["quantity"]),
            side=NB.side_from_buyer_maker(r["is_buyer_maker"]),
            trade_id=str(r["agg_trade_id"]),
            source="unit-literal", provenance="REAL"))
    return out


class TestAggressorMapping(unittest.TestCase):
    def test_buyer_maker_means_sell_aggressor(self):
        self.assertEqual(NB.side_from_buyer_maker(True), "sell")
        self.assertEqual(NB.side_from_buyer_maker(False), "buy")
        self.assertEqual(NB.side_from_buyer_maker("True"), "sell")
        with self.assertRaises(ValueError):
            NB.side_from_buyer_maker("maybe")

    def test_microsecond_timestamps(self):
        self.assertEqual(NB.parse_timestamp_us(1788566400003000), 1788566400003)
        self.assertEqual(NB.parse_timestamp_us(1788566400003), 1788566400003)

    def test_sample_sides(self):
        evts = _events()
        self.assertEqual([e.side for e in evts], ["buy", "sell"])
        self.assertEqual([e.event_timestamp for e in evts],
                         [1788566400003, 1788566400500])


class TestSampleQuality(unittest.TestCase):
    def test_clean_sample(self):
        accepted, rejected = Q.validate_trades(_events())
        self.assertEqual(len(accepted), 2)
        self.assertEqual(rejected, [])

    def test_duplicate_id_rejected(self):
        evts = _events() + [_events()[0]]
        _, rejected = Q.validate_trades(evts)
        self.assertIn("duplicate-trade", rejected[0]["reason"])

    def test_bad_price_qty_rejected(self):
        bad = EV.TradeEvent(symbol="X", event_timestamp=1, price=-2.0,
                            quantity=0.0, side="buy", trade_id="z", source="s")
        _, rejected = Q.validate_trades([bad])
        reasons = set(rejected[0]["reason"])
        self.assertTrue({"impossible-price", "non-positive-quantity"} <= reasons)

    def test_missing_side_rejected(self):
        bad = EV.TradeEvent(symbol="X", event_timestamp=1, price=2.0,
                            quantity=1.0, side=None, trade_id="z", source="s")
        _, rejected = Q.validate_trades([bad])
        # side None passes trade-shape validation but fails REAL use:
        from research.phase11g.orderflow import truth as TR
        with self.assertRaises(TR.UnavailableData):
            TR.require_trades([bad])


class TestFootprintOnSample(unittest.TestCase):
    def test_delta_math(self):
        from research.phase11g.orderflow import truth as TR
        evts = _events()
        fp = TR.footprint_for_bar(evts, 1788566400000, 1788566400600)
        self.assertEqual(fp["provenance"], "REAL")
        # buy 2.0 @100.5 bucketed 100.5, sell 1.0 @100.4 bucketed 100.4
        self.assertAlmostEqual(fp["bar_delta"], 2.0 - 1.0)
        self.assertAlmostEqual(fp["bar_volume"], 3.0)
        self.assertEqual(TR.cumulative_delta([fp, fp])[1], 2 * fp["bar_delta"])


class TestMutations11GI(unittest.TestCase):
    def test_mut1_future_trade_backdated(self):
        from research.phase11g.orderflow import truth as TR
        evts = _events()
        t0 = evts[0].event_timestamp
        ref = TR.footprint_for_bar(evts, t0, t0 + 600)["bar_delta"]
        # A trade inside the window MUST move the aggregate (time matters).
        inside = EV.TradeEvent(symbol="BTCUSDT", event_timestamp=t0 + 10,
                               price=1.0, quantity=999.0, side="buy",
                               trade_id="inside", source="s")
        self.assertNotEqual(
            TR.footprint_for_bar(list(evts) + [inside], t0, t0 + 600)["bar_delta"], ref)
        # A trade AFTER bar close MUST NOT leak into this bar (causality).
        future = EV.TradeEvent(symbol="BTCUSDT", event_timestamp=t0 + 600,
                               price=1.0, quantity=999.0, side="buy",
                               trade_id="future", source="s")
        self.assertEqual(
            TR.footprint_for_bar(list(evts) + [future], t0, t0 + 600)["bar_delta"], ref)

    def test_mut4_duplicate_id(self):
        evts = _events() + [_events()[0]]
        _, rejected = Q.validate_trades(evts)
        self.assertTrue(any("duplicate-trade" in r["reason"] for r in rejected))

    def test_mut5_crossed_book(self):
        from research.phase11g.orderflow import book as BK
        book = BK.BookState()
        self.assertTrue(book.apply(EV.BookSnapshotEvent(
            symbol="X", event_timestamp=1, sequence=1,
            bids=[[9.0, 1.0]], asks=[[11.0, 1.0]], source="s")))
        self.assertFalse(book.apply(EV.BookDeltaEvent(
            symbol="X", event_timestamp=2, sequence=2,
            side="bid", price=12.0, quantity=1.0, source="s")))

    def test_mut6_negative_quantity(self):
        from research.phase11g.orderflow import book as BK
        book = BK.BookState()
        self.assertFalse(book.apply(EV.BookDeltaEvent(
            symbol="X", event_timestamp=1, sequence=1,
            side="ask", price=10.0, quantity=-5.0, source="s")))

    def test_mut7_tamper_changes_hash(self):
        rows = [{"a": 1}]
        h1 = PM.content_hash(rows)
        rows[0]["a"] = 2
        self.assertNotEqual(PM.content_hash(rows), h1)

    def test_mut9_proxy_as_real_rejected(self):
        from research.phase11g.orderflow import truth as TR
        self.assertEqual(TR.classify("delta", "ohlcv"), "PROXY")
        self.assertNotEqual(TR.classify("delta", "ohlcv"), "REAL")


class TestSealAndProd11GI(unittest.TestCase):
    def test_d3_still_sealed(self):
        from research.phase11f import datasets as D11F
        from research.phase11g import datasets as D11G
        with self.assertRaises(Exception):
            D11F.load_holdout_candles("probe")
        with self.assertRaises(D11G.SealedHoldoutError):
            D11G.load_holdout("probe")
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)

    def test_no_production_or_live_paths(self):
        from pathlib import Path
        for rel in ("acquisition/fetch_binance.py", "normalize_binance.py",
                    "certify_11gi.py"):
            src = (Path("research/phase11g_i") / rel).read_text()
            for token in ("place_order", "submit_order", "ALLOW_LIVE",
                          "LIVE_EXECUTE", "DELTA_API_KEY", "DELTA_API_SECRET"):
                self.assertNotIn(token, src, rel)

    def test_no_network_in_tests(self):
        from pathlib import Path
        import re
        # Network CALL patterns (module path mentions like
        # "acquisition/fetch_binance.py" are legitimate references).
        patterns = [r"httpx\s*\.", r"requests\s*\.", r"urlopen\s*\(",
                    r"from\s+\S*fetch_binance", r"import\s+\S*fetch_binance",
                    r"candles_paginated\s*\("]
        for name in Path("research/phase11g_i/tests").glob("test_*.py"):
            src = name.read_text()
            for pat in patterns:
                self.assertIsNone(re.search(pat, src), "%s: %s" % (name.name, pat))


if __name__ == "__main__":
    unittest.main()
