"""
====================================================

QuantEngine

Build : 4.5

Module : Change Of Character

====================================================
"""

from dataclasses import dataclass


@dataclass
class CHoCH:

    direction: str

    timestamp: int

    price: float


class CHoCHDetector:

    def detect(self, structure):

        events = []

        trend = None

        for point in structure:

            label = point.label

            if trend is None:

                if label in ("HH", "HL"):
                    trend = "UP"

                elif label in ("LH", "LL"):
                    trend = "DOWN"

                continue

            if trend == "UP":

                if label == "LL":

                    events.append(

                        CHoCH(
                            direction="BEARISH",
                            timestamp=point.swing.timestamp,
                            price=point.swing.price,
                        )

                    )

                    trend = "DOWN"

            elif trend == "DOWN":

                if label == "HH":

                    events.append(

                        CHoCH(
                            direction="BULLISH",
                            timestamp=point.swing.timestamp,
                            price=point.swing.price,
                        )

                    )

                    trend = "UP"

        return events