"""
====================================================

QuantEngine

Counterfactual Simulation -- opportunity categories (Phase 9C)

Deterministic classification of an OpportunityRecord into the
category the counterfactual lab reasons over. Categories are
derived ONLY from authoritative Phase 9A facts already present in
the record (terminal outcome + verbatim rejection reasons); nothing
is fabricated. When the record does not carry enough evidence the
category is NON_EVALUABLE.

Vocabulary:
   FILLED               baseline filled (FILLED_OPEN / FILLED_CLOSED)
   REJECTED             rejected (rejection reasons or REJECTED/CANCELLED)
   MISSED_CONTINUATION  EXPIRED -- an unfilled limit that expired = a
                        missed continuation candidate
   INVALIDATED          INVALIDATED terminal
   ENTRY_NOT_REACHED    setup asserted but no order / pending -- entry
                        was not reached
   NON_EVALUABLE        insufficient authoritative evidence
====================================================
"""

FILLED = "FILLED"
REJECTED = "REJECTED"
MISSED_CONTINUATION = "MISSED_CONTINUATION"
INVALIDATED = "INVALIDATED"
ENTRY_NOT_REACHED = "ENTRY_NOT_REACHED"
NON_EVALUABLE = "NON_EVALUABLE"

_FILLED_TERMINALS = ("FILLED_OPEN", "FILLED_CLOSED")
_REJECTED_TERMINALS = ("REJECTED", "CANCELLED")


def classify_opportunity(record):
    """Deterministic category for an OpportunityRecord."""
    terminal = (getattr(record, "terminal_outcome", "") or "").upper()
    setup = getattr(record, "setup", None) or {}
    reasons = setup.get("rejection_reasons") or []

    if reasons:
        return REJECTED
    if terminal in _REJECTED_TERMINALS:
        return REJECTED
    if terminal in _FILLED_TERMINALS:
        return FILLED
    if terminal == "EXPIRED":
        return MISSED_CONTINUATION
    if terminal == "INVALIDATED":
        return INVALIDATED
    if terminal in ("ORDER_NOT_CREATED", "PENDING", ""):
        return ENTRY_NOT_REACHED
    return NON_EVALUABLE
