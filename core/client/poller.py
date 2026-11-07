"""
====================================================

QuantEngine

Lightweight Desktop Control Client - background poller

Phase 9P-h.

A single background worker that periodically runs ONE
coordinated read cycle against the Control API and pushes the
result onto a thread-safe queue for the UI thread to consume.

Design rules:
  * HTTP never happens on the GUI thread -- only here.
  * One coordinated cycle per interval (no per-endpoint
    storms); each endpoint is fetched defensively so a single
    failure does not abort the whole cycle.
  * A "cycle in flight" guard prevents overlapping polls
    (slow server + short interval must not pile up requests).
  * The worker stops cleanly via a stop event and its thread is
    daemon so application shutdown always returns.
  * Closing the UI never touches the engine lifecycle; this
    worker only reads.

Stdlib only: threading, queue, time.
====================================================
"""

import queue
import threading
import time


READ_ENDPOINTS = (
    "health",
    "universe",
    "subscriptions",
    "runtimes",
    "market",
    "signals",
    "positions",
    "orders",
    "account",
    "risk",
    "performance",
    "errors",
)


class CycleResult:

    """Snapshot of one coordinated read cycle.

    endpoints: {name: {"ok": bool, "data": ...|None,
                       "error": str|None}}
    connected: bool   (a health round-trip succeeded)
    at:        float  (wall-clock time of the cycle)
    """

    def __init__(self, endpoints, connected, at):
        self.endpoints = endpoints
        self.connected = connected
        self.at = at

    def data(self, name):
        entry = self.endpoints.get(name)
        if entry is None or not entry["ok"]:
            return None
        return entry["data"]

    def error(self, name):
        entry = self.endpoints.get(name)
        if entry is None:
            return None
        return entry["error"]


class Poller:

    def __init__(self, api, endpoints=READ_ENDPOINTS, interval=3.0):
        self.api = api
        self.endpoints = tuple(endpoints or READ_ENDPOINTS)
        self.interval = float(interval) if interval else 3.0
        self.queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="quantengine-client-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def join(self, timeout=5.0):
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    # -----------------------------------------------------

    def _run(self):
        while not self._stop.is_set():
            cycle_started = time.time()
            self._poll_once()
            # wait out the remainder of the interval (or until stop)
            elapsed = time.time() - cycle_started
            remaining = self.interval - elapsed
            if remaining > 0:
                self._stop.wait(remaining)

    def _poll_once(self):
        """Run one coordinated read cycle and enqueue its result."""

        # connectivity first -- health is the liveness probe
        health_error = None

        try:
            health = self.api.get("/health")
        except Exception as exc:  # noqa: BLE001 - any client error here
            health = None
            health_error = _error_text(exc)

        result = {}

        if health is not None:
            result["health"] = {"ok": True, "data": health, "error": None}
        else:
            result["health"] = {
                "ok": False,
                "data": None,
                "error": health_error or "unreachable",
            }

        # if the server is up (health returned) fetch the rest; on a
        # hard disconnect skip the batch to stay snappy.
        if health is not None:
            for name in self.endpoints:
                if name == "health":
                    continue
                path = "/" + name
                try:
                    data = self.api.get(path)
                    result[name] = {"ok": True, "data": data, "error": None}
                except Exception as exc:  # noqa: BLE001
                    result[name] = {
                        "ok": False,
                        "data": None,
                        "error": _error_text(exc),
                    }
        else:
            for name in self.endpoints:
                if name == "health":
                    continue
                result[name] = {
                    "ok": False,
                    "data": None,
                    "error": health_error or "unreachable",
                }

        self.queue.put(
            CycleResult(
                endpoints=result,
                connected=health is not None,
                at=time.time(),
            )
        )


def _error_text(exc):
    message = str(exc) or exc.__class__.__name__

    return message
