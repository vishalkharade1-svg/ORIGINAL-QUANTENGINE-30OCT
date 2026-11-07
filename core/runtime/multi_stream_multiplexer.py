"""Multi-instrument feed multiplexer and state isolation engine (Phase 163).

Manages concurrent candle streams across multiple instruments (e.g. BTCUSD,
ETHUSD, SOLUSD), guaranteeing strict cross-symbol state isolation, per-symbol
gap detection, and fail-closed feed safety.

Key Architectural Guarantees:
1. Strict Cross-Symbol Isolation:
   - Each symbol maintains its own isolated memory state (candles, swing points,
     displacement zones, and setup candidates).
   - State for Symbol A is never accessible or polluted by Symbol B.
2. Per-Symbol Fail-Closed Gap Detection:
   - If Symbol A encounters a gap or stale feed, trading intent emission for
     Symbol A is halted (SYMBOL_HALTED), while healthy symbols continue uninterrupted.
   - If total unhealthy symbols exceed portfolio fault-tolerance, the entire
     multiplexer halts (PORTFOLIO_HALTED).
3. Anti-Lookahead & Finality Invariant:
   - Unfinalized (forming) candles are rejected by the multiplexer. Only closed
     candles (is_final=True) are committed and dispatched to downstream listeners.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Callable

logger = logging.getLogger(__name__)


class StreamHealth(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    GAPPED = "GAPPED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class MultiplexerCandle:
    symbol: str
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_final: bool = True

    def validate(self) -> None:
        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError("Candle symbol must be a non-empty string")
        if self.timestamp_ms <= 0:
            raise ValueError(f"Invalid timestamp_ms: {self.timestamp_ms}")
        if self.high < self.low or self.high < self.open or self.high < self.close:
            raise ValueError(f"Malformed candle high={self.high} low={self.low}")
        if self.low > self.open or self.low > self.close:
            raise ValueError(f"Malformed candle low={self.low}")
        if self.volume < 0.0:
            raise ValueError(f"Negative volume: {self.volume}")
        if not self.is_final:
            raise ValueError("Multiplexer only accepts finalized closed candles")


@dataclass
class SymbolStreamState:
    symbol: str
    expected_interval_ms: int = 60000  # Default 1m = 60,000 ms
    stale_threshold_ms: int = 180000   # 3 intervals = stale
    last_timestamp_ms: int = 0
    candle_count: int = 0
    health: StreamHealth = StreamHealth.HEALTHY
    halt_reason: str | None = None
    candles: list[MultiplexerCandle] = field(default_factory=list)
    state_metadata: dict[str, Any] = field(default_factory=dict)


class MultiStreamMultiplexer:
    """Thread-safe multiplexer providing strictly isolated multi-instrument feeds."""

    def __init__(
        self,
        symbols: list[str],
        *,
        interval_ms: int = 60000,
        max_candles_per_symbol: int = 1000,
        max_unhealthy_symbols_tolerated: int = 0,
        on_candle_callback: Callable[[MultiplexerCandle], None] | None = None,
    ):
        if not symbols:
            raise ValueError("MultiStreamMultiplexer requires at least one symbol")
        self._lock = RLock()
        self._interval_ms = interval_ms
        self._max_candles = max_candles_per_symbol
        self._max_unhealthy_tolerated = max_unhealthy_symbols_tolerated
        self._callback = on_candle_callback
        self._portfolio_halted = False
        self._portfolio_halt_reason: str | None = None

        # Initialize dedicated isolated state per symbol
        self._streams: dict[str, SymbolStreamState] = {}
        for s in symbols:
            clean_sym = s.strip().upper()
            self._streams[clean_sym] = SymbolStreamState(
                symbol=clean_sym,
                expected_interval_ms=interval_ms,
            )

    @property
    def symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._streams.keys())

    @property
    def is_portfolio_halted(self) -> bool:
        with self._lock:
            return self._portfolio_halted

    @property
    def portfolio_halt_reason(self) -> str | None:
        with self._lock:
            return self._portfolio_halt_reason

    def get_symbol_health(self, symbol: str) -> StreamHealth:
        with self._lock:
            stream = self._get_stream(symbol)
            return stream.health

    def get_candles(self, symbol: str) -> list[MultiplexerCandle]:
        with self._lock:
            stream = self._get_stream(symbol)
            return list(stream.candles)

    def set_symbol_metadata(self, symbol: str, key: str, value: Any) -> None:
        """Store isolated symbol-specific context (e.g. structure swings)."""
        with self._lock:
            stream = self._get_stream(symbol)
            stream.state_metadata[key] = value

    def get_symbol_metadata(self, symbol: str, key: str, default: Any = None) -> Any:
        with self._lock:
            stream = self._get_stream(symbol)
            return stream.state_metadata.get(key, default)

    def ingest_candle(self, candle: MultiplexerCandle, *, current_time_ms: int | None = None) -> bool:
        """Ingest and validate a closed candle for a specific instrument.

        Returns True if accepted and dispatched; False if rejected or halted.
        """
        candle.validate()

        with self._lock:
            if self._portfolio_halted:
                logger.warning(
                    "Multiplexer rejected candle for %s: portfolio is halted (%s)",
                    candle.symbol, self._portfolio_halt_reason
                )
                return False

            stream = self._get_stream(candle.symbol)

            # Check sequence and gap detection
            if stream.last_timestamp_ms > 0:
                delta = candle.timestamp_ms - stream.last_timestamp_ms
                if delta <= 0:
                    stream.health = StreamHealth.HALTED
                    stream.halt_reason = (
                        f"Out-of-order or duplicate timestamp: new={candle.timestamp_ms} "
                        f"last={stream.last_timestamp_ms} delta={delta}"
                    )
                    self._evaluate_portfolio_health()
                    return False

                if delta > stream.expected_interval_ms:
                    stream.health = StreamHealth.GAPPED
                    stream.halt_reason = (
                        f"Gap detected: expected step={stream.expected_interval_ms}ms, "
                        f"actual delta={delta}ms"
                    )
                    self._evaluate_portfolio_health()
                    return False

            # Check staleness against current clock if provided
            if current_time_ms is not None:
                clock_delta = current_time_ms - candle.timestamp_ms
                if clock_delta > stream.stale_threshold_ms:
                    stream.health = StreamHealth.STALE
                    stream.halt_reason = (
                        f"Feed is stale: clock_delta={clock_delta}ms "
                        f"threshold={stream.stale_threshold_ms}ms"
                    )
                    self._evaluate_portfolio_health()
                    return False

            # Valid: append and update state
            stream.candles.append(candle)
            if len(stream.candles) > self._max_candles:
                stream.candles.pop(0)

            stream.last_timestamp_ms = candle.timestamp_ms
            stream.candle_count += 1
            stream.health = StreamHealth.HEALTHY
            stream.halt_reason = None

            # Dispatch callback safely
            if self._callback is not None:
                try:
                    self._callback(candle)
                except Exception as exc:
                    logger.error("Callback failed for %s candle: %s", candle.symbol, exc)

            return True

    def _get_stream(self, symbol: str) -> SymbolStreamState:
        clean_sym = symbol.strip().upper()
        if clean_sym not in self._streams:
            raise KeyError(f"Symbol {symbol!r} is not registered in multiplexer")
        return self._streams[clean_sym]

    def _evaluate_portfolio_health(self) -> None:
        """Evaluate if too many symbol streams are unhealthy."""
        unhealthy = [
            s.symbol for s in self._streams.values()
            if s.health != StreamHealth.HEALTHY
        ]
        if len(unhealthy) > self._max_unhealthy_tolerated:
            self._portfolio_halted = True
            self._portfolio_halt_reason = (
                f"Unhealthy streams ({len(unhealthy)}: {', '.join(unhealthy)}) "
                f"exceed tolerance of {self._max_unhealthy_tolerated}"
            )
            logger.error("Portfolio halted: %s", self._portfolio_halt_reason)
