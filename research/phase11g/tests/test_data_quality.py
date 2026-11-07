"""11G-E data-quality + provenance tests."""

import unittest

from research.phase11g.events import canonical as EV
from research.phase11g.provenance import model as PM
from research.phase11g.validation import quality as Q


def _candle(ts, o=1.0, h=2.0, l=0.5, c=1.5, v=3.0, symbol="X"):
    return EV.CandleEvent(symbol=symbol, event_timestamp=ts, open=o, high=h,
                          low=l, close=c, volume=v, source="s")


class TestQuality(unittest.TestCase):
    def test_clean_accepted(self):
        evts = [_candle(1), _candle(2), _candle(3)]
        accepted, rejected = Q.validate_candles(evts)
        self.assertEqual(len(accepted), 3)
        self.assertEqual(rejected, [])

    def test_duplicate_out_of_order_impossible(self):
        evts = [_candle(1), _candle(1), _candle(0),
                _candle(4, o=-1.0), _candle(5, h=0.1, l=5.0)]
        accepted, rejected = Q.validate_candles(evts)
        reasons = {r for x in rejected for r in x["reason"]}
        self.assertIn("duplicate-timestamp", reasons)
        self.assertIn("out-of-order", reasons)
        self.assertIn("impossible-price", reasons)
        self.assertIn("malformed-ohlc", reasons)
        self.assertEqual(len(accepted), 1)

    def test_non_finite_rejected(self):
        evts = [_candle(1, c=float("nan"))]
        accepted, rejected = Q.validate_candles(evts)
        self.assertEqual(accepted, [])
        self.assertIn("non-finite-close", rejected[0]["reason"])

    def test_trade_rules(self):
        good = [EV.TradeEvent(symbol="X", event_timestamp=1, price=10.0,
                              quantity=1.0, side="buy", trade_id="a", source="s")]
        accepted, _ = Q.validate_trades(good)
        self.assertEqual(len(accepted), 1)
        bad = [EV.TradeEvent(symbol="X", event_timestamp=1, price=10.0,
                             quantity=1.0, side="buy", trade_id="a", source="s"),
               EV.TradeEvent(symbol="X", event_timestamp=2, price=-5.0,
                             quantity=0.0, side="buy", trade_id="a", source="s")]
        _, rejected = Q.validate_trades(bad)
        reasons = {r for x in rejected for r in x["reason"]}
        self.assertIn("duplicate-trade", reasons)
        self.assertIn("impossible-price", reasons)
        self.assertIn("non-positive-quantity", reasons)

    def test_gaps_and_report(self):
        self.assertEqual(Q.detect_gaps([0, 60, 180], 60),
                         [{"after": 60, "missing": 1}])
        evts = [_candle(1), _candle(1)]
        accepted, rejected = Q.validate_candles(evts)
        rep = Q.quality_report(accepted, rejected, symbol="X", resolution="1m")
        self.assertEqual(rep["total_events"], 2)
        self.assertEqual(rep["accepted_events"], 1)
        self.assertEqual(rep["duplicates"], 1)
        self.assertEqual(rep["timestamp_range"], [1, 1])


class TestProvenance(unittest.TestCase):
    def _rec(self, **over):
        base = {k: "v" for k in PM.PROVENANCE_FIELDS}
        base.update({"freshness_verdict": "FRESH", "measurement_class": "REAL",
                     "row_count": 1, "content_hash": "a", "raw_file_hash": "b",
                     "transformation_hash": "c"})
        base.update(over)
        return base

    def test_build_and_hash(self):
        rec = PM.build_provenance(**self._rec())
        self.assertEqual(rec["freshness_verdict"], "FRESH")
        h1 = PM.content_hash([{"a": 1}])
        h2 = PM.content_hash([{"a": 2}])
        self.assertNotEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        t1 = PM.transformation_hash("d", "v1")
        self.assertNotEqual(t1, PM.transformation_hash("d", "v2"))

    def test_missing_and_invalid_rejected(self):
        bad = self._rec()
        del bad["symbol"]
        with self.assertRaises(ValueError):
            PM.build_provenance(**bad)
        with self.assertRaises(ValueError):
            PM.build_provenance(**self._rec(freshness_verdict="MAYBE"))
        with self.assertRaises(ValueError):
            PM.build_provenance(**self._rec(measurement_class="REALISH"))


if __name__ == "__main__":
    unittest.main()
