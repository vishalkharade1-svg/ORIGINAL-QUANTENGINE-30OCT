import json
import tempfile
import unittest
from pathlib import Path

from core.exchanges.delta.delta_history import DeltaHistory
from research.economics.funding_evidence import build_artifact, load_and_verify, to_schedule


class _FakeRest:
    def __init__(self, rows):
        self.rows = rows
    def get(self, endpoint, params=None):
        return {"result": self.rows}


class TestFundingEvidenceBindingPhase70(unittest.TestCase):
    def _evidence(self):
        history = DeltaHistory()
        history.rest = _FakeRest([
            {"time": 200, "rate": "0.002"},
            {"time": 100, "rate": "-0.001"},
        ])
        return history.funding_evidence("BTCUSDT", "1h", 1, 300)

    def test_artifact_binds_exact_market_bytes_and_replays(self):
        with tempfile.TemporaryDirectory() as d:
            market = Path(d) / "market.json"
            market.write_text('{"bars":[1,2,3]}\n', encoding="utf-8")
            artifact = build_artifact(
                self._evidence(), market_data_path=market,
                provenance_status="REAL", captured_at="2026-10-07T00:00:00Z")
            out = Path(d) / "funding.json"
            from research.economics.funding_evidence import write_artifact
            write_artifact(artifact, out)
            restored = load_and_verify(out, market_data_path=market)
            self.assertEqual(restored.market_data_sha256, artifact.market_data_sha256)
            self.assertEqual(to_schedule(restored).events[0].timestamp, 100)

    def test_market_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            market = Path(d) / "market.json"
            market.write_text("original\n", encoding="utf-8")
            artifact = build_artifact(self._evidence(), market_data_path=market,
                                      provenance_status="REAL", captured_at="t")
            out = Path(d) / "funding.json"
            from research.economics.funding_evidence import write_artifact
            write_artifact(artifact, out)
            market.write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_and_verify(out, market_data_path=market)

    def test_fixture_cannot_be_promoted_to_schedule(self):
        with tempfile.TemporaryDirectory() as d:
            market = Path(d) / "market.json"
            market.write_text("fixture\n", encoding="utf-8")
            artifact = build_artifact(self._evidence(), market_data_path=market,
                                      provenance_status="FIXTURE", captured_at="t")
            with self.assertRaises(ValueError):
                to_schedule(artifact)

    def test_fingerprint_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            market = Path(d) / "market.json"
            market.write_text("market\n", encoding="utf-8")
            artifact = build_artifact(self._evidence(), market_data_path=market,
                                      provenance_status="REAL", captured_at="t")
            out = Path(d) / "funding.json"
            from research.economics.funding_evidence import write_artifact
            write_artifact(artifact, out)
            raw = json.loads(out.read_text())
            raw["events"][0]["rate"] = 999.0
            out.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                load_and_verify(out, market_data_path=market)


if __name__ == "__main__":
    unittest.main()
