"""
====================================================

QuantEngine

Market Event Dispatcher

====================================================
"""

from collections import deque


class EventDispatcher:

    # Phase 12 explicit capacity: the bus drains synchronously
    # on every publish, so the queue only grows on re-entrant
    # publishes (a callback publishing while dispatch runs).
    # Beyond maxlen the OLDEST event is evicted (deterministic
    # FIFO) and counted in `dropped` -- unbounded growth is
    # impossible, and any eviction is observable instead of
    # silent. Normal operation never approaches the bound.
    DEFAULT_MAXLEN = 10000

    def __init__(self, maxlen=None):

        self._maxlen = (
            self.DEFAULT_MAXLEN
            if maxlen is None
            else max(1, int(maxlen))
        )

        self._queue = deque()

        self.dropped = 0

    # -------------------------------------------------

    def push(self, event):

        self._queue.append(event)

        while len(self._queue) > self._maxlen:

            self._queue.popleft()

            self.dropped += 1

    # -------------------------------------------------

    def pop(self):

        if not self._queue:

            return None

        return self._queue.popleft()

    # -------------------------------------------------

    def empty(self):

        return len(self._queue) == 0

    # -------------------------------------------------

    def clear(self):

        self._queue.clear()

    # -------------------------------------------------

    def drain_dropped(self):
        """Read and reset the eviction counter (tests/ops)."""

        count = self.dropped

        self.dropped = 0

        return count

    # -------------------------------------------------

    def __len__(self):

        return len(self._queue)