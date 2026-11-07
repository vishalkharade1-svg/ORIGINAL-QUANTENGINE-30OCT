"""
Phase 9P-f monitoring service wiring tests.

Verifies the fail-closed gating of the Control & Monitoring API:
disabled -> no server; enabled-without-token -> refuses to start
(ControlApiConfigError); enabled-with-token -> server runs on a
daemon thread and shuts down cleanly.
"""

import unittest

from core.monitoring import service
from core.monitoring.service import ControlApiConfigError


class FakeEngine:
    started = False
    time_frame = "1m"

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def poll(self, client=None, normalizer=None):
        pass


class FakeLifecycle:
    def health(self):
        return {"lifecycle_state": "STOPPED", "engine_started": False}


class TestServiceGating(unittest.TestCase):

    def setUp(self):
        import config.settings as _settings

        self._settings = _settings
        self._saved = {
            "enabled": _settings.settings.CONTROL_API_ENABLED,
            "token": _settings.settings.CONTROL_API_TOKEN,
            "port": _settings.settings.CONTROL_API_PORT,
        }

    def tearDown(self):
        s = self._settings.settings
        s.CONTROL_API_ENABLED = self._saved["enabled"]
        s.CONTROL_API_TOKEN = self._saved["token"]
        s.CONTROL_API_PORT = self._saved["port"]

    def test_disabled_returns_none(self):
        self._settings.settings.CONTROL_API_ENABLED = False
        self._settings.settings.CONTROL_API_TOKEN = "abc"

        engine = FakeEngine()
        lifecycle = FakeLifecycle()

        self.assertIsNone(service.start_api(engine, lifecycle))

    def test_enabled_without_token_fails_closed(self):
        self._settings.settings.CONTROL_API_ENABLED = True
        self._settings.settings.CONTROL_API_TOKEN = ""

        with self.assertRaises(ControlApiConfigError):
            service.start_api(FakeEngine(), FakeLifecycle())

    def test_enabled_with_token_starts_and_stops(self):
        self._settings.settings.CONTROL_API_ENABLED = True
        self._settings.settings.CONTROL_API_TOKEN = "tok"
        self._settings.settings.CONTROL_API_PORT = 0

        try:
            # avoid building a real engine: start_api only needs the
            # object for wiring; control endpoints are not exercised
            # here (covered by test_api_server_9pf).
            class _E:
                runtimes = {}
                refresh_scheduler = None
                subscriptions = None
                portfolio = None
                _instruments = {}
                started = False
                universe_mode = "explicit"
                timeframe = "1m"

            engine = _E()
            server = service.start_api(engine, FakeLifecycle())

            self.assertIsNotNone(server)
            self.assertTrue(server.running())
        finally:
            self._settings.settings.CONTROL_API_ENABLED = self._saved["enabled"]
            self._settings.settings.CONTROL_API_TOKEN = self._saved["token"]
            self._settings.settings.CONTROL_API_PORT = self._saved["port"]

        service.stop_api(server)
        self.assertFalse(server.running())

    def test_duplicate_server_refused(self):
        self._settings.settings.CONTROL_API_ENABLED = True
        self._settings.settings.CONTROL_API_TOKEN = "tok"
        self._settings.settings.CONTROL_API_PORT = 0

        class _E:
            runtimes = {}
            refresh_scheduler = None
            subscriptions = None
            portfolio = None
            _instruments = {}
            started = False
            universe_mode = "explicit"
            timeframe = "1m"

        try:
            engine = _E()
            first = service.start_api(engine, FakeLifecycle())
            self.assertIsNotNone(first)
            self.assertTrue(first.running())

            # a second start while the first is running is refused
            with self.assertRaises(ControlApiConfigError):
                service.start_api(engine, FakeLifecycle())
        finally:
            self._settings.settings.CONTROL_API_ENABLED = self._saved["enabled"]
            self._settings.settings.CONTROL_API_TOKEN = self._saved["token"]
            self._settings.settings.CONTROL_API_PORT = self._saved["port"]

        service.stop_api(first)
        self.assertFalse(first.running())

    def test_start_paper_service_disabled_runs_lifecycle_only(self):
        self._settings.settings.CONTROL_API_ENABLED = False

        class _E:
            started = False

            def start(self):
                self.started = True

            def stop(self):
                self.started = False

            def poll(self, client=None, normalizer=None):
                pass

        try:
            engine = _E()
            lifecycle, server = service.start_paper_service(
                engine, poll_interval_seconds=0.001
            )
            self.assertIsNotNone(lifecycle)
            self.assertIsNone(server)  # API disabled -> no server
            self.assertTrue(lifecycle.running())
            self.assertTrue(engine.started)
        finally:
            self._settings.settings.CONTROL_API_ENABLED = self._saved["enabled"]

        lifecycle.stop()

    def test_run_with_monitoring_disabled_clean_shutdown(self):
        self._settings.settings.CONTROL_API_ENABLED = False

        import threading
        import time

        class _E:
            started = False

            def start(self):
                self.started = True

            def stop(self):
                self.started = False

            def poll(self, client=None, normalizer=None):
                pass

        engine = _E()

        # start_paper_service returns the authoritative lifecycle; we
        # then block_until_stopped in a background thread and stop the
        # lifecycle through its public stop() to release the blocker.
        lifecycle, server = service.start_paper_service(
            engine, poll_interval_seconds=0.001
        )
        self.assertIsNotNone(lifecycle)
        self.assertIsNone(server)  # API disabled -> no HTTP server
        self.assertTrue(lifecycle.running())
        self.assertTrue(engine.started)

        result = {}

        def block():
            result["done"] = False
            service.block_until_stopped(lifecycle, server)
            result["done"] = True

        thread = threading.Thread(target=block, daemon=True)
        thread.start()

        time.sleep(0.05)

        # stop the lifecycle (as the API /control/stop or an
        # interrupt would) -> the blocking loop must exit + shut down
        lifecycle.stop()

        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertTrue(result["done"])
        self.assertFalse(lifecycle.running())
        self.assertFalse(engine.started)


if __name__ == "__main__":
    unittest.main()
