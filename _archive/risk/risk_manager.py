"""
====================================================

QuantEngine

Institutional Risk Manager

====================================================
"""


class RiskManager:
    """
    Institutional Risk Policy Manager.

    This class decides whether trading is allowed.

    It NEVER calculates position size.
    """

    # -------------------------------------------------

    def __init__(

        self,

        account_balance,

        risk_percent=1.0,

        max_daily_loss=3.0,

        max_drawdown=20.0,

        max_open_positions=5,

        trading_enabled=True,

    ):

        self.account_balance = account_balance

        self.risk_percent = risk_percent

        self.max_daily_loss = max_daily_loss

        self.max_drawdown = max_drawdown

        self.max_open_positions = max_open_positions

        self.trading_enabled = trading_enabled

        self.daily_loss = 0.0

        self.drawdown = 0.0

        self.open_positions = 0

    # -------------------------------------------------

    def can_trade(self):

        if not self.trading_enabled:

            return False

        if self.daily_loss >= (

            self.account_balance

            * self.max_daily_loss

            / 100

        ):

            return False

        if self.drawdown >= self.max_drawdown:

            return False

        if self.open_positions >= self.max_open_positions:

            return False

        return True

    # -------------------------------------------------

    def risk_amount(self):

        return (

            self.account_balance

            * self.risk_percent

            / 100

        )

    # -------------------------------------------------

    def record_loss(

        self,

        amount,

    ):

        self.daily_loss += amount

    # -------------------------------------------------

    def update_drawdown(

        self,

        drawdown,

    ):

        self.drawdown = max(

            0.0,

            drawdown,

        )

    # -------------------------------------------------

    def position_opened(self):

        self.open_positions += 1

    # -------------------------------------------------

    def position_closed(self):

        self.open_positions = max(

            0,

            self.open_positions - 1,

        )

    # -------------------------------------------------

    def reset_day(self):

        self.daily_loss = 0.0