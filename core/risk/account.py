"""
====================================================

Institutional Trading Account

====================================================
"""

from core.risk.account_state import AccountState


class Account:

    def __init__(self, starting_balance=2000):

        self.state = AccountState(

            starting_balance=starting_balance,

            balance=starting_balance,

            equity=starting_balance,

            free_margin=starting_balance,

            peak_equity=starting_balance,

        )

    # -------------------------------------------------

    @property
    def balance(self):

        return self.state.balance

    # -------------------------------------------------

    @property
    def equity(self):

        return self.state.equity

    # -------------------------------------------------

    def update_equity(self):

        self.state.equity = (

            self.state.balance

            + self.state.unrealized_pnl

        )

        if self.state.equity > self.state.peak_equity:

            self.state.peak_equity = self.state.equity

        self.state.drawdown = (

            self.state.peak_equity

            - self.state.equity

        )

        if self.state.peak_equity > 0:

            self.state.drawdown_percent = (

                self.state.drawdown

                / self.state.peak_equity

            ) * 100

        if self.state.drawdown > self.state.max_drawdown:

            self.state.max_drawdown = (

                self.state.drawdown

            )

    # -------------------------------------------------

    def reset(self, starting_balance=None):
        """Reset to a fresh session IN PLACE (identity
        preserved). Callers holding this Account (e.g. the
        code that passed it into Backtester / BrokerEngine)
        keep seeing the booked state after a run -- reset()
        must never silently swap the object. Defaults to
        the current starting_balance."""

        start = (
            starting_balance
            if starting_balance is not None
            else self.state.starting_balance
        )

        self.state = AccountState(

            starting_balance=start,

            balance=start,

            equity=start,

            free_margin=start,

            peak_equity=start,

        )

    # -------------------------------------------------

    def update_unrealized(self, pnl):

        self.state.unrealized_pnl = pnl

        self.state.floating_pnl = pnl

        self.update_equity()

    # -------------------------------------------------

    def book_profit(self, pnl):

        self.state.balance += pnl

        self.state.realized_pnl += pnl

        self.state.daily_pnl += pnl

        self.state.weekly_pnl += pnl

        self.state.monthly_pnl += pnl

        self.state.total_trades += 1

        self.state.winning_trades += 1

        self.state.consecutive_wins += 1

        self.state.consecutive_losses = 0

        self.state.unrealized_pnl = 0

        self.state.floating_pnl = 0

        self.state.free_margin = self.state.balance

        self.update_statistics()

        self.update_equity()

    # -------------------------------------------------

    def book_breakeven(self):

        # Canonical BREAKEVEN: pnl == 0 → neither win nor loss, but
        # counts toward total and resets both streaks (phase 9Q-5).
        self.state.total_trades += 1

        self.state.breakeven_trades += 1

        self.state.consecutive_wins = 0

        self.state.consecutive_losses = 0

        self.state.unrealized_pnl = 0

        self.state.floating_pnl = 0

        self.state.free_margin = self.state.balance

        self.update_statistics()

        self.update_equity()

    # -------------------------------------------------

    def book_loss(self, loss):

        loss = abs(loss)

        self.state.balance -= loss

        self.state.realized_pnl -= loss

        self.state.daily_pnl -= loss

        self.state.weekly_pnl -= loss

        self.state.monthly_pnl -= loss

        self.state.total_trades += 1

        self.state.losing_trades += 1

        self.state.consecutive_losses += 1

        self.state.consecutive_wins = 0

        self.state.unrealized_pnl = 0

        self.state.floating_pnl = 0

        self.state.free_margin = self.state.balance

        self.update_statistics()

        self.update_equity()

    # -------------------------------------------------

    def update_statistics(self):

        if self.state.total_trades:

            self.state.win_rate = (

                self.state.winning_trades

                / self.state.total_trades

            ) * 100

    # -------------------------------------------------

    def reset_daily(self):

        self.state.daily_pnl = 0

    # -------------------------------------------------

    def reset_weekly(self):

        self.state.weekly_pnl = 0

    # -------------------------------------------------

    def reset_monthly(self):

        self.state.monthly_pnl = 0

    # -------------------------------------------------

    def roll_pnl_windows(self, timestamp):
        """Roll daily/weekly/monthly PnL windows (Phase 12).

        Thin wrapper over roll_state_pnl_windows for the
        owned AccountState.
        """

        roll_state_pnl_windows(self.state, timestamp)


def roll_state_pnl_windows(state, timestamp):
    """Roll an AccountState's PnL windows (Phase 12).

    Derives UTC calendar keys from a candle timestamp
    (epoch seconds) and resets any window whose key has
    rolled over. Deterministic: identical timestamps always
    produce identical windows; a missing/invalid timestamp
    rolls nothing (never fabricates a window boundary).
    Called per candle by RiskEngine before the loss-limit
    gate so MAX_DAILY/WEEKLY/MONTHLY_LOSS mean "this UTC
    day / ISO week / calendar month". Operates on the state
    object because the pipeline publishes AccountState (not
    Account) into context.
    """

    import datetime

    try:
        moment = datetime.datetime.fromtimestamp(
            float(timestamp), tz=datetime.timezone.utc
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return

    day_key = moment.strftime("%Y-%m-%d")

    iso_year, iso_week, _ = moment.isocalendar()

    week_key = "%04d-W%02d" % (iso_year, iso_week)

    month_key = moment.strftime("%Y-%m")

    if not state.pnl_day_key:
        state.pnl_day_key = day_key

    elif state.pnl_day_key != day_key:
        state.pnl_day_key = day_key
        state.daily_pnl = 0.0

    if not state.pnl_week_key:
        state.pnl_week_key = week_key

    elif state.pnl_week_key != week_key:
        state.pnl_week_key = week_key
        state.weekly_pnl = 0.0

    if not state.pnl_month_key:
        state.pnl_month_key = month_key

    elif state.pnl_month_key != month_key:
        state.pnl_month_key = month_key
        state.monthly_pnl = 0.0