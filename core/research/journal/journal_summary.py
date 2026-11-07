"""
====================================================

QuantEngine

Research Journal -- summary (Phase 9A)

Aggregate counts + lifecycle analytics over the repository.
TERMINOLOGY reuse contract (Phase 9A): counts/averages speak
the SAME language as the authoritative PerformanceAnalytics
(WIN / LOSS / R / PnL). This module does NOT reimplement
performance math -- it only counts and averages OBSERVED facts
already recorded.

Deferred to later phases: expectancy / PF-style statistics keyed
to simulated counterfactuals (the authority for those outcomes
does not exist until a simulation phase provides them).
====================================================
"""

from core.research.journal.research_enums import Result


class JournalSummary:
    """Deterministic aggregate summary over a repository."""

    def __init__(self, repository):
        self.records = list(repository.records)
        self._setup = [
            r for r in self.records if r.setup
        ]
        self._orders = [
            r for r in self.records if r.order
        ]
        self._trades = [
            r for r in self.records if r.trade
        ]

    # --------------------------------------------------

    @property
    def total(self):
        return len(self.records)

    @property
    def setups_discovered(self):
        return len(self._setup)

    @property
    def setups_rejected(self):
        n = 0
        for r in self._setup:
            if r.setup.get("rejected", False):
                n += 1
        return n

    @property
    def setups_eligible(self):
        return self.setups_discovered - self.setups_rejected

    @property
    def orders_created(self):
        return len(self._orders)

    @property
    def orders_filled(self):
        n = 0
        for r in self._orders:
            if (r.order or {}).get("status") == "FILLED":
                n += 1
        return n

    @property
    def trades_closed(self):
        return len(self._trades)

    @property
    def wins(self):
        return self._count_result(Result.WIN.value)

    @property
    def losses(self):
        return self._count_result(Result.LOSS.value)

    def _count_result(self, result):
        n = 0
        for r in self._trades:
            if (r.trade or {}).get("result") == result:
                n += 1
        return n

    @property
    def total_pnl(self):
        return sum((r.trade or {}).get("pnl") or 0.0 for r in self._trades)

    @property
    def total_r(self):
        return sum(
            (r.trade or {}).get("r") or 0.0 for r in self._trades
        )

    # --------------------------------------------------

    def counts(self):
        return {
            "total_opportunities": self.total,
            "setups_discovered": self.setups_discovered,
            "setups_eligible": self.setups_eligible,
            "setups_rejected": self.setups_rejected,
            "orders_created": self.orders_created,
            "orders_filled": self.orders_filled,
            "trades_closed": self.trades_closed,
            "wins": self.wins,
            "losses": self.losses,
            "total_pnl": self.total_pnl,
            "total_r": self.total_r,
        }

    def by_entry_mode(self):
        """Count opportunities per entry_mode (strategy segment),
        with discover / eligible / rejected / filled breakdowns."""
        out = {}
        for r in self.records:
            mode = r.strategy or "(none)"
            bucket = out.setdefault(
                mode,
                {
                    "discovered": 0,
                    "eligible": 0,
                    "rejected": 0,
                    "orders": 0,
                    "filled": 0,
                },
            )
            bucket["discovered"] += 1
            if r.setup:
                if r.setup.get("rejected", False):
                    bucket["rejected"] += 1
                else:
                    bucket["eligible"] += 1
            if r.order:
                bucket["orders"] += 1
                if (r.order or {}).get("status") == "FILLED":
                    bucket["filled"] += 1
        return out

    def rejection_breakdown(self):
        """Tally of rejection reasons (verbatim preserved)."""
        tally = {}
        for r in self._setup:
            for reason in r.setup.get("rejection_reasons", []):
                key = str(reason)
                tally[key] = tally.get(key, 0) + 1
        return tally
