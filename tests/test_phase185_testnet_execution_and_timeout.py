"""
====================================================
QuantEngine - Phase 185 Testnet Execution & Timeout Tests
Phase 185 Verification Suite

Covers:
  1. Testnet vs. Production Endpoint Isolation & Safety Gate
  2. Credential Separation & Production Re-use Prohibition
  3. Symbol Eligibility Registry & Lifecycle Transitions
  4. Multi-Symbol Contract Specification & Multiplier Authority
  5. 120-Second Monotonic Order Timeout Policy & Cancellation
  6. Partial Fill Handling & Remaining-Quantity Cancellation
  7. Fill vs. Cancel Race-Condition Reconciliation
  8. Unknown Order State Isolation & Symbol Halt Enforcement
  9. Zero Network/Adapter Calls on Rejection Paths
====================================================
"""

from decimal import Decimal
import os
import pytest
import time

from core.execution.testnet_safety_gate import (
    TestnetSafetyGate,
    TestnetSafetyDecision,
    ProductionEndpointAttemptedError,
    TestnetBlockedError,
    TestnetConfigurationError,
    ALLOWED_TESTNET_REST_URLS,
    FORBIDDEN_PRODUCTION_URLS,
)
from core.execution.symbol_registry import (
    SymbolEligibilityRegistry,
    SymbolEligibilityState,
    InstrumentSpecification,
)
from core.execution.two_minute_order_policy import (
    TwoMinuteOrderPolicyManager,
    OrderTimeoutState,
    MonotonicOrderTracker,
)
from core.paper_trading.queue_aware_paper_engine import (
    QueueAwarePaperExecutionEngine,
    PaperOrderState,
    QueueScenario,
)
from core.execution.maker_execution_model import InstrumentMetadata


class TestTestnetSafetyGateIsolation:
    """Verifies strict production isolation and fail-closed safety gate checks."""

    def test_production_rest_endpoints_raise_typed_critical_error(self):
        """Production REST URLs must immediately raise ProductionEndpointAttemptedError."""
        for prod_url in FORBIDDEN_PRODUCTION_URLS:
            with pytest.raises(ProductionEndpointAttemptedError):
                TestnetSafetyGate.evaluate(
                    execution_mode="TESTNET",
                    allow_testnet=True,
                    testnet_execute=True,
                    rest_url=prod_url,
                    api_key="testnet_key_123",
                    api_secret="testnet_secret_abc",
                    symbol="BTCUSD",
                )

    def test_unauthorized_external_endpoints_rejected(self):
        """Unknown or arbitrary endpoints must be rejected."""
        decision = TestnetSafetyGate.evaluate(
            execution_mode="TESTNET",
            allow_testnet=True,
            testnet_execute=True,
            rest_url="https://api.binance.com",
            api_key="testnet_key_123",
            api_secret="testnet_secret_abc",
            symbol="BTCUSD",
        )
        assert not decision.allowed
        assert any("not an authorized testnet host" in r for r in decision.reasons)

    def test_valid_testnet_endpoint_and_credentials_armed(self):
        """Authorized testnet endpoint with valid params mints an armed decision."""
        decision = TestnetSafetyGate.evaluate(
            execution_mode="TESTNET",
            allow_testnet=True,
            testnet_execute=True,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            api_key="testnet_key_123",
            api_secret="testnet_secret_abc",
            symbol="BTCUSD",
            entry_price=Decimal("65000.0"),
            stop_price=Decimal("64000.0"),
            target_price=Decimal("67000.0"),
            risk_budget=Decimal("100.0"),
            total_risk=Decimal("50.0"),
            direction="BULLISH",
            reconciliation_ok=True,
        )
        assert decision.allowed
        assert decision.is_armed()
        TestnetSafetyGate.require_armed(decision)

    def test_missing_credentials_refused_fail_closed(self):
        """Empty or missing credentials must refuse execution."""
        decision = TestnetSafetyGate.evaluate(
            execution_mode="TESTNET",
            allow_testnet=True,
            testnet_execute=True,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            api_key="",
            api_secret="",
            symbol="BTCUSD",
        )
        assert not decision.allowed
        assert not decision.is_armed()
        with pytest.raises(TestnetBlockedError):
            TestnetSafetyGate.require_armed(decision)

    def test_production_credential_reuse_prohibited(self, monkeypatch):
        """Reusing DELTA_API_KEY as testnet key must fail closed."""
        monkeypatch.setenv("DELTA_API_KEY", "prod_secret_key_999")
        decision = TestnetSafetyGate.evaluate(
            execution_mode="TESTNET",
            allow_testnet=True,
            testnet_execute=True,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            api_key="prod_secret_key_999",
            api_secret="some_secret",
            symbol="BTCUSD",
        )
        assert not decision.allowed
        assert any("Production DELTA_API_KEY cannot be reused" in r for r in decision.reasons)

    def test_invalid_direction_geometry_rejected(self):
        """Bullish with stop >= entry or target <= entry must be rejected."""
        decision = TestnetSafetyGate.evaluate(
            execution_mode="TESTNET",
            allow_testnet=True,
            testnet_execute=True,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            api_key="testnet_k",
            api_secret="testnet_s",
            symbol="BTCUSD",
            entry_price=Decimal("65000.0"),
            stop_price=Decimal("66000.0"),  # invalid stop above entry for long
            direction="BULLISH",
        )
        assert not decision.allowed
        assert any("Invalid Long geometry" in r for r in decision.reasons)

    def test_risk_budget_breach_rejected(self):
        """Total risk exceeding risk budget must be refused."""
        decision = TestnetSafetyGate.evaluate(
            execution_mode="TESTNET",
            allow_testnet=True,
            testnet_execute=True,
            rest_url="https://cdn-ind.testnet.deltaex.org",
            api_key="testnet_k",
            api_secret="testnet_s",
            symbol="BTCUSD",
            risk_budget=Decimal("50.0"),
            total_risk=Decimal("75.0"),
        )
        assert not decision.allowed
        assert any("exceeds risk budget" in r for r in decision.reasons)


class TestSymbolEligibilityRegistry:
    """Verifies symbol discovery, verification lifecycle, and metadata lookup."""

    def test_authoritative_registry_contains_verified_symbols(self):
        """Registry pre-populates verified liquid contracts in ELIGIBLE state."""
        reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
        eligible = reg.list_eligible()
        assert "BTCUSD" in eligible
        assert "ETHUSD" in eligible
        assert "SOLUSD" in eligible
        assert "XRPUSD" in eligible
        assert "ADAUSD" in eligible

    def test_btcusd_spec_matches_product_id_84(self):
        """Product ID 84 BTCUSD contract multiplier is verified 0.001."""
        reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
        btc = reg.get("BTCUSD")
        assert btc is not None
        assert btc.product_id == 84
        assert btc.contract_multiplier == Decimal("0.001")
        assert btc.tick_size == Decimal("0.10")
        assert btc.state == SymbolEligibilityState.ELIGIBLE

    def test_ethusd_spec_matches_product_id_1699(self):
        """Product ID 1699 ETHUSD contract multiplier is verified 0.01."""
        reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
        eth = reg.get("ETHUSD")
        assert eth is not None
        assert eth.product_id == 1699
        assert eth.contract_multiplier == Decimal("0.01")
        assert eth.tick_size == Decimal("0.05")
        assert eth.state == SymbolEligibilityState.ELIGIBLE

    def test_solusd_spec_matches_product_id_92572(self):
        """Product ID 92572 SOLUSD contract multiplier is verified 1.0."""
        reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
        sol = reg.get("SOLUSD")
        assert sol is not None
        assert sol.product_id == 92572
        assert sol.contract_multiplier == Decimal("1.0")
        assert sol.tick_size == Decimal("0.0001")
        assert sol.state == SymbolEligibilityState.ELIGIBLE

    def test_unverified_candidates_cannot_be_retrieved_as_eligible_metadata(self):
        """High multiplier / synthetic perp candidates cannot return metadata until ELIGIBLE."""
        reg = SymbolEligibilityRegistry.create_phase185_authoritative_registry()
        doge = reg.get("DOGEUSD")
        assert doge.state == SymbolEligibilityState.RISK_VERIFIED
        with pytest.raises(ValueError, match="not ELIGIBLE"):
            reg.get_metadata("DOGEUSD")

        qqq = reg.get("QQQXUSD")
        assert qqq.state == SymbolEligibilityState.BLOCKED_EVIDENCE
        with pytest.raises(ValueError, match="not ELIGIBLE"):
            reg.get_metadata("QQQXUSD")

    def test_lifecycle_state_transition(self):
        """Registry records lifecycle state transitions and reasons."""
        reg = SymbolEligibilityRegistry()
        spec = InstrumentSpecification(
            symbol="TESTUSD",
            product_id=99999,
            contract_type="perpetual_futures",
            contract_multiplier=Decimal("1.0"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            state=SymbolEligibilityState.DISCOVERED,
        )
        reg.register(spec)
        assert not reg.is_eligible("TESTUSD")

        reg.transition("TESTUSD", SymbolEligibilityState.METADATA_VERIFIED, "Checked REST API")
        assert reg.get("TESTUSD").state == SymbolEligibilityState.METADATA_VERIFIED

        reg.transition("TESTUSD", SymbolEligibilityState.ELIGIBLE, "All safety gates passed")
        assert reg.is_eligible("TESTUSD")
        meta = reg.get_metadata("TESTUSD")
        assert meta.symbol == "TESTUSD"
        assert meta.contract_multiplier == Decimal("1.0")


class TestTwoMinuteOrderPolicy:
    """Verifies 120-second monotonic timeout, cancellation, partial fills, and race conditions."""

    def test_order_timeout_lifecycle_in_policy_manager(self):
        """Order resting past 120s monotonic expires and cancels cleanly."""
        mgr = TwoMinuteOrderPolicyManager(default_timeout_seconds=120.0)
        base_mono = 100_000_000_000  # 100s

        tracker = mgr.register_order(
            order_id="test_ord_1",
            client_order_id="cl_1",
            symbol="BTCUSD",
            side="BUY",
            limit_price=Decimal("65000.0"),
            quantity=Decimal("10"),
            submission_mono_ns=base_mono,
        )
        assert tracker.state == OrderTimeoutState.SUBMITTED

        tracker.record_ack()
        assert tracker.state == OrderTimeoutState.RESTING

        # At 60s elapsed: not timed out
        expired = mgr.check_expired_orders(current_mono_ns=base_mono + 60 * 1_000_000_000)
        assert len(expired) == 0
        assert not tracker.is_terminal()

        # At 121s elapsed: timed out
        expired = mgr.check_expired_orders(current_mono_ns=base_mono + 121 * 1_000_000_000)
        assert len(expired) == 1
        assert expired[0].order_id == "test_ord_1"
        assert expired[0].state == OrderTimeoutState.TIMED_OUT

        # Execute timeout cancel
        cancelled = mgr.process_timeout("test_ord_1")
        assert cancelled.state == OrderTimeoutState.CANCELLED
        assert cancelled.is_terminal()

    def test_partial_fill_before_timeout_cancels_only_remaining(self):
        """When an order has partially filled, timeout cancels only remaining quantity."""
        mgr = TwoMinuteOrderPolicyManager(default_timeout_seconds=120.0)
        base_mono = 100_000_000_000

        tracker = mgr.register_order(
            order_id="test_ord_2",
            client_order_id="cl_2",
            symbol="ETHUSD",
            side="BUY",
            limit_price=Decimal("3000.0"),
            quantity=Decimal("20"),
            submission_mono_ns=base_mono,
        )
        tracker.record_ack()

        # Partial fill of 8 contracts
        tracker.record_fill(qty=Decimal("8"), fill_price=Decimal("3000.0"))
        assert tracker.state == OrderTimeoutState.PARTIALLY_FILLED
        assert tracker.filled_quantity == Decimal("8")
        assert tracker.remaining_quantity == Decimal("12")

        # Cancel remaining at timeout
        cancelled_qty_received = []

        def mock_cancel_adapter(order_id: str, remaining_qty: Decimal) -> bool:
            cancelled_qty_received.append(remaining_qty)
            return True

        mgr.process_timeout("test_ord_2", cancel_adapter_func=mock_cancel_adapter)
        assert tracker.state == OrderTimeoutState.CANCELLED
        assert cancelled_qty_received == [Decimal("12")]
        assert tracker.filled_quantity == Decimal("8")  # filled quantity preserved!

    def test_fill_vs_cancel_race_condition_reconciliation(self):
        """If fill arrived during cancel request, reconciles filled quantity without fabricating."""
        mgr = TwoMinuteOrderPolicyManager(default_timeout_seconds=120.0)
        tracker = mgr.register_order(
            order_id="test_ord_race",
            client_order_id="cl_race",
            symbol="SOLUSD",
            side="BUY",
            limit_price=Decimal("150.0"),
            quantity=Decimal("5"),
        )
        tracker.record_ack()
        tracker.record_cancel_request()
        assert tracker.state == OrderTimeoutState.CANCEL_REQUESTED

        # Exchange reports that before cancel took effect, full fill executed!
        reconciled = mgr.reconcile_fill_and_cancel_race(
            order_id="test_ord_race",
            exchange_cumulative_filled=Decimal("5"),
            exchange_fill_price=Decimal("150.0"),
            exchange_status="FILLED",
        )
        assert reconciled.state == OrderTimeoutState.FILLED
        assert reconciled.filled_quantity == Decimal("5")
        assert reconciled.remaining_quantity == Decimal("0")

    def test_unknown_cancel_state_halts_symbol(self):
        """Adapter failure on cancel transitions order to UNKNOWN_RECONCILING and halts symbol."""
        mgr = TwoMinuteOrderPolicyManager(default_timeout_seconds=120.0)
        tracker = mgr.register_order(
            order_id="test_ord_fail",
            client_order_id="cl_fail",
            symbol="BTCUSD",
            side="BUY",
            limit_price=Decimal("65000.0"),
            quantity=Decimal("1"),
        )
        assert not mgr.is_symbol_halted("BTCUSD")

        def failing_adapter(order_id: str, qty: Decimal) -> bool:
            return False  # adapter could not confirm cancel

        mgr.process_timeout("test_ord_fail", cancel_adapter_func=failing_adapter)
        assert tracker.state == OrderTimeoutState.UNKNOWN_RECONCILING
        assert mgr.is_symbol_halted("BTCUSD")

        # Attempting new order for halted symbol must raise
        with pytest.raises(RuntimeError, match="halted symbol"):
            mgr.register_order(
                order_id="test_ord_blocked",
                client_order_id="cl_b",
                symbol="BTCUSD",
                side="BUY",
                limit_price=Decimal("65000.0"),
                quantity=Decimal("1"),
            )


class TestQueueAwarePaperEngineTimeoutIntegration:
    """Verifies timeout policy integration inside QueueAwarePaperExecutionEngine."""

    def test_paper_engine_cancels_timed_out_resting_order(self):
        """Paper engine check_order_timeouts cancels resting order after 120s monotonic."""
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        base_mono = 50_000_000_000

        order = engine.submit_candidate_trade(
            order_id="ord_paper_to_1",
            symbol="BTCUSD",
            side="BUY",
            entry_price="65000.0",
            stop_price="64000.0",
            target_price="67000.0",
            quantity="1",
            risk_budget="100.0",
            best_bid="65000.0",
            best_ask="65000.1",
            queue_ahead_estimate="50",
            timeout_seconds=120.0,
            submission_mono_ns=base_mono,
        )
        assert order.state == PaperOrderState.RESTING
        assert "ord_paper_to_1" in engine.active_orders

        # Check at 60s: not timed out
        cancelled = engine.check_order_timeouts(current_mono_ns=base_mono + 60 * 1_000_000_000)
        assert len(cancelled) == 0
        assert "ord_paper_to_1" in engine.active_orders

        # Check at 121s: timed out and cancelled without converting to market order
        cancelled = engine.check_order_timeouts(current_mono_ns=base_mono + 121 * 1_000_000_000)
        assert len(cancelled) == 1
        assert cancelled[0].order_id == "ord_paper_to_1"
        assert cancelled[0].state == PaperOrderState.CANCELLED
        assert "ord_paper_to_1" not in engine.active_orders
        assert "ord_paper_to_1" in engine.completed_orders

    def test_paper_engine_authoritative_metadata_lookup_for_ethusd(self):
        """Paper engine uses SymbolEligibilityRegistry for ETHUSD (mult=0.01, tick=0.05)."""
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        order = engine.submit_candidate_trade(
            order_id="ord_eth_1",
            symbol="ETHUSD",
            side="BUY",
            entry_price="3000.0",
            stop_price="2900.0",
            target_price="3200.0",
            quantity="10",
            risk_budget="50.0",
            best_bid="3000.0",
            best_ask="3000.1",
            queue_ahead_estimate="20",
        )
        assert order.multiplier == Decimal("0.01")
        assert order.tick_size == Decimal("0.05")
        assert order.state == PaperOrderState.RESTING

    def test_no_adapter_invocations_on_refused_paths(self):
        """Engine proves 0 live adapter calls even when orders are refused."""
        engine = QueueAwarePaperExecutionEngine()
        # Invalid risk order
        order = engine.submit_candidate_trade(
            order_id="ord_bad_risk",
            symbol="BTCUSD",
            side="BUY",
            entry_price="65000.0",
            stop_price="64000.0",
            target_price="67000.0",
            quantity="1000",  # huge quantity breaches 100 USD budget
            risk_budget="10.0",
            best_bid="65000.0",
            best_ask="65000.1",
        )
        assert order.state == PaperOrderState.REJECTED_RISK
        assert engine.assert_no_live_adapter_invocation()
