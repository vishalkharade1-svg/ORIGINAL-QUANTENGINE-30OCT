"""Phase 463: preserve and revalidate canonical option contract sizing."""
from core.registry.instrument import Instrument
from core.registry.instrument_registry import InstrumentRegistry
from core.registry.eligibility import InstrumentEligibility, IneligibleReason
from core.registry.product_types import (
    PRODUCT_CALL_OPTION,
    PRODUCT_STATE_ACTIVE,
    PRODUCT_STATE_NEWLY_LISTED,
)


def _option(**changes):
    values = dict(
        instrument_id="nse-nifty-2026-11-26-22500-ce",
        symbol="NIFTY26NOV22500CE",
        exchange="NSE",
        product_type=PRODUCT_CALL_OPTION,
        underlying_asset="NIFTY",
        quote_asset="INR",
        expiry_time=1795693500,
        strike_price=22500.0,
        option_type="call",
        tick_size=0.05,
        quantity_step=1.0,
        minimum_quantity=25.0,
        trading_enabled=True,
        lot_size=25,
        contract_multiplier=1.0,
    )
    values.update(changes)
    return Instrument(**values)


def test_option_contract_metadata_requires_verified_lot_and_expiry():
    assert _option().valid_option_contract_metadata
    assert not _option(lot_size=None).valid_option_contract_metadata
    assert not _option(lot_size=0).valid_option_contract_metadata
    assert not _option(expiry_time=0).valid_option_contract_metadata
    assert not _option(strike_price=0).valid_option_contract_metadata
    assert not _option(option_type="binary").valid_option_contract_metadata
    assert not _option(option_type="put").valid_option_contract_metadata
    assert not _option(contract_multiplier=0).valid_option_contract_metadata


def test_option_contract_metadata_round_trips_through_registry_serialization():
    original = _option(lot_size=50, contract_multiplier=0.01)
    restored = Instrument.from_dict(original.to_dict())
    assert restored.lot_size == 50
    assert restored.contract_multiplier == 0.01
    assert restored.valid_option_contract_metadata


def test_legacy_instrument_records_load_without_new_option_fields():
    legacy = _option().to_dict()
    legacy.pop("lot_size")
    legacy.pop("contract_multiplier")
    restored = Instrument.from_dict(legacy)
    assert restored.lot_size is None
    assert restored.contract_multiplier == 1.0
    assert not restored.valid_option_contract_metadata


def test_option_sizing_change_resets_registry_lifecycle_to_candidate():
    registry = InstrumentRegistry()
    first, is_new = registry.upsert(_option())
    assert is_new
    second, is_new = registry.upsert(_option())
    assert not is_new
    assert second.state == PRODUCT_STATE_ACTIVE

    registry.mark_eligible(second.key)
    changed, is_new = registry.upsert(_option(lot_size=50))
    assert not is_new
    assert changed.state == PRODUCT_STATE_NEWLY_LISTED


def test_valid_option_metadata_does_not_enable_unsupported_option_strategy():
    instrument = _option()
    assert instrument.valid_option_contract_metadata
    eligible, reason = InstrumentEligibility().evaluate(
        instrument, quote_volume_24h=10_000_000,
    )
    assert not eligible
    assert reason == IneligibleReason.UNSUPPORTED_TYPE
