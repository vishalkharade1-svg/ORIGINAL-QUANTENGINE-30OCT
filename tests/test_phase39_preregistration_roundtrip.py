import copy
import unittest

from core.research.oos.oos_types import HypothesisRecord
from core.research.readiness.preregistration import (
    FrozenPreregistration,
    PreregistrationError,
)


class TestPhase39PreregristrationRoundTrip(unittest.TestCase):
    def make(self):
        h = HypothesisRecord(
            origin="9L",
            statement="conditional entry evidence remains to be validated",
            symbol="BTCUSDT",
            direction="LONG",
            params={"entry_model": "BREAKOUT_CONTINUATION"},
            evidence=("9L:RPT1:entry_selection:F1",),
        )
        return FrozenPreregistration.create(
            hypotheses=(h,), dataset_identity="DATA1",
            discovery_boundary=100, oos_boundary=200,
            minimum_contiguous_bars=10, minimum_fresh_bars=100,
            economics_requirements=("expectancy_delta",),
            multiple_testing_family="SIDAK:TOTAL",
            symbol_constraints=("BTCUSDT",),
            frozen_execution_semantics="FROZEN_9C",
            limitations=("research_only",),
        )

    def test_round_trip_is_byte_equal_and_verifies(self):
        original = self.make()
        restored = FrozenPreregistration.from_dict(original.to_dict())
        self.assertEqual(restored.to_dict(), original.to_dict())
        self.assertTrue(restored.verify_identity())
        self.assertFalse(restored.is_production_ready)

    def test_tampered_hypothesis_fails_identity(self):
        payload = self.make().to_dict()
        payload["hypotheses"][0]["statement"] = "tampered"
        with self.assertRaises(PreregistrationError):
            FrozenPreregistration.from_dict(payload)

    def test_missing_field_fails_closed(self):
        payload = self.make().to_dict()
        payload.pop("dataset_identity")
        with self.assertRaises(PreregistrationError):
            FrozenPreregistration.from_dict(payload)

    def test_production_flag_cannot_be_rehydrated_true(self):
        payload = self.make().to_dict()
        payload["is_production_ready"] = True
        with self.assertRaises(PreregistrationError):
            FrozenPreregistration.from_dict(payload)

    def test_extra_fields_do_not_change_identity(self):
        payload = self.make().to_dict()
        payload["operator_note"] = "non-identity metadata"
        restored = FrozenPreregistration.from_dict(payload)
        self.assertEqual(restored.to_dict(), self.make().to_dict())


if __name__ == "__main__":
    unittest.main()
