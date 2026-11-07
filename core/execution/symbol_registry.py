"""
====================================================
QuantEngine - Symbol Eligibility Registry
Phase 185 Implementation

Authoritative registry managing multi-symbol discovery, verification,
and execution-eligibility lifecycle states:
  * DISCOVERED
  * METADATA_VERIFIED
  * DATA_VERIFIED
  * RISK_VERIFIED
  * TESTNET_VERIFIED
  * ELIGIBLE
  * REJECTED
  * BLOCKED_EVIDENCE

Fail-closed: Only instruments in ELIGIBLE state may be admitted
to order creation or execution pipelines.
====================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from core.common.logging_config import get_logger
from core.execution.maker_execution_model import InstrumentMetadata

log = get_logger(__name__)


class SymbolEligibilityState(str, Enum):
    """Lifecycle states for instrument trading eligibility."""
    DISCOVERED = "DISCOVERED"
    METADATA_VERIFIED = "METADATA_VERIFIED"
    DATA_VERIFIED = "DATA_VERIFIED"
    RISK_VERIFIED = "RISK_VERIFIED"
    TESTNET_VERIFIED = "TESTNET_VERIFIED"
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    BLOCKED_EVIDENCE = "BLOCKED_EVIDENCE"


@dataclass(frozen=True)
class InstrumentSpecification:
    """Complete, verified instrument specification."""
    symbol: str
    product_id: int
    contract_type: str
    contract_multiplier: Decimal
    tick_size: Decimal
    step_size: Decimal
    min_quantity: Decimal
    settlement_currency: str = "USD"
    quoting_currency: str = "USD"
    maker_fee_rate: Decimal = Decimal("0.0002")
    taker_fee_rate: Decimal = Decimal("0.0005")
    price_precision: int = 1
    qty_precision: int = 0
    min_notional: Decimal = Decimal("1.00")
    state: SymbolEligibilityState = SymbolEligibilityState.DISCOVERED
    reasons: tuple[str, ...] = field(default_factory=tuple)
    evidence_source: str = ""

    def to_instrument_metadata(self) -> InstrumentMetadata:
        """Convert to canonical InstrumentMetadata used by execution models."""
        return InstrumentMetadata(
            symbol=self.symbol,
            tick_size=self.tick_size,
            step_size=self.step_size,
            min_quantity=self.min_quantity,
            contract_multiplier=self.contract_multiplier,
            settlement_currency=self.settlement_currency,
            price_precision=self.price_precision,
            qty_precision=self.qty_precision,
            min_notional=self.min_notional,
        )


class SymbolEligibilityRegistry:
    """Registry managing multi-symbol eligibility and lifecycle transitions."""

    def __init__(self) -> None:
        self._symbols: Dict[str, InstrumentSpecification] = {}

    def register(self, spec: InstrumentSpecification) -> None:
        """Register an instrument candidate."""
        sym = spec.symbol.upper()
        self._symbols[sym] = spec
        log.info("Registered symbol candidate: %s with state %s", sym, spec.state.value)

    def get(self, symbol: str) -> Optional[InstrumentSpecification]:
        """Lookup instrument specification by symbol name."""
        return self._symbols.get(symbol.upper())

    def get_metadata(self, symbol: str) -> InstrumentMetadata:
        """Retrieve canonical InstrumentMetadata. Fails closed if not found or not eligible."""
        spec = self.get(symbol)
        if spec is None:
            raise KeyError(f"Symbol {symbol!r} not found in SymbolEligibilityRegistry")
        if spec.state != SymbolEligibilityState.ELIGIBLE:
            raise ValueError(f"Symbol {symbol!r} is in state {spec.state.value}, not ELIGIBLE")
        return spec.to_instrument_metadata()

    def transition(
        self,
        symbol: str,
        target_state: SymbolEligibilityState,
        reason: str = "",
        evidence_source: Optional[str] = None,
    ) -> InstrumentSpecification:
        """Transition an instrument to a new lifecycle state."""
        sym = symbol.upper()
        current = self._symbols.get(sym)
        if current is None:
            raise KeyError(f"Symbol {symbol!r} not found in registry")

        new_reasons = list(current.reasons)
        if reason:
            new_reasons.append(reason)

        src = evidence_source if evidence_source is not None else current.evidence_source

        updated = InstrumentSpecification(
            symbol=current.symbol,
            product_id=current.product_id,
            contract_type=current.contract_type,
            contract_multiplier=current.contract_multiplier,
            tick_size=current.tick_size,
            step_size=current.step_size,
            min_quantity=current.min_quantity,
            settlement_currency=current.settlement_currency,
            quoting_currency=current.quoting_currency,
            maker_fee_rate=current.maker_fee_rate,
            taker_fee_rate=current.taker_fee_rate,
            price_precision=current.price_precision,
            qty_precision=current.qty_precision,
            min_notional=current.min_notional,
            state=target_state,
            reasons=tuple(new_reasons),
            evidence_source=src,
        )
        self._symbols[sym] = updated
        log.info("Transitioned symbol %s: %s -> %s (%s)", sym, current.state.value, target_state.value, reason)
        return updated

    def is_eligible(self, symbol: str) -> bool:
        """Return True if symbol is registered and in ELIGIBLE state."""
        spec = self.get(symbol)
        return spec is not None and spec.state == SymbolEligibilityState.ELIGIBLE

    def list_symbols(self, state: Optional[SymbolEligibilityState] = None) -> List[str]:
        """List symbols, optionally filtered by state."""
        if state is None:
            return list(self._symbols.keys())
        return [sym for sym, spec in self._symbols.items() if spec.state == state]

    def list_eligible(self) -> List[str]:
        """List all currently eligible symbols."""
        return self.list_symbols(SymbolEligibilityState.ELIGIBLE)

    @classmethod
    def create_phase185_authoritative_registry(cls) -> "SymbolEligibilityRegistry":
        """Pre-populate registry with verified Delta India testnet perpetuals and candidates."""
        reg = cls()

        # 1. BTCUSD (Product ID 84) - Authoritative Verified Multiplier 0.001
        reg.register(InstrumentSpecification(
            symbol="BTCUSD",
            product_id=84,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("0.001"),
            tick_size=Decimal("0.10"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            price_precision=1,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.ELIGIBLE,
            reasons=("Verified by Delta India Testnet snapshot and BLOCK-184-03 resolution",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        # 2. ETHUSD (Product ID 1699) - Multiplier 0.01
        reg.register(InstrumentSpecification(
            symbol="ETHUSD",
            product_id=1699,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("0.01"),
            tick_size=Decimal("0.05"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            price_precision=2,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.ELIGIBLE,
            reasons=("Verified by Delta India Testnet snapshot",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        # 3. SOLUSD (Product ID 92572) - Multiplier 1.0
        reg.register(InstrumentSpecification(
            symbol="SOLUSD",
            product_id=92572,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("1.0"),
            tick_size=Decimal("0.0001"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            price_precision=4,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.ELIGIBLE,
            reasons=("Verified by Delta India Testnet snapshot",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        # 4. XRPUSD (Product ID 93723) - Multiplier 1.0
        reg.register(InstrumentSpecification(
            symbol="XRPUSD",
            product_id=93723,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("1.0"),
            tick_size=Decimal("0.0001"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            price_precision=4,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.ELIGIBLE,
            reasons=("Verified by Delta India Testnet snapshot",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        # 5. ADAUSD (Product ID 101760) - Multiplier 1.0
        reg.register(InstrumentSpecification(
            symbol="ADAUSD",
            product_id=101760,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("1.0"),
            tick_size=Decimal("0.00001"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            price_precision=5,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.ELIGIBLE,
            reasons=("Verified by Delta India Testnet snapshot",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        # 6. DOGEUSD (Product ID 101555) - Multiplier 100.0 (High multiplier contract)
        reg.register(InstrumentSpecification(
            symbol="DOGEUSD",
            product_id=101555,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("100.0"),
            tick_size=Decimal("0.000001"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            price_precision=6,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.RISK_VERIFIED,
            reasons=("Metadata verified, but high multiplier (100) pending conservative risk sizing audit",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        # 7. QQQXUSD (Product ID 184020) - Equity Index Synthetic Perp
        reg.register(InstrumentSpecification(
            symbol="QQQXUSD",
            product_id=184020,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("0.01"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            settlement_currency="USD",
            quoting_currency="USD",
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0002"),
            price_precision=2,
            qty_precision=0,
            min_notional=Decimal("1.00"),
            state=SymbolEligibilityState.BLOCKED_EVIDENCE,
            reasons=("Synthetic stock index perp: market-hours discontinuities and funding model uncalibrated",),
            evidence_source="research/results/phase185_testnet_products_snapshot.json",
        ))

        return reg
