from core.risk.account import Account


def main():

    account = Account(starting_balance=2000)

    print("=" * 60)
    print("INITIAL ACCOUNT")
    print("=" * 60)

    print("Balance :", account.balance)
    print("Equity  :", account.equity)

    print()

    print("=" * 60)
    print("BOOK PROFIT +100")
    print("=" * 60)

    account.book_profit(100)

    print("Balance :", account.balance)
    print("Equity  :", account.equity)
    print("Daily PnL :", account.state.daily_pnl)
    print("Win Rate :", account.state.win_rate)

    print()

    print("=" * 60)
    print("BOOK LOSS -40")
    print("=" * 60)

    account.book_loss(40)

    print("Balance :", account.balance)
    print("Equity  :", account.equity)
    print("Daily PnL :", account.state.daily_pnl)
    print("Win Rate :", account.state.win_rate)

    print()

    print("=" * 60)
    print("UNREALIZED +75")
    print("=" * 60)

    account.update_unrealized(75)

    print("Equity :", account.equity)
    print("Floating :", account.state.floating_pnl)

    print()

    print("=" * 60)
    print("DRAWDOWN")
    print("=" * 60)

    print("Peak Equity :", account.state.peak_equity)
    print("Drawdown :", account.state.drawdown)
    print("Drawdown % :", account.state.drawdown_percent)


if __name__ == "__main__":
    main()