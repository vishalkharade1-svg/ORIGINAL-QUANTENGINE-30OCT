"""
====================================================

QuantEngine

Research Lab -- opportunity recovery analysis (Phase 9B)

Classifies each replayed opportunity against its BASELINE terminal
to answer:

   * how many opportunities did the baseline leave on the table?
   * which rule changes recover them?
   * were the recovered trades profitable?

Classification (baseline immutable):
   CAPTURED_BY_BASELINE              baseline already filled
   MISSED_BY_BASELINE
     + experiment fill -> WIN        RECOVERED_AND_PROFITABLE
     + experiment fill -> LOSS       RECOVERED_BUT_UNPROFITABLE
     + no experiment fill            MISSED_AND_STILL_UNRECOVERABLE
   REJECTED_BY_BASELINE
     + experiment fill               RECOVERED_IF_FILTER_CHANGED
     + no experiment fill            MISSED_AND_STILL_UNRECOVERABLE
====================================================
"""

_BASELINE_FILLED_TERMINALS = ("FILLED_OPEN", "FILLED_CLOSED")
_REJECTED_TERMINALS = ("REJECTED", "CANCELLED")


def classify_outcome(outcome):
    """Classify one CounterfactualOutcome recovery category."""
    terminal = (outcome.baseline_terminal or "").upper()
    filled_by_baseline = terminal in _BASELINE_FILLED_TERMINALS

    if filled_by_baseline:
        return "CAPTURED_BY_BASELINE"

    rejected_by_baseline = (
        terminal in _REJECTED_TERMINALS
        or bool(outcome.baseline_rejection)
    )

    if not outcome.filled:
        return "MISSED_AND_STILL_UNRECOVERABLE"

    profitable = outcome.result == "WIN"
    if rejected_by_baseline:
        if profitable:
            return "RECOVERED_IF_FILTER_CHANGED"
        # a rejected baseline that the experiment now fills --
        # whether profitable or not, it was recovered by a filter
        # change; use the unprofitable class when it lost.
        return (
            "RECOVERED_BUT_UNPROFITABLE"
            if outcome.result == "LOSS"
            else "RECOVERED_IF_FILTER_CHANGED"
        )

    if profitable:
        return "RECOVERED_AND_PROFITABLE"
    return "RECOVERED_BUT_UNPROFITABLE"


class OpportunityRecoveryReport:
    """Aggregated recovery classification for an experiment."""

    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.counts = {}
        self._compute()

    def _compute(self):
        for o in self.outcomes:
            k = classify_outcome(o)
            self.counts[k] = self.counts.get(k, 0) + 1

    def recovered(self):
        return sum(
            v for k, v in self.counts.items()
            if k.startswith("RECOVERED")
        )

    def recovered_profitable(self):
        return self.counts.get("RECOVERED_AND_PROFITABLE", 0)

    def recovered_unprofitable(self):
        return (
            self.counts.get("RECOVERED_BUT_UNPROFITABLE", 0)
            + self.counts.get("RECOVERED_IF_FILTER_CHANGED", 0)
        )

    def to_dict(self):
        return {
            "counts": dict(self.counts),
            "total_recovered": self.recovered(),
            "recovered_profitable": self.recovered_profitable(),
            "recovered_unprofitable": self.recovered_unprofitable(),
        }
