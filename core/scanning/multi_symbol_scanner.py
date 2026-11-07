"""
====================================================

Multi-Symbol Scanner

Phase 6C -- consume the ELIGIBLE universe (never a
hardcoded symbol list), scan every instrument with its
own isolated SymbolPipeline, and aggregate a
deterministically ordered MultiSymbolScanResult.

Per-instrument isolation contract:
  * each instrument gets a FRESH context / world / bus /
    simulator / backtester (state can never leak between
    instruments, and no instrument can mutate a neighbour);
  * one instrument's failure is caught and recorded as
    FAILED while the remaining instruments keep scanning;
  * results are always ordered by (exchange, instrument_id)
    so repeated scans are directly comparable; and
  * an EMPTY universe degrades to a clean empty result --
    no scan is attempted and no exception escapes.

The universe argument accepts:
  * a MarketUniverse snapshot (the eligible cut),
  * an InstrumentRegistry (scanner uses executable()),
  * any iterable of Instrument records.

====================================================
"""

import time

from core.scanning.scan_result import MultiSymbolScanResult
from core.scanning.scan_result import ScanStatus
from core.scanning.scan_result import SymbolScanResult
from core.scanning.symbol_pipeline import SymbolPipeline


def _numeric_instrument_id(instrument_id):
    try:
        return int(str(instrument_id))
    except (TypeError, ValueError):
        return 0


def instrument_sort_key(instrument):
    """
    Deterministic cross-scan ordering: (exchange, numeric
    instrument_id, raw instrument_id, symbol). Two scans of
    the same universe collapse to the same order no matter
    how the source list was originally arranged.
    """
    exchange = (
        getattr(instrument, "exchange", "") or ""
    )

    raw_id = (
        getattr(instrument, "instrument_id", "") or ""
    )

    symbol = (
        getattr(instrument, "symbol", "") or ""
    )

    return (
        exchange,
        _numeric_instrument_id(raw_id),
        str(raw_id),
        symbol,
    )


class MultiSymbolScanner:

    def __init__(
        self,
        data_source=None,
        world_factory=None,
        timeframe="1m",
        strategy="",
        window=None,
    ):

        self.data_source = data_source

        self.world_factory = world_factory

        self.timeframe = timeframe

        self.strategy = strategy

        self.window = window

    # -------------------------------------------------

    def scan(
        self,
        universe,
        data_source=None,
        timeframe=None,
        window=None,
    ):
        """
        Scan every eligible instrument in the universe with an
        isolated pipeline per instrument. Never scans (and never
        even reads) an instrument that is not in the eligible
        cut. Returns a MultiSymbolScanResult.
        """
        instruments = self._eligible_instruments(universe)

        ordered = sorted(
            instruments,
            key=instrument_sort_key,
        )

        effective_timeframe = timeframe or self.timeframe

        effective_window = (
            window
            if window is not None
            else self.window
        )

        effective_data_source = (
            data_source
            if data_source is not None
            else self.data_source
        )

        results = []

        errors = []

        for instrument in ordered:

            symbol = (
                getattr(instrument, "symbol", "")
                or ""
            )

            pipeline = SymbolPipeline(
                instrument,
                timeframe=effective_timeframe,
                strategy=self.strategy,
                data_source=effective_data_source,
                world_factory=self.world_factory,
            )

            try:

                outcome = pipeline.run(
                    window=effective_window,
                )

                if (
                    outcome.status
                    == ScanStatus.FAILED
                ):

                    errors.append(
                        (symbol, outcome.error)
                    )

            except Exception as exc:  # noqa: BLE001
                outcome = SymbolScanResult(
                    instrument=instrument,
                    symbol=symbol,
                    status=ScanStatus.FAILED,
                    error=str(exc),
                )

                errors.append((symbol, str(exc)))

            results.append(outcome)

        return MultiSymbolScanResult(
            results=tuple(results),
            errors=tuple(errors),
            timeframe=effective_timeframe,
            captured_at=time.time(),
        )

    # -------------------------------------------------

    @staticmethod
    def _eligible_instruments(universe):
        """
        Extract ONLY the eligible cut. A MarketUniverse exposes
        eligible_instruments(); a registry exposes executable();
        a raw iterable is used as-is. None / empty -> nothing to
        scan (clean empty result, never an exception).
        """
        if universe is None:
            return ()

        if hasattr(
            universe, "eligible_instruments"
        ):
            return tuple(
                universe.eligible_instruments()
            )

        if hasattr(universe, "instruments"):
            return tuple(universe.instruments)

        if hasattr(universe, "executable"):
            return tuple(universe.executable())

        if isinstance(
            universe, (list, tuple, set)
        ) or hasattr(universe, "__iter__"):
            return tuple(universe)

        raise TypeError(
            "cannot extract eligible instruments from "
            "universe of type {}".format(
                type(universe).__name__
            )
        )