"""
====================================================

QuantEngine

Universe Policy

Phase 6B -- Market Universe.

The declared eligibility thresholds for building the live
market universe. Explicit and narrow by default: building
a universe REQUIRES data providers (liquidity + history
window), so a misconfigured manager degrades to an EMPTY
universe, never a silent everything-goes catalog.

    UniversePolicy(
        min_quote_volume_24h=8_000_000,   # measured quote volume
        min_history_bars=300,             # lookback window (1m)
    )

`None` on min_quote_volume_24h keeps the mandatory
liquidity bound (any measured figure passes it) -- a
product with NO volume figure is still denied upstream.
`None` on min_history_bars turns the history gate OFF.
====================================================
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UniversePolicy:

    # Minimum measured 24h quote volume. None -> no volume
    # bound (but volume data is still REQUIRED by the gate).
    min_quote_volume_24h: float = None

    # Minimum history bars (lookback window). None -> gate off.
    min_history_bars: int = None

    @property
    def requires_history(self):
        return self.min_history_bars is not None