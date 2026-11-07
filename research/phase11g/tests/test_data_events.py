"""11G-E event schema + normalization tests."""

import unittest

from research.phase11g.data import synthetic as SYN
from research.phase11g.events import canonical as EV
from research.phase11g.normalization import normalize as NZ


class TestSchema(unittest.TestCase):
    def test_frozen_types(self):
        self.assertEqual(EV.SCHEMA_VERSION, "11ge-v1")
        self.assertEqual(len(EV.EVENT_TYPES), 8)

    def test_unavailable_stays_none(self):
        t = EV.TradeEvent(symbol="X", event_timestamp=1, source="s")
        self.assertIsNone(t.side)
        self.assertIsNone(t.trade_id)
        q = EV.QuoteEvent(symbol="X", event_timestamp=1, bid=1.0, ask=2.0,
                          source="s")
        self.assertIsNone(q.bid_size)

    def test_round_trip(self):
        e = EV.CandleEvent(symbol="BTCUSDT", event_timestamp=10, open=1.0,
                           high=2.0, low=0.5, close=1.5, volume=3.0,
                           source="s", provenance="REAL")
        d = e.to_dict()
        self.assertEqual(d["close"], 1.5)
        self.assertIsNone(d["receive_timestamp"])
        self.assertEqual(EV.CandleEvent(**{k: v for k, v in d.items()
                                           if k in EV.CandleEvent.__dataclass_fields__}), e)


class TestNormalization(unittest.TestCase):
    def test_candles_real(self):
        rows = [{"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                 "volume": 3.0}]
        out = NZ.normalize_candles(rows, "BTCUSDT")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].provenance, "REAL")
        self.assertEqual(out[0].event_timestamp, 1)

    def test_trades_require_side(self):
        good = [{"time": 1, "price": 10.0, "quantity": 1.0, "side": "buy"}]
        self.assertEqual(len(NZ.normalize_trades(good, "X", "s")), 1)
        bad = [{"time": 1, "price": 10.0, "quantity": 1.0}]
        with self.assertRaises(NZ.DataMissing):
            NZ.normalize_trades(bad, "X", "s")

    def test_quotes_require_bid_ask(self):
        with self.assertRaises(NZ.DataMissing):
            NZ.normalize_quotes([{"time": 1, "bid": 1.0}], "X", "s")

    def test_order_deterministic(self):
        a = EV.TradeEvent(symbol="X", event_timestamp=5, sequence=2, source="s")
        b = EV.TradeEvent(symbol="X", event_timestamp=5, sequence=1, source="s")
        c = EV.CandleEvent(symbol="X", event_timestamp=4, source="s")
        self.assertEqual(NZ.order_stream([a, b, c]), [c, b, a])
        self.assertEqual(NZ.order_stream([a, b, c]), NZ.order_stream([c, a, b]))


if __name__ == "__main__":
    unittest.main()
