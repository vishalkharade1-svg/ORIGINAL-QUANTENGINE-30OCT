"""Prefix-invariance audit helpers for confirmed swing output.

The helpers are diagnostic/research tooling. They instantiate fresh engines
per prefix so memoization and trailing deque state cannot mask a look-ahead or
retroactive mutation defect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.market_structure.swing_engine import SwingEngine


@dataclass(frozen=True, slots=True)
class PrefixViolation:
    prefix_length: int
    swing_index: int
    expected: tuple[str, float, int]
    observed: tuple[str, float, int] | None


def _fingerprint(swing) -> tuple[str, float, int]:
    return swing.kind, swing.price, swing.confirmed_bar


def audit_confirmed_swing_prefixes(candles: Iterable[object], *, left: int = 3, right: int = 3) -> list[PrefixViolation]:
    """Return any confirmed swing that changes in a later prefix.

    Only pivots whose `confirmed_bar` lies within the earlier prefix are
    compared. The last ``right`` bars are intentionally excluded because they
    have not yet earned a causal confirmation.
    """
    bars = list(candles)
    baseline: dict[int, tuple[str, float, int]] = {}
    violations: list[PrefixViolation] = []
    for prefix_length in range(left + right + 1, len(bars) + 1):
        registry = SwingEngine(left=left, right=right).scan(bars[:prefix_length])
        current = {swing.index: _fingerprint(swing) for swing in registry.all()}
        for index, expected in baseline.items():
            observed = current.get(index)
            if observed != expected:
                violations.append(PrefixViolation(prefix_length, index, expected, observed))
        for index, value in current.items():
            if value[2] < prefix_length:
                baseline.setdefault(index, value)
    return violations
