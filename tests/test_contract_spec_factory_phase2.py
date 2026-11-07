"""No legacy registry field may silently become a settlement multiplier."""

import unittest

from core.registry.instrument import Instrument
from core.risk.contract_math import ContractKind
from core.risk.contract_spec_factory import contract_spec_from_instrument, cost_model_from_instrument


def instrument(metadata=None, **overrides):
    values = dict(
        instrument_id="1", symbol="BTCUSDT", exchange="DELTA", tick_size=0.5,
        quantity_step=0.001, minimum_quantity=0.001, trading_enabled=True,
        metadata=metadata or {},
    )
    values.update(overrides)
    return Instrument(**values)


class TestContractSpecFactory(unittest.TestCase):
    def test_unverified_contract_value_never_becomes_multiplier(self):
        item = instrument({"raw_contract_type": "perpetual_futures", "contract_value": 100})
        availability = contract_spec_from_instrument(item)
        self.assertIsNone(availability.spec)
        self.assertIn("external venue verification", availability.reason)

    def test_explicitly_verified_contract_facts_create_spec(self):
        item = instrument({
            "verified_contract_kind": "LINEAR", "verified_contract_multiplier": "0.001",
            "verified_venue_source": "Delta product specification",
            "verified_venue_verified_at": "2026-09-16",
        })
        availability = contract_spec_from_instrument(item)
        self.assertEqual(availability.spec.kind, ContractKind.LINEAR)
        self.assertEqual(str(availability.spec.multiplier), "0.001")

    def test_bad_verified_metadata_is_non_executable(self):
        availability = contract_spec_from_instrument(instrument({
            "verified_contract_kind": "INVERSE", "verified_contract_multiplier": "0",
            "verified_venue_source": "Delta product specification",
            "verified_venue_verified_at": "2026-09-16",
        }))
        self.assertIsNone(availability.spec)
        self.assertIn("invalid verified contract metadata", availability.reason)

    def test_contract_values_without_evidence_provenance_are_non_executable(self):
        availability = contract_spec_from_instrument(instrument({
            "verified_contract_kind": "LINEAR", "verified_contract_multiplier": "0.001",
        }))
        self.assertIsNone(availability.spec)
        self.assertIn("verification evidence", availability.reason)

    def test_costs_require_explicit_venue_evidence_even_when_values_are_zero(self):
        availability = cost_model_from_instrument(instrument({
            "verified_venue_source": "Delta fee schedule",
            "verified_venue_verified_at": "2026-09-16",
            "verified_entry_fee_bps": "0", "verified_exit_fee_bps": "0",
            "verified_half_spread": "0", "verified_slippage_bps": "0",
            "verified_funding_per_contract": "0",
        }))
        self.assertIsNotNone(availability.model)

    def test_missing_cost_value_never_defaults_to_zero(self):
        availability = cost_model_from_instrument(instrument({
            "verified_venue_source": "Delta fee schedule",
            "verified_venue_verified_at": "2026-09-16",
            "verified_entry_fee_bps": "1", "verified_exit_fee_bps": "1",
            "verified_half_spread": "0", "verified_slippage_bps": "1",
        }))
        self.assertIsNone(availability.model)
        self.assertIn("verification evidence", availability.reason)


if __name__ == "__main__":
    unittest.main()
