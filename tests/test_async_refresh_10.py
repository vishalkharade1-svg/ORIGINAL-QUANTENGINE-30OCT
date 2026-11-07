"""
Phase 10 — Provider non-blocking hardening (Gates 3-7).

Tests that intentionally make the provider extremely slow (2-5s)
and prove that the event loop continues processing.
"""

import time
import threading
import unittest

from core.universe.refresh_scheduler import RefreshScheduler
from core.universe.async_refresh_scheduler import AsyncRefreshScheduler


class SlowManager:
    def __init__(self, delay=2.0, fail=False):
        self.delay = delay
        self.fail = fail
        self.calls = 0
        self.refresh_count = 0
        self.registry = type("R", (), {"executable": lambda self: []})()

    def refresh_discovery(self, **kwargs):
        self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("provider failure")
        return {"ok": True}

    def build_universe(self, timeframe="1m"):
        from core.universe.market_universe import MarketUniverse
        from core.universe.universe_policy import UniversePolicy
        return MarketUniverse(policy=UniversePolicy(), instruments=[])


class TestAsyncNonBlocking(unittest.TestCase):

    def test_slow_provider_does_not_block_event_loop(self):
        # Gate 3A,B,C,D
        mgr = SlowManager(delay=2.0)
        base = RefreshScheduler(manager=mgr, interval_seconds=0, clock=time.time)
        async_sched = AsyncRefreshScheduler(base)

        start = time.time()
        # This should return immediately (non-blocking), not wait 2s
        result = async_sched.run_if_due()
        elapsed = time.time() - start
        self.assertIsNone(result)  # No universe yet, refresh in background
        self.assertLess(elapsed, 0.5, msg=f"run_if_due blocked for {elapsed:.2f}s, should be <0.5s")
        self.assertTrue(async_sched.refresh_in_progress)

        # Event loop should continue processing (simulate poll loop)
        poll_latencies = []
        for _ in range(5):
            t0 = time.perf_counter()
            # Simulate poll that checks scheduler but doesn't block
            async_sched.run_if_due()
            poll_latencies.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.1)

        # Poll latencies should be <10ms, not 2000ms
        for lat in poll_latencies:
            self.assertLess(lat, 50, msg=f"poll blocked: {lat:.1f}ms")

        # Wait for provider to finish
        time.sleep(2.5)
        self.assertFalse(async_sched.refresh_in_progress)
        self.assertIsNotNone(async_sched.last_universe)
        self.assertIsNone(async_sched.last_refresh_error)

    def test_single_bounded_worker(self):
        # Gate 4: maximum one active refresh, no duplicate workers
        mgr = SlowManager(delay=1.0)
        base = RefreshScheduler(manager=mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base)

        # Call run_if_due 10 times rapidly — should only start one worker
        for _ in range(10):
            async_sched.run_if_due()
            time.sleep(0.05)

        # Only one refresh should have been started
        self.assertEqual(mgr.calls, 1)
        time.sleep(1.5)
        self.assertEqual(mgr.calls, 1)  # still 1, not 10

    def test_cache_preserved_on_failure(self):
        # Gate 5: Failed refresh must not destroy last valid snapshot
        mgr = SlowManager(delay=0.1, fail=False)
        base = RefreshScheduler(manager=mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base)
        # First successful refresh
        async_sched.run_if_due()
        time.sleep(0.3)
        first = async_sched.last_universe
        self.assertIsNotNone(first)

        # Now make next refresh fail
        mgr.fail = True
        mgr.delay = 0.1
        # Need to make scheduler due again (interval 0 means always due, but _in_progress must be false)
        time.sleep(0.2)
        async_sched.run_if_due()
        time.sleep(0.3)
        # Last valid snapshot must still be there, error recorded
        self.assertIsNotNone(async_sched.last_universe)
        self.assertIsNotNone(async_sched.last_refresh_error)

    def test_stale_data_exposed(self):
        mgr = SlowManager(delay=0.1)
        base = RefreshScheduler(manager=mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base)
        async_sched.run_if_due()
        time.sleep(0.3)
        self.assertEqual(async_sched.health(), "HEALTHY")
        # Simulate stale: no refresh for a long time
        async_sched._last_success_time = time.time() - 700
        self.assertEqual(async_sched.health(), "STALE")

    def test_no_lock_held_across_io(self):
        # Gate 6: No lock held across network I/O — deterministic with Events
        # Prove that _lock is NOT held while provider does network I/O
        entered_io = threading.Event()
        proceed_io = threading.Event()
        lock_acquired_during_io = []

        class ControlledManager:
            def __init__(self):
                self.calls = 0
            def refresh_discovery(self, **kwargs):
                self.calls += 1
                entered_io.set()  # signal that we are inside provider I/O
                proceed_io.wait(timeout=5)  # pause inside I/O until test releases
                return {"ok": True}
            def build_universe(self, timeframe="1m"):
                from core.universe.market_universe import MarketUniverse
                from core.universe.universe_policy import UniversePolicy
                return MarketUniverse(policy=UniversePolicy(), instruments=[])

        mgr = ControlledManager()
        base = RefreshScheduler(manager=mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base)

        async_sched.run_if_due()
        # Wait until provider is inside I/O (blocked on proceed_io)
        entered = entered_io.wait(timeout=2)
        self.assertTrue(entered, msg="Provider did not enter I/O within 2s")

        # While provider is paused inside I/O, try to acquire _lock from another thread
        # If lock is held across I/O, this will block/fail
        def try_lock():
            acquired = async_sched._lock.acquire(blocking=False)
            lock_acquired_during_io.append(acquired)
            if acquired:
                async_sched._lock.release()

        t = threading.Thread(target=try_lock)
        t.start()
        t.join(timeout=1)
        self.assertTrue(lock_acquired_during_io, msg="Lock probe never ran")
        self.assertTrue(lock_acquired_during_io[0], msg="Lock was held across provider I/O — must not be")

        # Release provider I/O and let refresh complete
        proceed_io.set()
        time.sleep(0.3)
        self.assertFalse(async_sched.refresh_in_progress)

    def test_refresh_failure_preserves_runtime_continuation(self):
        # Gate 7: Runtime continues processing while provider is slow/fails
        mgr = SlowManager(delay=1.0, fail=True)
        base = RefreshScheduler(manager=mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base)

        # Start with a valid universe
        mgr.fail = False
        mgr.delay = 0.05
        async_sched.run_if_due()
        time.sleep(0.2)
        valid = async_sched.last_universe
        self.assertIsNotNone(valid)

        # Now slow failing refresh
        mgr.fail = True
        mgr.delay = 1.0
        async_sched.run_if_due()
        # While refresh is running/failing, runtime should still be able to poll
        poll_ok = True
        for _ in range(5):
            try:
                # Simulate runtime poll that checks scheduler
                async_sched.run_if_due()
                _ = async_sched.last_universe  # should still be valid
            except Exception:
                poll_ok = False
        self.assertTrue(poll_ok)
        time.sleep(1.5)
        # Previous valid still there
        self.assertIsNotNone(async_sched.last_universe)

    def test_no_unbounded_worker_creation(self):
        mgr = SlowManager(delay=0.5)
        base = RefreshScheduler(manager=mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base)

        # Rapid calls should not create unbounded threads
        initial_threads = threading.active_count()
        for _ in range(20):
            async_sched.run_if_due()
        time.sleep(0.1)
        # Only one worker should have been created
        self.assertEqual(mgr.calls, 1)
        # Thread count should not have exploded
        self.assertLess(threading.active_count() - initial_threads, 5)

    def test_paper_runtime_continues_while_provider_delayed(self):
        # Gate J: PAPER runtime continues processing candles while provider refresh is delayed
        from core.runtime.realtime_engine import RealTimeEngine
        from unittest.mock import Mock

        # Create a slow manager
        slow_mgr = SlowManager(delay=2.0)
        base_sched = RefreshScheduler(manager=slow_mgr, interval_seconds=0)
        async_sched = AsyncRefreshScheduler(base_sched)

        # Create a mock engine that just counts polls
        mock_manager = Mock()
        mock_manager.build_universe.return_value = None
        mock_manager.refresh_discovery.return_value = {}
        # Use async scheduler
        engine = RealTimeEngine(
            universe_manager=mock_manager,
            refresh_scheduler=async_sched,
            subscription_manager=Mock(poll=Mock()),
        )
        engine.start()
        # Poll should not block even though provider is slow
        t0 = time.perf_counter()
        engine.poll()
        elapsed = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed, 100, msg=f"poll blocked for {elapsed:.1f}ms")
        engine.stop()
