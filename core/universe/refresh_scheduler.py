"""
====================================================

QuantEngine

Refresh Scheduler

Phase 6B -- Market Universe.

Drives discovery + eligibility on a cadence without
importing a wall-clock into the engine.

    scheduler = RefreshScheduler(manager, interval_seconds=60)
    scheduler.run_if_due()      # no-op until the interval elapses
    scheduler.force_refresh()   # immediate, regardless of time

Deterministic under an injectable clock (tests pass a fake
clock; production uses time.time). An interval <= 0 means
"always due" -- every run_if_due() refreshes.
====================================================
"""

import time


class RefreshScheduler:

    def __init__(self, manager, interval_seconds=60, clock=None):
        self.manager = manager
        self.interval_seconds = interval_seconds
        self._clock = clock or time.time
        self.last_run = None
        self.runs = 0
        self.last_universe = None
        self.last_summary = None
        self.errors = []

    @property
    def due(self):
        if self.interval_seconds <= 0:
            return True
        if self.last_run is None:
            return True
        return (self._clock() - self.last_run) >= self.interval_seconds

    def run_if_due(self, **kwargs):
        if not self.due:
            return None
        return self.refresh(**kwargs)

    def force_refresh(self, **kwargs):
        return self.refresh(**kwargs)

    def refresh(self, **kwargs):
        # kwargs are the discovery plumbing (client, normalizer);
        # discovery failures are recorded, the loop never dies.
        try:
            summary = self.manager.refresh_discovery(
                client=kwargs.get("client"),
                normalizer=kwargs.get("normalizer"),
            )
        except Exception as error:  # one failed pass never kills the loop
            self.errors.append(error)
            summary = {"error": str(error)}
        finally:
            self.last_run = self._clock()
            self.runs += 1
        self.last_summary = summary
        try:
            self.last_universe = self.manager.build_universe(
                timeframe=kwargs.get("timeframe", "1m")
            )
            return self.last_universe
        except Exception as error:
            self.errors.append(error)
            return None