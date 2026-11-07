"""Heuristic ranking scores must not become probability claims."""

import unittest

from core.scoring.score_engine import ScoreEngine
from core.setup.setup_candidate import SetupCandidate
from core.setup.trade_setup import TradeSetup


class FixedScore(ScoreEngine):
    def calculate(self, _obj):
        return 90.0


class TestScoreProbabilityContract(unittest.TestCase):
    def test_score_confidence_does_not_create_probability(self):
        candidate = SetupCandidate()
        FixedScore().score(candidate)
        self.assertEqual(candidate.score, 90.0)
        self.assertEqual(candidate.confidence, 97)
        self.assertIsNone(candidate.calibrated_probability)

    def test_setup_defaults_to_no_calibrated_probability(self):
        setup = TradeSetup("BULLISH", 100.0, 90.0, 160.0, 6.0, 80.0)
        self.assertIsNone(setup.calibrated_probability)


if __name__ == "__main__":
    unittest.main()
