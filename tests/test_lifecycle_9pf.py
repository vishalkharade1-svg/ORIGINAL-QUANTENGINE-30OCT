"""
Phase 9P-f Engine Lifecycle manager tests.

A thin control seam (API -> Command -> Existing Runtime) that owns
the poll thread + lock + state machine and only ever calls the
engine's OWN public start()/stop()/poll() primitives. Verified
against a FakeEngine so no network/exchange is involved.
"""

import unittest

from core.runtime.lifecycle import (
    COMMANDS,
    ControlCommandError,
    EngineLifecycle,
    STATE_FAILED,
    STATE_RUNNING,
    STATE_STOPPED,
)


class FakeEngine:
    """Minimal engine contract the lifecycle drives."""

    def __init__(self):

        self.started = False

        self.start_calls = 0

        self.stop_calls = 0

        self.poll_calls = 0

        self.timeframe = "1m"

    def start(self):

        self.start_calls += 1
        self.started = True

    def stop(self):

        self.stop_calls += 1
        self.started = False

    def poll(self, client=None, normalizer=None):

        self.poll_calls += 1


class FailingEngine(FakeEngine):

    def start(self):

        self.start_calls += 1

        raise RuntimeError("engine refused to start")


class TestLifecycleState(unittest.TestCase):

    def test_initial_state_is_stopped(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        self.assertEqual(life.state, STATE_STOPPED)
        self.assertFalse(life.running())
        self.assertFalse(engine.started)

    def test_start_transitions_and_calls_engine_start(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        state = life.start()

        self.assertEqual(state, STATE_RUNNING)
        self.assertTrue(life.running())
        self.assertTrue(engine.started)
        self.assertEqual(engine.start_calls, 1)

    def test_start_is_idempotent(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()
        life.start()

        self.assertEqual(state := life.state, STATE_RUNNING)
        self.assertEqual(engine.start_calls, 1)

    def test_stop_returns_stopped_and_calls_engine_stop(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()

        state = life.stop()

        self.assertEqual(state, STATE_STOPPED)
        self.assertFalse(life.running())
        self.assertFalse(engine.started)
        self.assertEqual(engine.stop_calls, 1)

    def test_stop_when_already_stopped_is_noop(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        self.assertEqual(life.stop(), STATE_STOPPED)
        self.assertEqual(engine.stop_calls, 0)

    def test_restart_stops_then_starts(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()

        state = life.restart()

        self.assertEqual(state, STATE_RUNNING)
        self.assertEqual(engine.stop_calls, 1)
        self.assertEqual(engine.start_calls, 2)
        self.assertTrue(engine.started)

    def test_emergency_stop_immediately(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()

        state = life.emergency_stop()

        self.assertEqual(state, STATE_STOPPED)
        self.assertFalse(engine.started)
        self.assertEqual(engine.stop_calls, 1)


class TestLifecycleCommands(unittest.TestCase):

    def test_command_allowlist(self):

        self.assertEqual(
            COMMANDS, frozenset(
                {"start", "stop", "restart", "emergency_stop", "pause", "resume"}
            )
        )

    def test_unknown_command_rejected_without_engine_touch(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        with self.assertRaises(ControlCommandError):

            life.command("market_order")  # a non-control verb

        self.assertEqual(engine.start_calls, 0)
        self.assertEqual(engine.stop_calls, 0)
        self.assertEqual(engine.poll_calls, 0)

    def test_command_routes_each_verb(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine)

        # start then stop via the unified command entry
        life.command("start")

        self.assertEqual(life.state, STATE_RUNNING)
        self.assertEqual(engine.start_calls, 1)

        life.command("stop")

        self.assertEqual(life.state, STATE_STOPPED)
        self.assertEqual(engine.stop_calls, 1)


class TestLifecycleHealth(unittest.TestCase):

    def test_health_snapshot_has_expected_fields(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        h = life.health()

        for key in (
            "lifecycle_state",
            "engine_started",
            "poll_interval_seconds",
            "uptime_seconds",
            "polls",
            "control_thread_alive",
            "last_error",
        ):
            self.assertIn(key, h)

        self.assertEqual(h["lifecycle_state"], STATE_STOPPED)
        self.assertFalse(h["engine_started"])

    def test_poll_loop_increments_polls_while_running(self):

        engine = FakeEngine()

        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        life.start()

        # allow the daemon loop to tick a few times
        import time

        deadline = time.time() + 0.3

        while time.time() < deadline and engine.poll_calls < 3:

            time.sleep(0.01)

        self.assertGreaterEqual(engine.poll_calls, 3)

        self.assertGreaterEqual(life.health()["polls"], 3)

        life.stop()

        self.assertEqual(life.state, STATE_STOPPED)


class TestEmergencyStopSemantics(unittest.TestCase):
    """emergency_stop is the HIGH-PRIORITY immediate PAPER shutdown:
    it is semantically distinct from graceful stop and it is
    strictly idempotent (no duplicate shutdown work, no error on a
    second call)."""

    def test_emergency_stop_called_twice_performs_single_shutdown(self):
        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()

        first = life.emergency_stop()

        self.assertEqual(first, STATE_STOPPED)
        self.assertEqual(engine.stop_calls, 1)

        second = life.emergency_stop()

        self.assertEqual(second, STATE_STOPPED)
        # a second emergency_stop must NOT re-run shutdown work
        self.assertEqual(engine.stop_calls, 1)
        self.assertEqual(life.state, STATE_STOPPED)

    def test_emergency_stop_after_graceful_stop_is_noop(self):
        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()

        life.stop()

        self.assertEqual(engine.stop_calls, 1)

        result = life.emergency_stop()

        self.assertEqual(result, STATE_STOPPED)
        self.assertEqual(engine.stop_calls, 1)
        self.assertEqual(life.state, STATE_STOPPED)

    def test_emergency_stop_remaining_stopped_allows_restart(self):
        engine = FakeEngine()

        life = EngineLifecycle(engine)

        life.start()

        life.emergency_stop()

        # remains STOPPED, then a fresh start is still allowed
        self.assertEqual(life.state, STATE_STOPPED)

        life.start()

        self.assertEqual(life.state, STATE_RUNNING)
        self.assertTrue(engine.started)

    def test_emergency_stop_when_not_started_is_noop(self):
        engine = FakeEngine()

        life = EngineLifecycle(engine)

        result = life.emergency_stop()

        self.assertEqual(result, STATE_STOPPED)
        self.assertEqual(engine.stop_calls, 0)
        self.assertEqual(life.state, STATE_STOPPED)


class TestFailureState(unittest.TestCase):
    """A failed engine.start() transitions to a visible FAILED state
    and can be recovered with a subsequent start."""

    def test_start_failure_transitions_to_failed(self):
        engine = FailingEngine()

        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        with self.assertRaises(ControlCommandError):
            life.start()

        self.assertEqual(life.state, STATE_FAILED)
        self.assertFalse(life.running())
        self.assertEqual(life.health()["lifecycle_state"], STATE_FAILED)

    def test_can_recover_from_failed(self):
        engine = FailingEngine()

        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        with self.assertRaises(ControlCommandError):
            life.start()

        # engine healthy now -> start succeeds from FAILED
        engine.start = FakeEngine.start.__get__(engine, FailingEngine)

        state = life.start()

        self.assertEqual(state, STATE_RUNNING)
        self.assertTrue(engine.started)

    def test_stop_from_failed_ends_stopped(self):
        engine = FailingEngine()

        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        with self.assertRaises(ControlCommandError):
            life.start()

        self.assertEqual(life.stop(), STATE_STOPPED)


class FailingEngine2:

    def __init__(self):
        self.started = False

    def start(self):
        raise RuntimeError("boom")

    def stop(self):
        self.started = False

    def poll(self, client=None, normalizer=None):
        pass


class TestWait(unittest.TestCase):

    def test_wait_returns_when_stopped(self):
        engine = FakeEngine()
        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        import threading
        import time

        # wait() BLOCKS only while the lifecycle is RUNNING; it
        # returns once the lifecycle stops.
        life.start()

        result = {}

        def run():
            state = life.wait()
            result["state"] = state

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        time.sleep(0.05)
        self.assertNotIn("state", result)

        life.stop()

        thread.join(timeout=5.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["state"], STATE_STOPPED)

    def test_wait_returns_immediately_as_blocking_command(self):
        engine = FakeEngine()
        life = EngineLifecycle(engine, poll_interval_seconds=0.001)
        # already STOPPED (never started) -> wait() returns at once
        self.assertEqual(life.wait(), STATE_STOPPED)

    def test_wait_releases_after_emergency_stop(self):
        engine = FakeEngine()
        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        import threading
        import time

        result = {}

        def run():
            state = life.wait()
            result["state"] = state

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        life.start()
        time.sleep(0.05)

        life.emergency_stop()

        thread.join(timeout=5.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["state"], STATE_STOPPED)

    def test_wait_returns_on_failed_start(self):
        engine = FailingEngine2()
        life = EngineLifecycle(engine, poll_interval_seconds=0.001)

        with self.assertRaises(ControlCommandError):
            life.start()

        # start failed -> FAILED with the release event set, so a
        # subsequent wait() (e.g. the entrypoint blocker) returns.
        self.assertEqual(life.wait(), STATE_FAILED)


if __name__ == "__main__":
    unittest.main()
