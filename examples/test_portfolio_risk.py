"""
====================================================

QuantEngine

Portfolio Manager Example

Run with:

    python -m examples.test_portfolio_risk

Drives the shared PortfolioRiskManager (risk/portfolio_risk.py)
that PortfolioBacktester wires in as its per-engine gate.
Demonstrates the three layers of portfolio control:

    1. Legacy caps      - dollar risk pool + position count.
    2. Allocation caps  - open notional as a % of equity,
                          both portfolio-wide and per symbol.
    3. Daily loss floor - realized PnL lagging the starting
                          balance by the limit orders every gate.

====================================================
"""

from risk.portfolio_risk import PortfolioRiskManager


def main():

    manager = PortfolioRiskManager(
        max_portfolio_risk=50.0,
        max_positions=4,
        starting_balance=10000.0,
        daily_loss_limit=200.0,
        max_portfolio_allocation=60.0,
        max_per_symbol_allocation=25.0,
    )

    orders = [
        ("BTC", 1200.0),
        ("ETH", 1800.0),
        ("BTC", 1000.0),
        ("SOL", 1500.0),
        ("ADA", 600.0),
    ]

    print("\n" + "=" * 60)
    print("PORTFOLIO MANAGER")
    print("=" * 60)
    print(f"Equity          : {manager.equity:,.2f}")
    print(f"Risk / positions: {manager.max_portfolio_risk} / "
          f"{manager.max_positions}")
    print(f"Allocation caps : portfolio "
          f"{manager.max_portfolio_allocation}%, per-symbol "
          f"{manager.max_per_symbol_allocation}%")
    print(f"Daily loss floor: "
          f"{manager.starting_balance - manager.daily_loss_limit:,.2f}")

    for symbol, notional in orders:

        opened = manager.can_open(
            10.0,
            symbol=symbol,
            position_value=notional,
        )

        if opened:
            manager.register_trade(
                10.0,
                symbol=symbol,
                position_value=notional,
            )

        print(
            f"  {symbol:>4} {notional:>7,.0f}  ->  "
            f"{'OPENED' if opened else 'BLOCKED'}"
            f"   (open notional {manager.open_notional:>7,.0f} / "
            f"equity {manager.equity:,.0f})"
        )

    # Close the BTC legs and show the notional release.
    manager.close_trade(10.0, symbol="BTC", pnl=-60.0)
    manager.close_trade(10.0, symbol="BTC", pnl=90.0)

    print(
        "\nAfter BTC closes: realized "
        f"{manager.realized_pnl:+.0f}, equity "
        f"{manager.equity:,.0f}, open notional "
        f"{manager.open_notional:,.0f}"
    )

    print()


if __name__ == "__main__":
    main()