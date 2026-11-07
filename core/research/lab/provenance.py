"""
====================================================

QuantEngine

Research Lab -- provenance (Phase 9B)

Lab results are COUNTERFACTUAL / SIMULATED by construction. They
describe what WOULD have happened under an alternative rule set,
NOT what actually happened. The Phase 9A journal Provenance
(BACKTEST / PAPER / LIVE) records reality; the lab provenance
below is distinct and immutable so that a simulated trade can
never be mistaken for a settled production trade.

====================================================
"""

from enum import Enum


class LabProvenance(str, Enum):
    COUNTERFACTUAL = "COUNTERFACTUAL"
    SIMULATED = "SIMULATED"

    @property
    def value_str(self):
        return str(self.value)
