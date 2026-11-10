"""Unit test for Phase 168 Strategy Historical Identity Reconstruction and Execution Economics."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from core.research.historical_reconstruction import (
    reconstruct_strategy_history,
)

try:
    from tests.evidence_mode import require_git_fact
except ImportError:
    from evidence_mode import require_git_fact

ROOT = Path(__file__).resolve().parents[1]


class TestStrategyHistoricalReconstructionPhase168(unittest.TestCase):
    def test_historical_reconstruction_structure_and_milestones(self):
        require_git_fact(
            self,
            "test_strategy_historical_reconstruction_phase168::baseline_milestones",
            required_commit="3f19895",
        )
        require_git_fact(
            self,
            "test_strategy_historical_reconstruction_phase168::runtime_milestone",
            required_commit="fbeb860",
        )
        report = reconstruct_strategy_history(ROOT)
        self.assertEqual(report["schema"], "quantengine.strategy-historical-reconstruction.v1")
        self.assertEqual(report["phase"], 168)
        self.assertEqual(
            report["historical_pinned_hash"],
            "c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6"
        )

        milestones = {m["name"]: m for m in report["milestones"]}
        self.assertIn("Phase 14 Baseline Mint", milestones)
        self.assertIn("Phase 14 Runtime Boundary", milestones)
        self.assertIn("Git HEAD (Current Branch)", milestones)
        self.assertIn("Current Disk Working Tree", milestones)

        # Baseline mint commit 3f19895
        self.assertEqual(
            milestones["Phase 14 Baseline Mint"]["composite_sha256_lf"],
            "db5bcdc01cd88b6c997e630e7ad1f6879f72f4ccc191393a6ff41675df52be72"
        )

        # Runtime boundary commit fbeb860
        self.assertEqual(
            milestones["Phase 14 Runtime Boundary"]["composite_sha256_lf"],
            "9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2"
        )

        # Current Disk Working Tree — advanced by the Phase 22
        # re-registration (frozen-era OOS semantics restored; all recorded
        # OOS funnels reproduce). Provenance:
        # reports/PHASE22_STRATEGY_IDENTITY_BASELINE.json - the historical
        # Phase 14 pin (c52e648c...) remains the authority.
        self.assertEqual(
            milestones["Current Disk Working Tree"]["composite_sha256_lf"],
            "05986916c990dbda8329b7fa8230ced878f951c68ed87e071b6afd3b8475afda"
        )

    def test_file_reconciliation_layer_and_diffs(self):
        require_git_fact(
            self,
            "test_strategy_historical_reconstruction_phase168::file_reconciliation",
            required_commit="3f19895",
        )
        report = reconstruct_strategy_history(ROOT)
        reconciled = {f["file"]: f for f in report["file_reconciliation"]}
        self.assertEqual(len(reconciled), 9)

        # 3 files identical to Phase 14 baseline in LF canonical form
        unmodified = [f for f, data in reconciled.items() if not data["modified_since_phase14"]]
        expected_unmodified = [
            "core/execution/entry_model.py",
            "core/execution/execution_engine.py",
            "core/setup/trade_setup_builder.py",
        ]
        self.assertEqual(sorted(unmodified), sorted(expected_unmodified))

        # 6 files modified (4 runtime/alpha fixes + 2 uncommitted local refinements)
        modified = [f for f, data in reconciled.items() if data["modified_since_phase14"]]
        expected_modified = [
            "config/risk_settings.py",
            "core/backtesting/accounting.py",
            "backtesting/backtester.py",
            "core/paper_trading/paper_trading_engine.py",
            "core/risk/risk_engine.py",
            "core/setup/decision_engine.py",
        ]
        self.assertEqual(sorted(modified), sorted(expected_modified))

    def test_execution_economics_reconciliation_artifact_invariants(self):
        econ_path = ROOT / "research" / "results" / "phase168_execution_economics_reconciliation.json"
        self.assertTrue(econ_path.exists(), "Missing execution economics reconciliation artifact")
        data = json.loads(econ_path.read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "RECONCILED_EXACT")
        self.assertEqual(data["symbol"], "BTCUSD")
        self.assertEqual(data["economics"]["gross_pnl_usd"], "0.0045")
        self.assertEqual(data["economics"]["total_commissions_usd"], "0.08710286")
        self.assertEqual(data["economics"]["net_pnl_usd"], "-0.08260286")
        self.assertTrue(data["balance_reconciliation"]["exact_balance_delta_match"])
        self.assertTrue(data["venue_integrity"]["positions_flat"])


if __name__ == "__main__":
    unittest.main()
