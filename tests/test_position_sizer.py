from core.risk.position_sizer import PositionSizer


def main():

    sizer = PositionSizer()

    result = sizer.calculate(

        balance=2000,

        entry_price=250000,

        stop_price=248000,

        leverage=10,

    )

    print("=" * 60)

    print("POSITION SIZER")

    print("=" * 60)

    print("Balance         :", result.balance)

    print("Risk %          :", result.risk_percent * 100)

    print("Risk Amount     :", result.risk_amount)

    print("Allocation      :", result.allocation)

    print("Entry           :", result.entry_price)

    print("Stop            :", result.stop_price)

    print("Stop Distance   :", result.stop_distance)

    print("Quantity        :", result.quantity)

    print("Position Value  :", result.position_value)

    print("Expected Loss   :", result.expected_loss)

    print("Valid           :", result.valid)

    print("Reason          :", result.reason)


if __name__ == "__main__":
    main()