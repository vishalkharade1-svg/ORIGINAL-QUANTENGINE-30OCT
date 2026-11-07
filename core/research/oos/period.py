"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- periods

Deterministic chronological partition of the opportunity population
into a DISCOVERY region and an OUT-OF-SAMPLE region, then the OOS
region into N equal, non-overlapping chronological periods.

   |---------- DISCOVERY 50% ----------|-------- OOS 50% --------|
                                        | O1 | O2 | O3 | O4 | O5 | O6 |

Transitions:
   * chronological only -- no shuffle, no randomization;
   * boundaries are INDEX boundaries into the time-ordered population
     (never invented calendar dates; no dates are fabricated);
   * purge/embargo are explicit (default 0) and applied only when the
     dataset can support the requested removal -- otherwise the
     leakage guard reports UNAVAILABLE rather than pretending;
   * the outcome-horizon leakage guard derives the required protection
     from the existing outcome/expiry semantics and reports
     NOT_REQUIRED / PROTECTED / UNAVAILABLE honestly.
====================================================================
"""

import math
from dataclasses import dataclass, field

from core.research.oos.oos_types import PeriodBoundary


def _proto_item(record):
    if hasattr(record, "decision_bar"):
        bar = record.decision_bar
        if isinstance(bar, (int, float)):
            return bar
    order = getattr(record, "order", {}) or {}
    if order.get("created_bar") is not None:
        return order["created_bar"]
    setup = getattr(record, "setup", {}) or {}
    if setup.get("bar") is not None:
        return setup["bar"]
    if hasattr(record, "bar") and isinstance(record.bar, (int, float)):
        return record.bar
    return None


def time_key(item, index):
    """Deterministic chronological key for an opportunity.

    Mirrors the 9G split convention (decision_bar preferred) with a
    stable (canonical_id) tie-break so duplicate decision bars never
    produce ordering ambiguity.
    """
    cid = getattr(item, "canonical_id", "") or ""
    bar = _proto_item(item)
    if bar is not None and isinstance(bar, (int, float)):
        return (0, float(bar), cid)
    if hasattr(item, "timestamp") and item.timestamp is not None:
        try:
            return (1, float(item.timestamp), cid)
        except (TypeError, ValueError):
            pass
    return (2, float(index), cid)


def sorted_opportunities(opportunities):
    indexed = list(enumerate(opportunities))
    indexed.sort(key=lambda t: time_key(t[1], t[0]))
    return [it for _, it in indexed]


def decision_bar(item):
    """The decision bar used for chronological positioning (aligns with
    the 9C simulator's created_bar -> setup.bar precedence)."""
    bar = _proto_item(item)
    if bar is None:
        return None
    return int(bar)


@dataclass(frozen=True)
class OosPartition:
    """The deterministic 9M partition of one opportunity population."""

    ordered: tuple = field(default_factory=tuple)
    discovery: tuple = field(default_factory=tuple)
    oos_periods: tuple = field(default_factory=tuple)  # tuple of tuples
    boundaries: tuple = field(default_factory=tuple)   # PeriodBoundary
    purge_bars: int = 0
    embargo_bars: int = 0
    leak: dict = field(default_factory=dict)

    def period_records(self, i):
        return self.oos_periods[i]

    def n_periods(self):
        return len(self.oos_periods)

    def to_dict(self):
        return {
            "n_total": len(self.ordered),
            "n_discovery": len(self.discovery),
            "n_oos": sum(len(p) for p in self.oos_periods),
            "n_oos_periods": len(self.oos_periods),
            "chronological": True,
            "no_shuffle": True,
            "discovery_fraction": round(
                (len(self.discovery) / len(self.ordered))
                if self.ordered else 0.0, 6),
            "purge_bars": self.purge_bars,
            "embargo_bars": self.embargo_bars,
            "leak_guard": dict(self.leak),
            "boundaries": [b.to_dict() for b in self.boundaries],
        }


def outcome_leakage(partition, outcome_bars=None, expiry=None):
    """Derive explicit temporal separation protection from the existing
    outcome/expiry semantics.

    The required gap is expiry (max bars from decision to entry) PLUS
    outcome_bars (max bars of outcome evaluation after a fill) -- the
    widest window a discovery-period outcome could extend past its
    decision bar.  When the population supports that gap the guard is
    PROTECTED; when the data cannot support it the honest answer is
    UNAVAILABLE (never pretend protection was applied).
    """
    required = 0
    if expiry is not None:
        required += max(0, int(expiry))
    if outcome_bars is not None:
        required += max(0, int(outcome_bars))

    gap = None
    if partition.discovery and partition.oos_periods:
        last_disc = decision_bar(partition.discovery[-1])
        first_oos = None
        for period in partition.oos_periods:
            if period:
                first_oos = decision_bar(period[0])
                break
        if last_disc is not None and first_oos is not None:
            gap = first_oos - last_disc

    if required == 0:
        return {
            "status": "NOT_REQUIRED",
            "required_horizon_bars": 0,
            "gap_bars": gap,
            "note": "no outcome horizon requires protection",
        }
    if gap is None:
        return {
            "status": "UNAVAILABLE",
            "required_horizon_bars": required,
            "gap_bars": None,
            "note": "decision bars unavailable; cannot verify a "
                    "deterministic protection gap",
        }
    if gap >= required:
        return {
            "status": "PROTECTED",
            "required_horizon_bars": required,
            "gap_bars": gap,
            "note": "discovery outcomes cannot reach the first OOS "
                    "decision bar within the derived horizon",
        }
    return {
        "status": "UNAVAILABLE",
        "required_horizon_bars": required,
        "gap_bars": gap,
        "note": "dataset cannot support the derived protection gap of "
                "%d bars (gap %d) without fabricating dates or "
                "silently dropping observations" % (required, gap),
    }


def partition(
    opportunities,
    oos_periods=6,
    discovery_fraction=0.5,
    purge_bars=0,
    embargo_bars=0,
    min_oos_opportunities_per_period=30,
    outcome_bars=None,
    expiry=None,
):
    """Build the deterministic chronological 9M partition.

    Discovery is the leading `discovery_fraction`, the trailing region
    is divided into `oos_periods` EQUAL chronological windows. Purge
    removes the trailing `purge_bars` discovery opportunities; embargo
    removes the leading `embargo_bars` opportunities of the OOS
    region. Both are applied ONLY when the population supports them;
    otherwise they are reported as not applied (never silently
    invented).
    """
    ordered = tuple(sorted_opportunities(opportunities))
    n = len(ordered)
    if n <= 1:
        raise ValueError("9M partition requires at least two opportunities")

    disc_n = int(round(n * float(discovery_fraction)))
    diff = max(0, min(purge_bars or 0, disc_n))
    disc = list(ordered[:disc_n])
    if purge_bars:
        disc = disc[:len(disc) - diff] if diff else disc
        if diff != (purge_bars or 0):
            purge_applied = False
        else:
            purge_applied = True
    else:
        purge_applied = True

    oos_head = disc_n
    if embargo_bars:
        rem = max(0, min(int(embargo_bars), n - oos_head))
        oos_head += rem
        if rem != int(embargo_bars):
            embargo_applied = False
        else:
            embargo_applied = True
    else:
        embargo_applied = True

    oos_region = list(ordered[oos_head:])
    oos_n = len(oos_region)

    periods = []
    boundaries = []
    if oos_periods and oos_n > 0:
        chunk = int(math.ceil(oos_n / float(oos_periods)))
    else:
        chunk = 0
    for i in range(oos_periods):
        s = i * chunk
        e = min(oos_n, (i + 1) * chunk) if chunk else oos_n
        if s >= oos_n:
            sl = ordered[oos_head + oos_n:oos_head + oos_n]
            n_slice = 0
        else:
            sl = list(oos_region[s:e])
            n_slice = len(sl)
        periods.append(tuple(sl))
        boundaries.append(PeriodBoundary(
            region="OOS",
            label="OOS-%d" % (i + 1),
            period_index=i,
            start=oos_head + s,
            stop=oos_head + e,
            n=n_slice,
            sample_sufficient=(
                n_slice >= min_oos_opportunities_per_period
            ),
        ))

    boundaries.insert(0, PeriodBoundary(
        region="DISCOVERY",
        label="DISCOVERY",
        period_index=-1,
        start=0,
        stop=disc_n,
        n=len(disc),
        sample_sufficient=True,
    ))

    partition_obj = OosPartition(
        ordered=tuple(ordered),
        discovery=tuple(disc),
        oos_periods=tuple(periods),
        boundaries=tuple(boundaries),
        purge_bars=purge_bars or 0,
        embargo_bars=embargo_bars or 0,
    )
    leak = outcome_leakage(partition_obj, outcome_bars, expiry)
    leak["purge_applied"] = purge_applied or not (purge_bars or 0)
    leak["embargo_applied"] = embargo_applied or not (embargo_bars or 0)
    object.__setattr__(partition_obj, "leak", leak)
    return partition_obj