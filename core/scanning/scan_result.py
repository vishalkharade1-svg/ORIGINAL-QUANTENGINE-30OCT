"""
====================================================

Scan Results

Phase 6C -- per-symbol and multi-symbol scan outcomes.

Every per-symbol outcome is classified as SUCCESS,
SKIPPED (no data / no data source) or FAILED (hard
error, caught and isolated so neighbouring symbols
keep scanning). Raw engine objects are retained so
consumers can read the canonical identity off every
setup / order / trade without re-derivation.

====================================================
"""

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any
from typing import Optional
from typing import Tuple


class ScanStatus(Enum):

    SUCCESS = "SUCCESS"

    SKIPPED = "SKIPPED"

    FAILED = "FAILED"


@dataclass(slots=True)
class SymbolScanResult:
    """
    The outcome of scanning ONE instrument with its OWN
    isolated pipeline. 'pipeline' is the SymbolPipeline that
    ran the scan (its .context / .world / .simulator explain
    the instrument's isolated state), so state-isolation
    tests and live diagnostics can drill into one symbol
    without touching any other.
    """

    instrument: Any

    symbol: str = ""

    status: ScanStatus = ScanStatus.SKIPPED

    error: str = ""

    setups: Tuple[Any, ...] = ()

    decisions: Tuple[Any, ...] = ()

    orders: Tuple[Any, ...] = ()

    trades: Tuple[Any, ...] = ()

    pipeline: Any = None

    @property
    def ok(self):
        return self.status == ScanStatus.SUCCESS


@dataclass(slots=True)
class MultiSymbolScanResult:
    """
    Deterministically ordered aggregation of every per-symbol
    outcome. results are ordered by (exchange, instrument_id)
    regardless of the source universe's insertion order, so
    two scans of the same universe are always comparable.
    """

    results: Tuple[SymbolScanResult, ...] = ()

    errors: Tuple[Tuple[str, str], ...] = ()

    timeframe: str = "1m"

    captured_at: float = 0.0

    # -------------------------------------------------

    @property
    def scanned(self):
        return len(self.results)

    @property
    def successful(self):
        return sum(
            1
            for r in self.results
            if r.status == ScanStatus.SUCCESS
        )

    @property
    def skipped(self):
        return sum(
            1
            for r in self.results
            if r.status == ScanStatus.SKIPPED
        )

    @property
    def failed(self):
        return sum(
            1
            for r in self.results
            if r.status == ScanStatus.FAILED
        )

    @property
    def symbols(self):
        return tuple(r.symbol for r in self.results)

    @property
    def instrument_ids(self):
        return tuple(
            getattr(r.instrument, "instrument_id", "")
            for r in self.results
        )

    # -------------------------------------------------
    # Flat slices for analytics/reporting
    # -------------------------------------------------

    @property
    def setups(self):
        return tuple(
            s for r in self.results for s in r.setups
        )

    @property
    def decisions(self):
        return tuple(
            s for r in self.results for s in r.decisions
        )

    @property
    def orders(self):
        return tuple(
            o for r in self.results for o in r.orders
        )

    @property
    def trades(self):
        return tuple(
            t for r in self.results for t in r.trades
        )

    # -------------------------------------------------

    def for_symbol(self, symbol):
        return next(
            (r for r in self.results if r.symbol == symbol),
            None,
        )

    # -------------------------------------------------

    def summary(self):
        return {
            "scanned": self.scanned,
            "successful": self.successful,
            "skipped": self.skipped,
            "failed": self.failed,
            "setups": len(self.setups),
            "decisions": len(self.decisions),
            "orders": len(self.orders),
            "trades": len(self.trades),
            "timeframe": self.timeframe,
        }