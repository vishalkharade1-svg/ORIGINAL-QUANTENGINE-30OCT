"""
====================================================

QuantEngine

Research Journal -- query (Phase 9A)

Read-only filter surface over the repository. Every filter is
a deterministic, side-effect-free selection on OBSERVED facts.
No filter mutates the repository or alters any decision.

Key filters in the Phase 9A acceptance contract:

   * provenance      (BACKTEST / PAPER / LIVE)
   * entry_mode      (strategy segment of the canonical id)
   * rejection reason (exact verbatim string)
   * terminal outcome
   * symbol / timeframe
====================================================
"""


class JournalQuery:
    """Composable read-only filters over a ResearchRepository."""

    def __init__(self, repository):
        self.records = list(repository.records)

    # --------------------------------------------------
    # Primitive filters (each returns a new JournalQuery)
    # --------------------------------------------------

    def with_provenance(self, provenance):
        p = str(provenance)
        self.records = [
            r for r in self.records if str(r.provenance) == p
        ]
        return self

    def with_entry_mode(self, entry_mode):
        self.records = [
            r for r in self.records if r.strategy == entry_mode
        ]
        return self

    def with_terminal_outcome(self, outcome):
        self.records = [
            r for r in self.records if r.terminal_outcome == outcome
        ]
        return self

    def with_symbol(self, exchange=None, instrument_id=None):
        def _match(r):
            if exchange is not None and r.exchange != exchange:
                return False
            if instrument_id is not None and r.instrument_id != instrument_id:
                return False
            return True

        self.records = [r for r in self.records if _match(r)]
        return self

    def with_rejection_reason(self, reason):
        reason = str(reason)
        out = []
        for r in self.records:
            reasons = (r.setup or {}).get("rejection_reasons", [])
            if reason in [str(x) for x in reasons]:
                out.append(r)
        self.records = out
        return self

    def with_rejection(self):
        """Only opportunities whose setup was rejected."""
        out = []
        for r in self.records:
            if (r.setup or {}).get("rejected", False):
                out.append(r)
        self.records = out
        return self

    def with_order_status(self, status):
        status = str(status)
        out = []
        for r in self.records:
            if (r.order or {}).get("status") == status:
                out.append(r)
        self.records = out
        return self

    def with_result(self, result):
        result = str(result)
        out = []
        for r in self.records:
            if (r.trade or {}).get("result") == result:
                out.append(r)
        self.records = out
        return self

    # --------------------------------------------------
    # Terminal materialisers
    # --------------------------------------------------

    def all(self):
        return list(self.records)

    def count(self):
        return len(self.records)

    def first(self):
        return self.records[0] if self.records else None

    def last(self):
        return self.records[-1] if self.records else None
