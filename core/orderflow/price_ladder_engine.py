"""
====================================================

QuantEngine

Institutional Price Ladder Engine

Supports:
1. Replay Mode (OHLCV Approximation)
2. Live Mode (Trade Stream)

====================================================
"""

from core.orderflow.price_ladder import PriceLadder
from core.orderflow.price_level import PriceLevel


class PriceLadderEngine:

    def __init__(

        self,

        mode="REPLAY",

    ):

        self.mode = mode

    # =================================================

    def process(

        self,

        context,

    ):

        if context.latest_candle is None:

            return PriceLadder()

        if self.mode.upper() == "LIVE":

            return self._process_live(context)

        return self._process_replay(context)

    # =================================================

    def _process_replay(

        self,

        context,

    ):

        candle = context.latest_candle

        ladder = PriceLadder(

            candle_index=getattr(

                candle,

                "index",

                0,

            ),

            timestamp=candle.timestamp,

            timeframe=getattr(

                candle,

                "timeframe",

                "",

            ),

        )

        total_volume = max(

            getattr(

                candle,

                "volume",

                0.0,

            ),

            0.0,

        )

        prices = [

            candle.low,

            (

                candle.low

                + candle.high

            ) / 2,

            candle.high,

        ]

        bullish = candle.close >= candle.open

        volume_each = (

            total_volume

            / len(prices)

            if prices

            else 0.0

        )

        body = abs(

            candle.close

            - candle.open

        )

        rng = max(

            candle.high

            - candle.low,

            1e-9,

        )

        body_ratio = body / rng

        bias = 0.15 + body_ratio * 0.20

        for price in prices:

            level = PriceLevel(

                price=price,

                total_volume=volume_each,

            )

            if bullish:

                buy_ratio = 0.50 + bias

            else:

                buy_ratio = 0.50 - bias

            buy_ratio = max(

                0.05,

                min(

                    buy_ratio,

                    0.95,

                ),

            )

            sell_ratio = 1.0 - buy_ratio

            level.buy_volume = volume_each * buy_ratio

            level.sell_volume = volume_each * sell_ratio

            level.delta = (

                level.buy_volume

                - level.sell_volume

            )

            level.imbalance = abs(

                level.delta

            ) / max(

                level.total_volume,

                1.0,

            )

            level.absorption = (

                body_ratio < 0.30

                and level.imbalance > 0.40

            )

            level.exhaustion = (

                body_ratio > 0.85

                and level.imbalance < 0.20

            )

            ladder.add_level(

                level,

            )

        self._finalize(

            ladder,

        )

        return ladder

    # =================================================

    def _process_live(

        self,

        context,

    ):

        ladder = PriceLadder()

        trades = getattr(

            context,

            "trades",

            [],

        )

        if not trades:

            return ladder

        levels = {}

        for trade in trades:

            price = trade.price

            if price not in levels:

                levels[price] = PriceLevel(

                    price=price,

                )

            level = levels[price]

            qty = trade.quantity

            if trade.side.upper() == "BUY":

                level.buy_volume += qty

            else:

                level.sell_volume += qty

            level.total_volume += qty

            level.delta = (

                level.buy_volume

                - level.sell_volume

            )

            level.trades += 1

        for level in sorted(

            levels.values(),

            key=lambda x: x.price,

        ):

            ladder.add_level(level)

        self._finalize(

            ladder,

        )

        return ladder

    # =================================================

    def _finalize(

        self,

        ladder,

    ):

        if not ladder.levels:

            return

        ladder.update()

        if ladder.strongest_level:

            ladder.poc = (

                ladder.strongest_level.price

            )

        ladder.absorption = any(

            level.absorption

            for level in ladder.levels

        )

        ladder.exhaustion = any(

            level.exhaustion

            for level in ladder.levels

        )

        ladder.stacked_imbalance = (

            sum(

                1

                for level in ladder.levels

                if level.imbalance >= 0.60

            ) >= 2

        )

        ladder.score = min(

            ladder.imbalance * 0.5

            + abs(

                ladder.total_delta

            )

            / max(

                ladder.total_volume,

                1.0,

            )

            * 50,

            100.0,

        )

        ladder.confidence = (

            ladder.score / 100.0

        )