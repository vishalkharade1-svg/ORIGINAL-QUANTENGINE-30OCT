"""
====================================================

Replay Engine

Feeds historical candles one-by-one.

Publishes CandleEvents through the
Market Event Bus.

====================================================
"""

from core.events.candle_event import CandleEvent


class ReplayEngine:

    def __init__(

        self,

        candles,

        event_bus=None,

        symbol="",

        timeframe="",

    ):

        self.candles = candles

        self.index = 0

        self.event_bus = event_bus

        self.symbol = symbol

        self.timeframe = timeframe

    # -------------------------------------------------

    def reset(self):

        self.index = 0

    # -------------------------------------------------

    def finished(self):

        return self.index >= len(

            self.candles

        )

    # -------------------------------------------------

    def next(self):

        if self.finished():

            return None

        candle = self.candles[

            self.index

        ]

        self.index += 1

        # ---------------------------------------------
        # Publish Event
        # ---------------------------------------------

        if self.event_bus is not None:

            event = CandleEvent(

                timestamp=candle.timestamp,

                candle=candle,

                symbol=self.symbol,

                timeframe=self.timeframe,

            )

            self.event_bus.publish(

                event

            )

        return candle

    # -------------------------------------------------

    def current_index(self):

        return self.index

    # -------------------------------------------------

    def progress(self):

        if len(self.candles) == 0:

            return 100.0

        return (

            self.index

            / len(self.candles)

        ) * 100