"""
====================================================

QuantEngine

Institutional Delta Analyzer

====================================================
"""

from core.orderflow.delta_signal import DeltaSignal


class DeltaAnalyzer:

    def __init__(

        self,

        lookback=10,

    ):

        self.lookback = lookback

    # ==================================================

    def analyze(

        self,

        registry,

    ):

        signal = DeltaSignal()

        history = registry.last(

            self.lookback,

        )

        if len(history) < 2:

            return signal

        latest = history[-1]

        previous = history[-2]

        average = (

            sum(

                d.delta

                for d in history

            )

            / len(history)

        )

        average_abs = (

            sum(

                abs(d.delta)

                for d in history

            )

            / len(history)

        )

        # -------------------------------------------------
        # Trend
        # -------------------------------------------------

        if latest.delta > previous.delta:

            signal.increasing_delta = True

            signal.score += 10

            signal.reasons.append(

                "Increasing Delta",

            )

        elif latest.delta < previous.delta:

            signal.decreasing_delta = True

            signal.score += 10

            signal.reasons.append(

                "Decreasing Delta",

            )

        # -------------------------------------------------
        # Strong Buying
        # -------------------------------------------------

        if (

            latest.delta > 0

            and latest.delta > average_abs * 1.50

        ):

            signal.strong_buying = True

            signal.aggressive_buying = True

            signal.score += 20

            signal.reasons.append(

                "Strong Buying Pressure",

            )

        # -------------------------------------------------
        # Strong Selling
        # -------------------------------------------------

        if (

            latest.delta < 0

            and abs(latest.delta) > average_abs * 1.50

        ):

            signal.strong_selling = True

            signal.aggressive_selling = True

            signal.score += 20

            signal.reasons.append(

                "Strong Selling Pressure",

            )

        # -------------------------------------------------
        # Buying Exhaustion
        # -------------------------------------------------

        if (

            previous.delta > 0

            and latest.delta < previous.delta * 0.40

        ):

            signal.buying_exhaustion = True

            signal.score += 20

            signal.reasons.append(

                "Buying Exhaustion",

            )

        # -------------------------------------------------
        # Selling Exhaustion
        # -------------------------------------------------

        if (

            previous.delta < 0

            and abs(latest.delta)

            < abs(previous.delta) * 0.40

        ):

            signal.selling_exhaustion = True

            signal.score += 20

            signal.reasons.append(

                "Selling Exhaustion",

            )

        # -------------------------------------------------
        # Imbalance
        # -------------------------------------------------

        if abs(latest.delta_percent) >= 60:

            if latest.delta > 0:

                signal.imbalance_buy = True

                signal.score += 15

                signal.reasons.append(

                    "Buy Imbalance",

                )

            else:

                signal.imbalance_sell = True

                signal.score += 15

                signal.reasons.append(

                    "Sell Imbalance",

                )

        # -------------------------------------------------
        # Absorption
        # -------------------------------------------------

        if (

            abs(latest.delta) > average_abs

            and abs(

                latest.delta

                - previous.delta

            ) < average_abs * 0.20

        ):

            signal.absorption = True

            signal.score += 15

            signal.reasons.append(

                "Possible Absorption",

            )

        # -------------------------------------------------
        # Confidence
        # -------------------------------------------------

        signal.score = min(

            signal.score,

            100.0,

        )

        signal.confidence = (

            signal.score / 100.0

        )

        signal.institutional_score = (

            signal.score

        )

        return signal