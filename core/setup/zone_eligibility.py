"""
====================================================

QuantEngine

Zone Eligibility Log

Phase 4G STEP 12 -- an at-creation ledger of EVERY canonical
structural zone the TradeSetupBuilder generated a candidate
for, eligible or not, with the explicit rejection reason.

WHY IT EXISTS:
    Before Phase 4G the funnel only ever saw setups that
    reached the economic stage, so "how many zones were too
    old / too far / too thin to trade" was invisible. This log
    captures the zones that were REJECTED BEFORE an order could
    be minted, so the ENTRY ELIGIBILITY REPORT can count them
    and the ORDER BLOCK FRESHNESS REPORT can age-bucket them.

POPULATION RULE (identical to the EntryTracker's):
    one record per structural_id on its FIRST canonical
    appearance during the run. Re-derivations of the same zone
    on later candles re-use the first record, so the report
    population is directly comparable to the Phase 4F
    "entries tracked" number.

TIME SAFETY:
    Everything the log records is the candidate's at-creation
    snapshot -- zone age, freshness, entry distance, eligibility
    decision and reason, all measured at the creating candle.
    The log is consumed ONLY by reports; nothing it stores is
    ever read by TradeSetupBuilder / DecisionEngine / Execution
    / Risk / Backtester. It cannot leak future information by
    construction, and it cannot change a single order outcome.

====================================================
"""

from collections import Counter
from dataclasses import dataclass, field

from core.order_blocks.zone_freshness import (
    age_bucket,
    REASON_TOO_MANY_TOUCHES,
    REASON_WEAK_DISPLACEMENT,
)

# The report's age buckets (Phase 4G STEP 11), driven by the
# same bucket helper the freshness classifiers share.
_AGE_BUCKETS = ("0-5", "6-15", "16-30", "31-60", "61-120", "120+")


@dataclass(slots=True)
class ZoneEligibilityState:
    """
    First-appearance record of a canonical zone's at-creation
    statement. All fields are snapshots from the creating candle.
    """

    setup_id: str = ""

    structural_id: str = ""

    economic_fingerprint: str = ""

    direction: str = ""

    entry: float = 0.0

    stop_loss: float = 0.0

    take_profit: float = 0.0

    atr: float = 0.0

    # ---- eligibility (STEP 4 / 7) ----

    structurally_valid: bool = True

    trade_eligible: bool = True

    entry_rejection_reason: str = ""

    zone_diagnostics: list[str] = field(default_factory=list)

    # ---- zone snapshot (STEP 1-3) ----

    zone_age_bars: int = 0

    zone_freshness: str = "FRESH"

    zone_distance: float = 0.0

    zone_distance_atr: float = 0.0

    zone_is_canonical: bool = True

    observed_bar: int = 0


class ZoneEligibilityLog:
    """
    Session-state diagnostic (lives on PipelineContext like the
    EntryTracker / OrderRegistry): created once per run, untouched
    by reset_cycle(), re-created on reset().

        observe(setup, bar)              called by TradeSetupBuilder
                                         for every canonical candidate
        note_structurally_suppressed(n)  non-canonical zones merged
                                         this candle (STEP 9)
        report([direction])              end-of-run ENTRY ELIGIBILITY
                                         + FRESHNESS aggregates
        reset()                          fresh run
    """

    def __init__(self):

        self._states = {}

        self.structural_suppressed_total = 0

    # ==========================================================
    # Configuration / reset
    # ==========================================================

    def reset(self):

        self._states.clear()

        self.structural_suppressed_total = 0

    # ==========================================================
    # Recording
    # ==========================================================

    def observe(self, setup, bar=0):
        """
        First-appearance rule: one record per structural_id (the
        same key the EntryTracker uses), so the eligibility report
        population stays comparable to Phase 4F's tracked count.
        Recorded whether eligible or rejected -- the rejections are
        the missing half of the Phase 4F picture.
        """

        sid = (
            getattr(setup, "structural_id", "") or ""
        ) or (getattr(setup, "setup_id", "") or "")

        if not sid or sid in self._states:

            return

        self._states[sid] = ZoneEligibilityState(
            setup_id=(getattr(setup, "setup_id", "") or sid),
            structural_id=sid,
            economic_fingerprint=getattr(
                setup, "economic_fingerprint", ""
            ) or "",
            direction=getattr(setup, "direction", "") or "",
            entry=float(getattr(setup, "entry", 0.0) or 0.0),
            stop_loss=float(getattr(setup, "stop_loss", 0.0) or 0.0),
            take_profit=float(
                getattr(setup, "take_profit", 0.0) or 0.0
            ),
            atr=float(getattr(setup, "atr", 0.0) or 0.0),
            structurally_valid=bool(
                getattr(setup, "structurally_valid", True)
            ),
            trade_eligible=bool(
                getattr(setup, "trade_eligible", True)
            ),
            entry_rejection_reason=getattr(
                setup, "entry_rejection_reason", ""
            ) or "",
            zone_diagnostics=list(
                getattr(setup, "zone_diagnostics", None) or []
            ),
            zone_age_bars=int(
                getattr(setup, "zone_age_bars", 0) or 0
            ),
            zone_freshness=getattr(
                setup, "zone_freshness", ""
            ) or "FRESH",
            zone_distance=float(
                getattr(setup, "zone_distance", 0.0) or 0.0
            ),
            zone_distance_atr=float(
                getattr(setup, "zone_distance_atr", 0.0) or 0.0
            ),
            zone_is_canonical=bool(
                getattr(setup, "zone_is_canonical", True)
            ),
            observed_bar=int(bar or 0),
        )

    # ----------------------------------------------------------

    def note_structurally_suppressed(self, count):
        """
        STEP 9 ledger: how many non-canonical zones were merged
        into structural clusters (per candle, summed by the log).
        """

        if count:

            self.structural_suppressed_total += int(count or 0)

    # ==========================================================
    # Report (STEP 11 / 12)
    # ==========================================================

    def report(self, direction=None):
        """
        End-of-run ENTRY ELIGIBILITY + ORDER BLOCK FRESHNESS
        aggregates. `direction` filters to BULLISH / BEARISH for
        the report's per-direction block. Every number is drawn
        from at-creation snapshots -- diagnostic only.
        """

        states = list(self._states.values())

        if direction is not None:

            states = [
                s for s in states
                if (s.direction or "").upper()
                == (direction or "").upper()
            ]

        total = len(states)

        def _mean(values):

            vals = [v for v in values if v is not None]

            return (
                sum(vals) / len(vals)
                if vals
                else 0.0
            )

        by_reason = Counter(
            s.entry_rejection_reason for s in states
            if s.entry_rejection_reason
        )

        return {
            "zones_considered": total,
            "distinct_fingerprints": len({
                s.economic_fingerprint for s in states
                if s.economic_fingerprint
            }),
            "structurally_valid": sum(
                1 for s in states if s.structurally_valid
            ),
            "structurally_invalid": sum(
                1 for s in states if not s.structurally_valid
            ),
            "trade_eligible": sum(
                1 for s in states if s.trade_eligible
            ),
            "trade_ineligible": sum(
                1 for s in states if not s.trade_eligible
            ),
            "by_reason": dict(
                (k, by_reason.get(k, 0))
                for k in (
                    "STALE_ZONE",
                    "TOO_FAR_FROM_MARKET",
                    "ALREADY_MITIGATED",
                    "INVALIDATED_STRUCTURE",
                    "INSUFFICIENT_RISK_WIDTH",
                )
            ),
            "by_freshness": dict(
                (k, sum(1 for s in states if s.zone_freshness == k))
                for k in ("FRESH", "ACTIVE", "TESTED",
                          "MITIGATED", "STALE", "INVALIDATED")
            ),
            "by_age_bucket": dict(
                (k, sum(
                    1 for s in states
                    if age_bucket(s.zone_age_bars) == k
                ))
                for k in _AGE_BUCKETS
            ),
            "weak_displacement": sum(
                1 for s in states
                if REASON_WEAK_DISPLACEMENT in s.zone_diagnostics
            ),
            "too_many_touches": sum(
                1 for s in states
                if REASON_TOO_MANY_TOUCHES in s.zone_diagnostics
            ),
            "avg_zone_age_bars": round(
                _mean([s.zone_age_bars for s in states]), 2
            ),
            "avg_zone_distance": round(
                _mean([s.zone_distance for s in states]), 2
            ),
            "avg_zone_distance_atr": round(
                _mean([s.zone_distance_atr for s in states]), 2
            ),
            "structural_suppressed": (
                self.structural_suppressed_total
                if direction is None
                else 0
            ),
        }

    # ----------------------------------------------------------

    def states(self):

        return list(self._states.values())

    # ----------------------------------------------------------

    def count(self):

        return len(self._states)