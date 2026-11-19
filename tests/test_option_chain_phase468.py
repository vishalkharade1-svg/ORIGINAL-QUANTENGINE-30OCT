"""Phase 468: immutable option contract snapshots."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import pytest

from core.options import OptionContractSnapshot, build_option_chain
from core.registry.instrument import Instrument
from core.registry.product_types import PRODUCT_CALL_OPTION

AS_OF = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
EXPIRY = int(datetime(2026, 12, 31, 8, 0, tzinfo=timezone.utc).timestamp())


def _call():
    return Instrument(
        instrument_id=f"nse-nifty-{EXPIRY}-call",
        symbol="NIFTY26DEC22500CE", exchange="NSE",
        product_type=PRODUCT_CALL_OPTION, underlying_asset="NIFTY",
        quote_asset="INR", expiry_time=EXPIRY, strike_price=22500.0,
        option_type="call", tick_size=0.05, quantity_step=1.0,
        minimum_quantity=25.0, trading_enabled=True, lot_size=25,
        contract_multiplier=1.0, metadata={"mutable": ["original"]},
    )


def test_chain_captures_immutable_scalar_contract_snapshot():
    instrument = _call()
    chain = build_option_chain(
        [instrument], {}, underlying="NIFTY",
        expiry_time=EXPIRY, as_of=AS_OF,
    )
    snapshot = chain.entries[0].call.instrument
    assert isinstance(snapshot, OptionContractSnapshot)
    assert snapshot.symbol == "NIFTY26DEC22500CE"
    assert snapshot.strike_price == 22500.0
    assert snapshot.exchange == "NSE"

    instrument.symbol = "MUTATED"
    instrument.strike_price = 23000.0
    instrument.exchange = "BSE"
    instrument.metadata["mutable"].append("changed")

    assert snapshot.symbol == "NIFTY26DEC22500CE"
    assert snapshot.strike_price == 22500.0
    assert snapshot.exchange == "NSE"


def test_contract_snapshot_rejects_direct_mutation():
    chain = build_option_chain(
        [_call()], {}, underlying="NIFTY",
        expiry_time=EXPIRY, as_of=AS_OF,
    )
    snapshot = chain.entries[0].call.instrument
    with pytest.raises(FrozenInstanceError):
        snapshot.exchange = "BSE"
