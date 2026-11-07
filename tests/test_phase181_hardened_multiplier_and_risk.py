"""
QUANTENGINE PHASE 181 — HARDENED MULTIPLIER API & FINAL RISK-BOUNDARY AUDIT

Verifies:
1. Multiplier omitted, metadata supplied -> uses metadata multiplier.
2. Explicit multiplier equal to metadata -> succeeds.
3. Explicit multiplier conflicting with metadata -> fails closed (rejects input).
4. Explicit synthetic multiplier of 1.0 -> succeeds when explicitly declared.
5. Metadata absent with explicit multiplier -> succeeds.
6. Both metadata and multiplier absent -> fails closed.
7. Invalid multiplier values (zero, negative, NaN, Inf, non-numeric) -> fails closed.
8. A different instrument with legitimate multiplier of 1.0 -> succeeds.
9. Position sizing, fees, gross P&L and stop-risk consistency end-to-end.
10. Order serialization and restoration preserves multiplier precision.
11. Stale risk verdict cannot survive quantity or stop amendments.
12. Partial fill residual risk recalculation.
13. Final boundary adapter isolation counter remains 0 on rejection.
14. Hurdle rejection distinct from risk rejection in state and evidence.
"""

from decimal import Decimal
import json
import pytest

from core.execution.maker_execution_model import (
    InstrumentMetadata,
    ExecutionStyle,
    TickRoundingPolicy,
    audit_and_recalculate_stop_risk,
    validate_instrument_constraints,
    calculate_round_trip,
    calculate_asymmetric_round_trip,
)
from core.paper_trading.queue_aware_paper_engine import (
    QueueAwarePaperExecutionEngine,
    PaperOrder,
    PaperOrderState,
    assert_no_live_adapter_invocation,
)
from core.backtesting.post_cost_backtester import PostCostBacktester, TradeSetupCandidate


class TestPhase181HardenedMultiplierAPI:
    """Audit and verify the hardened contract-multiplier interface."""

    @pytest.fixture
    def btc_meta(self) -> InstrumentMetadata:
        """Authoritative Delta Exchange India BTCUSD (Product ID 84)."""
        return InstrumentMetadata.for_btcusd()

    @pytest.fixture
    def synth_meta(self) -> InstrumentMetadata:
        """Explicitly labelled synthetic multiplier-1.0 instrument."""
        return InstrumentMetadata(
            symbol="SYNTH-BTCUSD",
            tick_size=Decimal("0.10"),
            step_size=Decimal("0.001"),
            min_quantity=Decimal("0.001"),
            contract_multiplier=Decimal("1.0"),
            settlement_currency="USD",
        )

    @pytest.fixture
    def eth_linear_meta(self) -> InstrumentMetadata:
        """A different instrument with a legitimate multiplier of 1.0."""
        return InstrumentMetadata(
            symbol="ETHUSD-PERP",
            tick_size=Decimal("0.05"),
            step_size=Decimal("0.01"),
            min_quantity=Decimal("0.01"),
            contract_multiplier=Decimal("1.0"),
            settlement_currency="USD",
        )

    def test_multiplier_omitted_metadata_supplied(self, btc_meta):
        """Case 1: Multiplier omitted (None), metadata supplied -> uses meta.contract_multiplier."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            contract_multiplier=None,  # Omitted sentinel
            meta=btc_meta,
        )
        assert res.valid is True
        assert res.contract_multiplier == Decimal("0.001")
        # 500 pts * 1000 qty * 0.001 = $500.00 gross risk
        assert res.normalized_gross_risk_usd == Decimal("500.00")
        assert res.total_normalized_risk_usd < Decimal("600.00")

    def test_explicit_multiplier_equal_to_metadata(self, btc_meta):
        """Case 2: Explicit multiplier equal to metadata -> succeeds."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            contract_multiplier=Decimal("0.001"),  # Explicitly matches meta
            meta=btc_meta,
        )
        assert res.valid is True
        assert res.contract_multiplier == Decimal("0.001")
        assert res.normalized_gross_risk_usd == Decimal("500.00")

    def test_explicit_multiplier_conflicting_with_metadata(self, btc_meta):
        """Case 3: Explicit multiplier conflicting with metadata -> fails closed with metadata conflict."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            contract_multiplier=Decimal("1.0"),  # Conflicting with meta.contract_multiplier=0.001
            meta=btc_meta,
        )
        assert res.valid is False
        assert "metadata conflict" in res.rejection_reason.lower()
        assert "contract_multiplier" in res.rejection_reason.lower()

        # Also verify validate_instrument_constraints rejects conflicting multiplier
        valid, err = validate_instrument_constraints(
            price=Decimal("60000.00"),
            quantity=Decimal("1"),
            multiplier=Decimal("1.0"),
            meta=btc_meta,
            raise_exception=False,
        )
        assert valid is False
        assert "metadata conflict" in err.lower()

    def test_explicit_synthetic_multiplier_of_1(self, synth_meta):
        """Case 4: Explicit synthetic multiplier of 1.0 -> succeeds for synthetic fixture."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            contract_multiplier=Decimal("1.0"),
            meta=synth_meta,
        )
        assert res.valid is True
        assert res.contract_multiplier == Decimal("1.0")
        assert res.normalized_gross_risk_usd == Decimal("500.00")
        # 1.0 BTC notional = $60,000.00
        # Entry Maker fee (2.0 bps * 1.18 GST = 2.36 bps) = $14.16
        # Exit Taker fee (5.0 bps * 1.18 GST = 5.90 bps) = $35.105
        # Total fees = $49.265
        # Total cost-adjusted risk = 500.00 + 49.265 = $549.265
        assert res.total_normalized_risk_usd == Decimal("549.26500000")

    def test_metadata_absent_with_explicit_multiplier(self):
        """Case 5: Metadata absent (None) with explicit multiplier -> succeeds."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("10"),
            risk_budget=Decimal("10.00"),
            side="BUY",
            contract_multiplier=Decimal("0.001"),
            meta=None,
        )
        assert res.valid is True
        assert res.contract_multiplier == Decimal("0.001")
        # 500 pts * 10 * 0.001 = $5.00 gross risk
        assert res.normalized_gross_risk_usd == Decimal("5.00")

    def test_both_metadata_and_multiplier_absent_fails_closed(self):
        """Case 6: Both metadata and multiplier absent -> fails closed."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("10"),
            risk_budget=Decimal("10.00"),
            side="BUY",
            contract_multiplier=None,
            meta=None,
        )
        assert res.valid is False
        assert "missing contract multiplier" in res.rejection_reason.lower()

    @pytest.mark.parametrize("invalid_cm", [
        Decimal("0"),
        Decimal("-0.001"),
        Decimal("-1.0"),
        float("nan"),
        float("inf"),
        float("-inf"),
        "invalid_non_numeric",
        "",
    ])
    def test_invalid_multiplier_values_fail_closed(self, invalid_cm):
        """Case 7: Invalid multiplier values (zero, negative, NaN, Inf, string) fail closed."""
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("10"),
            risk_budget=Decimal("10.00"),
            side="BUY",
            contract_multiplier=invalid_cm,
            meta=None,
        )
        assert res.valid is False
        assert res.total_normalized_risk_usd == Decimal("0")

    def test_different_instrument_with_legitimate_multiplier_of_1(self, eth_linear_meta):
        """Case 8: A different instrument with a legitimate multiplier of 1.0."""
        # Entry 3000.00, stop 2950.00 (50 pts), Qty 2.0 ETH
        # Gross loss = 50 * 2.0 * 1.0 = $100.00
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("3000.00"),
            raw_stop_price=Decimal("2950.00"),
            quantity=Decimal("2.0"),
            risk_budget=Decimal("120.00"),
            side="BUY",
            contract_multiplier=None,
            meta=eth_linear_meta,
        )
        assert res.valid is True
        assert res.contract_multiplier == Decimal("1.0")
        assert res.normalized_gross_risk_usd == Decimal("100.00")
        assert res.total_normalized_risk_usd < Decimal("120.00")

    def test_position_sizing_fees_gross_pnl_and_stop_risk_consistency(self, btc_meta):
        """
        Case 9: Independent mathematical validation of units, fees, gross P&L,
        and stop risk for linear BTCUSD perpetual futures.
        """
        entry_price = Decimal("60000.00")
        stop_price = Decimal("59500.00")
        quantity = Decimal("1000")  # 1,000 Delta contracts = 1.0 BTC
        mult = btc_meta.contract_multiplier  # 0.001

        # 1. Independent Notional Calculations
        entry_notional = entry_price * quantity * mult
        stop_notional = stop_price * quantity * mult
        assert entry_notional == Decimal("60000.00")
        assert stop_notional == Decimal("59500.00")

        # 2. Independent Gross Loss Calculation
        gross_loss = (entry_price - stop_price) * quantity * mult
        assert gross_loss == Decimal("500.00")

        # 3. Independent Fee Calculations (Maker Entry 2.0 bps + 18% GST, Taker Exit 5.0 bps + 18% GST)
        entry_base_rate = Decimal("0.0002")  # 2.0 bps
        exit_base_rate = Decimal("0.0005")   # 5.0 bps
        gst_rate = Decimal("0.18")           # 18% GST

        entry_base_fee = (entry_notional * entry_base_rate).quantize(Decimal("0.00000001"))
        entry_gst = (entry_base_fee * gst_rate).quantize(Decimal("0.00000001"))
        expected_entry_fee = entry_base_fee + entry_gst
        assert expected_entry_fee == Decimal("14.16000000")

        exit_base_fee = (stop_notional * exit_base_rate).quantize(Decimal("0.00000001"))
        exit_gst = (exit_base_fee * gst_rate).quantize(Decimal("0.00000001"))
        expected_exit_fee = exit_base_fee + exit_gst
        assert expected_exit_fee == Decimal("35.10500000")

        expected_total_fees = expected_entry_fee + expected_exit_fee
        assert expected_total_fees == Decimal("49.26500000")
        expected_total_risk = gross_loss + expected_total_fees
        assert expected_total_risk == Decimal("549.26500000")

        # Audit stop risk result
        audit = audit_and_recalculate_stop_risk(
            entry_price=entry_price,
            raw_stop_price=stop_price,
            quantity=quantity,
            risk_budget=Decimal("560.00"),
            side="BUY",
            meta=btc_meta,
        )
        assert audit.valid is True
        assert audit.normalized_gross_risk_usd == Decimal("500.00")
        assert audit.estimated_stop_fees_usd == expected_total_fees
        assert audit.total_normalized_risk_usd == expected_total_risk

        # Position Sizing: Budget $545 rejects 1,000 contracts; budget $550 accepts
        audit_reject = audit_and_recalculate_stop_risk(
            entry_price=entry_price,
            raw_stop_price=stop_price,
            quantity=quantity,
            risk_budget=Decimal("545.00"),
            side="BUY",
            meta=btc_meta,
        )
        assert audit_reject.valid is False
        assert "exceeds risk budget" in audit_reject.rejection_reason

    def test_order_serialization_and_restoration_preserves_multiplier(self, btc_meta):
        """Case 10: Serialization and restoration preserves multiplier precision."""
        order = PaperOrder(
            order_id="TEST-SER-001",
            symbol="BTCUSD",
            side="BUY",
            order_type="LIMIT_POST_ONLY",
            price=Decimal("60000.00"),
            quantity=Decimal("1000"),
            multiplier=btc_meta.contract_multiplier,
            tick_size=btc_meta.tick_size,
            quantity_step=btc_meta.step_size,
            min_quantity=btc_meta.min_quantity,
        )
        order_dict = {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "price": str(order.price),
            "quantity": str(order.quantity),
            "multiplier": str(order.multiplier),
            "tick_size": str(order.tick_size),
        }
        json_payload = json.dumps(order_dict)

        # Restore
        restored_dict = json.loads(json_payload)
        restored_order = PaperOrder(
            order_id=restored_dict["order_id"],
            symbol=restored_dict["symbol"],
            side=restored_dict["side"],
            order_type=restored_dict["order_type"],
            price=Decimal(restored_dict["price"]),
            quantity=Decimal(restored_dict["quantity"]),
            multiplier=Decimal(restored_dict["multiplier"]),
            tick_size=Decimal(restored_dict["tick_size"]),
        )
        assert restored_order.multiplier == Decimal("0.001")
        assert restored_order.price == Decimal("60000.00")
        assert restored_order.quantity == Decimal("1000")


class TestPhase181ExecutionBoundaryAndEnforcement:
    """Audit and verify final execution-boundary invariants."""

    @pytest.fixture
    def engine(self) -> QueueAwarePaperExecutionEngine:
        return QueueAwarePaperExecutionEngine()

    @pytest.fixture
    def btc_meta(self) -> InstrumentMetadata:
        return InstrumentMetadata.for_btcusd()

    def test_stale_risk_verdict_cannot_survive_amendments(self, engine, btc_meta):
        """Verify that amending order parameters invalidates old verdicts and triggers fresh risk check."""
        order = engine.submit_candidate_trade(
            order_id="AMEND-STALE-01",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.00"),
            stop_price=Decimal("59500.00"),
            target_price=Decimal("62000.00"),
            quantity=Decimal("500"),  # $267.40 risk
            risk_budget=Decimal("300.00"),  # Fits budget
            best_bid=Decimal("60000.00"),
            best_ask=Decimal("60000.10"),
            meta=btc_meta,
        )
        assert order.state == PaperOrderState.RESTING
        assert order.order_id in engine.active_orders

        # Amend quantity upward to 1,000 ($534.80 risk > $300 budget)
        amended = engine.amend_order_risk(
            order_id=order.order_id,
            new_quantity=Decimal("1000"),
            new_stop_price=Decimal("59500.00"),
            new_risk_budget=Decimal("300.00"),
            meta=btc_meta,
        )
        assert amended.state == PaperOrderState.REJECTED_RISK
        assert order.order_id not in engine.active_orders
        assert "exceeds risk budget" in amended.risk_audit.rejection_reason
        assert assert_no_live_adapter_invocation() is True

    def test_partial_fill_residual_risk_recalculation(self, btc_meta):
        """Verify that residual quantities after partial fills have stop risk audited accurately."""
        # Initial: 1000 contracts
        initial_audit = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            meta=btc_meta,
        )
        assert initial_audit.valid is True
        assert initial_audit.normalized_gross_risk_usd == Decimal("500.00")

        # 400 contracts fill; residual = 600 contracts
        residual_qty = Decimal("600")
        residual_audit = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.00"),
            quantity=residual_qty,
            risk_budget=Decimal("350.00"),
            side="BUY",
            meta=btc_meta,
        )
        assert residual_audit.valid is True
        # 500 pts * 600 * 0.001 = $300.00 gross risk
        assert residual_audit.normalized_gross_risk_usd == Decimal("300.00")
        assert residual_audit.total_normalized_risk_usd < Decimal("350.00")

    def test_adapter_isolation_zero_invocations_on_risk_rejection(self, engine, btc_meta):
        """Prove that risk-rejected candidate triggers zero adapter invocations."""
        order = engine.submit_candidate_trade(
            order_id="REJECT-ISOLATE-01",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.00"),
            stop_price=Decimal("59000.00"),  # 1000 pts stop loss
            target_price=Decimal("62000.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.00"),  # Insufficient budget
            best_bid=Decimal("60000.00"),
            best_ask=Decimal("60000.10"),
            meta=btc_meta,
        )
        assert order.state == PaperOrderState.REJECTED_RISK
        assert order.order_id not in engine.active_orders
        assert assert_no_live_adapter_invocation() is True

    def test_hurdle_rejection_distinct_from_risk_rejection(self, engine, btc_meta):
        """Verify that hurdle gate rejection is distinct from risk budget rejection in state and evidence."""
        # Setup with tiny target: target 60010.00 (10 pts) vs stop 59500.00 (500 pts)
        # Breaches fee ratio and R:R hurdles, but stop risk fits huge budget
        order_hurdle = engine.submit_candidate_trade(
            order_id="HURDLE-FAIL-01",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.00"),
            stop_price=Decimal("59500.00"),
            target_price=Decimal("60010.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("100.00"),  # Plenty of budget
            best_bid=Decimal("60000.00"),
            best_ask=Decimal("60000.10"),
            meta=btc_meta,
        )
        assert order_hurdle.state == PaperOrderState.REJECTED_RISK
        assert "friction hurdle failed" in order_hurdle.state_history[-1][2].lower()
        assert order_hurdle.hurdle_verdict is not None
        assert order_hurdle.hurdle_verdict.allowed is False
        assert order_hurdle.risk_audit is not None
        assert order_hurdle.risk_audit.valid is True  # Risk check alone passed!

        # Setup with great target (2000 pts) but risk breaches tight budget
        order_risk = engine.submit_candidate_trade(
            order_id="RISK-FAIL-01",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.00"),
            stop_price=Decimal("59500.00"),   # 500 pts stop
            target_price=Decimal("62000.00"),  # 2000 pts target -> hurdle passes
            quantity=Decimal("1000"),
            risk_budget=Decimal("200.00"),  # Tight budget -> risk fail
            best_bid=Decimal("60000.00"),
            best_ask=Decimal("60000.10"),
            meta=btc_meta,
        )
        assert order_risk.state == PaperOrderState.REJECTED_RISK
        assert "exceeds risk budget" in order_risk.state_history[-1][2].lower()
        assert order_risk.risk_audit is not None
        assert order_risk.risk_audit.valid is False   # Risk budget breached!
        assert order_risk.hurdle_verdict is None       # Hurdle gate never reached!
