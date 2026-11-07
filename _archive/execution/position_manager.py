"""
====================================================

QuantEngine

Institutional Position Manager

====================================================
"""

from execution.position import Position


class PositionManager:

    def __init__(self):

        self.positions = {}

        self.closed_positions = []

    # -------------------------------------------------

    def open_position(self, order):

        position = Position(

            symbol=order.symbol,

            side=order.side,

            quantity=order.quantity,

            entry=order.entry,

            stop_loss=order.stop_loss,

            take_profit=order.take_profit,

        )

        # Institutional metadata
        position.open = True
        position.pnl = 0.0

        position.highest_price = position.entry
        position.lowest_price = position.entry

        position.max_profit = 0.0
        position.max_loss = 0.0

        position.exit_reason = None

        self.positions[order.symbol] = position

        return position

    # -------------------------------------------------

    def get(self, symbol):

        return self.positions.get(symbol)

    # -------------------------------------------------

    def is_open(self, symbol):

        position = self.get(symbol)

        return position is not None and position.open

    # -------------------------------------------------

    def update_price(

        self,

        symbol,

        price,

    ):

        position = self.get(symbol)

        if position is None:

            return None

        # --------------------------------------------
        # Track Extremes
        # --------------------------------------------

        position.highest_price = max(

            position.highest_price,

            price,

        )

        position.lowest_price = min(

            position.lowest_price,

            price,

        )

        # --------------------------------------------
        # BUY
        # --------------------------------------------

        if position.side == "BUY":

            pnl = (

                price - position.entry

            ) * position.quantity

            position.pnl = pnl

            position.max_profit = max(

                position.max_profit,

                pnl,

            )

            position.max_loss = min(

                position.max_loss,

                pnl,

            )

            if price <= position.stop_loss:

                return self.close(

                    symbol,

                    price,

                    "STOP_LOSS",

                )

            if price >= position.take_profit:

                return self.close(

                    symbol,

                    price,

                    "TAKE_PROFIT",

                )

        # --------------------------------------------
        # SELL
        # --------------------------------------------

        elif position.side == "SELL":

            pnl = (

                position.entry - price

            ) * position.quantity

            position.pnl = pnl

            position.max_profit = max(

                position.max_profit,

                pnl,

            )

            position.max_loss = min(

                position.max_loss,

                pnl,

            )

            if price >= position.stop_loss:

                return self.close(

                    symbol,

                    price,

                    "STOP_LOSS",

                )

            if price <= position.take_profit:

                return self.close(

                    symbol,

                    price,

                    "TAKE_PROFIT",

                )

        return position

    # -------------------------------------------------

    def close(

        self,

        symbol,

        price,

        reason="MANUAL",

    ):

        position = self.get(symbol)

        if position is None:

            return None

        position.open = False

        position.exit_price = price

        position.exit_reason = reason

        self.closed_positions.append(position)

        self.positions.pop(symbol, None)

        return position

    # -------------------------------------------------

    def reset(self):

        self.positions.clear()

        self.closed_positions.clear()

    # -------------------------------------------------

    @property

    def open_count(self):

        return len(self.positions)

    # -------------------------------------------------

    @property

    def closed_count(self):

        return len(self.closed_positions)