import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestPhase64StrategyRecertification(unittest.TestCase):
    def test_current_source_does_not_claim_historical_recertification(self):
        report = json.loads((ROOT / "research/results/phase64_strategy_recertification.json").read_text())
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["strategy_identity"]["matches_recorded"])
        self.assertFalse(report["strategy_identity"]["matches_forensic"])
        self.assertFalse(report["gate_a"]["matches_historical"]["orders"])
        self.assertFalse(report["gate_a"]["matches_historical"]["fills"])
        self.assertFalse(report["historical_inputs"]["D2_phase7"])

    def test_gate_a_current_result_is_explicitly_preserved(self):
        report = json.loads((ROOT / "research/results/phase64_strategy_recertification.json").read_text())
        self.assertEqual(report["gate_a"]["current"], {
            "orders": 4, "fills": 1, "wins": 1, "losses": 0,
            "breakevens": 0, "net": 0.344788,
        })


if __name__ == "__main__":
    unittest.main()
