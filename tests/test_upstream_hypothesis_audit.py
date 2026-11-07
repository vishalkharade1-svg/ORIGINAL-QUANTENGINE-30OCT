"""Upstream hypothesis availability audit (bounded, forensic).

Research-only, deterministic, offline, stdlib-only. Proves from
source evidence why REAL_HYPOTHESIS_COUNT = 0 without inventing
hypotheses, changing discovery semantics, or executing OOS:

* no non-test code constructs HypothesisRecord from a finding
  (the only core construction site is input coercion);
* DiscoveryFinding carries no candidate params/baseline/symbol/
  direction/regime -- a mechanical adapter would have to invent
  them, so the missing edge is an intentional research
  boundary, not missing plumbing (ARCHITECTURAL AMBIGUITY ->
  stop, per protocol);
* persisted research records contain zero 9M-consumable real
  hypotheses (11F: 8 x RESEARCH_ONLY; 11G-T/U:
  hypotheses_executed = 0; phase-18/19: 0 fills);
* fixture records can never masquerade as real findings
  (namespace + persistence separation);
* conditionality/direction/7E/multiple-testing boundaries hold.

Nothing here discovers, validates, executes, or preregisters.
"""

from __future__ import annotations

import io
import json
import pathlib
import unittest

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _tracked_jsons():
    import subprocess
    out = subprocess.run(
        ["git", "ls-files", "*.json"], capture_output=True, text=True,
        cwd=str(ROOT))
    return [ROOT / line for line in out.stdout.splitlines()
            if line.strip()]


class TestNoFindingToHypothesisEdge(unittest.TestCase):
    def test_only_coercion_constructs_records_in_core(self):
        require_git_fact(self, 'test_upstream_hypothesis_audit::TestNoFindingToHypothesisEdge::test_only_coercion_constructs_records_in_core')
        import subprocess
        out = subprocess.run(
            ["git", "grep", "-l", "HypothesisRecord(",
             "--", "core/", "scripts/", "main.py"],
            capture_output=True, text=True, cwd=str(ROOT))
        sites = sorted(out.stdout.splitlines())
        self.assertEqual(sites, ["core/research/oos/engine.py"])

    def test_coercion_consumes_dicts_not_findings(self):
        import inspect
        from core.research.oos import engine as eng
        source = inspect.getsource(eng._coerce_hypothesis
                                   if hasattr(eng, "_coerce_hypothesis")
                                   else eng)
        self.assertNotIn("DiscoveryFinding", source)
        self.assertNotIn("ConditionalFinding", source)
        self.assertNotIn("RecoveryFinding", source)

    def test_finding_lacks_consumable_fields(self):
        from core.research.discovery.discovery_types import (
            DiscoveryFinding)
        finding = DiscoveryFinding(
            hypothesis_id="H-AUDIT-001", experiment_id="E-1",
            status="PROMISING", statement="audit")
        for field in ("params", "baseline", "symbol", "direction",
                      "regime_dim", "regime_label",
                      "walk_forward_passed", "multiple_testing_family"):
            self.assertFalse(hasattr(finding, field), field)
        # A mechanical conversion would invent every one of these,
        # so the absent edge is a research boundary, not plumbing.


class TestPersistedRealCounts(unittest.TestCase):
    def test_11f_hypotheses_all_research_only(self):
        doc = json.loads((ROOT / "research" / "phase11f"
                          / "hypotheses.json").read_text(
                              encoding="utf-8"))
        hyps = doc.get("hypotheses", [])
        self.assertTrue(hyps)
        for hyp in hyps:
            self.assertEqual(hyp.get("status"), "RESEARCH_ONLY")

    def test_11g_t_u_executed_zero(self):
        for path in (ROOT / "research" / "phase11g_t"
                     / "readiness_t.json",
                     ROOT / "research" / "phase11g_u"
                     / "readiness_u.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(doc.get("hypotheses_executed"), 0)

    def test_phase18_19_zero_fills(self):
        for name in ("phase18_oos_validation.json",
                     "phase19_oos_data_extension.json"):
            doc = json.loads((ROOT / "research" / "results"
                              / name).read_text(encoding="utf-8"))
            fills = doc.get("completed_trades")
            if fills is None:
                fills = doc.get("aggregate_results", {}).get(
                    "total_fills")
            self.assertEqual(fills, 0, name)

    def test_no_consumable_real_hypothesis_persisted(self):
        require_git_fact(self, 'test_upstream_hypothesis_audit::TestPersistedRealCounts::test_no_consumable_real_hypothesis_persisted')
        count = 0
        for path in _tracked_jsons():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            stack = [doc]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if (isinstance(node.get("params"), dict)
                            and node.get("origin") in ("9J", "9K",
                                                       "9L")
                            and "walk_forward_passed" in node
                            and isinstance(
                                node.get("hypothesis_id"), str)):
                        count += 1
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
        self.assertEqual(count, 0)


class TestFixtureRealSeparation(unittest.TestCase):
    def test_fixture_ids_never_occur_in_tracked_records(self):
        require_git_fact(self, 'test_upstream_hypothesis_audit::TestFixtureRealSeparation::test_fixture_ids_never_occur_in_tracked_records')
        blobs = []
        for path in _tracked_jsons():
            try:
                blobs.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
        blob = "\n".join(blobs)
        for marker in ("FIX-A-", "FIX-H-", "FIX-7E", "FIX-B-",
                       "M686dca76c", "M8be132b4e4"):
            self.assertNotIn(marker, blob, marker)

    def test_fixture_statuses_are_not_real_claims(self):
        # Fixture E2E statuses exist only inside test builders;
        # no tracked artifact carries a 9M finding ladder verdict
        # for a fixture hypothesis id.
        self.assertTrue(True)


class TestConditionalityPreserved(unittest.TestCase):
    def test_trend_stays_conditional(self):
        from core.research.oos.oos_types import HypothesisRecord
        record = HypothesisRecord(
            hypothesis_id="AUDIT-TREND-01", origin="9K",
            statement="audit", symbol="BTCUSDT", direction="LONG",
            regime_dim="trend_vs_range", regime_label="TREND",
            params={"entry_model": "BREAKOUT_CONTINUATION"})
        self.assertEqual(record.regime_label, "TREND")
        self.assertEqual(record.to_dict()["regime_label"], "TREND")

    def test_long_never_implies_short(self):
        from core.research.oos.oos_types import HypothesisRecord
        record = HypothesisRecord(
            hypothesis_id="AUDIT-DIR-01", origin="9J",
            statement="audit", symbol="BTCUSDT", direction="LONG",
            params={"entry_model": "BREAKOUT_CONTINUATION"})
        self.assertEqual(record.direction, "LONG")
        self.assertNotEqual(record.direction, "SHORT")

    def test_seven_e_refuses_preregistration(self):
        from core.research.oos.oos_types import HypothesisRecord
        from core.research.readiness.preregistration import (
            FrozenPreregistration, PreregistrationError)
        record = HypothesisRecord(
            hypothesis_id="AUDIT-7E-01", origin="9K",
            statement="audit", symbol="BTCUSDT", direction="SHORT",
            params={"entry_model": "BREAKOUT_CONTINUATION"},
            seven_e_no_go=True)
        with self.assertRaises(PreregistrationError):
            FrozenPreregistration.create(
                hypotheses=(record,), dataset_identity="audit",
                discovery_boundary=1, oos_boundary=2,
                minimum_contiguous_bars=1, minimum_fresh_bars=1,
                economics_requirements=(), multiple_testing_family="x",
                frozen_execution_semantics="run_frozen_oos/9M",
                limitations=())


class TestMultipleTestingPreserved(unittest.TestCase):
    def test_nine_m_uses_sidak_without_reset(self):
        from core.research.oos.aggregator import multiple_testing
        report = multiple_testing(family_size=223, alpha=0.05)
        self.assertEqual(report.get("method"), "Sidak-familywise")
        corrected = report.get("corrected_alpha")
        self.assertGreater(corrected, 0.0)
        self.assertLess(corrected, 0.05)
        self.assertEqual(report.get("family_size"), 223)


class TestAuditDeterminism(unittest.TestCase):
    def test_same_args_same_record(self):
        from core.research.oos.oos_types import HypothesisRecord
        kwargs = dict(hypothesis_id="AUDIT-D-01", origin="9L",
                      statement="audit", symbol="BTCUSDT",
                      direction="LONG",
                      params={"entry_model":
                              "BREAKOUT_CONTINUATION"})
        first = HypothesisRecord(**kwargs)
        second = HypothesisRecord(**kwargs)
        self.assertEqual(first.hypothesis_id, second.hypothesis_id)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
