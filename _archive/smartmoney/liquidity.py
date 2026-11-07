"""
====================================================

QuantEngine

Build : 4.6
Module : Liquidity Engine

Detects Equal Highs and Equal Lows.

====================================================
"""

from dataclasses import dataclass


@dataclass
class LiquidityZone:

    type: str

    price: float

    first_timestamp: int

    second_timestamp: int


class LiquidityDetector:

    def __init__(self, tolerance=0.001):
        """
        tolerance = 0.001 = 0.1%
        """

        self.tolerance = tolerance

    def detect(self, swings):

        zones = []

        for i in range(len(swings) - 1):

            a = swings[i]
            b = swings[i + 1]

            if a.type != b.type:
                continue

            difference = abs(a.price - b.price)

            average = (a.price + b.price) / 2

            if average == 0:
                continue

            if difference / average <= self.tolerance:

                if a.type == "HIGH":

                    zone_type = "EQH"

                else:

                    zone_type = "EQL"

                zones.append(

                    LiquidityZone(

                        type=zone_type,

                        price=average,

                        first_timestamp=a.timestamp,

                        second_timestamp=b.timestamp,

                    )

                )

        return zones