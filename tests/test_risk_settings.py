# Phase 12 triage: DOCUMENTED AS EXAMPLE (manual risk
# settings print demo; collects 0 tests by design).
# Top-level demo code is guarded so pytest collection has
# no side effects and stays silent.
import config.risk_settings as settings


def main():
    print()

    print("=" * 60)

    print("RISK SETTINGS")

    print("=" * 60)

    print("Balance :", settings.STARTING_BALANCE)

    print("Risk :", settings.RISK_PER_TRADE)

    print("Allocation :", settings.MAX_ALLOCATION_PER_TRADE)

    print("Paper :", settings.PAPER_MODE)

    print("Profit Protection :", settings.PROFIT_PROTECTION)


if __name__ == "__main__":
    main()
