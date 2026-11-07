"""Build executable math specs only from explicitly verified instrument facts.

Current registry normalization preserves raw Delta metadata but cannot yet
prove that every product's ``contract_value`` is a quantity increment versus a
settlement multiplier.  This factory therefore refuses to infer either.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.registry.instrument import Instrument
from core.risk.contract_math import CostModel, ContractKind, ContractMathError, ContractSpec


@dataclass(frozen=True, slots=True)
class ContractSpecAvailability:
    spec: ContractSpec | None
    reason: str


@dataclass(frozen=True, slots=True)
class CostModelAvailability:
    model: CostModel | None
    reason: str


def _verified_metadata(metadata: dict, fields: tuple[str, ...], description: str) -> tuple[bool, str]:
    """Require explicit values plus non-empty venue evidence fields."""
    missing = [field for field in fields if metadata.get(field) is None]
    source = metadata.get("verified_venue_source")
    verified_at = metadata.get("verified_venue_verified_at")
    if missing or not isinstance(source, str) or not source.strip() or not isinstance(verified_at, str) or not verified_at.strip():
        return False, description + " require external venue verification evidence"
    return True, ""


def contract_spec_from_instrument(instrument: Instrument) -> ContractSpecAvailability:
    """Return a spec only when all settlement-critical fields are verified."""
    if not instrument.valid_precision:
        return ContractSpecAvailability(None, "instrument tick or quantity precision is unavailable")
    metadata = instrument.metadata if isinstance(instrument.metadata, dict) else {}
    kind = metadata.get("verified_contract_kind")
    multiplier = metadata.get("verified_contract_multiplier")
    verified, reason = _verified_metadata(
        metadata,
        ("verified_contract_kind", "verified_contract_multiplier"),
        "contract kind and multiplier",
    )
    if not verified or kind is None or multiplier is None:
        return ContractSpecAvailability(
            None,
            reason,
        )
    try:
        spec = ContractSpec(
            ContractKind(str(kind).upper()),
            Decimal(str(multiplier)),
            Decimal(str(instrument.tick_size)),
            Decimal(str(instrument.quantity_step)),
            Decimal(str(instrument.minimum_quantity)),
        )
    except (ContractMathError, ValueError, ArithmeticError) as error:
        return ContractSpecAvailability(None, "invalid verified contract metadata: " + str(error))
    return ContractSpecAvailability(spec, "verified contract specification")


def cost_model_from_instrument(instrument: Instrument) -> CostModelAvailability:
    """Build costs only from explicitly evidenced venue metadata.

    Values of zero are accepted only when they were explicitly verified; absent
    costs are never silently translated into zero operational economics.
    """
    metadata = instrument.metadata if isinstance(instrument.metadata, dict) else {}
    fields = (
        "verified_entry_fee_bps", "verified_exit_fee_bps",
        "verified_half_spread", "verified_slippage_bps",
        "verified_funding_per_contract",
    )
    verified, reason = _verified_metadata(metadata, fields, "cost model")
    if not verified:
        return CostModelAvailability(None, reason)
    try:
        model = CostModel(*(Decimal(str(metadata[field])) for field in fields))
    except (ContractMathError, ValueError, ArithmeticError) as error:
        return CostModelAvailability(None, "invalid verified cost metadata: " + str(error))
    return CostModelAvailability(model, "verified cost model")
