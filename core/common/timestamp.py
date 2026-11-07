"""
====================================================

QuantEngine — Canonical Timestamp

Phase 9Q-6

Canonical internal representation: UTC epoch seconds as int.

Exchange adapters must normalize at the boundary before
producing MarketState / CandleBuilder inputs.

Supports seconds, milliseconds, microseconds, nanoseconds.
Invalid / None → raises ValueError (fail-fast).

====================================================
"""

from typing import Optional


def normalize_timestamp(ts) -> int:
    """
    Normalize an exchange timestamp to canonical UTC seconds (int).

    Accepts int/float/str in seconds, ms, µs, or ns.
    Detection by magnitude:

      >= 1e18  → nanoseconds  (19 digits, ns)
      >= 1e15  → microseconds (16 digits, µs)
      >= 1e12  → milliseconds (13 digits, ms)
      else     → seconds      (10 digits, s)

    Raises ValueError for None, non-numeric, negative, or zero.
    """
    if ts is None:
        raise ValueError("timestamp is None")

    # Coerce string
    if isinstance(ts, str):
        ts = ts.strip()
        if not ts:
            raise ValueError("timestamp string is empty")
        try:
            # Handle "1700000000.123" string
            if "." in ts:
                ts = float(ts)
            else:
                ts = int(ts)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"timestamp string not numeric: {ts!r}") from exc

    if not isinstance(ts, (int, float)):
        raise ValueError(f"timestamp must be numeric, got {type(ts).__name__}: {ts!r}")

    # Reject non-finite
    if isinstance(ts, float):
        if ts != ts or ts == float("inf") or ts == float("-inf"):
            raise ValueError(f"timestamp not finite: {ts!r}")
        # Convert float seconds with fractional part to int seconds
        # e.g. 1700000000.123 → 1700000000
        # But for ms/µs floats, we still need magnitude detection.
        # Keep as int for magnitude check (truncate toward zero)
        ts_int = int(ts)
    else:
        ts_int = int(ts)

    if ts_int <= 0:
        raise ValueError(f"timestamp must be positive, got {ts!r}")

    # Magnitude detection on absolute int value
    abs_ts = abs(ts_int)

    if abs_ts >= 1_000_000_000_000_000_000:  # 1e18 ns
        return ts_int // 1_000_000_000
    if abs_ts >= 1_000_000_000_000_000:  # 1e15 µs
        return ts_int // 1_000_000
    if abs_ts >= 1_000_000_000_000:  # 1e12 ms
        return ts_int // 1_000
    # Seconds (also handles 1e9 range)
    return ts_int


def normalize_timestamp_or_none(ts) -> Optional[int]:
    """Same as normalize_timestamp but returns None for invalid instead of raising."""
    try:
        return normalize_timestamp(ts)
    except (ValueError, TypeError):
        return None
