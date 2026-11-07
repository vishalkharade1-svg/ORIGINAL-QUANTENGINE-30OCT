"""Phase 169 Regression Suite: Execution Economics Verifier Hardening.

Validates that every check in core/reconciliation/execution_economics_verifier.py
is derived from actual evidence and fails closed on corrupted, missing, duplicate,
ambiguous, or inconsistent data across all 6 subsystems:
1. Private WebSocket fills (missing, duplicate, ambiguous, field mismatch, malformed schema)
2. Top-of-book L2 quote binding (missing snapshots, inverted quotes, ambiguous ties, side-aware slippage vs limit improvement)
3. Commission reconciliation (duplicate postings, amount mismatch, fee + GST decomposition discrepancy)
4. Realized cashflow (missing, ambiguous candidates, contract multiplier, unbalanced legs)
5. Chronological ledger balances (running balance step mismatch, delta mismatch, preceding balance derivation)
6. Positions & open orders (non-flat positions, unverifiable open orders)
7. Decimal precision, explicit tolerances, and determinism.

NOTE: Synthetic fixtures used herein are strictly labelled SYNTHETIC_TEST_FIXTURE
and used solely for testing software error paths.
"""

from __future__ import annotations

import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path

from core.reconciliation.execution_economics_verifier import (
    ExecutionEconomicsVerifier,
    run_full_execution_economics_verification,
)

ROOT = Path(__file__).resolve().parents[1]


class TestExecutionEconomicsVerifierPhase169(unittest.TestCase):
    def setUp(self):
        self.verifier = ExecutionEconomicsVerifier(ROOT)
        # Load baseline artifacts
        self.recon_report = json.loads(
            (ROOT / "research/captures/phase167_recon/recon_experiment_report.json").read_text(encoding="utf-8")
        )
        self.rest_data = json.loads(
            (ROOT / "research/captures/phase167_recon/rest_fills.json").read_text(encoding="utf-8")
        )
        self.ws_frames = json.loads(
            (ROOT / "research/captures/phase167_recon/private_ws_frames.json").read_text(encoding="utf-8")
        )
        self.mf_data = json.loads(
            (ROOT / "research/captures/phase167_recon/l2/market_friction_evidence.json").read_text(encoding="utf-8")
        )
        self.l2_data = json.loads(
            (ROOT / "research/captures/phase167_recon/l2/delta_ob_updates_archive.json").read_text(encoding="utf-8")
        )
        self.wallet_txns = json.loads(
            (ROOT / "research/captures/phase168_ledger/wallet_100.json").read_text(encoding="utf-8")
        )
        self.balances_data = json.loads(
            (ROOT / "research/captures/phase168_ledger/balances.json").read_text(encoding="utf-8")
        )
        self.positions_data = json.loads(
            (ROOT / "research/captures/phase168_ledger/positions.json").read_text(encoding="utf-8")
        )

        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]
        self.in_window_fills = [f for f in self.rest_data["fills"] if f["fill_id"] in matched_ids]
        self.in_window_fills.sort(key=lambda x: x["timestamp"])

    # -------------------------------------------------------------------------
    # Baseline Real Evidence Verification
    # -------------------------------------------------------------------------
    def test_real_artifacts_reconcile_exact(self):
        """Verifies that all 6 subsystems pass against actual venue evidence."""
        res = self.verifier.run_full_reconciliation(phase=169)
        self.assertEqual(res["overall_status"], "RECONCILED_EXACT")
        self.assertTrue(res["all_components_passed"])

        # Check economics figures
        econ = res["economics"]
        self.assertEqual(econ["gross_pnl_usd"], "0.0045")
        self.assertEqual(econ["total_commissions_usd"], "0.08710286")
        self.assertEqual(econ["net_pnl_usd"], "-0.08260286")
        self.assertEqual(econ["fee_drag_bps"], "10.62")

        # Check balances
        bal = res["balance_summary"]
        self.assertEqual(bal["pre_experiment_balance_usd"], "198.47068846")
        self.assertEqual(bal["post_experiment_balance_usd"], "198.3880856")
        self.assertEqual(bal["observed_delta_usd"], "-0.08260286")
        self.assertEqual(bal["expected_delta_usd"], "-0.08260286")
        self.assertTrue(bal["exact_balance_delta_match"])

        # Check venue integrity
        venue = res["venue_integrity"]
        self.assertTrue(venue["positions_flat"])
        self.assertEqual(venue["open_orders"], 0)
        self.assertTrue(venue["private_ws_matched"])
        self.assertTrue(venue["l2_quote_bound"])

    # -------------------------------------------------------------------------
    # 1. Private WebSocket Fills Failures
    # -------------------------------------------------------------------------
    def test_ws_missing_frames_fails_closed(self):
        """SYNTHETIC_TEST_FIXTURE: Missing a required trade frame must fail closed."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        # Drop the second trade frame (index 3)
        synthetic_frames = synthetic_frames[:3]
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAILED")
        self.assertGreater(res.records_unmatched, 0)
        self.assertIn("No WebSocket trade frame found", str(res.failure_reason))

    def test_ws_duplicate_fill_match_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Duplicate trade frames for the same fill must be rejected."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        # Duplicate the trade frame at index 2
        synthetic_frames.append(copy.deepcopy(synthetic_frames[2]))
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAILED")
        self.assertGreater(res.records_duplicated, 0)
        self.assertIn("Duplicate WebSocket trade frames", str(res.failure_reason))

    def test_ws_side_mismatch_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Inverted side in WS trade frame must be rejected."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        synthetic_frames[2]["S"] = "sell"  # Leg 1 is a buy
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertIn("Side mismatch", str(res.failure_reason))

    def test_ws_size_mismatch_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Size mismatch in WS trade frame must be rejected."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        synthetic_frames[2]["s"] = "2"  # Expected size is 1
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertIn("Size mismatch", str(res.failure_reason))

    def test_ws_price_mismatch_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Price mismatch in WS trade frame must be rejected."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        synthetic_frames[2]["p"] = "82016.0"  # Expected price 82015.5
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertIn("Price mismatch", str(res.failure_reason))

    def test_ws_symbol_mismatch_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Symbol mismatch in WS trade frame must be rejected."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        synthetic_frames[2]["sy"] = "ETHUSD"
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertIn("Symbol mismatch", str(res.failure_reason))

    def test_ws_timestamp_tolerance_exceeded_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Large timestamp divergence between WS and REST must fail."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        # Shift timestamp by 10,000 microseconds (10ms > 5ms tolerance)
        synthetic_frames[2]["t"] += 10000000
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertIn("Timestamp delta too large", str(res.failure_reason))

    def test_ws_malformed_schema_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Missing required trade schema fields must be rejected."""
        synthetic_frames = copy.deepcopy(self.ws_frames)
        del synthetic_frames[2]["s"]  # remove size
        matched_ids = self.recon_report["reconciliation"]["matched_fill_ids"]

        res = self.verifier.verify_private_ws_fills(
            synthetic_frames, self.rest_data["fills"], matched_ids
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAILED_SCHEMA")

    # -------------------------------------------------------------------------
    # 2. L2 Quote Binding Failures & Side-Aware Slippage
    # -------------------------------------------------------------------------
    def test_l2_missing_snapshots_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Missing L2 samples within alignment window fails closed."""
        synthetic_mf = {"samples": []}
        res = self.verifier.verify_l2_quote_binding(synthetic_mf, None, self.in_window_fills)
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAILED_NO_SAMPLES")

    def test_l2_out_of_window_samples_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Samples beyond max_delta_ms fail closed."""
        synthetic_mf = copy.deepcopy(self.mf_data)
        # Shift all samples by 1 hour
        for s in synthetic_mf["samples"]:
            s["timestamp_ms"] += 3600000

        res = self.verifier.verify_l2_quote_binding(
            synthetic_mf, None, self.in_window_fills, max_delta_ms=1000
        )
        self.assertFalse(res.passed)
        self.assertIn("No contemporaneous L2 sample within 1000ms", str(res.failure_reason))

    def test_l2_inverted_book_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Inverted book (bid > ask) must be rejected as invalid."""
        synthetic_mf = copy.deepcopy(self.mf_data)
        for s in synthetic_mf["samples"]:
            s["best_bid"] = "82030.0"
            s["best_ask"] = "82010.0"

        res = self.verifier.verify_l2_quote_binding(synthetic_mf, None, self.in_window_fills)
        self.assertFalse(res.passed)
        self.assertIn("Invalid/inverted L2 touch", str(res.failure_reason))

    def test_l2_ambiguous_equidistant_quotes_rejected(self):
        """SYNTHETIC_TEST_FIXTURE: Ambiguous equidistant L2 samples with conflicting quotes."""
        synthetic_mf = {
            "samples": [
                {
                    "best_bid": "82011.5",
                    "best_ask": "82015.5",
                    "timestamp_ms": self.in_window_fills[0]["timestamp"] - 50,
                },
                {
                    "best_bid": "82010.0",
                    "best_ask": "82014.0",
                    "timestamp_ms": self.in_window_fills[0]["timestamp"] + 50,
                },
            ]
        }
        res = self.verifier.verify_l2_quote_binding(synthetic_mf, None, [self.in_window_fills[0]])
        self.assertFalse(res.passed)
        self.assertIn("Ambiguous equidistant L2 samples", str(res.failure_reason))

    def test_l2_slippage_and_price_improvement_distinction(self):
        """Validates that contemporaneous quote slippage and limit price improvement are distinguished."""
        res = self.verifier.verify_l2_quote_binding(
            self.mf_data, self.l2_data, self.in_window_fills, self.recon_report
        )
        self.assertTrue(res.passed)
        bindings = res.details["bindings"]
        self.assertEqual(len(bindings), 2)

        # Leg 1: Buy
        b1 = bindings[0]
        self.assertEqual(b1["side"], "buy")
        self.assertEqual(b1["quote_slippage_usd"], "0.0")  # Executed at ask
        self.assertEqual(b1["limit_price_improvement_usd"], "0.0")  # At limit

        # Leg 2: Sell (crossed at favorable price)
        b2 = bindings[1]
        self.assertEqual(b2["side"], "sell")
        self.assertEqual(b2["quote_slippage_usd"], "0.0")  # Executed at contemporaneous bid
        self.assertEqual(b2["limit_price_improvement_usd"], "8.5")  # +8.50 points favorable limit improvement

    # -------------------------------------------------------------------------
    # 3. Commission Reconciliation Failures
    # -------------------------------------------------------------------------
    def test_commission_duplicate_postings_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Duplicate commission postings for same fill must fail."""
        synthetic_txns = copy.deepcopy(self.wallet_txns)
        # Add duplicate of transaction 0 (Leg 2 commission)
        synthetic_txns.append(copy.deepcopy(synthetic_txns[0]))

        res = self.verifier.verify_commissions(synthetic_txns, self.in_window_fills)
        self.assertFalse(res.passed)
        self.assertGreater(res.records_duplicated, 0)
        self.assertIn("Duplicate wallet commission postings", str(res.failure_reason))

    def test_commission_amount_mismatch_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Commission amount differing from REST fill must fail."""
        synthetic_txns = copy.deepcopy(self.wallet_txns)
        synthetic_txns[0]["amount"] = "-0.05000000"

        res = self.verifier.verify_commissions(synthetic_txns, self.in_window_fills)
        self.assertFalse(res.passed)
        self.assertIn("Commission amount mismatch", str(res.failure_reason))

    def test_commission_fee_decomposition_discrepancy_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Base fee + GST not summing to total commission must fail."""
        synthetic_txns = copy.deepcopy(self.wallet_txns)
        # Corrupt GST so base_fee + gst != total_commission
        synthetic_txns[0]["meta_data"]["gst"] = "-0.00500000"

        res = self.verifier.verify_commissions(synthetic_txns, self.in_window_fills)
        self.assertFalse(res.passed)
        self.assertIn("Fee decomposition mismatch", str(res.failure_reason))

    # -------------------------------------------------------------------------
    # 4. Realized Cashflow Failures
    # -------------------------------------------------------------------------
    def test_cashflow_missing_candidate_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Missing matching realized cashflow must fail closed."""
        synthetic_txns = [t for t in self.wallet_txns if t.get("transaction_type") != "cashflow"]
        res = self.verifier.verify_realized_cashflow(
            synthetic_txns, self.in_window_fills[0], self.in_window_fills[1]
        )
        self.assertFalse(res.passed)
        self.assertIn("No unique matching realized PnL cashflow found", str(res.failure_reason))

    def test_cashflow_ambiguous_duplicate_candidates_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Multiple identical candidate cashflows must fail closed."""
        synthetic_txns = copy.deepcopy(self.wallet_txns)
        # Duplicate index 1 (the experiment cashflow)
        synthetic_txns.append(copy.deepcopy(synthetic_txns[1]))

        res = self.verifier.verify_realized_cashflow(
            synthetic_txns, self.in_window_fills[0], self.in_window_fills[1]
        )
        self.assertFalse(res.passed)
        self.assertGreater(res.records_duplicated, 0)
        self.assertIn("Multiple plausible candidate cashflows", str(res.failure_reason))

    def test_cashflow_wrong_contract_multiplier_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Wrong contract multiplier (e.g. 0.01 vs 0.001) must fail."""
        res = self.verifier.verify_realized_cashflow(
            self.wallet_txns,
            self.in_window_fills[0],
            self.in_window_fills[1],
            contract_multiplier=Decimal("0.01"),  # Wrong multiplier
        )
        self.assertFalse(res.passed)
        self.assertIn("Gross PnL mismatch", str(res.failure_reason))

    def test_cashflow_unbalanced_legs_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Unbalanced leg sizes must fail closed."""
        unbalanced_leg1 = copy.deepcopy(self.in_window_fills[0])
        unbalanced_leg1["size"] = "2"

        res = self.verifier.verify_realized_cashflow(
            self.wallet_txns, unbalanced_leg1, self.in_window_fills[1]
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAILED_UNBALANCED_LEGS")

    # -------------------------------------------------------------------------
    # 5. Chronological Ledger Balances Failures
    # -------------------------------------------------------------------------
    def test_chronological_balances_preceding_balance_independently_derived(self):
        """Verifies starting balance is taken from the preceding transaction, not back-calculated."""
        gross_pnl = Decimal("0.0045")
        commissions = Decimal("0.08710286")
        res = self.verifier.verify_chronological_balances(
            self.wallet_txns, self.balances_data, gross_pnl, commissions
        )
        self.assertTrue(res.passed)
        self.assertEqual(res.details["pre_experiment_balance_usd"], "198.47068846")
        self.assertEqual(res.details["post_experiment_balance_usd"], "198.3880856")
        self.assertEqual(res.details["running_balance_steps_verified"], 3)

    def test_chronological_balances_running_balance_step_mismatch_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Intermediate running balance corruption must fail."""
        synthetic_txns = copy.deepcopy(self.wallet_txns)
        # Corrupt balance at Step 2 (cashflow)
        synthetic_txns[1]["balance"] = "199.00000000"

        gross_pnl = Decimal("0.0045")
        commissions = Decimal("0.08710286")
        res = self.verifier.verify_chronological_balances(
            synthetic_txns, self.balances_data, gross_pnl, commissions
        )
        self.assertFalse(res.passed)
        self.assertIn("running balance mismatch", str(res.failure_reason))

    def test_chronological_balances_delta_mismatch_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Ending balance mismatch against expected delta must fail."""
        synthetic_bal = copy.deepcopy(self.balances_data)
        # Change final USD balance
        synthetic_bal["result"][0]["balance"] = "200.0000000"

        gross_pnl = Decimal("0.0045")
        commissions = Decimal("0.08710286")
        res = self.verifier.verify_chronological_balances(
            self.wallet_txns, synthetic_bal, gross_pnl, commissions
        )
        self.assertFalse(res.passed)
        self.assertIn("Final ledger balance", str(res.failure_reason))

    # -------------------------------------------------------------------------
    # 6. Positions & Open Orders Failures
    # -------------------------------------------------------------------------
    def test_positions_non_flat_fails(self):
        """SYNTHETIC_TEST_FIXTURE: Non-zero position size must fail."""
        synthetic_positions = {"BTCUSD": {"size": 1}, "ADAUSD": {"size": 0}}
        res = self.verifier.verify_positions_and_open_orders(
            synthetic_positions, self.balances_data, self.recon_report
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "FAILED_NON_FLAT_POSITION")

    def test_open_orders_unverifiable_when_margin_nonzero(self):
        """SYNTHETIC_TEST_FIXTURE: Non-zero order margin without open orders capture fails."""
        synthetic_bal = copy.deepcopy(self.balances_data)
        synthetic_bal["result"][0]["order_margin"] = "5.0000000"

        res = self.verifier.verify_positions_and_open_orders(
            self.positions_data, synthetic_bal, None, open_orders_data=None
        )
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "BLOCKED_EVIDENCE")

    # -------------------------------------------------------------------------
    # 7. Determinism
    # -------------------------------------------------------------------------
    def test_deterministic_repeated_output(self):
        """Verifies repeated verifications produce identical deterministic outputs."""
        res1 = self.verifier.run_full_reconciliation(phase=169)
        res2 = self.verifier.run_full_reconciliation(phase=169)
        json1 = json.dumps(res1, sort_keys=True)
        json2 = json.dumps(res2, sort_keys=True)
        self.assertEqual(json1, json2)


if __name__ == "__main__":
    unittest.main()
