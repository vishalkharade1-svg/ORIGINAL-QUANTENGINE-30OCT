"""Provider-neutral, fail-closed option-chain assembly."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Mapping, Sequence
from core.exchanges.market_data_validation import NormalizedQuote, validate_quote
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION, PRODUCT_PUT_OPTION

@dataclass(frozen=True, slots=True)
class OptionContractSnapshot:
    """Deeply immutable canonical contract facts captured at chain-build time."""
    instrument_id: str
    symbol: str
    exchange: str
    product_type: str
    underlying_asset: str
    quote_asset: str
    expiry_time: int
    strike_price: float
    option_type: str
    tick_size: float
    quantity_step: float
    minimum_quantity: float
    trading_enabled: bool
    lot_size: int
    contract_multiplier: float


@dataclass(frozen=True, slots=True)
class OptionLeg:
    instrument: OptionContractSnapshot
    quote: NormalizedQuote | None

@dataclass(frozen=True, slots=True)
class OptionChainEntry:
    strike: float
    call: OptionLeg | None
    put: OptionLeg | None

@dataclass(frozen=True, slots=True)
class OptionChain:
    underlying: str
    exchange: str
    expiry_time: int
    lot_size: int
    contract_multiplier: float
    as_of: datetime
    quote_timestamp_start: datetime | None
    quote_timestamp_end: datetime | None
    quote_skew_seconds: float | None
    source: str
    entries: tuple[OptionChainEntry, ...]

    @property
    def missing_call_quotes(self) -> int:
        return sum(1 for entry in self.entries if entry.call is not None and entry.call.quote is None)

    @property
    def missing_put_quotes(self) -> int:
        return sum(1 for entry in self.entries if entry.put is not None and entry.put.quote is None)

    @property
    def missing_call_legs(self) -> int:
        return sum(1 for entry in self.entries if entry.call is None)

    @property
    def missing_put_legs(self) -> int:
        return sum(1 for entry in self.entries if entry.put is None)

    @property
    def contract_count(self) -> int:
        return sum(int(entry.call is not None) + int(entry.put is not None) for entry in self.entries)

    @property
    def quoted_contract_count(self) -> int:
        return sum(
            int(entry.call is not None and entry.call.quote is not None)
            + int(entry.put is not None and entry.put.quote is not None)
            for entry in self.entries
        )

    @property
    def quote_coverage(self) -> float:
        """Fraction of supplied contracts with a validated quote (0.0 to 1.0)."""
        total = self.contract_count
        return self.quoted_contract_count / total if total else 0.0

def _snapshot_instrument(instrument: Instrument) -> OptionContractSnapshot:
    """Copy only scalar contract facts; never retain a mutable Instrument."""
    return OptionContractSnapshot(
        instrument_id=instrument.instrument_id,
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        product_type=instrument.product_type,
        underlying_asset=instrument.underlying_asset,
        quote_asset=instrument.quote_asset,
        expiry_time=instrument.expiry_time,
        strike_price=float(instrument.strike_price),
        option_type=instrument.option_type,
        tick_size=float(instrument.tick_size),
        quantity_step=float(instrument.quantity_step),
        minimum_quantity=float(instrument.minimum_quantity),
        trading_enabled=bool(instrument.trading_enabled),
        lot_size=instrument.lot_size,
        contract_multiplier=float(instrument.contract_multiplier),
    )


def build_option_chain(instruments: Sequence[Instrument], quotes: Mapping[str, NormalizedQuote], *,
                       underlying: str, expiry_time: int, as_of: datetime,
                       max_quote_age_seconds: float = 5.0,
                       max_quote_skew_seconds: float = 2.0) -> OptionChain:
    """Pair calls/puts by strike; reject ambiguous identity and stale input.

    Quote mappings may contain a broader provider snapshot; only selected
    instrument symbols are consumed. Each selected instrument must have a
    unique canonical symbol and instrument ID.
    """
    if not isinstance(underlying, str) or not underlying.strip():
        raise ValueError("underlying is required")
    if isinstance(expiry_time, bool) or not isinstance(expiry_time, int) or expiry_time <= 0:
        raise ValueError("expiry_time must be a positive Unix timestamp")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    current = as_of.astimezone(timezone.utc)
    if expiry_time <= int(current.timestamp()):
        raise ValueError("option chain expiry is not in the future")
    if isinstance(max_quote_age_seconds, bool):
        raise ValueError("max_quote_age_seconds must be finite and non-negative")
    try:
        max_age = float(max_quote_age_seconds)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("max_quote_age_seconds must be finite and non-negative") from None
    if not math.isfinite(max_age) or max_age < 0:
        raise ValueError("max_quote_age_seconds must be finite and non-negative")
    if isinstance(max_quote_skew_seconds, bool):
        raise ValueError("max_quote_skew_seconds must be finite and non-negative")
    try:
        max_skew = float(max_quote_skew_seconds)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("max_quote_skew_seconds must be finite and non-negative") from None
    if not math.isfinite(max_skew) or max_skew < 0:
        raise ValueError("max_quote_skew_seconds must be finite and non-negative")
    if not isinstance(instruments, Sequence) or isinstance(instruments, (str, bytes)) or not instruments:
        raise ValueError("option chain requires at least one instrument")
    if not isinstance(quotes, Mapping):
        raise TypeError("quotes must be a symbol-to-quote mapping")
    grouped: dict[float, dict[str, OptionLeg]] = {}
    seen_symbols: set[str] = set()
    seen_instrument_ids: set[str] = set()
    sources: set[str] = set()
    quote_timestamps: list[datetime] = []
    common_lot: int | None = None
    common_multiplier: float | None = None
    common_exchange: str | None = None
    for instrument in instruments:
        if not isinstance(instrument, Instrument):
            raise TypeError("option chain instruments must be canonical Instrument records")
        if not isinstance(instrument.instrument_id, str) or not instrument.instrument_id.strip():
            raise ValueError("option instrument ID is required")
        if not isinstance(instrument.symbol, str) or not instrument.symbol.strip():
            raise ValueError("option instrument symbol is required")
        if not isinstance(instrument.exchange, str) or not instrument.exchange.strip():
            raise ValueError("option instrument exchange is required")
        if common_exchange is None:
            common_exchange = instrument.exchange
        elif instrument.exchange != common_exchange:
            raise ValueError("option chain exchange mismatch")
        if instrument.symbol in seen_symbols:
            raise ValueError("duplicate option instrument symbol")
        seen_symbols.add(instrument.symbol)
        if instrument.product_type not in (PRODUCT_CALL_OPTION, PRODUCT_PUT_OPTION):
            raise ValueError("option chain contains a non-option instrument")
        if instrument.underlying_asset != underlying:
            raise ValueError("option chain underlying mismatch")
        if instrument.expiry_time != expiry_time:
            raise ValueError("option chain expiry mismatch")
        if not instrument.valid_option_contract_metadata:
            raise ValueError("option contract metadata is incomplete or inconsistent")
        try:
            precision_values = (
                float(instrument.tick_size),
                float(instrument.quantity_step),
                float(instrument.minimum_quantity),
            )
        except (TypeError, ValueError, OverflowError):
            raise ValueError("option contract precision metadata is invalid") from None
        if any(not math.isfinite(value) or value <= 0 for value in precision_values):
            raise ValueError("option contract precision metadata is invalid")
        if common_lot is None:
            common_lot = instrument.lot_size
            common_multiplier = float(instrument.contract_multiplier)
        elif instrument.lot_size != common_lot or float(instrument.contract_multiplier) != common_multiplier:
            raise ValueError("option chain lot size or multiplier mismatch")
        right = "call" if instrument.product_type == PRODUCT_CALL_OPTION else "put"
        strike = float(instrument.strike_price)
        legs = grouped.setdefault(strike, {})
        if right in legs:
            raise ValueError("duplicate %s contract at strike" % right)
        if instrument.instrument_id in seen_instrument_ids:
            raise ValueError("duplicate option instrument ID")
        seen_instrument_ids.add(instrument.instrument_id)
        quote = quotes.get(instrument.symbol)
        if quote is not None:
            if not isinstance(quote, NormalizedQuote):
                raise TypeError("option quote values must be NormalizedQuote records")
            report = validate_quote(quote, now=current, max_age_seconds=max_age,
                                    expected_symbol=instrument.symbol)
            if not report.valid:
                raise ValueError("invalid option quote: %s" % ", ".join(report.errors))
            sources.add(quote.source)
            quote_timestamps.append(quote.timestamp)
        legs[right] = OptionLeg(instrument=_snapshot_instrument(instrument), quote=quote)
    if len(sources) > 1:
        raise ValueError("option chain quotes must use one consistent source")
    quote_timestamp_start = min(quote_timestamps) if quote_timestamps else None
    quote_timestamp_end = max(quote_timestamps) if quote_timestamps else None
    quote_skew_seconds = (
        (quote_timestamp_end - quote_timestamp_start).total_seconds()
        if quote_timestamp_start is not None and quote_timestamp_end is not None
        else None
    )
    if quote_skew_seconds is not None and quote_skew_seconds > max_skew:
        raise ValueError("option chain quote timestamp skew exceeds limit")
    entries = tuple(OptionChainEntry(strike=strike, call=legs.get("call"), put=legs.get("put"))
                    for strike, legs in sorted(grouped.items()))
    return OptionChain(underlying=underlying, exchange=common_exchange, expiry_time=expiry_time, lot_size=common_lot,
                       contract_multiplier=common_multiplier, as_of=current,
                       quote_timestamp_start=quote_timestamp_start,
                       quote_timestamp_end=quote_timestamp_end,
                       quote_skew_seconds=quote_skew_seconds,
                       source=next(iter(sources)) if sources else "",
                       entries=entries)
