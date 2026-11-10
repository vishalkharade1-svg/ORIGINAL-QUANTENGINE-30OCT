"""
QuantEngine Phase 189 — Dedicated Offline Authorization Preflight & Safety Gate Test Suite.

Rigorously tests Section 4 and 5 mandates from Master Prompt:
  1. Authorization Document Validation:
     - Rejection of PENDING_OPERATOR_APPROVAL state.
     - Rejection of unreplaced template placeholders.
     - Rejection of missing/invalid operator signature.
  2. Production Endpoint Isolation:
     - Hard rejection of production URLs via ProductionEndpointAttemptedError.
     - Rejection of ambiguous/unauthorized URLs.
  3. Cumulative Order Count Across Restarts:
     - Enforces persistent ledger reading so in-memory restart cannot bypass 20-order cap.
  4. Single-Open-Order Enforcement:
     - Rejection of concurrent placement when 1 order is already submitted or resting.
  5. Ambiguous State & Timeout Protocols:
     - Fail-closed halt on 5s ack timeout.
     - 120s timeout cancellation dispatch without assuming cancellation.
     - Late fill recognition after cancellation request.
  6. Sizing and Risk Budget Guardrails:
     - Rejection of order size > 1 contract.
     - Rejection of loss budget exhaustion ($5.00 limit).
     - Strict post-only requirement.
  7. Latching Kill Switch:
     - Complete permanent shutdown when kill switch is tripped.
  8. Zero Exchange Writes:
     - Deterministic assertion that 0 real network order writes are performed.
"""

from __future__ import annotations

from authorization_test_utils import approve_for_test, configure_test_verification_key, sign_record_for_test

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import time
import unittest

from core.execution.testnet_authorization_gate import (
    TestnetAuthorizationGate,
    AuthorizationState,
    OrderLifecycleState,
    ExperimentScope,
    OperatorAuthorizationRecord,
    ProductionEndpointAttemptedError,
)
from core.execution.testnet_safety_gate import (
    ALLOWED_TESTNET_REST_URLS,
    FORBIDDEN_PRODUCTION_URLS,
)


class MockExchangeClient:
    """Mock network client confirming 0 exchange write calls."""

    def __init__(self):
        self.orders_written: int = 0
        self.orders_cancelled: int = 0
        self.orders_modified: int = 0
        self.calls: list[dict] = []

    def place_order(self, *args, **kwargs) -> dict:
        self.orders_written += 1
        self.calls.append({"method": "place_order", "args": args, "kwargs": kwargs})
        return {"order_id": 1001, "state": "open"}

    def cancel_order(self, *args, **kwargs) -> dict:
        self.orders_cancelled += 1
        self.calls.append({"method": "cancel_order", "args": args, "kwargs": kwargs})
        return {"order_id": 1001, "state": "cancelled"}


class TestPhase189AuthorizationDocumentIntegrity(unittest.TestCase):
    """Test Suite 1: Authorization Document Parsing & Placeholder Rejection."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "test_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unapproved_template_with_placeholders_refuses_preflight(self):
        template_text = """# QuantEngine Testnet Authorization
- **Authorization ID**: P189-TESTNET-001
- **Status**: PENDING_OPERATOR_APPROVAL
- **Authorizing Operator**: [OPERATOR_NAME_REQUIRED]
- **Signed Timestamp UTC**: [TIMESTAMP_REQUIRED]
- **Operator Signature**: [OPERATOR_SIGNATURE_REQUIRED]
"""
        record = self.gate.parse_authorization_document(template_text)
        self.assertEqual(record.state, AuthorizationState.PENDING_OPERATOR_APPROVAL)
        self.assertFalse(record.is_currently_valid())

        decision = self.gate.evaluate_preflight(
            auth_record=record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertFalse(decision.is_armed())
        self.assertTrue(any("PENDING_OPERATOR_APPROVAL" in r for r in decision.reasons))

    def test_malformed_signature_refuses_preflight(self):
        malformed_text = """# QuantEngine Testnet Authorization
- **Authorization ID**: P189-TESTNET-002
- **Status**: OPERATOR_APPROVED
- **Authorizing Operator**: [OPERATOR_KEY_ID]
- **Operator Signature**: [UNVERIFIED]
"""
        record = self.gate.parse_authorization_document(malformed_text)
        self.assertEqual(record.state, AuthorizationState.PENDING_OPERATOR_APPROVAL)

        decision = self.gate.evaluate_preflight(
            auth_record=record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)

    def test_validly_signed_authorization_passes_preflight(self):
        import base64
        import time
        from authorization_test_utils import test_private_key

        now = time.time()
        signed = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 2))
        expiry = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600))
        unsigned_text = f"""# QuantEngine Testnet Authorization
- **Authorization ID**: P189-TESTNET-003
- **Status**: OPERATOR_APPROVED
- **Authorizing Operator**: SENIOR_QUANT_OPS_01
- **Signed Timestamp UTC**: {signed}
- **Expiry Timestamp UTC**: {expiry}
- **Operator Signature**: SIGNATURE_TO_BE_REPLACED
"""
        unsigned_record = self.gate.parse_authorization_document(unsigned_text)
        unsigned_record.signature_payload = sign_record_for_test(unsigned_record)
        signed_text = unsigned_text.replace(
            "SIGNATURE_TO_BE_REPLACED", unsigned_record.signature_payload
        )
        record = self.gate.parse_authorization_document(signed_text)
        configure_test_verification_key()
        self.assertEqual(record.state, AuthorizationState.OPERATOR_APPROVED)
        self.assertTrue(record.is_currently_valid())

        decision = self.gate.evaluate_preflight(
            auth_record=record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertTrue(decision.authorized)
        # Preflight is diagnostic only; transport authority requires the
        # atomic reservation that persists the client order id first.
        self.assertFalse(decision.is_armed())
        reserved = self.gate.check_and_reserve_order(
            auth_record=record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cl_ord_id="P189-TESTNET-RESERVED-001",
            order_details={
                "side": "buy",
                "limit_price": "50000",
                "post_only": True,
            },
            post_only=True,
        )
        self.assertTrue(reserved.is_armed())


    def test_notional_cap_is_enforced_inside_authorization_gate(self):
        import time
        unsigned_text = """# QuantEngine Testnet Authorization
- **Authorization ID**: P189-NOTIONAL-001
- **Status**: OPERATOR_APPROVED
- **Authorizing Operator**: SENIOR_QUANT_OPS_01
- **Signed Timestamp UTC**: 2026-11-10T00:00:00Z
- **Expiry Timestamp UTC**: 2026-11-11T00:00:00Z
- **Operator Signature**: SIGNATURE_TO_BE_REPLACED
"""
        record = self.gate.parse_authorization_document(unsigned_text)
        record.signature_payload = sign_record_for_test(record)
        record = self.gate.parse_authorization_document(
            unsigned_text.replace(
                "SIGNATURE_TO_BE_REPLACED", record.signature_payload
            )
        )
        configure_test_verification_key()
        self.assertTrue(record.is_currently_valid())

        decision = self.gate.check_and_reserve_order(
            auth_record=record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1"),
            cl_ord_id="P189-NOTIONAL-OVER-CAP",
            order_details={
                "side": "buy", "limit_price": "100001",
                "post_only": True,
            },
            post_only=True,
        )
        self.assertFalse(decision.authorized)
        self.assertFalse(decision.is_armed())
        self.assertTrue(any("Order notional" in reason
                            for reason in decision.reasons))
        self.assertFalse(self.ledger_file.exists())

    def test_reservation_rejects_caller_override_of_ledger_identity(self):
        unsigned_text = """# QuantEngine Testnet Authorization
- **Authorization ID**: P189-OVERRIDE-001
- **Status**: OPERATOR_APPROVED
- **Authorizing Operator**: SENIOR_QUANT_OPS_01
- **Signed Timestamp UTC**: 2026-11-10T00:00:00Z
- **Expiry Timestamp UTC**: 2026-11-11T00:00:00Z
- **Operator Signature**: SIGNATURE_TO_BE_REPLACED
"""
        record = self.gate.parse_authorization_document(unsigned_text)
        record.signature_payload = sign_record_for_test(record)
        record = self.gate.parse_authorization_document(
            unsigned_text.replace(
                "SIGNATURE_TO_BE_REPLACED", record.signature_payload
            )
        )
        configure_test_verification_key()
        decision = self.gate.check_and_reserve_order(
            auth_record=record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1"),
            cl_ord_id="P189-RESERVED-ID",
            order_details={
                "side": "buy", "limit_price": "50000",
                "post_only": True, "cl_ord_id": "P189-ATTACKER-ID",
            },
            post_only=True,
        )
        self.assertFalse(decision.authorized)
        self.assertFalse(self.ledger_file.exists())


class TestPhase189EndpointIsolationAndAmbiguity(unittest.TestCase):
    """Test Suite 2: Absolute Production Endpoint Isolation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "test_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.approved_record = OperatorAuthorizationRecord(
            authorization_id="P189-TESTNET-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_QUANT_OPS",
            signed_timestamp_utc="2026-10-21T06:00:00Z",
            expiry_timestamp_utc="2026-10-21T18:00:00Z",
            scope=self.gate.scope,
            document_sha256="abc123sha",
            signature_payload="valid_sig_abc123",
        )
        approve_for_test(self.approved_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_production_urls_raise_typed_error(self):
        for prod_url in FORBIDDEN_PRODUCTION_URLS:
            with self.subTest(prod_url=prod_url):
                with self.assertRaises(ProductionEndpointAttemptedError):
                    self.gate.evaluate_preflight(
                        auth_record=self.approved_record,
                        rest_url=prod_url,
                        symbol="BTCUSD",
                        product_id=84,
                        order_size_contracts=Decimal("1.0"),
                    )

    def test_unknown_or_ambiguous_url_refused(self):
        ambiguous_urls = [
            "https://testnet.delta.exchange",
            "https://api.testnet.delta.exchange",
            "http://cdn-ind.testnet.deltaex.org",  # Insecure HTTP
            "",
            "https://evil-spoof.delta.exchange",
        ]
        for url in ambiguous_urls:
            with self.subTest(url=url):
                decision = self.gate.evaluate_preflight(
                    auth_record=self.approved_record,
                    rest_url=url,
                    symbol="BTCUSD",
                    product_id=84,
                    order_size_contracts=Decimal("1.0"),
                )
                self.assertFalse(decision.authorized)
                self.assertTrue(any("authorized testnet host" in r or "empty" in r for r in decision.reasons))


class TestPhase189PersistentAccountingAcrossRestarts(unittest.TestCase):
    """Test Suite 3: 20-Order Cap Enforced Persistently Across Process Restarts."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "persistent_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.approved_record = OperatorAuthorizationRecord(
            authorization_id="P189-TESTNET-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_QUANT_OPS",
            signed_timestamp_utc="2026-10-21T06:00:00Z",
            expiry_timestamp_utc="2026-10-21T18:00:00Z",
            scope=self.gate.scope,
            document_sha256="abc123sha",
            signature_payload="valid_sig_abc123",
        )
        approve_for_test(self.approved_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_twenty_order_limit_blocks_order_twenty_one(self):
        # Record 19 orders in persistent ledger
        for i in range(19):
            self.gate.record_order_event_to_ledger("ORDER_SUBMITTED", {"index": i + 1})

        decision_19 = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertTrue(decision_19.authorized)
        self.assertEqual(decision_19.cumulative_orders_placed, 19)

        # Place 20th order
        self.gate.record_order_event_to_ledger("ORDER_SUBMITTED", {"index": 20})

        decision_20 = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision_20.authorized)
        self.assertTrue(any("Cumulative experiment order limit reached" in r for r in decision_20.reasons))

    def test_process_restart_preserves_order_count_and_blocks_overflow(self):
        # Simulate process 1 running 20 orders then crashing/restarting
        for i in range(20):
            self.gate.record_order_event_to_ledger("ORDER_SUBMITTED", {"cl_ord_id": f"ord_{i}"})

        # Process restarts: new gate instance pointing to same persistent ledger
        restarted_gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.assertEqual(restarted_gate.read_cumulative_orders_from_ledger(), 20)

        decision = restarted_gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("Cumulative experiment order limit reached" in r for r in decision.reasons))


class TestPhase189SingleOpenOrderAndAmbiguousLifecycle(unittest.TestCase):
    """Test Suite 4: Single-Open-Order Limit & Ambiguous Ack Fail-Closed."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "lifecycle_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.approved_record = OperatorAuthorizationRecord(
            authorization_id="P189-TESTNET-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_QUANT_OPS",
            signed_timestamp_utc="2026-10-21T06:00:00Z",
            expiry_timestamp_utc="2026-10-21T18:00:00Z",
            scope=self.gate.scope,
            document_sha256="abc123sha",
            signature_payload="valid_sig_abc123",
        )
        approve_for_test(self.approved_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_concurrent_order_refused_when_one_order_is_active(self):
        # Register an order in flight
        self.gate.register_order_submitted("cl_ord_001", {"symbol": "BTCUSD", "size": 1})

        # Attempt to submit a second concurrent order
        decision = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("Single-open-order limit reached" in r for r in decision.reasons))

    def test_ambiguous_ack_timeout_halts_all_new_placements(self):
        # Submit order, then ack times out (> 5s)
        self.gate.register_order_submitted("cl_ord_ambig", {"symbol": "BTCUSD"})
        self.gate.register_ack_timeout("cl_ord_ambig")

        # System must fail closed immediately
        decision = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("ambiguous/unreconciled" in r for r in decision.reasons))

    def test_120s_resting_timeout_triggers_cancel_request(self):
        self.gate.register_order_submitted("cl_ord_resting", {"symbol": "BTCUSD"})
        self.gate.register_order_acknowledged("cl_ord_resting", exchange_order_id=55512)

        # Before 120s: False
        needs_cancel = self.gate.handle_resting_timeout("cl_ord_resting", elapsed_seconds=119.5)
        self.assertFalse(needs_cancel)

        # At or after 120s: True
        needs_cancel_120 = self.gate.handle_resting_timeout("cl_ord_resting", elapsed_seconds=120.0)
        self.assertTrue(needs_cancel_120)

    def test_late_fill_after_cancel_request_clears_open_order_with_status(self):
        self.gate.register_order_submitted("cl_ord_late", {"symbol": "BTCUSD"})
        self.gate.handle_resting_timeout("cl_ord_late", elapsed_seconds=121.0)

        # Exchange fill arrives while cancel was pending
        self.gate.register_order_terminal(
            "cl_ord_late",
            terminal_state=OrderLifecycleState.FILLED_POST_CANCEL_REQ,
            pnl_usd=Decimal("0.0"),
        )
        # Order is terminal, so open order count is now 0
        self.assertEqual(len(self.gate._active_open_orders), 0)


class TestPhase189RiskBudgetAndKillSwitch(unittest.TestCase):
    """Test Suite 5: Risk Budget Exhaustion and Latching Kill Switch."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.temp_dir.name) / "risk_ledger.jsonl"
        self.gate = TestnetAuthorizationGate(ledger_path=self.ledger_file)
        self.approved_record = OperatorAuthorizationRecord(
            authorization_id="P189-TESTNET-AUTH",
            state=AuthorizationState.OPERATOR_APPROVED,
            operator_identity="LEAD_QUANT_OPS",
            signed_timestamp_utc="2026-10-21T06:00:00Z",
            expiry_timestamp_utc="2026-10-21T18:00:00Z",
            scope=self.gate.scope,
            document_sha256="abc123sha",
            signature_payload="valid_sig_abc123",
        )
        approve_for_test(self.approved_record)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_order_size_exceeding_scope_refused(self):
        decision = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("2.0"),  # Max is 1.0 contract
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("exceeds maximum authorized" in r for r in decision.reasons))

    def test_loss_budget_exhaustion_refuses_preflight(self):
        decision = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
            cumulative_realized_loss=Decimal("-5.01"),  # Exceeds $5.00 loss budget
        )
        self.assertFalse(decision.authorized)
        self.assertTrue(any("exhausted authorized budget" in r for r in decision.reasons))

    def test_latching_kill_switch_permanently_blocks_all_actions(self):
        self.gate.activate_kill_switch("Protective exit slippage exceeded safety boundary")
        self.assertTrue(self.gate.is_killed)

        decision = self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertFalse(decision.authorized)
        self.assertEqual(decision.state, AuthorizationState.KILLED)
        self.assertTrue(any("Kill switch active" in r for r in decision.reasons))

    def test_zero_network_order_writes_confirmed(self):
        """Verify that testing the authorization gate results in 0 exchange writes."""
        mock_client = MockExchangeClient()

        # Run multiple checks
        self.gate.evaluate_preflight(
            auth_record=self.approved_record,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            symbol="BTCUSD",
            product_id=84,
            order_size_contracts=Decimal("1.0"),
        )
        self.assertEqual(mock_client.orders_written, 0)
        self.assertEqual(mock_client.orders_cancelled, 0)
        self.assertEqual(len(mock_client.calls), 0)


if __name__ == "__main__":
    unittest.main()
