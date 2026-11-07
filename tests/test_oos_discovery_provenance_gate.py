import unittest

from core.research.conditional_ml.report import ConditionalMlReport
from core.research.conditional_ml.types import EntrySelection
from core.research.oos import HypothesisRecord, OosValidationEngine
from core.research.oos.intake import DiscoveryBindingError


class TestOosDiscoveryProvenanceGate(unittest.TestCase):
    def setUp(self):
        self.report = ConditionalMlReport(
            symbol="X",
            entry_selection=(EntrySelection(cell_id="TREND:LONG"),),
        )
        self.h = HypothesisRecord(
            origin="9L", statement="x", symbol="X", direction="LONG",
            params={"entry_model": "LIMIT_RETEST"},
            evidence=(
                "9L:%s:entry_selection:TREND:LONG" % self.report.report_id,
            ),
        )

    def test_binding_can_be_used_by_strict_gate_logic(self):
        from core.research.oos.intake import validate_9l_binding
        result = validate_9l_binding(self.h, self.report)
        self.assertTrue(result["bound"])

    def test_strict_gate_rejects_missing_source_report(self):
        with self.assertRaises(DiscoveryBindingError):
            OosValidationEngine().run(
                [], [], {"rr": 2.0}, [self.h],
                require_discovery_provenance=True,
            )


if __name__ == "__main__":
    unittest.main()
