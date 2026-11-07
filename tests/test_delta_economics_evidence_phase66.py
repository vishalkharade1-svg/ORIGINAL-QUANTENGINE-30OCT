import unittest

from core.exchanges.delta.delta_history import DeltaHistory
from data.delta.product_normalizer import DeltaProductNormalizer


class _FakeRest:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get(self, endpoint, params=None):
        self.calls.append((endpoint, params))
        return {"result": self.rows}


class TestDeltaEconomicsEvidencePhase66(unittest.TestCase):
    def test_funding_history_is_explicit_and_deterministic(self):
        rest = _FakeRest([
            {"time": 120, "close": "0.001"},
            {"time": 60, "rate": "0.002"},
            {"time": 60, "rate": "0.999"},
            {"time": 180, "close": "bad"},
        ])
        history = DeltaHistory()
        history.rest = rest
        rows = history.funding_rates(
            "BTCUSDT", resolution="1h", start=1, end=1000)
        self.assertEqual(rows, [
            {"time": 60, "rate": 0.002},
            {"time": 120, "rate": 0.001},
        ])
        self.assertEqual(rest.calls[0][0], "/v2/history/candles")
        self.assertEqual(rest.calls[0][1]["symbol"], "FUNDING:BTCUSDT")

    def test_product_normalizer_preserves_venue_economics_metadata(self):
        product = {
            "id": 1, "symbol": "BTCUSDT", "contract_type": "perpetual_futures",
            "state": "live", "tick_size": "0.1", "contract_value": "1",
            "maker_commission_rate": "0.0002",
            "taker_commission_rate": "0.0005",
            "funding_method": "mark_price",
            "annualized_funding": "10.95",
            "funding_clamp_value": "0.05",
        }
        inst = DeltaProductNormalizer().normalize(product)
        self.assertEqual(inst.metadata["maker_commission_rate"], "0.0002")
        self.assertEqual(inst.metadata["taker_commission_rate"], "0.0005")
        self.assertEqual(inst.metadata["funding_method"], "mark_price")
        self.assertEqual(inst.metadata["annualized_funding"], "10.95")
        self.assertEqual(inst.metadata["funding_clamp_value"], "0.05")


    def test_strict_funding_evidence_rejects_duplicate_rows_and_fingerprints(self):
        rest = _FakeRest([
            {"time": 120, "close": "0.001"},
            {"time": 60, "rate": "0.002"},
        ])
        history = DeltaHistory(); history.rest = rest
        evidence = history.funding_evidence("BTCUSD", resolution="1h", start=1, end=1000)
        self.assertEqual(evidence["event_count"], 2)
        self.assertEqual(evidence["events"], [
            {"time": 60, "rate": 0.002}, {"time": 120, "rate": 0.001}
        ])
        self.assertEqual(len(evidence["sha256"]), 64)
        self.assertEqual(evidence["request"]["symbol"], "FUNDING:BTCUSD")

    def test_strict_funding_evidence_fails_on_duplicate_timestamp(self):
        rest = _FakeRest([
            {"time": 60, "rate": "0.002"},
            {"time": 60, "rate": "0.003"},
        ])
        history = DeltaHistory(); history.rest = rest
        with self.assertRaises(ValueError):
            history.funding_evidence("BTCUSD", start=1, end=1000)

    def test_invalid_funding_window_fails_closed(self):
        with self.assertRaises(ValueError):
            DeltaHistory().funding_rates("BTCUSDT", start=100, end=100)

    def test_invalid_resolution_fails_closed(self):
        with self.assertRaises(ValueError):
            DeltaHistory().funding_rates("BTCUSDT", resolution="7m")


if __name__ == "__main__":
    unittest.main()
