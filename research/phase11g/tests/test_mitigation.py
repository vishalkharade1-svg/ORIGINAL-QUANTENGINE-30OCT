"""11G-A mitigation state-machine tests."""

import unittest

from research.phase11g.features import mitigation as M
from research.phase11g.tests.test_feature_contracts import bars


def _flat_touch_zone():
    # SHORT zone 100-105; price starts below at ~90, pushes up: touch
    # at 3, partial at 5, full traverse with close back inside at 6.
    # Flat bars never touch (high < bottom) nor invalidate (close <= top).
    b = []
    for i in range(11):
        b.append({"time": i * 60, "open": 90, "high": 92, "low": 88,
                  "close": 90, "volume": 10.0})
    b[3] = dict(b[3], high=102.0, low=98.0, close=101.0)   # touch
    b[5] = dict(b[5], high=104.5, low=101.0, close=103.0)  # >=50% depth
    b[6] = dict(b[6], high=106.0, low=99.0, close=104.0)   # traverse, hold
    return b


ZONE = (105.0, 100.0, "short")


class TestMitigation(unittest.TestCase):
    def test_state_progression(self):
        b = _flat_touch_zone()
        z = [M.new_zone(*ZONE, 0, 0)]
        states = [row[0]["state"] for row in M.track(b, z)]
        self.assertEqual(states[0], "UNTOUCHED")
        self.assertEqual(states[3], "TOUCHED")
        self.assertEqual(states[5], "PARTIALLY_MITIGATED")
        self.assertEqual(states[6], "MITIGATED")
        self.assertEqual(states[10], "MITIGATED")

    def test_touch_accounting(self):
        b = _flat_touch_zone()
        z = [M.new_zone(*ZONE, 0, 0)]
        row = M.track(b, z)[6][0]
        self.assertEqual(row["first_touch"], 3)
        self.assertGreaterEqual(row["touch_count"], 2)
        self.assertEqual(row["last_touch"], 6)
        self.assertGreaterEqual(row["penetration"], 1.0)

    def test_invalidation_on_close_through(self):
        b = _flat_touch_zone()
        b[8] = dict(b[8], high=99.0, low=95.0, close=96.0)
        z = [M.new_zone(*ZONE, 0, 0)]
        states = [row[0]["state"] for row in M.track(b, z)]
        # Bar 6 already mitigated -> terminal wins over later invalidation.
        self.assertEqual(states[6], "MITIGATED")
        z2 = [M.new_zone(*ZONE, 0, 0)]
        b2 = _flat_touch_zone()
        b2[4] = dict(b2[4], high=108.0, low=104.0, close=107.0)
        states2 = [row[0]["state"] for row in M.track(b2, z2)]
        self.assertEqual(states2[4], "INVALIDATED")

    def test_future_touch_cannot_change_history(self):
        b = _flat_touch_zone()
        z = [M.new_zone(*ZONE, 0, 0)]
        ref = [row[0]["state"] for row in M.track(b, z)]
        wild = [dict(x) for x in b] + [
            {"time": 660 + 60 * k, "open": 200, "high": 300,
             "low": 50, "close": 250, "volume": 999.0} for k in range(5)]
        got = [row[0]["state"] for row in M.track(wild, z)]
        self.assertEqual(got[:len(b)], ref)

    def test_pre_confirmation_pending(self):
        b = bars(60)
        z = [M.new_zone(105.0, 100.0, "long", 40, 50)]
        rows = M.track(b, z)
        self.assertTrue(rows[30][0].get("pending"))
        self.assertFalse(rows[55][0].get("pending", False))


if __name__ == "__main__":
    unittest.main()
