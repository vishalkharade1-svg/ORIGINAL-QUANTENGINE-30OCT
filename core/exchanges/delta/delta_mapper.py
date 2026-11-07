"""
====================================================

Delta Contract Mapper

Converts Delta REST API product JSON into
internal DeltaContract objects.

Real-payload defenses (verified against /v2/products):

- `contract_type` values are lowercase in the payload:
  call_options / put_options / binary_call_options /
  binary_put_options / perpetual_futures / spot.
- Options and tokens carry None values for fields a
  perpetual future would populate (strike_price is
  None on perps, numeric on options; tick sizes etc.
  vary), so every numeric field is coerced safely.
- `underlying_asset` is a dict (asset object); the
  asset's `symbol` key is extracted.
- Delta does not emit an `option_type` or `expiry_time`
  field; the direction lives in contract_type + the
  symbol prefix (C- / P-), and the expiry in the symbol
  tail, so option_type is derived from contract_type.

====================================================
"""

from core.exchanges.delta.delta_contract import DeltaContract

_DERIVED_OPTION_TYPE = {
    "call_options": "call",
    "binary_call_options": "call",
    "put_options": "put",
    "binary_put_options": "put",
}


def _num(value, default):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default):
    return int(_num(value, default))


def _asset_symbol(value):
    if isinstance(value, dict):
        return value.get("symbol", "")
    if isinstance(value, str):
        return value
    return ""


def _option_type(product):
    raw = product.get("option_type")
    if raw:
        return raw
    return _DERIVED_OPTION_TYPE.get(
        product.get("contract_type", "").lower(),
        "",
    )


class DeltaMapper:

    def map(self, product):

        return DeltaContract(

            symbol=product["symbol"],

            exchange="DELTA",

            contract_type=product.get(
                "contract_type",
                "UNKNOWN",
            ),

            tick_size=_num(
                product.get(
                    "tick_size",
                    0,
                ),
                0,
            ),

            quantity_step=_num(
                product.get(
                    "contract_value",
                    1,
                ),
                1,
            ),

            min_quantity=_num(
                product.get(
                    "minimum_order_size",
                    0,
                ),
                0,
            ),

            max_leverage=_num(
                product.get(
                    "maximum_leverage",
                    1,
                ),
                1,
            ),

            maker_fee=_num(
                product.get(
                    "maker_commission_rate",
                    0,
                ),
                0,
            ),

            taker_fee=_num(
                product.get(
                    "taker_commission_rate",
                    0,
                ),
                0,
            ),

            price_precision=_int(
                product.get(
                    "price_precision",
                    2,
                ),
                2,
            ),

            quantity_precision=_int(
                product.get(
                    "contract_value_precision",
                    3,
                ),
                3,
            ),

            underlying_asset=_asset_symbol(
                product.get(
                    "underlying_asset",
                    "",
                )
            ),

            option_type=_option_type(product),

            strike_price=_num(
                product.get(
                    "strike_price",
                    0,
                ),
                0,
            ),

            expiry_time=0,

            product_id=_int(
                product.get(
                    "id",
                    0,
                ),
                0,
            ),

        )