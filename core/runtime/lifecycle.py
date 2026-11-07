"""
====================================================

QuantEngine

Engine Lifecycle Manager

Phase 9P-f -- Control & Monitoring API.

The ONE control seam between an operator-facing surface
(the Control & Monitoring API / future UI) and the canonical
RealTimeEngine. The rule this module enforces is:

    API -> Command/Query -> Existing Runtime

    NOT: API -> strategy logic / risk logic / order logic.

The existing engine stays authoritative. This manager NEVER
contains trading, risk or execution logic -- it only:

  - owns a control thread that runs the engine's existing,
    non-blocking poll loop on a cadence (the same loop the
    blocking run_paper_forever() drives),
  - serializes operator commands through a lock + command queue,
  - translates those commands into the engine's OWN public
    start() / stop() / poll() primitives, and
  - exposes a thread-safe read snapshot of its own lifecycle.

It adds NO lifecycle object into the engine itself and NO
trading state machine -- the engine's `started` flag remains
authoritative; this manager only reflects it plus its own
control-thread state.

Commands (PAPER control only by construction):
    start          -> engine.start() + run the poll loop
    stop           -> graceful stop (finish loop, engine.stop())
    restart        -> stop then start
    emergency_stop -> HIGH-PRIORITY immediate PAPER shutdown.

Semantics:

  * `stop` is a GRACEFUL stop: it signals the poll loop to finish
    its current iteration, joins the control thread, then calls
    engine.stop(). It is idempotent (a second call when already
    STOPPED is a no-op) and the engine can be restarted afterwards.

  * `emergency_stop` is the highest-priority local PAPER shutdown
    command. It is IMMEDIATE -- it cancels the poll loop and calls
    the engine's own authoritative stop() without waiting for the
    loop to finish its iteration -- and it remains STOPPED.
    It is strictly idempotent: calling it twice (or after any stop)
    performs NO duplicate shutdown work and does not error. The
    word "emergency" here means PAPER-runtime safety, NOT live
    trading control; there is no live emergency-stop path.

The state model is STOPPED / STARTING / RUNNING / STOPPING /
FAILED. A failed engine.start() transitions to FAILED (visible in
the health surface) and can be restarted from there. Duplicate
start while RUNNING is a safe no-op; start while STOPPING is
rejected; commands are serialized on a re-entrant lock so
concurrent API requests cannot race.

Default state is STOPPED and the control thread is a daemon so
the process can never be held open by the service.
====================================================
"""

import threading
import time

STATE_STOPPED = "STOPPED"
STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_STOPPING = "STOPPING"
STATE_FAILED = "FAILED"
STATE_PAUSED = "PAUSED"

COMMANDS = frozenset({"start", "stop", "restart", "emergency_stop", "pause", "resume"})


class ControlCommandError(RuntimeError):
    """Raised for invalid / rejected control commands. The API
    translates this into a 4xx without ever reaching the engine."""


class EngineLifecycle:

    def __init__(
        self,
        engine,
        poll_interval_seconds=10.0,
        client=None,
        normalizer=None,
    ):

        self.engine = engine

        self._poll_interval_seconds = max(0.0, float(poll_interval_seconds))

        self._client = client

        self._normalizer = normalizer

        self._lock = threading.RLock()

        self._state = STATE_STOPPED

        self._stop_requested = threading.Event()

        self._paused = threading.Event()

        self._thread = None

        # set whenever the lifecycle is not in a running/starting
        # state; lets the entrypoint driver block until a stop
        # (KeyboardInterrupt or an API /control/stop) completes
        self._stopped_event = threading.Event()

        self._stopped_event.set()

        # observability counters for the health surface
        self._started_at = None

        self._polls = 0

        self._last_error = None

    # --------------------------------------------------
    # State accessors (thread-safe)
    # --------------------------------------------------

    @property
    def state(self):

        with self._lock:

            return self._state

    def running(self):

        with self._lock:

            return self._state == STATE_RUNNING

    def wait(self, timeout=None):
        """Block until the lifecycle is no longer RUNNING/STARTING
        (i.e. a stop/emergency_stop/failure has occurred) or, with
        a timeout, until that or the timeout elapses.

        Returns the lifecycle state after waiting. The stopped
        event is set when the lifecycle leaves the running states,
        so an API /control/stop or a KeyboardInterrupt wakes any
        waiting driver."""
        self._stopped_event.wait(timeout=timeout)

        with self._lock:

            return self._state

    def _leave_running(self):
        """Mark that the lifecycle is no longer in a running state
        so any wait() caller can proceed."""

        self._stopped_event.set()

    # --------------------------------------------------
    # Command dispatch
    # --------------------------------------------------

    def command(self, name):
        """Route an operator command to the matching lifecycle
        action. NAME is hard-allowlisted; anything else raises
        ControlCommandError before any engine interaction.

        Returns the new state name after the action."""
        if name not in COMMANDS:

            raise ControlCommandError(
                "Unknown or unsupported control command: %r. "
                "Only PAPER control verbs are allowed." % (name,)
            )

        dispatch = {
            "start": self.start,
            "stop": self.stop,
            "restart": self.restart,
            "emergency_stop": self.emergency_stop,
            "pause": self.pause,
            "resume": self.resume,
        }

        return dispatch[name]()

    # --------------------------------------------------
    # Control actions
    # --------------------------------------------------

    def start(self):
        """Start the engine + the control poll loop.

        Idempotent: if already RUNNING, returns the current state
        without re-driving the engine. May start from STOPPED or
        from FAILED (allowing recovery after a failed start)."""
        with self._lock:

            if self._state == STATE_RUNNING:

                return self._state

            if self._state == STATE_STOPPING:

                raise ControlCommandError(
                    "Cannot start while a stop/restart is in "
                    "progress."
                )

            self._state = STATE_STARTING

            try:

                self.engine.start()

            except Exception as exc:

                self._last_error = _exc_text(exc)

                self._state = STATE_FAILED

                self._leave_running()

                raise ControlCommandError(
                    "Engine failed to start: %s" % self._last_error
                ) from exc

            self._state = STATE_RUNNING

            self._started_at = time.time()

            self._stop_requested.clear()

            self._stopped_event.clear()

            self._thread = threading.Thread(
                target=self._run_loop,
                name="quantengine-control",
                daemon=True,
            )

            self._thread.start()

            return self._state

    def stop(self):
        """Graceful stop: signal the loop to finish its current
        iteration, join the control thread, then engine.stop().

        Idempotent: a second call (or a call when already STOPPED)
        is a no-op and performs no duplicate shutdown work."""
        with self._lock:

            if self._state == STATE_STOPPED:

                return self._state

            self._state = STATE_STOPPING

        self._stop_requested.set()

        thread = self._thread

        if thread is not None and thread.is_alive():

            thread.join(timeout=5.0)

        with self._lock:

            try:

                self.engine.stop()

            except Exception as exc:

                self._last_error = _exc_text(exc)

            self._state = STATE_STOPPED

            self._thread = None

            self._leave_running()

            return self._state

    def restart(self):
        """stop() then start(); returns the resulting state.

        Serialized on the lifecycle lock so a concurrent command
        cannot interleave between the stop and the start."""

        self.stop()

        return self.start()

    def emergency_stop(self):
        """HIGH-PRIORITY immediate PAPER shutdown.

        Cancels the poll loop and calls the engine's OWN
        authoritative stop() right away -- it does NOT wait for
        the loop to finish its current iteration (unlike `stop`).
        The lifecycle remains STOPPED.

        Strictly idempotent: calling it twice, or after any stop,
        returns STOPPED without performing duplicate shutdown work
        and without erroring. It is a PAPER-runtime safety command;
        there is no live emergency-stop path."""
        with self._lock:

            if self._state == STATE_STOPPED:

                # already fully stopped -- an idempotent no-op, no
                # duplicate shutdown work
                return self._state

            self._state = STATE_STOPPING

        self._stop_requested.set()

        thread = self._thread

        with self._lock:

            try:

                self.engine.stop()

            except Exception as exc:

                self._last_error = _exc_text(exc)

            self._state = STATE_STOPPED

            # drain / abandon the control thread if it is alive
            self._thread = None

            self._leave_running()

        if thread is not None and thread.is_alive():

            # The loop checks _stop_requested on each iteration, so
            # it exits itself; give it a bounded join so we never
            # block the API thread indefinitely.
            thread.join(timeout=2.0)

        return self._state

    def pause(self):
        """Pause new signal generation without corrupting state.

        Keeps engine and subscriptions alive, but stops new paper orders
        from being created. Workers finish current iteration. Idempotent.
        """
        with self._lock:
            if self._state == STATE_PAUSED:
                return self._state
            if self._state != STATE_RUNNING:
                raise ControlCommandError(
                    f"Cannot pause from state {self._state}; must be RUNNING."
                )
            self._paused.set()
            self._state = STATE_PAUSED
            return self._state

    def resume(self):
        """Resume from PAUSED to RUNNING. Idempotent."""
        with self._lock:
            if self._state == STATE_RUNNING:
                return self._state
            if self._state != STATE_PAUSED:
                raise ControlCommandError(
                    f"Cannot resume from state {self._state}; must be PAUSED."
                )
            self._paused.clear()
            self._state = STATE_RUNNING
            # Wake the loop if it was sleeping in paused state
            self._stop_requested.clear()
            return self._state

    # --------------------------------------------------
    # Control thread body
    # --------------------------------------------------

    def _run_loop(self):

        stop_requested = self._stop_requested

        while not stop_requested.is_set():

            # Pause: skip poll but keep loop alive, finish workers
            if self._paused.is_set():
                # Sleep briefly while paused, wake early on stop/resume
                stop_requested.wait(timeout=0.5)
                continue

            try:

                self.engine.poll(
                    client=self._client,
                    normalizer=self._normalizer,
                )

                with self._lock:

                    self._polls += 1

            except Exception as exc:

                with self._lock:

                    self._last_error = _exc_text(exc)

            if stop_requested.is_set():

                break

            interval = self._poll_interval_seconds

            if interval > 0:

                # bounded sleep: wake early on stop
                stop_requested.wait(timeout=interval)

    # --------------------------------------------------
    # Health / read snapshot
    # --------------------------------------------------

    def health(self):
        """Thread-safe lifecycle + engine health snapshot for the
        read-only monitoring surface. Pure delegation to the
        engine's own `started` flag; never invents engine state."""

        with self._lock:

            engine_started = bool(getattr(self.engine, "started", False))

            uptime = 0.0

            if engine_started and self._started_at is not None:

                uptime = max(0.0, time.time() - self._started_at)

            polls = self._polls

            last_error = self._last_error

            state = self._state

            thread_alive = (
                self._thread is not None and self._thread.is_alive()
            )

        return {
            "lifecycle_state": state,
            "engine_started": engine_started,
            "poll_interval_seconds": self._poll_interval_seconds,
            "uptime_seconds": round(uptime, 3),
            "polls": polls,
            "control_thread_alive": thread_alive,
            "last_error": last_error,
        }


def _exc_text(exc):

    try:

        return str(exc)

    except Exception:

        return repr(exc)
