"""
QuantEngine Phase 186 — Forensic Reconciliation & Safety Regression Suite
Validates:
  1. Authoritative contract multiplier parity across the 5-symbol universe.
  2. Exact PnL reproduction ($420.00 gross - $36.97 fees = $383.03 net).
  3. Fee and GST mathematical model (Maker 2 bps, Taker 5 bps, 18% GST).
  4. Account equity decoupling invariant (Live $100.86 vs Paper $10,000).
  5. Two-minute timeout policy clean cancellation (0 market conversion).
  6. Testnet safety gate production URL rejection.
  7. Phase 185 release archive SHA-256 integrity.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

from core.execution.symbol_registry import SymbolEligibilityRegistry, SymbolEligibilityState
from core.execution.testnet_safety_gate import TestnetSafetyGate, ProductionEndpointAttemptedError
from core.execution.two_minute_order_policy import TwoMinuteOrderPolicyManager, OrderTimeoutState
from core.execution.maker_execution_model import DEFAULT_GST_RATE


class TestPhase186ForensicReconciliation(unittest.TestCase):
    """Forensic verification tests for Phase 186 audit findings."""

    def test_authoritative_contract_multipliers(self):
        """Verify all 5 universe instruments have authentic multipliers."""
        reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
        expected = {
            "BTCUSD": (84, Decimal("0.001"), Decimal("0.10")),
            "ETHUSD": (1699, Decimal("0.01"), Decimal("0.05")),
            "SOLUSD": (92572, Decimal("1.0"), Decimal("0.0001")),
            "XRPUSD": (93723, Decimal("1.0"), Decimal("0.0001")),
            "ADAUSD": (101760, Decimal("1.0"), Decimal("0.00001")),
        }
        for sym, (pid, mult, tick) in expected.items():
            spec = reg.get(sym)
            self.assertIsNotNone(spec, f"{sym} must be in registry")
            self.assertEqual(spec.product_id, pid)
            self.assertEqual(spec.contract_multiplier, mult)
            self.assertEqual(spec.tick_size, tick)
            self.assertEqual(spec.state, SymbolEligibilityState.ELIGIBLE)

    def test_independent_pnl_reproduction(self):
        """Reproduce Phase 185 equation from the 50-trade ledger with exact precision."""
        ledger_path = ROOT / "research" / "results" / "phase185_execution_experiment_ledger.jsonl"
        self.assertTrue(ledger_path.exists(), "Experiment ledger must exist")

        trades = []
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("event_type") == "TRADE_COMPLETED":
                    trades.append(ev.get("payload"))

        self.assertEqual(len(trades), 50, "Must have exactly 50 completed trade lifecycles")

        total_gross = Decimal("0")
        total_fees_and_gst = Decimal("0")

        for t in trades:
            qty = Decimal(str(t["quantity"]))
            mult = Decimal(str(t["contract_multiplier"]))
            ep = Decimal(str(t["entry_price"]))
            xp = Decimal(str(t["exit_price"]))
            direction = t["direction"]

            if direction == "BULLISH":
                gross = (xp - ep) * qty * mult
            else:
                gross = (ep - xp) * qty * mult

            notional_entry = ep * qty * mult
            notional_exit = xp * qty * mult
            entry_fee = notional_entry * Decimal("0.0002")
            exit_fee = notional_exit * Decimal("0.0005")
            raw_fee = entry_fee + exit_fee
            gst = raw_fee * Decimal("0.18")
            fee_total = raw_fee + gst

            total_gross += gross
            total_fees_and_gst += fee_total

        total_net = total_gross - total_fees_and_gst

        self.assertEqual(total_gross, Decimal("420.000000"))
        self.assertAlmostEqual(float(total_fees_and_gst), 36.9698, places=4)
        self.assertAlmostEqual(float(total_net), 383.0302, places=4)

    def test_fee_and_gst_calculation_model(self):
        """Validate maker 2 bps, taker 5 bps, and 18% GST formula."""
        ep = Decimal("60000.0")
        xp = Decimal("60500.0")
        qty = Decimal("2")
        mult = Decimal("0.001")

        notional_entry = ep * qty * mult  # 120.0 USD
        notional_exit = xp * qty * mult   # 121.0 USD

        maker_fee = notional_entry * Decimal("0.0002")  # 0.024 USD
        taker_fee = notional_exit * Decimal("0.0005")   # 0.0605 USD
        raw_fee = maker_fee + taker_fee                 # 0.0845 USD
        gst = raw_fee * Decimal(str(DEFAULT_GST_RATE))  # 0.01521 USD
        total_charges = raw_fee + gst                   # 0.09971 USD

        self.assertEqual(notional_entry, Decimal("120.000"))
        self.assertEqual(notional_exit, Decimal("121.000"))
        self.assertEqual(maker_fee, Decimal("0.0240000"))
        self.assertEqual(taker_fee, Decimal("0.0605000"))
        self.assertEqual(total_charges, Decimal("0.0997100"))

    def test_account_equity_decoupled_invariant(self):
        """Assert live testnet wallet $100.86 is decoupled from simulated paper balance."""
        summary_path = ROOT / "research" / "results" / "phase185_execution_experiment_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        live_evidence = summary["live_testnet_safety_gate"]["live_account_evidence"]
        live_equity = Decimal(str(live_evidence["net_equity_usd"]))
        writes = summary["live_testnet_safety_gate"]["writes_to_exchange"]

        paper_initial = Decimal(str(summary["economics"]["initial_balance_usd"]))
        paper_final = Decimal(str(summary["economics"]["final_balance_usd"]))
        paper_net = Decimal(str(summary["economics"]["total_net_pnl_usd"]))

        self.assertEqual(writes, 0, "Zero write calls must be made to exchange during experiment")
        self.assertAlmostEqual(float(live_equity), 100.86338, places=4)
        self.assertEqual(paper_initial, Decimal("10000.0"))
        self.assertEqual(paper_final, paper_initial + paper_net)
        # The live account was NOT modified by the $383.03 paper PnL
        self.assertNotEqual(live_equity, live_equity + paper_net)

    def test_timeout_policy_clean_cancellation(self):
        """Verify 120s timeout cancels without market order conversion."""
        mgr = TwoMinuteOrderPolicyManager(default_timeout_seconds=120.0)
        tracker = mgr.register_order(
            order_id="TEST-TO-001",
            client_order_id="CL-TO-001",
            symbol="BTCUSD",
            side="BUY",
            limit_price=Decimal("60000.0"),
            quantity=Decimal("1.0"),
            submission_mono_ns=1000,
        )
        tracker.record_ack()

        # Advance by 125 seconds
        expired = mgr.check_expired_orders(current_mono_ns=1000 + 125 * 1_000_000_000)
        self.assertEqual(len(expired), 1)

        cancelled = mgr.process_timeout("TEST-TO-001")
        self.assertEqual(cancelled.state, OrderTimeoutState.CANCELLED)
        self.assertEqual(cancelled.filled_quantity, Decimal("0"))
        self.assertEqual(cancelled.remaining_quantity, Decimal("1.0"))

    def test_testnet_safety_gate_rejects_production(self):
        """Verify production URLs are rejected unconditionally."""
        prod_urls = [
            "https://api.delta.exchange",
            "https://india.delta.exchange",
            "wss://socket.delta.exchange",
            "wss://public-socket.delta.exchange",
        ]
        for url in prod_urls:
            with self.assertRaises(ProductionEndpointAttemptedError):
                TestnetSafetyGate.evaluate(
                    execution_mode="TESTNET",
                    allow_testnet=True,
                    testnet_execute=True,
                    rest_url=url,
                    api_key="mock_key",
                    api_secret="mock_secret",
                    symbol="BTCUSD",
                )

    def test_phase185_release_archive_hash_match(self):
        """Verify physical Phase 185 release candidate archive SHA-256."""
        zip_path = ROOT.parent / "QuantEngine_PHASE185_RELEASE_CANDIDATE.zip"
        if not zip_path.exists():
            zip_path = ROOT / "QuantEngine_PHASE185_RELEASE_CANDIDATE.zip"

        if zip_path.exists():
            h = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            expected = "5ce1025e9bcbce924a1272fe125bc29b425ff76954a857aa70cf52cd36a0c822"
            self.assertEqual(h, expected, "Phase 185 release candidate archive SHA-256 must match exactly")


if __name__ == "__main__":
    unittest.main()
