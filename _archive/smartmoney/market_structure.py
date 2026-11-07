"""
====================================================

QuantEngine

Build : 4.3
Module : Market Structure

Labels swings as:

HH
HL
LH
LL

====================================================
"""

from smartmoney.structure import StructurePoint


class MarketStructure:

    def analyze(self, swings):

        structure = []

        previous_high = None
        previous_low = None

        for swing in swings:

            if swing.type == "HIGH":

                if previous_high is None:

                    label = "HH"

                elif swing.price > previous_high:

                    label = "HH"

                else:

                    label = "LH"

                previous_high = swing.price

            else:

                if previous_low is None:

                    label = "HL"

                elif swing.price > previous_low:

                    label = "HL"

                else:

                    label = "LL"

                previous_low = swing.price

            structure.append(
                StructurePoint(
                    swing=swing,
                    label=label,
                )
            )

        return structure