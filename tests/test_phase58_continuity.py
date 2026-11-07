import unittest
from core.research.journal.opportunity_record import OpportunityRecord
from core.research.oos.discovery_input import Discovery9LInput, DiscoveryInputError, from_opportunity_records


class TestPhase58Continuity(unittest.TestCase):
    def rec(self, symbol="BTCUSDT", bar=10, cid="a"):
        return OpportunityRecord(
            canonical_id=cid, instrument_id=symbol, exchange="DELTA",
            timeframe="1m", setup={"bar": bar}, hub_timestamp=bar,
        )

    def test_frozen_input_from_existing_records(self):
        obj = from_opportunity_records(
            records=(self.rec(bar=10), self.rec(bar=20, cid="b")),
            dataset_identity="DATA", provenance_identity="PROV",
            discovery_boundary=100, outcome_horizon=5,
        )
        self.assertIsInstance(obj, Discovery9LInput)
        self.assertEqual(len(obj.opportunity_records), 2)
        self.assertTrue(obj.input_identity)
        self.assertEqual(obj.to_dict()["input_identity"], obj.input_identity)

    def test_post_boundary_is_rejected(self):
        with self.assertRaises(DiscoveryInputError):
            from_opportunity_records(
                records=(self.rec(bar=100),), dataset_identity="D",
                provenance_identity="P", discovery_boundary=100,
            )

    def test_outcome_horizon_crossing_boundary_is_rejected(self):
        with self.assertRaises(DiscoveryInputError):
            from_opportunity_records(
                records=(self.rec(bar=96),), dataset_identity="D",
                provenance_identity="P", discovery_boundary=100,
                outcome_horizon=5,
            )

    def test_duplicate_decision_point_is_rejected(self):
        with self.assertRaises(DiscoveryInputError):
            from_opportunity_records(
                records=(self.rec(cid="a"), self.rec(cid="b")),
                dataset_identity="D", provenance_identity="P",
                discovery_boundary=100,
            )

    def test_empty_source_is_rejected(self):
        with self.assertRaises(DiscoveryInputError):
            from_opportunity_records(
                records=(), dataset_identity="D", provenance_identity="P",
                discovery_boundary=100,
            )


if __name__ == "__main__":
    unittest.main()
