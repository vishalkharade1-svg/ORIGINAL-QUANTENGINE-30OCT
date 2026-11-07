# Phase 12 triage: DOCUMENTED AS EXAMPLE (manual trading
# profile print demo; collects 0 tests by design).
# Top-level demo code is guarded so pytest collection has
# no side effects and stays silent.
from config.trading_profile import PROFILE
from config.trading_profile import PROFILES


def main():
    print()

    print("=" * 60)

    print(PROFILE)

    print("=" * 60)

    print(PROFILES[PROFILE])


if __name__ == "__main__":
    main()
