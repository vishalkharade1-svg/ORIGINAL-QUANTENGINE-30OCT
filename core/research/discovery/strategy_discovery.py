"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- top-level entry point

The StrategyDiscoveryEngine is the public 9J surface: one call into the
deterministic pipeline for a symbol / dataset / evidence batch.

    engine = StrategyDiscoveryEngine(candles, ...)
    report = engine.run(records, base_config, dataset=dataset,
                        symbol="SYMBOL")

It is research-only: it never trades, never writes a ledger, never
mutates production strategy/risk state, never auto-promotes, and every
emitted status is one of the closed discovery vocabulary (REJECTED /
INCONCLUSIVE / PROMISING / REQUIRES_OOS / VALIDATED / BLOCKED) -- a
promotion token is never emitted (see constants.NEVER_EMITTED).

Optional AI providers are a LATER milestone (9L) and are NOT loaded by
this engine; nothing here requires sklearn / scipy / an AI SDK.
====================================================
"""

from core.research.discovery.discovery_runner import DiscoveryRunner
from core.research.discovery.robustness_filter import DiscoveryGates


class StrategyDiscoveryEngine:
    """Public 9J entry point: deterministic strategy discovery."""

    def __init__(self, candles=None, baseline_id="baseline",
                 oos_fraction=0.2, memory=None, gates=None, budget=None):
        self.candles = list(candles or ())
        self.baseline_id = baseline_id
        self.oos_fraction = oos_fraction
        self.memory = memory
        self.gates = gates or DiscoveryGates()
        self.budget = budget

    # -------------------------------------------------

    def run(self, records, base_config, dataset=None, symbol="UNKNOWN",
            extra_hypotheses=(), memory=None, budget=None):
        """Run one deterministic discovery session. Research-only."""
        memory = memory if memory is not None else self.memory
        budget = budget if budget is not None else self.budget
        runner = DiscoveryRunner(
            self.candles,
            baseline_id=self.baseline_id,
            oos_fraction=self.oos_fraction,
            gates=self.gates,
        )
        return runner.run(
            records,
            base_config,
            dataset=dataset,
            symbol=symbol,
            memory=memory,
            budget=budget,
            extra_hypotheses=tuple(extra_hypotheses or ()),
        )

    # -------------------------------------------------

    @staticmethod
    def availability():
        """Deterministic capability/availability statement."""
        return {
            "phase": "9J",
            "datasets": ["9I unified research dataset"],
            "executes": [
                "9C counterfactual grid",
                "9D analysis",
                "9E research intelligence",
                "9G temporal OOS + statistical baselines",
            ],
            "consumes": ["9F feature rows (observed only)"],
            "emits": [
                "REJECTED", "INCONCLUSIVE", "PROMISING",
                "REQUIRES_OOS", "VALIDATED", "BLOCKED",
            ],
            "never_emits": ["AUTOMATICALLY_DEPLOY", "PRODUCTION_READY"],
            "requires_external_sdk": False,
            "lookahead": False,
            "audit": False,
        }