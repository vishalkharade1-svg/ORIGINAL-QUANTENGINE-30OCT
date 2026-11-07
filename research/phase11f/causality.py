"""Phase 11F-2 causality contract (certification only, no research).

The single causal rule for every research feature:

  feature(t) depends only on information available at or before t.

Critical corollary:

  CONFIRMATION TIME != STRUCTURE ORIGIN TIME.

A structure may originate at bar e, but where confirmation needs
later bars, the structure becomes consumable only at its
confirmation bar. Availability timestamps are KNOWABILITY
timestamps — never origin timestamps, never back-dated.

This module declares the per-structure timing table (populated from
the actual 11F-1 implementation, not from intent) and provides two
certification instruments:

  * HostileBars — a bar container that raises FutureAccessError the
    instant any computation touches an index beyond the decision bar.
  * assert_preregistered_state — fails if the research log shows any
    evaluated variant (11F-2 must not execute research).

No D1/D2/D3 data is loaded here. No candidate is evaluated here.
"""

from __future__ import annotations


class FutureAccessError(AssertionError):
    pass


# Structure | origin | confirmation | earliest legal use | backdating.
# Origins/confirmations below are read off the implementation:
#   features.swings publishes extreme e at e+right;
#   equal_levels/sweeps consume confirmed swings only;
#   fvg_zones at i uses bars[i-2..i];
#   order_block_before scans strictly before the reference bar;
#   range_state needs min_hold unchanged Donchian bars;
#   candidates arm pendings at setup bar c, trigger on (c, c+wait];
#   fibonacci levels timestamp at max anchor confirmations.
STRUCTURE_TIMING = [
    {"structure": "Swing", "origin": "extreme bar e",
     "confirmation": "e+right (default right=3)",
     "earliest_legal_use": "e+right", "backdating_allowed": "NO"},
    {"structure": "Equal level", "origin": "swing extremes",
     "confirmation": "each touch confirmed as a swing; level needs >=3 touches",
     "earliest_legal_use": "first bar with >=3 confirmed touches", "backdating_allowed": "NO"},
    {"structure": "Sweep", "origin": "wick beyond level + close back inside, bar i",
     "confirmation": "same bar i (no extra bar)",
     "earliest_legal_use": "i", "backdating_allowed": "NO"},
    {"structure": "Displacement", "origin": "range[i] > mult*ATR14[i]",
     "confirmation": "same bar i",
     "earliest_legal_use": "i", "backdating_allowed": "NO"},
    {"structure": "FVG", "origin": "bars[i-2..i] gap",
     "confirmation": "bar i",
     "earliest_legal_use": "i", "backdating_allowed": "NO"},
    {"structure": "Order block", "origin": "last opposite candle j < setup bar",
     "confirmation": "displacement bar c (OB resolved from strictly past)",
     "earliest_legal_use": "retest bars in (c, c+wait], never c itself",
     "backdating_allowed": "NO"},
    {"structure": "Breaker level", "origin": "confirmed swing extreme",
     "confirmation": "close crossing back through the level, bar c",
     "earliest_legal_use": "retest bars in (c, c+wait], never c itself",
     "backdating_allowed": "NO"},
    {"structure": "Range state", "origin": "Donchian pair change bar",
     "confirmation": "pair unchanged for min_hold bars",
     "earliest_legal_use": "first bar with hold >= min_hold", "backdating_allowed": "NO"},
    {"structure": "Fibonacci anchor", "origin": "anchor swing extremes",
     "confirmation": "max(low_confirmed, high_confirmed)",
     "earliest_legal_use": "max anchor confirmation bar", "backdating_allowed": "NO"},
    {"structure": "Mitigation/pending", "origin": "setup bar c",
     "confirmation": "setup bar c (armed, not yet entered)",
     "earliest_legal_use": "touch bars in (c, c+wait], never c itself",
     "backdating_allowed": "NO"},
]


class HostileBars:
    """Bar container that explodes on any future access.

    ``HostileBars(bars, decision)`` presents the decision prefix
    ``bars[:decision+1]`` (``len()`` and iteration cover the prefix
    only) while raising FutureAccessError the instant any read
    addresses an index beyond the decision bar. A causal
    computation over the decision prefix must complete without
    raising; any future leak raises immediately instead of
    silently succeeding on out-of-range data.
    """

    def __init__(self, bars, decision):
        self._bars = list(bars)
        self._decision = decision

    def __len__(self):
        return self._decision + 1

    def __iter__(self):
        return iter(self._bars[:self._decision + 1])

    def _check(self, idx):
        n = self._decision + 1
        if idx < 0:
            idx += n
        if idx < 0 or idx >= n:
            raise FutureAccessError(
                "future access: bar %d beyond decision %d" % (idx, self._decision))

    def __getitem__(self, key):
        if isinstance(key, slice):
            idxs = range(*key.indices(len(self._bars)))
            for i in idxs:
                self._check(i)
            return [self._bars[i] for i in idxs]
        self._check(key)
        return self._bars[key]


def assert_preregistered_state(log: dict) -> None:
    """Fail if the research log shows any executed evaluation."""
    for entry in log.get("entries", []):
        if entry.get("status") != "REGISTERED":
            raise AssertionError("%s left REGISTERED" % entry.get("id"))
        if entry.get("variants_tested") != 0:
            raise AssertionError("%s has variants_tested != 0" % entry.get("id"))
        if entry.get("result") is not None:
            raise AssertionError("%s has a result" % entry.get("id"))
