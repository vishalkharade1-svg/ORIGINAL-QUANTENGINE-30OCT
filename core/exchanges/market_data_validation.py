"""Venue-neutral validation for normalized market data (Phase 203).

This module validates caller-supplied snapshots only. It does not fetch data,
prove exchange authenticity, or authorize trading. All failures are explicit
and safe to log; raw payloads and credential-bearing exceptions are not used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable


def _price(name: str, value: Decimal | str | int | float | None, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite positive number") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return parsed


def _aware_utc(name: str, value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class NormalizedQuote:
    symbol: str
    timestamp: datetime
    source: str
    last: Decimal | str | int | float | None = None
    bid: Decimal | str | int | float | None = None
    ask: Decimal | str | int | float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol is required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")
        object.__setattr__(self, "timestamp", _aware_utc("timestamp", self.timestamp))
        for field in ("last", "bid", "ask"):
            object.__setattr__(self, field, _price(field, getattr(self, field), optional=True))
        if self.last is None and self.bid is None and self.ask is None:
            raise ValueError("at least one of last, bid, or ask is required")
        if (self.bid is None) != (self.ask is None):
            raise ValueError("bid and ask must either both be present or both be absent")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("crossed quote: bid exceeds ask")


@dataclass(frozen=True, slots=True)
class NormalizedBar:
    symbol: str
    timestamp: datetime
    source: str
    open: Decimal | str | int | float
    high: Decimal | str | int | float
    low: Decimal | str | int | float
    close: Decimal | str | int | float
    volume: Decimal | str | int | float = 0

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol is required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source is required")
        object.__setattr__(self, "timestamp", _aware_utc("timestamp", self.timestamp))
        for field in ("open", "high", "low", "close"):
            object.__setattr__(self, field, _price(field, getattr(self, field)))
        try:
            volume = Decimal(str(self.volume))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("volume must be a finite non-negative number") from None
        if not volume.is_finite() or volume < 0:
            raise ValueError("volume must be a finite non-negative number")
        object.__setattr__(self, "volume", volume)
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.low > self.high:
            raise ValueError("inconsistent OHLC range")


@dataclass(frozen=True, slots=True)
class MarketDataValidationReport:
    valid: bool
    errors: tuple[str, ...]
    normalized_timestamp: datetime | None = None


def validate_quote(
    quote: NormalizedQuote,
    *,
    now: datetime,
    max_age_seconds: float,
    expected_symbol: str | None = None,
    future_tolerance_seconds: float = 1.0,
) -> MarketDataValidationReport:
    """Check symbol identity and time freshness without accessing a venue."""
    errors: list[str] = []
    try:
        current = _aware_utc("now", now)
    except ValueError as exc:
        return MarketDataValidationReport(False, (str(exc),))
    if max_age_seconds < 0 or future_tolerance_seconds < 0:
        return MarketDataValidationReport(False, ("age tolerances must be non-negative",))
    if expected_symbol is not None and quote.symbol != expected_symbol:
        errors.append("symbol mismatch")
    age = (current - quote.timestamp).total_seconds()
    if age > max_age_seconds:
        errors.append("stale market data")
    if age < -future_tolerance_seconds:
        errors.append("market data timestamp is in the future")
    return MarketDataValidationReport(not errors, tuple(errors), quote.timestamp)


def validate_quote_batch(
    quotes: Iterable[NormalizedQuote], *, now: datetime, max_age_seconds: float
) -> MarketDataValidationReport:
    """Validate a batch and reject duplicate normalized symbols."""
    seen: set[str] = set()
    errors: list[str] = []
    count = 0
    for quote in quotes:
        count += 1
        key = quote.symbol.strip().upper()
        if key in seen:
            errors.append("duplicate symbol in quote batch")
        seen.add(key)
        report = validate_quote(quote, now=now, max_age_seconds=max_age_seconds)
        errors.extend(report.errors)
    if count == 0:
        errors.append("quote batch is empty")
    return MarketDataValidationReport(not errors, tuple(errors))
