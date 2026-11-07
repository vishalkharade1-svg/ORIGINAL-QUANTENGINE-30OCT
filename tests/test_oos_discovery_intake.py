import unittest

from core.research.conditional_ml.types import EntrySelection
from core.research.conditional_ml.report import ConditionalMlReport
from core.research.oos import HypothesisRecord
from core.research.oos.intake import DiscoveryBindingError, validate_9l_binding


class TestOosDiscoveryIntake(unittest.TestCase):
    def report(self):
        finding = EntrySelection(
            cell_id="TREND:LONG",
            regime="TREND",
            direction="LONG",
            selected="LIMIT_RETEST",
        )
        return ConditionalMlReport(
            symbol="BTCUSDT",
            entry_selection=(finding,),
        )

    def test_binding_matches_report_surface_and_key(self):
        report = self.report()
        h = HypothesisRecord(
            origin="9L",
            statement="conditional entry",
            symbol="BTCUSDT",
            direction="LONG",
            params={"entry_model": "LIMIT_RETEST"},
            evidence=(
                "9L:%s:entry_selection:TREND:LONG" % report.report_id,
            ),
        )
        result = validate_9l_binding(h, report)
        self.assertTrue(result["bound"])
        self.assertEqual(result["report_id"], report.report_id)

    def test_missing_binding_fails(self):
        with self.assertRaises(DiscoveryBindingError):
            validate_9l_binding(
                HypothesisRecord(origin="9L", statement="x"),
                self.report(),
            )

    def test_wrong_report_fails(self):
        report = self.report()
        h = HypothesisRecord(
            origin="9L", statement="x",
            evidence=("9L:OTHER:entry_selection:TREND:LONG",),
        )
        with self.assertRaises(DiscoveryBindingError):
            validate_9l_binding(h, report)

    def test_evidence_is_serialized(self):
        h = HypothesisRecord(origin="9L", statement="x", evidence=("9L:R:S:K",))
        self.assertEqual(h.to_dict()["evidence"], ["9L:R:S:K"])


if __name__ == "__main__":
    unittest.main()
