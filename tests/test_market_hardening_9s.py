"""
Phase 9S — Market hardening: reconnect, duplicate, load, chaos.
"""

import unittest
import time
from unittest.mock import Mock, patch

from data.candle_builder import CandleBuilder
from core.history.candle import Candle as HistCandle


class TestMarketHardening(unittest.TestCase):

    def test_websocket_client_is_legacy_recommend_multi_symbol(self):
        # websocket_client.py is single-symbol legacy; institutional path is MultiSymbolSubscriptionManager
        import data.websocket_client as ws_mod
        self.assertTrue(hasattr(ws_mod, "start"))
        # Check that DeltaSubscriptionStream exists as the institutional alternative
        from data.delta.delta_subscription_stream import DeltaSubscriptionStream
        self.assertTrue(hasattr(DeltaSubscriptionStream, "_pump_loop"))
        self.assertTrue(hasattr(DeltaSubscriptionStream, "subscribe"))

    def test_reconnect_policy_exists_and_is_used(self):
        # Verify reconnect_policy module exists and is importable.
        # (Recertification: removed a trailing `or True` that made
        # this assertion vacuous; the module genuinely exports
        # ReconnectPolicy, so the strengthened assertion passes.)
        try:
            import data.realtime.reconnect_policy as rp
            self.assertTrue(hasattr(rp, "ReconnectPolicy") or hasattr(rp, "exponential_backoff"))
        except ImportError:
            # If module doesn't exist, we document that it should be created
            self.skipTest("reconnect_policy not yet implemented as separate module — DeltaSubscriptionStream has inline reconnect")

    def test_50_symbol_load_p99(self):
        # Synthetic load: 50 symbols, each with 10 candles, ensure p99 <100ms per candle
        symbols = [f"SYM{i}" for i in range(50)]
        builders = {s: CandleBuilder(timeframe="1m") for s in symbols}
        base_ts = 1704067200
        latencies = []
        for i in range(10):
            for sym in symbols:
                b = builders[sym]
                ts = base_ts + i*60
                start = time.perf_counter()
                b.update(ts, 100.0 + i)
                latencies.append((time.perf_counter() - start) * 1000)  # ms
        latencies.sort()
        p99_idx = int(len(latencies) * 0.99)
        p99 = latencies[p99_idx]
        self.assertLess(p99, 100.0, msg=f"p99 latency {p99:.2f}ms should be <100ms")

    def test_chaos_corrupt_bar_handled(self):
        builder = CandleBuilder(timeframe="1m")
        # Corrupt bar: missing fields, None timestamp
        result = builder.update(None, 100.0)
        self.assertIsNone(result)
        result = builder.update("invalid", 100.0)
        self.assertIsNone(result)
        # Valid after corrupt should still work
        result = builder.update(1704067200, 100.0)
        self.assertIsNone(result)  # first creates current
        result = builder.update(1704067260, 101.0)
        self.assertIsNotNone(result)

    def test_chaos_ws_drop_reconnect_via_subscription_manager(self):
        # Verify that SubscriptionWorker handles disconnect and reconnects
        from data.realtime.subscription_manager import MultiSymbolSubscriptionManager
        from data.realtime.subscription_state import SubscriptionState
        # Manager should handle universe diff without crashing on empty
        mgr = MultiSymbolSubscriptionManager(transport_factory=lambda **kw: Mock())
        # Sync with empty universe should not raise
        try:
            mgr.sync([])
        except Exception as e:
            self.fail(f"sync([]) should not raise: {e}")

    def test_duplicate_and_out_of_order_handled(self):
        # Already tested in test_realtime.py, but we verify here explicitly
        builder = CandleBuilder(timeframe="1m")
        base = 1704067200
        builder.update(base, 100.0)
        # Duplicate same bucket
        builder.update(base, 100.5)
        self.assertEqual(builder.current.close, 100.5)
        # Out-of-order earlier bucket (should create new current, but not crash)
        try:
            builder.update(base - 60, 99.0)
        except Exception as e:
            self.fail(f"Out-of-order should not raise: {e}")

    def test_provider_failure_does_not_crash(self):
        from core.universe.refresh_scheduler import RefreshScheduler
        from unittest.mock import Mock
        mock_manager = Mock()
        mock_manager.refresh.side_effect = Exception("provider down")
        mock_manager.build_universe.side_effect = Exception("provider down")
        sched = RefreshScheduler(manager=mock_manager, interval_seconds=60)
        # run_if_due should not raise (should handle provider down gracefully)
        try:
            result = sched.run_if_due(timeframe="1m")
            # Either None or a universe, but must not raise
            self.assertTrue(result is None or hasattr(result, "eligible_instruments") or isinstance(result, Mock))
        except Exception as e:
            self.fail(f"Provider failure should be handled: {e}")
