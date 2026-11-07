"""Post-reconnect candle session gate tests."""

import unittest

from data.delta.candle_session_gate import CandleSessionGate


class TestCandleSessionGate(unittest.TestCase):
    def test_socket_open_is_not_a_resynchronization(self):
        gate = CandleSessionGate("1m")
        gate.on_connected()
        self.assertFalse(gate.status()["ready"])
        self.assertEqual(gate.observe_candle_start(1_700_000_000).reason, "forming baseline observed")
        self.assertFalse(gate.status()["ready"])
        decision = gate.observe_candle_start(1_700_000_060)
        self.assertTrue(decision.accepted)
        self.assertTrue(decision.ready)

    def test_disconnect_revokes_readiness_until_new_rollover(self):
        gate = CandleSessionGate("1m")
        gate.on_connected()
        gate.observe_candle_start(1_700_000_000)
        gate.observe_candle_start(1_700_000_060)
        gate.on_disconnected()
        self.assertFalse(gate.status()["ready"])
        self.assertFalse(gate.observe_candle_start(1_700_000_120).accepted)
        gate.on_connected()
        gate.observe_candle_start(1_700_000_120)
        self.assertFalse(gate.status()["ready"])
        self.assertTrue(gate.observe_candle_start(1_700_000_180).ready)

    def test_gap_or_out_of_order_frame_fails_closed(self):
        gate = CandleSessionGate("1m")
        gate.on_connected()
        gate.observe_candle_start(1_700_000_000)
        self.assertFalse(gate.observe_candle_start(1_700_000_120).accepted)
        self.assertFalse(gate.status()["ready"])
        self.assertFalse(gate.observe_candle_start(1_700_000_060).accepted)
        self.assertFalse(gate.status()["ready"])

    def test_missing_start_cannot_synchronize(self):
        gate = CandleSessionGate("1m")
        gate.on_connected()
        decision = gate.observe_candle_start(None)
        self.assertFalse(decision.accepted)
        self.assertFalse(decision.ready)


if __name__ == "__main__":
    unittest.main()
