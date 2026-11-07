"""
====================================================

QuantEngine

Institutional BOS Engine

====================================================
"""

from dataclasses import dataclass

from core.common.base_engine import BaseEngine


@dataclass(slots=True)
class BOSEvent:

    direction: str
    level: float
    close: float
    timestamp: int
    swing_index: int


class BOSEngine(BaseEngine):

    priority = 130

    dependencies = [
        "SwingEngine",
    ]

    enabled = True

    def __init__(self):

        super().__init__()

        self.events = []

        self.last_bull_break = None
        self.last_bear_break = None

    # -------------------------------------------------

    def analyze(self, context):

        registry = context.swings

        bars = list(context.candles)

        if registry is None:
            context.bos = []
            return

        if len(bars) == 0:
            context.bos = []
            return

        context.bos = self.update(
            bars,
            registry,
        )

    # -------------------------------------------------

    def update(
        self,
        bars,
        registry,
    ):

        self.events.clear()

        latest = bars[-1]

        close = latest.close

        highs = registry.highs()

        lows = registry.lows()

        if highs:

            swing = highs[-1]

            if close > swing.price:

                if self.last_bull_break != swing.index:

                    self.last_bull_break = swing.index

                    self.events.append(

                        BOSEvent(

                            direction="BULLISH",

                            level=swing.price,

                            close=close,

                            timestamp=latest.timestamp,

                            swing_index=swing.index,

                        )

                    )

        if lows:

            swing = lows[-1]

            if close < swing.price:

                if self.last_bear_break != swing.index:

                    self.last_bear_break = swing.index

                    self.events.append(

                        BOSEvent(

                            direction="BEARISH",

                            level=swing.price,

                            close=close,

                            timestamp=latest.timestamp,

                            swing_index=swing.index,

                        )

)

        return list(self.events)

    # -------------------------------------------------

    def latest(self):

        if not self.events:
            return None

        return self.events[-1]

    # -------------------------------------------------

    def bullish(self):

        return [
            e
            for e in self.events
            if e.direction == "BULLISH"
        ]

    # -------------------------------------------------

    def bearish(self):

        return [
            e
            for e in self.events
            if e.direction == "BEARISH"
        ]

    # -------------------------------------------------

    def reset(self):

        self.events.clear()

        self.last_bull_break = None
        self.last_bear_break = None