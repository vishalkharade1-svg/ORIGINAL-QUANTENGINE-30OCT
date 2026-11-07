"""
====================================================

Institutional Volume Profile Engine

====================================================
"""

from collections import defaultdict

from core.volume_profile.profile import VolumeProfile
from core.volume_profile.volume_node import VolumeNode


class VolumeProfileEngine:

    def __init__(

        self,

        rows=40,

        value_area=0.70,

    ):

        self.rows = rows

        self.value_area = value_area

    # -------------------------------------------------

    def build(

        self,

        candles,

    ):

        profile = VolumeProfile()

        if not candles:

            return profile

        low = min(c.low for c in candles)

        high = max(c.high for c in candles)

        price_range = high - low

        if price_range <= 0:

            return profile

        step = price_range / self.rows

        histogram = defaultdict(float)
        buy_histogram = defaultdict(float)
        sell_histogram = defaultdict(float)

        # -------------------------------------------------
        # Build Histogram
        # -------------------------------------------------

        for candle in candles:

            typical = (

                candle.high

                + candle.low

                + candle.close

            ) / 3.0

            bucket = int(

                (typical - low) / step

            )

            bucket = max(

                0,

                min(bucket, self.rows - 1),

            )

            histogram[bucket] += candle.volume

            profile.total_volume += candle.volume

            if candle.close >= candle.open:

                buy_histogram[bucket] += candle.volume

            else:

                sell_histogram[bucket] += candle.volume

        # -------------------------------------------------
        # Create Nodes
        # -------------------------------------------------

        for bucket in sorted(histogram):

            node = VolumeNode(

                price=low + bucket * step,

                buy_volume=buy_histogram[bucket],

                sell_volume=sell_histogram[bucket],

                trades=1,

            )

            node.update()

            profile.nodes.append(node)

        if not profile.nodes:

            return profile

        # -------------------------------------------------
        # Point Of Control
        # -------------------------------------------------

        poc = max(

            profile.nodes,

            key=lambda n: n.volume,

        )

        poc.poc = True

        profile.poc = poc.price

        profile.developing_poc = poc.price

        # -------------------------------------------------
        # Value Area
        # -------------------------------------------------

        target = (

            profile.total_volume

            * self.value_area

        )

        running = 0.0

        selected = []

        ordered = sorted(

            profile.nodes,

            key=lambda n: n.volume,

            reverse=True,

        )

        for node in ordered:

            selected.append(node)

            node.value_area = True

            running += node.volume

            if running >= target:

                break

        prices = [

            n.price

            for n in selected

        ]

        profile.vah = max(prices)

        profile.val = min(prices)

        # -------------------------------------------------
        # HVN / LVN
        # -------------------------------------------------

        average = (

            profile.total_volume

            / len(profile.nodes)

        )

        for node in profile.nodes:

            if node.volume >= average * 1.50:

                node.hvn = True

                profile.hvn.append(node.price)

            elif node.volume <= average * 0.50:

                node.lvn = True

                profile.lvn.append(node.price)

            if node.delta > 0:

                node.buying_node = True

            elif node.delta < 0:

                node.selling_node = True

        # -------------------------------------------------
        # Finalize Profile
        # -------------------------------------------------

        profile.update()

        if profile.total_volume > 0:

            profile.confidence = 1.0

            profile.score = min(

                100.0,

                40.0
                + len(profile.hvn) * 5
                + len(profile.nodes) * 0.5,

            )

        return profile