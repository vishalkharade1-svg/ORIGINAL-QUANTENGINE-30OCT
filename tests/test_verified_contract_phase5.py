"""Phase-5 verified instrument metadata: no silent defaults (offline)."""

import unittest

from core.registry.verified_contract import (
    size_quantity,
    verify_contract_spec,
)


def _raw(**overrides):
    raw = {
        "product_id": 27,
        "symbol": "BTCUSDT",
        "instrument_type": "perpetual_futures",
        "contract_type": "perpetual_futures",
        "tick_size": 0.5,
        "quantity_step": 1,
        "minimum_quantity": 1,
        "minimum_notional": 10.0,
        "multiplier": 0.001,
        "settlement_currency": "USDT",
        "leverage": {
            "max_leverage": 100.0,
            "initial_margin_rate": 0.01,
            "maintenance_margin_rate": 0.005,
            "margin_asset": "USDT",
        },
    }
    raw.update(overrides)
    return raw


PROVENANCE = {"venue": "DELTA_GLOBAL", "source": "delta-v2-products",
              "verified_at": "2026-09-18T00:00:00Z"}


class TestVerifiedContractSpec(unittest.TestCase):
    def test_complete_spec_verifies(self):
        spec = verify_contract_spec(_raw(), **PROVENANCE)
        self.assertEqual(spec.symbol, "BTCUSDT")
        self.assertEqual(spec.multiplier, 0.001)

    def test_missing_product_id_raises(self):
        raw = _raw()
        del raw["product_id"]
        with self.assertRaises(ValueError):
            verify_contract_spec(raw, **PROVENANCE)

    def test_spot_is_never_assumed(self):
        raw = _raw()
        del raw["instrument_type"]
        with self.assertRaisesRegex(ValueError, "instrument_type"):
            verify_contract_spec(raw, **PROVENANCE)

    def test_missing_multiplier_raises_not_defaulted(self):
        raw = _raw()
        del raw["multiplier"]
        with self.assertRaises(ValueError):
            verify_contract_spec(raw, **PROVENANCE)

    def test_missing_tick_or_quantity_fields_raise(self):
        for key in ("tick_size", "quantity_step", "minimum_quantity",
                    "minimum_notional", "settlement_currency",
                    "contract_type"):
            raw = _raw()
            del raw[key]
            with self.assertRaises(ValueError, msg=key):
                verify_contract_spec(raw, **PROVENANCE)

    def test_missing_leverage_semantics_raise(self):
        raw = _raw()
        del raw["leverage"]
        with self.assertRaises(ValueError):
            verify_contract_spec(raw, **PROVENANCE)
        with self.assertRaises(ValueError):
            verify_contract_spec(
                _raw(leverage={"max_leverage": 10.0}), **PROVENANCE)

    def test_missing_provenance_raises(self):
        with self.assertRaises(ValueError):
            verify_contract_spec(_raw(), venue="", source="s", verified_at="t")

    def test_sizing_is_multiplier_aware_and_minimum_enforcing(self):
        spec = verify_contract_spec(_raw(), **PROVENANCE)
        quantity = size_quantity(risk_amount=20.0, stop_distance=500.0,
                                 spec=spec, entry_price=100_000.0)
        # 20 / (500 * 0.001) = 40 contracts, step 1 -> 40.
        self.assertEqual(quantity, 40)
        with self.assertRaises(ValueError):
            size_quantity(risk_amount=0.0001, stop_distance=500.0,
                          spec=spec, entry_price=100_000.0)

    def test_sizing_refuses_unverified_input(self):
        spec = verify_contract_spec(_raw(), **PROVENANCE)
        with self.assertRaises(TypeError):
            size_quantity(risk_amount=20.0, stop_distance=500.0,
                          spec={"multiplier": 0.001}, entry_price=100_000.0)
        _ = spec


if __name__ == "__main__":
    unittest.main()
