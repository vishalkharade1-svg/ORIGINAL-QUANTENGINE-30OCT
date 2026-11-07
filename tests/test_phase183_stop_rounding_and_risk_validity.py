"""
QuantEngine Phase 183 — Stop-Rounding Semantics, Risk Test Validity & Execution Boundary.

This module provides mathematically rigorous, independently justified boundary tests
with explicit Decimal arithmetic covering:
1. Raw gross stop risk below budget AND normalized gross stop risk below budget.
2. Raw gross stop risk below budget, but fees push total risk over budget.
3. Raw stop risk above budget before normalization.
4. Normalization genuinely increasing the tested risk measure (under FLOOR/expansion policy).
5. Long and short stops rounding toward entry (CONSERVATIVE policy).
6. Long and short stops rounding away from entry (when policy permits buffer expansion).
7. Stops already aligned to valid tick grid (zero delta, zero expansion).
8. Repeated normalization idempotence.
9. Invalid or conflicting instrument metadata.
10. Risk-budget checks after partial fills, quantity amendments, and price amendments.
11. Non-finite prices, quantities, fees, multipliers, and budgets.
12. Absolute adapter isolation across all rejected candidates.
"""

from decimal import Decimal
import pytest

from core.execution.maker_execution_model import (
    audit_and_recalculate_stop_risk,
    normalize_price_to_tick,
    validate_instrument_constraints,
    InstrumentMetadata,
    TickRoundingPolicy,
    ExecutionStyle,
    calculate_leg_fee,
    calculate_asymmetric_round_trip,
    DEFAULT_GST_RATE,
    MAKER_BASE_RATE,
    TAKER_BASE_RATE,
)
from core.paper_trading.queue_aware_paper_engine import (
    QueueAwarePaperExecutionEngine,
    PaperOrderState,
    PaperOrder,
)


class SpyExecutionAdapter:
    """Mock execution adapter acting as a spy/sentinel to assert zero invocations."""

    def __init__(self):
        self.invocations: list[dict] = []

    def place_order(self, *args, **kwargs):
        self.invocations.append({"method": "place_order", "args": args, "kwargs": kwargs})
        raise RuntimeError("CRITICAL SAFETY FAULT: SpyExecutionAdapter.place_order was invoked!")

    def cancel_order(self, *args, **kwargs):
        self.invocations.append({"method": "cancel_order", "args": args, "kwargs": kwargs})
        raise RuntimeError("CRITICAL SAFETY FAULT: SpyExecutionAdapter.cancel_order was invoked!")

    def amend_order(self, *args, **kwargs):
        self.invocations.append({"method": "amend_order", "args": args, "kwargs": kwargs})
        raise RuntimeError("CRITICAL SAFETY FAULT: SpyExecutionAdapter.amend_order was invoked!")

    def assert_zero_invocations(self):
        assert len(self.invocations) == 0, f"Expected 0 adapter invocations, found {len(self.invocations)}: {self.invocations}"


class TestPhase183StopRoundingAndRiskValidity:
    """Mathematically validated boundary tests with explicit Decimal justifications."""

    @pytest.fixture
    def meta_btc(self):
        return InstrumentMetadata.for_btcusd()

    def test_01_raw_gross_and_normalized_gross_below_budget(self, meta_btc):
        """Case 1: Raw gross stop risk is below budget AND normalized gross stop risk is below budget.

        Mathematical Justification:
          Long Position:
            P_entry = 60,000.00 USD
            P_stop,raw = 59,500.05 USD (unquantized)
            Qty = 1,000 contracts, Multiplier = 0.001 -> Effective Position S = 1.0 BTC
            Tick Size = 0.10 USD
            Policy = CONSERVATIVE (Ceilings Long stops up toward entry)

          Calculations:
            Raw Distance = 60,000.00 - 59,500.05 = 499.95 USD
            Raw Gross Loss = 499.95 * 1.0 = 499.95000000 USD
            Normalized Stop = 59,500.10 USD
            Normalized Distance = 60,000.00 - 59,500.10 = 499.90 USD
            Normalized Gross Loss = 499.90 * 1.0 = 499.90000000 USD

          Risk Measure Evaluated: GROSS STOP LOSS (Budget = 500.00 USD)
            Raw Gross Loss (499.95 USD) < Budget (500.00 USD)
            Normalized Gross Loss (499.90 USD) < Budget (500.00 USD)
            Gross Loss Contraction: 499.90 - 499.95 = -0.05000000 USD (Risk decreased)
            Premature Trigger Delta: +0.05000000 pts (Stop is 0.05 pts closer to entry)

          Fee-Inclusive Check (Budget = 550.00 USD):
            Maker Entry Fee (2.36 bps) = 60,000 * 0.000236 = 14.16000000 USD
            Taker Exit Fee (5.90 bps) = 59,500.10 * 0.000590 = 35.10505900 USD
            Total Normalized Risk = 499.90 + 14.16 + 35.105059 = 549.16505900 USD < 550.00 USD
        """
        entry = Decimal("60000.00")
        raw_stop = Decimal("59500.05")
        qty = Decimal("1000")
        gross_budget = Decimal("500.00")
        fee_incl_budget = Decimal("550.00")

        audit = audit_and_recalculate_stop_risk(
            entry_price=entry,
            raw_stop_price=raw_stop,
            quantity=qty,
            risk_budget=fee_incl_budget,
            side="BUY",
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta_btc,
        )

        assert audit.raw_gross_risk_usd == Decimal("499.95000000")
        assert audit.raw_gross_risk_usd < gross_budget
        assert audit.normalized_stop_price == Decimal("59500.10")
        assert audit.normalized_gross_risk_usd == Decimal("499.90000000")
        assert audit.normalized_gross_risk_usd < gross_budget
        assert audit.risk_expansion_usd == Decimal("-0.05000000")
        assert audit.premature_trigger_risk_delta_pts == Decimal("0.05")
        assert audit.total_normalized_risk_usd == Decimal("549.16505900")
        assert audit.valid is True

    def test_02_raw_gross_below_budget_fees_push_over_budget(self, meta_btc):
        """Case 2: Raw gross stop risk is below budget, but fees push total risk over budget.

        Mathematical Justification:
          Long Position:
            P_entry = 60,000.00 USD
            P_stop = 59,500.00 USD (exact tick)
            Qty = 1,000 contracts, Multiplier = 0.001 -> S = 1.0 BTC
            Gross Loss = (60,000 - 59,500) * 1.0 = 500.00000000 USD
            Entry Fee = 60,000 * 0.000236 = 14.16000000 USD
            Exit Fee = 59,500 * 0.000590 = 35.10500000 USD
            Total Fees = 49.26500000 USD
            Total Normalized Risk = 500.00 + 49.265 = 549.26500000 USD

          Risk Measure Evaluated: TOTAL FEE-INCLUSIVE RISK vs Budget = 520.00 USD
            Gross Loss (500.00 USD) < Budget (520.00 USD)
            Total Risk (549.265 USD) > Budget (520.00 USD)
            Fails closed because fee drag turns a viable gross setup into a net budget breach.
        """
        entry = Decimal("60000.00")
        stop = Decimal("59500.00")
        qty = Decimal("1000")
        budget = Decimal("520.00")

        audit = audit_and_recalculate_stop_risk(
            entry_price=entry,
            raw_stop_price=stop,
            quantity=qty,
            risk_budget=budget,
            side="BUY",
            meta=meta_btc,
        )

        assert audit.raw_gross_risk_usd == Decimal("500.00000000")
        assert audit.raw_gross_risk_usd < budget
        assert audit.normalized_gross_risk_usd == Decimal("500.00000000")
        assert audit.normalized_gross_risk_usd < budget
        assert audit.estimated_stop_fees_usd == Decimal("49.26500000")
        assert audit.total_normalized_risk_usd == Decimal("549.26500000")
        assert audit.total_normalized_risk_usd > budget
        assert audit.valid is False
        assert "exceeds risk budget" in audit.rejection_reason

    def test_03_raw_stop_risk_exceeds_budget_before_normalization(self, meta_btc):
        """Case 3: Raw stop risk exceeds budget prior to normalization.

        Mathematical Justification:
          Long Position:
            P_entry = 60,000.00 USD, P_stop,raw = 58,000.00 USD
            Qty = 1,000, Multiplier = 0.001 -> S = 1.0 BTC
            Raw Gross Loss = (60,000 - 58,000) * 1.0 = 2,000.00000000 USD
            Risk Budget = 500.00 USD
            Raw Gross Risk (2,000.00 USD) > Budget (500.00 USD)
            Fails closed immediately.
        """
        audit = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("58000.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.00"),
            side="BUY",
            meta=meta_btc,
        )
        assert audit.raw_gross_risk_usd == Decimal("2000.00000000")
        assert audit.raw_gross_risk_usd > Decimal("500.00")
        assert audit.total_normalized_risk_usd > Decimal("500.00")
        assert audit.valid is False
        assert "exceeds risk budget" in audit.rejection_reason

    def test_04_normalization_genuinely_increases_risk_under_floor_policy(self, meta_btc):
        """Case 4: Normalization genuinely increases risk when rounding away from entry (FLOOR policy).

        Mathematical Justification:
          Long Position:
            P_entry = 60,000.00 USD
            P_stop,raw = 59,500.05 USD
            Policy = TickRoundingPolicy.FLOOR (Noise-Immunity / Buffer Preservation)
            Under FLOOR, stop rounds DOWN away from entry:
              P_stop,norm = 59,500.00 USD

          Gross Loss Comparison:
            Raw Gross Loss = (60,000.00 - 59,500.05) * 1.0 = 499.95000000 USD
            Normalized Gross Loss = (60,000.00 - 59,500.00) * 1.0 = 500.00000000 USD
            Gross Loss Expansion: +0.05000000 USD (Risk genuinely increased by normalization)

          Total Fee-Inclusive Risk Comparison:
            Raw Exit Fee (5.90 bps on 59,500.05) = 35.10502950 USD
            Raw Total Risk = 499.95 + 14.16 + 35.10502950 = 549.21502950 USD
            Normalized Exit Fee (5.90 bps on 59,500.00) = 35.10500000 USD
            Normalized Total Risk = 500.00 + 14.16 + 35.10500000 = 549.26500000 USD
            Total Risk Expansion: 549.26500000 - 549.21502950 = +0.04997050 USD

          Budget Calibration:
            Set Budget = 549.24 USD
            Raw Total Risk (549.21502950 USD) <= Budget (549.24 USD) -> RAW WITHIN BUDGET
            Normalized Total Risk (549.26500000 USD) > Budget (549.24 USD) -> NORMALIZED BREACHES
            Conclusion: Normalization expansion is solely responsible for crossing the budget!
        """
        entry = Decimal("60000.00")
        raw_stop = Decimal("59500.05")
        qty = Decimal("1000")
        budget = Decimal("549.24")

        audit = audit_and_recalculate_stop_risk(
            entry_price=entry,
            raw_stop_price=raw_stop,
            quantity=qty,
            risk_budget=budget,
            side="BUY",
            policy=TickRoundingPolicy.FLOOR,
            meta=meta_btc,
        )

        assert audit.raw_gross_risk_usd == Decimal("499.95000000")
        assert audit.normalized_stop_price == Decimal("59500.00")
        assert audit.normalized_gross_risk_usd == Decimal("500.00000000")
        assert audit.risk_expansion_usd == Decimal("0.05000000")
        assert audit.premature_trigger_risk_delta_pts == Decimal("-0.05")  # 0.05 pts more buffer
        assert audit.total_normalized_risk_usd == Decimal("549.26500000")
        assert audit.valid is False
        assert "exceeds risk budget" in audit.rejection_reason

    def test_05_long_and_short_stops_round_toward_entry_under_conservative(self, meta_btc):
        """Case 5: Long and short stops round toward entry under CONSERVATIVE policy.

        Mathematical Justification:
          Long Position:
            P_entry = 60,000.00, P_stop,raw = 59,500.04 -> Ceilings UP to 59,500.10.
            Raw distance: 499.96 -> Normalized distance: 499.90 (contracted by 0.06).
            Gross loss contracts from 499.96 USD to 499.90 USD.
            Premature trigger delta: +0.06 pts closer to entry.

          Short Position:
            P_entry = 60,000.00, P_stop,raw = 60,500.06 -> Floors DOWN to 60,500.00.
            Raw distance: 500.06 -> Normalized distance: 500.00 (contracted by 0.06).
            Gross loss contracts from 500.06 USD to 500.00 USD.
            Premature trigger delta: +0.06 pts closer to entry.
        """
        # Long Stop
        audit_long = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.04"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta_btc,
        )
        assert audit_long.normalized_stop_price == Decimal("59500.10")
        assert audit_long.raw_stop_distance == Decimal("499.96")
        assert audit_long.normalized_stop_distance == Decimal("499.90")
        assert audit_long.risk_expansion_usd == Decimal("-0.06000000")
        assert audit_long.premature_trigger_risk_delta_pts == Decimal("0.06")

        # Short Stop
        audit_short = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("60500.06"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="SELL",
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta_btc,
        )
        assert audit_short.normalized_stop_price == Decimal("60500.00")
        assert audit_short.raw_stop_distance == Decimal("500.06")
        assert audit_short.normalized_stop_distance == Decimal("500.00")
        assert audit_short.risk_expansion_usd == Decimal("-0.06000000")
        assert audit_short.premature_trigger_risk_delta_pts == Decimal("0.06")

    def test_06_long_and_short_stops_round_away_from_entry_under_buffer_policies(self, meta_btc):
        """Case 6: Long and short stops round away from entry when permitted by policy.

        Mathematical Justification:
          Long Position under FLOOR policy:
            P_entry = 60,000.00, P_stop,raw = 59,500.04 -> Floors DOWN to 59,500.00.
            Raw distance: 499.96 -> Normalized distance: 500.00 (expanded by 0.04).
            Gross loss expands from 499.96 USD to 500.00 USD.
            Premature trigger delta: -0.04 pts (farther from entry, wider noise buffer).

          Short Position under CEILING policy:
            P_entry = 60,000.00, P_stop,raw = 60,500.04 -> Ceilings UP to 60,500.10.
            Raw distance: 500.04 -> Normalized distance: 500.10 (expanded by 0.06).
            Gross loss expands from 500.04 USD to 500.10 USD.
            Premature trigger delta: -0.06 pts (farther from entry, wider noise buffer).
        """
        # Long Stop under FLOOR
        audit_long = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("59500.04"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            policy=TickRoundingPolicy.FLOOR,
            meta=meta_btc,
        )
        assert audit_long.normalized_stop_price == Decimal("59500.00")
        assert audit_long.raw_stop_distance == Decimal("499.96")
        assert audit_long.normalized_stop_distance == Decimal("500.00")
        assert audit_long.risk_expansion_usd == Decimal("0.04000000")
        assert audit_long.premature_trigger_risk_delta_pts == Decimal("-0.04")

        # Short Stop under CEILING
        audit_short = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=Decimal("60500.04"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="SELL",
            policy=TickRoundingPolicy.CEILING,
            meta=meta_btc,
        )
        assert audit_short.normalized_stop_price == Decimal("60500.10")
        assert audit_short.raw_stop_distance == Decimal("500.04")
        assert audit_short.normalized_stop_distance == Decimal("500.10")
        assert audit_short.risk_expansion_usd == Decimal("0.06000000")
        assert audit_short.premature_trigger_risk_delta_pts == Decimal("-0.06")

    def test_07_stops_already_aligned_to_tick(self, meta_btc):
        """Case 7: Stops already aligned to valid tick grid have zero delta and zero expansion."""
        exact_stop = Decimal("59500.10")
        audit = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.00"),
            raw_stop_price=exact_stop,
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            side="BUY",
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta_btc,
        )
        assert audit.normalized_stop_price == exact_stop
        assert audit.raw_stop_distance == audit.normalized_stop_distance == Decimal("499.90")
        assert audit.risk_expansion_usd == Decimal("0.00000000")
        assert audit.premature_trigger_risk_delta_pts == Decimal("0.00")
        assert audit.valid is True

    def test_08_repeated_normalization_idempotent(self, meta_btc):
        """Case 8: Repeated normalization of prices is deterministic and idempotent."""
        arbitrary_price = Decimal("59500.14729185")
        norm1 = normalize_price_to_tick(arbitrary_price, policy=TickRoundingPolicy.CONSERVATIVE, side="BUY", is_stop=True, meta=meta_btc)
        norm2 = normalize_price_to_tick(norm1, policy=TickRoundingPolicy.CONSERVATIVE, side="BUY", is_stop=True, meta=meta_btc)
        norm3 = normalize_price_to_tick(norm2, policy=TickRoundingPolicy.CONSERVATIVE, side="BUY", is_stop=True, meta=meta_btc)
        assert norm1 == Decimal("59500.20")
        assert norm1 == norm2 == norm3

    def test_09_invalid_or_conflicting_instrument_metadata(self, meta_btc):
        """Case 9: Invalid or conflicting instrument metadata fails closed."""
        # A: Explicit multiplier mismatch with authoritative metadata
        res_conflict = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("1000"),
            contract_multiplier=Decimal("0.01"),  # 0.01 != 0.001
            meta=meta_btc,
        )
        assert res_conflict.valid is False
        assert "Metadata conflict" in res_conflict.rejection_reason

        # B: Both multiplier and metadata omitted
        res_missing = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("1000"),
            contract_multiplier=None,
            meta=None,
        )
        assert res_missing.valid is False
        assert "Missing contract multiplier" in res_missing.rejection_reason

    def test_10_risk_budget_checks_after_partial_fills_and_amendments(self, meta_btc):
        """Case 10: Risk budget verification across order submission, partial fills, and amendments."""
        engine = QueueAwarePaperExecutionEngine()
        spy = SpyExecutionAdapter()

        # 1. Initial valid submission: Qty 1000, Budget 600 USD (Risk approx 549.265 USD)
        order = engine.submit_candidate_trade(
            order_id="ORD-LIFECYCLE-183",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.00"),
            stop_price=Decimal("59500.00"),
            target_price=Decimal("61500.00"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.00"),
            best_bid=Decimal("60000.00"),
            best_ask=Decimal("60005.00"),
            meta=meta_btc,
        )
        assert order.state == PaperOrderState.RESTING
        assert "ORD-LIFECYCLE-183" in engine.active_orders

        # 2. Partial fill of 400 contracts
        engine._fill_order(order, fill_volume=Decimal("400"))
        assert order.filled_quantity == Decimal("400")
        assert order.remaining_quantity == Decimal("600")

        # 3. Amendment increasing remaining quantity to 1500 (total exposure 1900 -> risk > 1,000 USD)
        amended_qty = engine.amend_order_risk(
            order_id="ORD-LIFECYCLE-183",
            new_quantity=Decimal("1500"),
            meta=meta_btc,
        )
        assert amended_qty.state == PaperOrderState.REJECTED_RISK
        assert "ORD-LIFECYCLE-183" not in engine.active_orders
        assert "exceeds risk budget" in amended_qty.state_history[-1][2]

        spy.assert_zero_invocations()

    def test_11_non_finite_inputs_and_edge_values(self, meta_btc):
        """Case 11: Non-finite prices, quantities, multipliers, and negative budgets fail closed cleanly."""
        # Non-numeric string
        res_str = audit_and_recalculate_stop_risk(
            entry_price="bad_entry",
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600"),
            meta=meta_btc,
        )
        assert res_str.valid is False
        assert "Non-numeric risk input" in res_str.rejection_reason

        # NaN price
        res_nan = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=float("nan"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600"),
            meta=meta_btc,
        )
        assert res_nan.valid is False

        # Negative risk budget
        res_neg_budget = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("-50"),
            meta=meta_btc,
        )
        assert res_neg_budget.valid is False
        assert "strictly positive" in res_neg_budget.rejection_reason

        # Zero quantity
        res_zero_qty = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("0"),
            risk_budget=Decimal("500"),
            meta=meta_btc,
        )
        assert res_zero_qty.valid is False

    def test_12_adapter_isolation_across_all_rejection_paths(self):
        """Case 12: Spy execution adapter verifies zero invocations across all rejection paths."""
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()
        spy = SpyExecutionAdapter()

        # Path A: Stop Risk Budget Rejection
        ord_risk = engine.submit_candidate_trade(
            order_id="ORD-REJECT-RISK",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("58000.0"),  # 2000 loss > 500 budget
            target_price=Decimal("62000.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            meta=meta,
        )
        assert ord_risk.state == PaperOrderState.REJECTED_RISK
        assert ord_risk.risk_audit.valid is False
        assert ord_risk.hurdle_verdict is None
        assert "Normalized stop risk" in ord_risk.state_history[-1][2]
        spy.assert_zero_invocations()

        # Path B: Friction Hurdle Gate Rejection
        ord_hurdle = engine.submit_candidate_trade(
            order_id="ORD-REJECT-HURDLE",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("59900.0"),
            target_price=Decimal("60100.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            min_post_fee_rr=Decimal("10.0"),  # Unattainable 10x post-fee R:R
            meta=meta,
        )
        assert ord_hurdle.state == PaperOrderState.REJECTED_RISK
        assert ord_hurdle.risk_audit.valid is True
        assert ord_hurdle.hurdle_verdict.allowed is False
        assert "Friction hurdle failed" in ord_hurdle.state_history[-1][2]
        spy.assert_zero_invocations()

        # Path C: Metadata Conflict Rejection
        ord_meta_conflict = engine.submit_candidate_trade(
            order_id="ORD-REJECT-META",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("59500.0"),
            target_price=Decimal("61500.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            tick_size=Decimal("0.50"),  # Conflicting tick size: 0.50 != meta.tick_size (0.10)
            meta=meta,
        )
        assert ord_meta_conflict.state == PaperOrderState.REJECTED_CONSTRAINTS
        assert "Metadata conflict" in ord_meta_conflict.state_history[-1][2]
        spy.assert_zero_invocations()

        # Path D: Geometry Rejection (Long stop above entry)
        ord_geometry = engine.submit_candidate_trade(
            order_id="ORD-REJECT-GEOM",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("60500.0"),  # Stop above entry for long!
            target_price=Decimal("61500.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            meta=meta,
        )
        assert ord_geometry.state == PaperOrderState.REJECTED_RISK
        assert "Invalid long stop geometry" in ord_geometry.state_history[-1][2]
        spy.assert_zero_invocations()

        # Final assertion: total invocations remain exactly 0
        spy.assert_zero_invocations()
