"""
====================================================

Base Contract Specification

====================================================
"""

from dataclasses import dataclass


@dataclass(slots=True)
class BaseContract:

    symbol: str

    exchange: str

    contract_type: str

    tick_size: float

    quantity_step: float

    min_quantity: float

    max_leverage: float

    maker_fee: float

    taker_fee: float

    price_precision: int

    quantity_precision: int

    # -------------------------------------------------
    # Optional instrument metadata (""/0 when not
    # applicable). Options carry option_type, strike and
    # expiry; every instrument carries its underlying
    # asset. Kept as defaults so non-option instruments
    # and existing constructions stay untouched.
    # -------------------------------------------------

    underlying_asset: str = ""

    option_type: str = ""

    strike_price: float = 0.0

    expiry_time: int = 0

    # Delta REST product id. The private order endpoints take
    # product_id (not symbol); the mapper extracts it from the
    # real /v2/products `id` field. Defaulted so instruments
    # and fixtures that omit it stay untouched.
    product_id: int = 0

    # Live order payloads require separately recorded venue evidence. Raw
    # product discovery is useful for research and paper eligibility, but it
    # does not prove request-schema, product-id, rounding, or bracket semantics
    # for a financial write. Defaults fail closed.
    live_execution_verified: bool = False

    live_execution_evidence: str = ""
