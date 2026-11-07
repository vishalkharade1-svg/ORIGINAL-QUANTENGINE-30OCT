"""11G-J canonical/aggressor/timestamp/ordering tests (no network)."""

import unittest

from research.phase11g_j.replay import engine as ENG
from research.phase11g_j.replay import events as REV
from research.phase11g_j.tests import fixtures as FX


class TestCanonical(unittest.TestCase):
    def test_fields_and_mapping(self):
        row = {"agg_trade_id": "7", "price": "10.5", "quantity": "2.0",
               "first_trade_id": "7", "last_trade_id": "9",
               "transact_time": 1788566400003, "is_buyer_maker": True}
        t = REV.from_csv_row(row, 4, symbol="BTCUSDT")
        self.assertEqual(t.event_ms, 1788566400003)
        self.assertEqual(t.transact_raw, 1788566400003)
        self.assertEqual(t.source_index, 4)
        self.assertEqual(t.aggressor_side, "sell")
        self.assertEqual(t.first_trade_id, "7")
        self.assertEqual(t.last_trade_id, "9")
        self.assertEqual(t.provenance, "REAL")
        self.assertEqual(t.feature_version, "real-trade-features-v1")
        c = t.to_canonical()
        self.assertEqual(c.price, 10.5)
        self.assertEqual(c.side, "sell")

    def test_ms_timestamps_accepted_garbage_rejected(self):
        row = {"agg_trade_id": "7", "price": "10.5", "quantity": "2.0",
               "first_trade_id": "7", "last_trade_id": "7",
               "transact_time": 1788566400003, "is_buyer_maker": False}
        t = REV.from_csv_row(row, 0)
        self.assertEqual(t.event_ms, 1788566400003)
        bad = dict(row, transact_time=999)
        with self.assertRaises(ValueError):
            REV.from_csv_row(bad, 0)

    def test_bad_side_rejected(self):
        with self.assertRaises(ValueError):
            REV.side_from_buyer_maker("unknown")


class TestAggressor(unittest.TestCase):
    def test_buy_sell_mix(self):
        self.assertEqual(REV.side_from_buyer_maker(False), "buy")
        self.assertEqual(REV.side_from_buyer_maker(True), "sell")


class TestTimestamps(unittest.TestCase):
    def test_collision_audit_shape(self):
        # Collision math on a crafted microsecond series.
        us = [1000000, 1001000, 1001000, 1002500]
        ms = [u // 1000 for u in us]
        self.assertEqual(len(set(ms)), 3)
        self.assertEqual(ms[1], ms[2])

    def test_order_key_total(self):
        a = FX.GOLDEN[0]
        b = FX.GOLDEN[1]
        self.assertLess(a.order_key(), b.order_key())


class TestOrdering(unittest.TestCase):
    def test_deterministic_replay_order(self):
        rev = ENG.TradeReplay(list(reversed(FX.GOLDEN)))
        keys = [t.order_key() for t in rev._trades]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual([t.trade_id for t in rev._trades],
                         ["g1", "g2", "g3", "g4", "g5"])

    def test_prefix_state(self):
        rev = ENG.TradeReplay(FX.GOLDEN)
        self.assertEqual(len(rev.prefix(3)), 3)
        self.assertEqual(len(rev.prefix_before(FX.T0 + 2)), 3)
        self.assertEqual(len(rev.prefix_through(FX.T0 + 2)), 4)


if __name__ == "__main__":
    unittest.main()
