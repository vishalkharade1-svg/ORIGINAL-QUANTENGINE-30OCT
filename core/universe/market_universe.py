"""
====================================================

QuantEngine

Market Universe (snapshot)

Phase 6B -- Market Universe.

The immutable snapshot of every instrument that is
ELIGIBLE to trade at a given moment. Scanning / sizing /
execution consume THIS object -- an instrument that is
discovered but not eligible never reaches it.

    universe.symbols()          -> ["BTCUSDT", ...]
    universe.get_by_symbol(...) -> Instrument | None
    universe.count              -> int
    universe.reasons            -> {symbol: reason}

DELISTED / NEWLY_LISTED / ACTIVE / INELIGIBLE instruments
are intentionally ABSENT: the snapshot is the ELIGIBLE cut.
====================================================
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Dict
from typing import List
from typing import Optional

from core.registry.instrument import Instrument
from core.universe.universe_policy import UniversePolicy


@dataclass(frozen=True, slots=True)
class MarketUniverse:

    policy: UniversePolicy
    instruments: List[Instrument]
    timeframe: str = "1m"
    captured_at: float = 0.0
    reasons: Dict[str, str] = field(default_factory=dict)

    @property
    def count(self):
        return len(self.instruments)

    @property
    def symbols(self):
        return tuple(i.symbol for i in self.instruments)

    def eligible_instruments(self):
        """The scanner-facing ELIGIBLE cut (Phase 6C). Every
        instrument returned by this snapshot is eligible to
        trade; the MultiSymbolScanner scans exactly this set
        and nothing else."""
        return self.instruments

    def get_by_symbol(self, symbol):
        return next(
            (i for i in self.instruments if i.symbol == symbol),
            None,
        )

    def contains(self, instrument):
        """Sized, printable candidate membership check used by the
        scanning layer (Phase 6C) so a universe lookup can never be
        fooled by a near-but-not-equal symbol string."""
        return any(
            i.key == instrument.key
            or i.symbol == getattr(instrument, "symbol", None)
            for i in self.instruments
        )

    def symbols_text(self):
        text = ",\n".join(f"    {s}" for s in self.symbols)
        return f"[{text}]" if text else "[]"