import unittest

from core.research.conditional_ml.report import ConditionalMlReport
from core.research.conditional_ml.types import RecoveryFinding, RECOVERY_SUPPORTED
from core.research.oos.selection import NineLSelection, NineLSelectionError, admit_9l_selection
from core.research.readiness.selection_preregistration import (
    create_9l_preregistration, SelectionPreregistrationError,
)
from core.research.oos.engine import OosValidationEngine


class TestPhase4042FrozenHandoff(unittest.TestCase):
    def report(self):
        f = RecoveryFinding(
            alternative="LIMIT_RETEST", regime="TREND", n=20, recovered=12,
            p_recovery=0.6, expected_r=1.2, expected_drawdown=0.5,
            loss_probability=0.2, min_n_gate=10,
            status=RECOVERY_SUPPORTED, survives_familywise=True,
            finding_id="REC-1",
        )
        return ConditionalMlReport(
            symbol="BTCUSDT", dataset_shape={"opportunities": 100},
            recovery=(f,), multiple_testing={"total_hypotheses": 1, "n_survive": 1},
            robustness={"level": "ROBUST"}, limitations=(),
        )

    def selection(self, report):
        return NineLSelection(
            report_id=report.report_id, surface="recovery", finding_key="REC-1",
            statement="LIMIT_RETEST recovery survives the frozen familywise gate.",
            symbol="BTCUSDT", regime_dim="trend_vs_range", regime_label="TREND",
            params={"entry_model": "LIMIT_RETEST"}, expected_outcome="positive recovery",
        )

    def prereg(self):
        r=self.report(); h=admit_9l_selection(self.selection(r), r)
        return r, h, create_9l_preregistration(
            selections=(h,), report=r, dataset_identity="DATASET-1",
            discovery_boundary=100, oos_boundary=200,
            minimum_contiguous_bars=100, minimum_fresh_bars=300,
            economics_requirements=("expectancy_delta",),
            multiple_testing_family="9M-1",
            regime_constraints=("trend_vs_range=TREND",),
            symbol_constraints=("BTCUSDT",), directional_constraints=(),
            frozen_execution_semantics="frozen-9C-counterfactual",
            limitations=("research-only",),
        )

    def test_report_roundtrip_and_full_identity(self):
        r=self.report(); payload=r.to_dict(); restored=ConditionalMlReport.from_dict(payload)
        self.assertEqual(restored.to_dict(), payload)
        altered=dict(payload); altered["robustness"]={"level":"INCONCLUSIVE"}
        with self.assertRaises(ValueError): ConditionalMlReport.from_dict(altered)

    def test_explicit_selection_requires_familywise_survival(self):
        r=self.report(); sel=self.selection(r)
        h=admit_9l_selection(sel, r)
        self.assertEqual(h.origin, "9L")
        bad=RecoveryFinding(alternative="LIMIT_RETEST", regime="TREND", n=20,
                            status=RECOVERY_SUPPORTED, survives_familywise=False,
                            finding_id="REC-1")
        badr=ConditionalMlReport(symbol="BTCUSDT", recovery=(bad,))
        with self.assertRaises(NineLSelectionError): admit_9l_selection(
            NineLSelection(report_id=badr.report_id, surface="recovery", finding_key="REC-1",
                           statement="x", params={"entry_model":"LIMIT_RETEST"}), badr)

    def test_preregistration_is_frozen_and_provenance_bound(self):
        r,h,p=self.prereg(); self.assertTrue(p.verify_identity()); self.assertFalse(p.is_production_ready)
        tampered=p.to_dict(); tampered["hypotheses"][0]["statement"]="tampered"
        with self.assertRaises(Exception): type(p).from_dict(tampered)

    def test_preregistered_execution_refuses_dataset_drift(self):
        _,_,p=self.prereg(); engine=OosValidationEngine()
        with self.assertRaises(ValueError): engine.run_preregistered(
            preregistration=p, dataset_identity="OTHER", opportunities=(), candles=(),
            base_config={"symbol":"BTCUSDT"})

    def test_preregistered_execution_refuses_unverified_prereg(self):
        _,_,p=self.prereg(); data=p.to_dict(); data["limitations"]=["tampered"]
        with self.assertRaises(Exception): type(p).from_dict(data)


if __name__ == "__main__": unittest.main()
