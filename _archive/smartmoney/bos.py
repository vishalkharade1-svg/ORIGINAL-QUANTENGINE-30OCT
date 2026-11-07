"""
====================================================

QuantEngine

Build : 4.4
Module : Break Of Structure (BOS)

Detects bullish and bearish BOS events.

====================================================
"""

from dataclasses import dataclass


@dataclass
class BOS:

    direction: str

    price: float

    timestamp: int

    broken_label: str


class BOSDetector:

    def detect(self, structure):

        events = []

        previous_high = None
        previous_low = None

        for point in structure:

            swing = point.swing

            # Higher High breaks previous high
            if point.label == "HH":

                if previous_high is not None:

                    if swing.price > previous_high:

                        events.append(
                            BOS(
                                direction="BULLISH",
                                price=swing.price,
                                timestamp=swing.timestamp,
                                broken_label="HH",
                            )
                        )

                previous_high = swing.price

            # Lower Low breaks previous low
            elif point.label == "LL":

                if previous_low is not None:

                    if swing.price < previous_low:

                        events.append(
                            BOS(
                                direction="BEARISH",
                                price=swing.price,
                                timestamp=swing.timestamp,
                                broken_label="LL",
                            )
                        )

                previous_low = swing.price

        return events