"""
====================================================

Execution Engine Test

====================================================
"""

# Phase 12 triage: DOCUMENTED AS EXAMPLE (manual
# execution-engine demo; collects 0 tests by design). The
# import-time print below was collection noise and is
# removed; the demo itself runs under main() only.
from core.execution.execution_engine import ExecutionEngine
from core.setup.setup_candidate import SetupCandidate
from core.setup.trade_setup_registry import TradeSetupRegistry


class DummyContext:

    def __init__(self):

        self.decision = TradeSetupRegistry()
        self.execution_signal = None


def main():

    context = DummyContext()

    buy = SetupCandidate(
        direction="BULLISH",
        entry=100,
        stop_loss=95,
        take_profit=120,
        risk_reward=4,
        confidence=88,
        score=88,
    )

    sell = SetupCandidate(
        direction="BEARISH",
        entry=110,
        stop_loss=115,
        take_profit=90,
        risk_reward=4,
        confidence=95,
        score=95,
    )

    # Add both setups
    context.decision.add(buy)
    context.decision.add(sell)

    # Run engine
    engine = ExecutionEngine()
    engine.analyze(context)

    print()
    print("=" * 60)
    print("TEST RESULT")
    print("=" * 60)

    if context.execution_signal is None:
        print("FAILED")
        return

    signal = context.execution_signal

    print("Direction :", signal.direction)
    print("Entry     :", signal.entry)
    print("Stop      :", signal.stop_loss)
    print("Target    :", signal.take_profit)
    print("Score     :", signal.score)

    assert signal.score == 95
    assert signal.direction == "BEARISH"

    print()
    print("ExecutionEngine Test PASSED")


if __name__ == "__main__":
    print("MAIN STARTED")
    main()