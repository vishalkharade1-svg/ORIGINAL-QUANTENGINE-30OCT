"""
Async Refresh Scheduler — Phase 10 fix for provider blocking.

Wraps RefreshScheduler to make provider refresh non-blocking:
- Slow REST/network operations run in a dedicated background thread (single worker, bounded)
- The poll loop never blocks on provider refresh
- Latest successful snapshot is cached atomically
- Refresh failures preserve last valid snapshot
- Stale-data age is exposed

Uses a single daemon thread + queue, not unbounded threads.
"""

import threading
import time


class AsyncRefreshScheduler:
    """
    Non-blocking wrapper around RefreshScheduler — Design A (bounded active refresh).

    - `run_if_due()` returns immediately; at most ONE active refresh at a time, no queue.
    - Repeated due checks while one is running are coalesced/ignored (no duplicate workers, no unbounded threads).
    - `last_universe` always holds the latest successful universe (or None if never succeeded).
    - `refresh_in_progress` indicates a background refresh is running.
    - `last_refresh_error` holds the last error, if any.
    - `provider_refresh_age` is seconds since last successful refresh.
    """

    def __init__(self, scheduler, max_workers=1):
        self.scheduler = scheduler
        self.max_workers = max_workers
        self._lock = threading.RLock()
        self._thread = None
        self._in_progress = False
        self._last_success = None
        self._last_error = None
        self._last_success_time = None
        self._stop = threading.Event()

    @property
    def last_universe(self):
        with self._lock:
            # Prefer scheduler's last_universe if it has one, else our cached
            if self.scheduler.last_universe is not None:
                return self.scheduler.last_universe
            return self._last_success

    @property
    def refresh_in_progress(self):
        with self._lock:
            return self._in_progress

    @property
    def last_refresh_error(self):
        with self._lock:
            return self._last_error

    @property
    def provider_refresh_age(self):
        with self._lock:
            if self._last_success_time is None:
                return None
            return time.time() - self._last_success_time

    def _background_refresh(self, kwargs):
        # Capture error count before refresh to detect new failures
        errors_before = len(self.scheduler.errors) if hasattr(self.scheduler, 'errors') else 0
        try:
            # This is the blocking call — runs in background thread
            result = self.scheduler.refresh(**kwargs)
            with self._lock:
                errors_after = len(self.scheduler.errors) if hasattr(self.scheduler, 'errors') else 0
                has_new_error = errors_after > errors_before
                # Only cache if refresh produced a universe and had no new errors
                # If it had new errors, preserve last valid snapshot
                if result is not None and not has_new_error:
                    self._last_success = result
                    self._last_success_time = time.time()
                    self._last_error = None
                elif has_new_error:
                    # Keep last success, record error
                    if errors_after > errors_before:
                        last_err = self.scheduler.errors[-1] if self.scheduler.errors else "refresh failed"
                        self._last_error = str(last_err)
                # If result is None but scheduler has last_universe, keep it
        except Exception as e:
            with self._lock:
                self._last_error = str(e)
        finally:
            with self._lock:
                self._in_progress = False

    def run_if_due(self, **kwargs):
        # Never block the poll loop
        if not self.scheduler.due:
            return None

        with self._lock:
            if self._in_progress:
                # Already refreshing — don't start another, return None (use cached)
                return None
            # Check due again under lock
            if not self.scheduler.due:
                return None
            self._in_progress = True

        # Start background thread for the blocking refresh
        t = threading.Thread(target=self._background_refresh, args=(kwargs,), daemon=True)
        t.start()
        # Also store for join on stop
        self._thread = t
        return None  # No new universe yet; caller will use cached on next poll

    def force_refresh(self, **kwargs):
        # Runtime-facing force refresh must NOT block event loop.
        # Use same non-blocking path as run_if_due, but ensure it starts even if not due.
        with self._lock:
            if self._in_progress:
                # Already refreshing — return cached immediately, don't block
                return self.get_cached_universe()
            self._in_progress = True
        t = threading.Thread(target=self._background_refresh, args=(kwargs,), daemon=True)
        t.start()
        self._thread = t
        # Return cached immediately (may be None on first call, but caller can poll get_cached_universe)
        # For startup, caller can wait briefly if needed, but poll loop will pick up new universe on next poll
        return self.get_cached_universe()

    def get_cached_universe(self):
        with self._lock:
            return self._last_success or self.scheduler.last_universe

    def health(self):
        with self._lock:
            age = self.provider_refresh_age
            if self._last_error and age is not None and age > 300:
                return "STALE"
            if self._last_error:
                return "ERROR"
            if age is not None and age > 600:
                return "STALE"
            return "HEALTHY"
