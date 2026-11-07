"""
====================================================

QuantEngine

Deterministic Capital Allocator (Phase 8B)

The portfolio-layer allocator that turns a set of SIMULTANEOUS
candidate setups into a deterministic accept / defer decision
against the shared portfolio capital + risk budget.

For the canonical example:

    Portfolio equity:        $10,000
    Maximum portfolio risk:  2R        (risk budget)
    Available risk:          2R

    BTC candidate:           0.8R
    ETH candidate:           0.7R
    SOL candidate:           0.9R

    BTC -> ACCEPT 0.8R   (remaining 1.2R)
    ETH -> ACCEPT 0.7R   (remaining 0.5R)
    SOL -> REJECT/DEFER  (0.9R > 0.5R remaining; 0.8+0.7+0.9=2.4R
                           > 2R budget -- the allocator refuses it)

The allocator is DELIBERATELY DETERMINISTIC and has NO "smart
ranking" / scoring: candidates are processed strictly in the
order presented and accepted while the budget allows, so two
identical inputs always produce the identical allocation. This
is the infrastructure foundation; opportunity SELECTION (which
competing valid setup wins a scarce slot) belongs to a later
portfolio-opportunity layer (Phase 8C), and confluence / feature
ranking belongs to the future Confluence Engine (Phase 9) -- NOT
here.

THE INVARIANT (carried forward): the allocator only GATES (accept
/ defer) and only BOOKKEEPS (reserve on accept). It never
mutates a candidate / order / setup / strategy.
====================================================
"""

from core.risk.portfolio_state import CapitalCandidate, PortfolioState


class AllocationResult:
    """Per-candidate allocation outcome.

    accepted          -- did the portfolio accept (reserve) it?
    reason            -- on defer/decline, the gating dimension
    reservation_id    -- on accept, the id that must be released
                         on close / cancelled on failed execution
    """

    def __init__(self, candidate, accepted, reason="",
                 reservation_id=None):

        self.candidate = candidate
        self.accepted = accepted
        self.reason = reason or ""
        self.reservation_id = reservation_id

    @property
    def symbol(self):
        return self.candidate.symbol

    @property
    def direction(self):
        return self.candidate.direction

    @property
    def risk(self):
        return self.candidate.risk

    @property
    def capital(self):
        return self.candidate.capital

    def __repr__(self):
        if self.accepted:
            return (
                f"AllocationResult(ACCEPT {self.symbol} "
                f"{self.risk}R id={self.reservation_id})"
            )
        return (
            f"AllocationResult(REJECT/DEFER {self.symbol} "
            f"{self.risk}R reason={self.reason})"
        )


class CapitalAllocator:
    """Deterministic portfolio capital allocator.

    Processes candidates strictly in order, reserving each while
    the shared PortfolioState permits; defers the first candidate
    that would exceed the budget. No ranking -- deterministic by
    construction."""

    def __init__(self, state):
        self.state = state

    def _candidate(self, item):
        if isinstance(item, CapitalCandidate):
            return item
        if isinstance(item, dict):
            return CapitalCandidate(**item)
        return CapitalCandidate(order=item)

    def allocate(self, candidates):
        """Allocate a batch of simultaneous candidates.

        Returns a list[AllocationResult] in the SAME order as the
        input candidates (deterministic). Accepted candidates are
        reserved against the shared state; their reservation_id is
        returned so the caller can release (on close) or cancel
        (on failed execution)."""

        results = []

        for item in candidates:

            c = self._candidate(item)

            if self.state.can_accept(c):

                rid = self.state.reserve(c)

                results.append(
                    AllocationResult(c, True, reservation_id=rid)
                )

            else:

                results.append(
                    AllocationResult(c, False, reason=self.state.last_reason)
                )

        return results

    def release(self, reservation_id, pnl=0.0):
        """Release an accepted (reserved) candidate's capital.

        Called when its trade CLOSES. Delegate to the state."""

        self.state.release(reservation_id, pnl=pnl)

    def cancel(self, reservation_id):
        """Cancel a reservation after a failed execution.

        Called when execution never converted into a position.
        Delegate to the state."""

        self.state.cancel(reservation_id)
