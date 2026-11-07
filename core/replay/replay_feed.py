"""
====================================================

Replay Feed

Maintains the visible market history.

====================================================
"""


class ReplayFeed:

    def __init__(self):

        self.history = []

    # -------------------------------------------------

    def reset(self):

        self.history.clear()

    # -------------------------------------------------

    def add(

        self,

        candle,

    ):

        self.history.append(

            candle

        )

    # -------------------------------------------------

    def candles(self):

        return self.history

    # -------------------------------------------------

    def latest(self):

        if not self.history:

            return None

        return self.history[-1]

    # -------------------------------------------------

    def size(self):

        return len(

            self.history

        )