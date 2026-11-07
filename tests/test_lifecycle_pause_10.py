"""
Phase 10 — PAPER runtime lifecycle PAUSE/RESUME.
"""

import time
import unittest

from core.runtime.lifecycle import EngineLifecycle, STATE_RUNNING, STATE_PAUSED, STATE_STOPPED


class FakeEngine:
    def __init__(self):
        self.started = False
        self.poll_count = 0
    def start(self):
        self.started = True
    def stop(self):
        self.started = False
    def poll(self, **kwargs):
        self.poll_count += 1


class TestLifecyclePauseResume(unittest.TestCase):

    def test_pause_resume_cycle(self):
        eng = FakeEngine()
        lc = EngineLifecycle(eng, poll_interval_seconds=0.01)
        lc.start()
        time.sleep(0.05)
        self.assertEqual(lc.state, STATE_RUNNING)
        # Pause
        lc.pause()
        self.assertEqual(lc.state, STATE_PAUSED)
        polls_at_pause = eng.poll_count
        time.sleep(0.05)
        # While paused, poll should not increase (or increase very little)
        self.assertEqual(eng.poll_count, polls_at_pause)
        # Resume
        lc.resume()
        self.assertEqual(lc.state, STATE_RUNNING)
        time.sleep(0.6)  # wait for paused loop to wake (0.5s sleep in loop)
        self.assertGreater(eng.poll_count, polls_at_pause)
        lc.stop()
        self.assertEqual(lc.state, STATE_STOPPED)

    def test_pause_idempotent(self):
        eng = FakeEngine()
        lc = EngineLifecycle(eng, poll_interval_seconds=0.01)
        lc.start()
        lc.pause()
        lc.pause()  # second pause is idempotent
        self.assertEqual(lc.state, STATE_PAUSED)
        lc.stop()

    def test_pause_requires_running(self):
        eng = FakeEngine()
        lc = EngineLifecycle(eng, poll_interval_seconds=0.01)
        with self.assertRaises(Exception):
            lc.pause()
        lc.start()
        lc.pause()
        # Second pause is idempotent (returns PAUSED, not raise)
        self.assertEqual(lc.pause(), STATE_PAUSED)
        lc.stop()
        lc2 = EngineLifecycle(FakeEngine(), poll_interval_seconds=0.01)
        with self.assertRaises(Exception):
            lc2.resume()

    def test_health_reflects_paused(self):
        eng = FakeEngine()
        lc = EngineLifecycle(eng, poll_interval_seconds=0.01)
        lc.start()
        lc.pause()
        h = lc.health()
        self.assertEqual(h["lifecycle_state"], STATE_PAUSED)
        lc.stop()
