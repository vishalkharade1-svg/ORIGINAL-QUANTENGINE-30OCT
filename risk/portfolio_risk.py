"""
====================================================

QuantEngine

Portfolio Risk Manager

====================================================
"""


class PortfolioRiskManager:

    def __init__(
        self,
        max_portfolio_risk=5.0,
        max_positions=5,
        starting_balance=0.0,
        daily_loss_limit=0.0,
        max_portfolio_allocation=0.0,
        max_per_symbol_allocation=0.0,
    ):

        # Legacy risk caps (dollar risk / position count).
        self.max_portfolio_risk = max_portfolio_risk
        self.max_positions = max_positions

        # Equity basis for the allocation and daily-loss guards.
        # 0.0 leaves each guard disabled (fully backward
        # compatible) -- enable by passing a value > 0.
        self.starting_balance = starting_balance
        self.daily_loss_limit = daily_loss_limit

        # Notional (position_value) caps expressed as a
        # percentage of current equity. 0.0 = disabled.
        self.max_portfolio_allocation = max_portfolio_allocation
        self.max_per_symbol_allocation = max_per_symbol_allocation

        self.current_risk = 0.0
        self.open_positions = 0

        # Per-symbol open notional bookkeeping so concentration
        # can be enforced and released symmetrically on close.
        # {symbol: {"notional": float, "risk": float}}
        self.open_by_symbol = {}

        self.realized_pnl = 0.0

    # -------------------------------------------------

    @property
    def equity(self):

        return self.starting_balance + self.realized_pnl

    # -------------------------------------------------

    @property
    def open_notional(self):

        return sum(
            entry["notional"]
            for entry in self.open_by_symbol.values()
        )

    # -------------------------------------------------

    def _allocation_cap(self, percent):

        if percent <= 0.0:
            return None

        if self.equity <= 0.0:
            return 0.0

        return self.equity * percent / 100.0

    # -------------------------------------------------

    def can_open(
        self,
        trade_risk,
        symbol=None,
        position_value=0.0,
    ):

        # Daily loss guard: once realized PnL lags the starting
        # balance by more than the limit, every order is gated.
        if self.daily_loss_limit > 0.0:

            floor = self.starting_balance - self.daily_loss_limit

            if self.equity <= floor:
                return False

        if self.open_positions >= self.max_positions:
            return False

        if (
            self.current_risk + trade_risk
            > self.max_portfolio_risk
        ):
            return False

        cap = self._allocation_cap(
            self.max_portfolio_allocation
        )

        if cap is not None:

            if self.open_notional + position_value > cap:
                return False

        symbol_cap = self._allocation_cap(
            self.max_per_symbol_allocation
        )

        if symbol_cap is not None:

            symbol_notional = 0.0

            if symbol is not None:
                entry = self.open_by_symbol.get(symbol)
                symbol_notional = (
                    entry["notional"] if entry else 0.0
                )

            if symbol_notional + position_value > symbol_cap:
                return False

        return True

    # -------------------------------------------------

    def register_trade(
        self,
        trade_risk,
        symbol=None,
        position_value=0.0,
    ):

        self.current_risk += trade_risk
        self.open_positions += 1

        if symbol is not None:

            entry = self.open_by_symbol.get(symbol)

            if entry is None:

                entry = {
                    "notional": position_value,
                    "risk": trade_risk,
                }

                self.open_by_symbol[symbol] = entry

            else:

                entry["notional"] += position_value
                entry["risk"] += trade_risk

    # -------------------------------------------------

    def close_trade(
        self,
        trade_risk,
        symbol=None,
        pnl=0.0,
    ):

        self.current_risk -= trade_risk

        if self.current_risk < 0:
            self.current_risk = 0

        if self.open_positions > 0:
            self.open_positions -= 1

        if symbol is not None:
            self.open_by_symbol.pop(symbol, None)

        self.realized_pnl += pnl

    # -------------------------------------------------

    def reset(self):

        self.current_risk = 0.0
        self.open_positions = 0
        self.open_by_symbol = {}
        self.realized_pnl = 0.0