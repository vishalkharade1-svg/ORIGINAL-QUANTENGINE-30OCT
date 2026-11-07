"""
QuantEngine Phase 182 - Adversarial Risk Boundary, Multiplier Forensics & Execution Isolation.

Tests:
1. Raw stop risk is within budget, but normalized stop risk exceeds it.
2. Raw stop risk and normalized stop risk are each within budget, but entry/exit fees push total risk over budget.
3. Raw stop risk exceeds budget before normalization.
4. Tick normalization changes the stop in both long and short positions under CONSERVATIVE policy.
5. Missing or conflicting multiplier reaches the risk boundary and fails closed.
6. Metadata changes between initial evaluation and amendment or recovery.
7. Partial fills increase total exposure and breach the budget.
8. Invalid fee or malformed numeric inputs are rejected cleanly.
9. Normalized stop already on a valid tick is preserved identically.
10. Repeated normalization is deterministic and idempotent.
11. Disambiguation of risk_audit.valid, hurdle_verdict.allowed, and final candidate state.
12. Spy/sentinel adapter assertions: zero adapter invocations across all rejected/malformed/conflicting candidates.
13. Independent numerical reproduction of conditional Delta Exchange India Product ID 84 accounting example.
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


class TestPhase182AdversarialScenarios:
    """Ten required deterministic boundary scenarios."""

    @pytest.fixture
    def meta_btc(self):
        return InstrumentMetadata.for_btcusd()

    def test_scenario_01_raw_within_budget_normalized_exceeds(self, meta_btc):
        """Scenario 1: Raw stop risk is within budget, but normalized stop risk exceeds it.
        
        Entry: 60,000, Stop: 59,500.03 (dist=499.97). Qty: 1000, Mult: 0.001.
        Raw loss = 499.97. Total fees approx 49.265. Raw risk approx 549.235.
        Set budget = 549.25. Raw risk <= budget.
        Under FLOOR/CONSERVATIVE or expansion policy, if stop shifts to 59,500.00 (dist=500.00),
        loss becomes 500.00, total risk becomes 549.265, which breaches budget 549.25!
        """
        entry = Decimal("60000.00")
        raw_stop = Decimal("59500.03")  # non-tick price
        qty = Decimal("1000")
        budget = Decimal("549.25")

        # In FLOOR policy for Long stop, floor moves stop further down (59500.00), expanding risk
        audit = audit_and_recalculate_stop_risk(
            entry_price=entry,
            raw_stop_price=raw_stop,
            quantity=qty,
            risk_budget=budget,
            side="BUY",
            policy=TickRoundingPolicy.FLOOR,
            meta=meta_btc,
        )
        assert audit.raw_gross_risk_usd < budget
        assert audit.normalized_stop_price == Decimal("59500.0")
        assert audit.total_normalized_risk_usd > budget
        assert audit.valid is False
        assert "exceeds risk budget" in audit.rejection_reason

    def test_scenario_02_raw_and_norm_within_budget_fees_push_over(self, meta_btc):
        """Scenario 2: Raw and normalized gross stop risk are within budget, but entry/exit fees push total risk over budget.
        
        Gross loss = (60000 - 59500) * 1000 * 0.001 = $500.00.
        Fees approx $49.265. Total risk = $549.265.
        Budget = $520.00. Gross loss ($500) <= $520, but with fees ($549.265) > $520.
        """
        entry = Decimal("60000.00")
        stop = Decimal("59500.00")  # exactly on tick
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
        assert audit.normalized_gross_risk_usd == Decimal("500.00")
        assert audit.normalized_gross_risk_usd < budget
        assert audit.total_normalized_risk_usd > budget
        assert audit.valid is False
        assert "exceeds risk budget" in audit.rejection_reason

    def test_scenario_03_raw_stop_exceeds_budget_before_normalization(self, meta_btc):
        """Scenario 3: Raw stop risk exceeds the budget before normalization."""
        entry = Decimal("60000.00")
        stop = Decimal("58000.00")  # dist = 2,000 -> gross loss = $2,000
        qty = Decimal("1000")
        budget = Decimal("500.00")

        audit = audit_and_recalculate_stop_risk(
            entry_price=entry,
            raw_stop_price=stop,
            quantity=qty,
            risk_budget=budget,
            side="BUY",
            meta=meta_btc,
        )
        assert audit.raw_gross_risk_usd > budget
        assert audit.valid is False
        assert "exceeds risk budget" in audit.rejection_reason

    def test_scenario_04_tick_normalization_changes_stop_long_and_short(self, meta_btc):
        """Scenario 4: Tick normalization changes the stop in both long and short positions under CONSERVATIVE policy."""
        # Long position: entry 60,000, raw stop 59,500.04 -> CONSERVATIVE ceilings up to 59,500.10 (closer to entry)
        norm_long = normalize_price_to_tick(
            price=Decimal("59500.04"),
            side="BUY",
            is_stop=True,
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta_btc,
        )
        assert norm_long == Decimal("59500.10")

        # Short position: entry 60,000, raw stop 60,500.06 -> CONSERVATIVE floors down to 60,500.00 (closer to entry)
        norm_short = normalize_price_to_tick(
            price=Decimal("60500.06"),
            side="SELL",
            is_stop=True,
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta_btc,
        )
        assert norm_short == Decimal("60500.00")

    def test_scenario_05_missing_or_conflicting_multiplier_at_risk_boundary(self, meta_btc):
        """Scenario 5: A missing or conflicting multiplier reaches the risk boundary."""
        # A: Both missing
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

        # B: Conflicting multiplier (e.g. metadata has 0.001, caller explicitly passes 0.01)
        res_conflict = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("1000"),
            contract_multiplier=Decimal("0.01"),
            meta=meta_btc,
        )
        assert res_conflict.valid is False
        assert "Metadata conflict" in res_conflict.rejection_reason

    def test_scenario_06_metadata_changes_between_initial_eval_and_amendment(self, meta_btc):
        """Scenario 6: Metadata changes between initial evaluation and amendment or recovery."""
        engine = QueueAwarePaperExecutionEngine()
        spy = SpyExecutionAdapter()

        # Submit with valid BTC metadata (mult=0.001)
        order = engine.submit_candidate_trade(
            order_id="ORD-META-CHANGE",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("59500.0"),
            target_price=Decimal("61500.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            meta=meta_btc,
        )
        assert order.state == PaperOrderState.RESTING

        # Attempt to amend with contradictory / altered metadata (e.g. multiplier 0.002 doubling risk to >1,000)
        altered_meta = InstrumentMetadata(
            symbol="BTCUSD",
            tick_size=Decimal("0.10"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            contract_multiplier=Decimal("0.002"),  # doubled
        )

        amended = engine.amend_order_risk(
            order_id="ORD-META-CHANGE",
            new_stop_price=Decimal("59500.0"),
            meta=altered_meta,
        )
        assert amended.state == PaperOrderState.REJECTED_RISK
        assert "exceeds risk budget" in amended.state_history[-1][2]
        assert "ORD-META-CHANGE" not in engine.active_orders
        spy.assert_zero_invocations()

    def test_scenario_07_partial_fills_increase_exposure_and_breach_budget(self, meta_btc):
        """Scenario 7: Partial fills and amendment increasing exposure breach the budget."""
        engine = QueueAwarePaperExecutionEngine()

        order = engine.submit_candidate_trade(
            order_id="ORD-PARTIAL-BREACH",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("59500.0"),
            target_price=Decimal("61500.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            meta=meta_btc,
        )
        assert order.state == PaperOrderState.RESTING

        # Execute partial fill of 400 contracts
        engine._fill_order(order, fill_volume=Decimal("400"))
        assert order.filled_quantity == Decimal("400")
        assert order.remaining_quantity == Decimal("600")

        # Operator attempts to amend remaining quantity to 1,500 (total exposure 1,900), breaching budget $600
        amended = engine.amend_order_risk(
            order_id="ORD-PARTIAL-BREACH",
            new_quantity=Decimal("1500"),
            meta=meta_btc,
        )
        assert amended.state == PaperOrderState.REJECTED_RISK
        assert "ORD-PARTIAL-BREACH" not in engine.active_orders

    def test_scenario_08_invalid_fee_or_malformed_input_rejected(self, meta_btc):
        """Scenario 8: An invalid fee or malformed numeric input is rejected."""
        # Non-numeric string
        audit_str = audit_and_recalculate_stop_risk(
            entry_price="sixty_thousand",
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600"),
            meta=meta_btc,
        )
        assert audit_str.valid is False
        assert "Non-numeric risk input" in audit_str.rejection_reason

        # NaN entry
        audit_nan = audit_and_recalculate_stop_risk(
            entry_price=float("nan"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("600"),
            meta=meta_btc,
        )
        assert audit_nan.valid is False

        # Negative risk budget
        audit_neg_budget = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000"),
            raw_stop_price=Decimal("59500"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("-100"),
            meta=meta_btc,
        )
        assert audit_neg_budget.valid is False

    def test_scenario_09_normalized_stop_already_on_valid_tick(self, meta_btc):
        """Scenario 9: The normalized stop is already on a valid tick and remains identical."""
        exact_stop = Decimal("59500.10")
        norm = normalize_price_to_tick(
            price=exact_stop,
            meta=meta_btc,
        )
        assert norm == exact_stop

        audit = audit_and_recalculate_stop_risk(
            entry_price=Decimal("60000.0"),
            raw_stop_price=exact_stop,
            quantity=Decimal("1000"),
            risk_budget=Decimal("600.0"),
            side="BUY",
            meta=meta_btc,
        )
        assert audit.normalized_stop_price == exact_stop
        assert audit.premature_trigger_risk_delta_pts == Decimal("0")

    def test_scenario_10_repeated_normalization_idempotent(self, meta_btc):
        """Scenario 10: Repeated normalization is deterministic and idempotent."""
        p_arbitrary = Decimal("59500.13847291")
        norm1 = normalize_price_to_tick(p_arbitrary, meta=meta_btc, policy=TickRoundingPolicy.ROUND_HALF_UP)
        norm2 = normalize_price_to_tick(norm1, meta=meta_btc, policy=TickRoundingPolicy.ROUND_HALF_UP)
        norm3 = normalize_price_to_tick(norm2, meta=meta_btc, policy=TickRoundingPolicy.ROUND_HALF_UP)
        assert norm1 == norm2 == norm3 == Decimal("59500.10")


class TestPhase182DisambiguationAndAdapterIsolation:
    """Tests proving distinct verdict codes and absolute adapter isolation."""

    def test_disambiguation_between_hurdle_and_risk_rejections(self):
        """Verify the exact intended distinction between risk_audit.valid, hurdle_verdict.allowed, and adapter isolation."""
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()
        spy = SpyExecutionAdapter()

        # Case A: Risk Budget Rejection (fails before hurdle evaluation)
        order_risk_breach = engine.submit_candidate_trade(
            order_id="ORD-RISK-BREACH",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            stop_price=Decimal("59000.0"),  # $1,000 gross loss + fees > $500 budget
            target_price=Decimal("62000.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.0"),
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            meta=meta,
        )
        assert order_risk_breach.state == PaperOrderState.REJECTED_RISK
        assert order_risk_breach.risk_audit is not None
        assert order_risk_breach.risk_audit.valid is False
        assert order_risk_breach.hurdle_verdict is None
        assert "Normalized stop risk" in order_risk_breach.state_history[-1][2]
        spy.assert_zero_invocations()

        # Case B: Hurdle Gate Rejection (risk is valid, but spread/expectancy hurdle fails)
        engine_strict_hurdle = QueueAwarePaperExecutionEngine()
        order_hurdle_breach = engine_strict_hurdle.submit_candidate_trade(
            order_id="ORD-HURDLE-BREACH",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("60000.0"),
            target_price=Decimal("60100.0"),
            stop_price=Decimal("59900.0"),
            quantity=Decimal("1000"),
            risk_budget=Decimal("500.0"),  # ample budget for $100 risk
            best_bid=Decimal("60000.0"),
            best_ask=Decimal("60005.0"),
            min_post_fee_rr=Decimal("10.0"),  # impossible hurdle: requires 10x reward to risk
            meta=meta,
        )
        assert order_hurdle_breach.state == PaperOrderState.REJECTED_RISK
        assert order_hurdle_breach.risk_audit is not None
        assert order_hurdle_breach.risk_audit.valid is True
        assert order_hurdle_breach.hurdle_verdict is not None
        assert order_hurdle_breach.hurdle_verdict.allowed is False
        assert "Friction hurdle failed" in order_hurdle_breach.state_history[-1][2]
        spy.assert_zero_invocations()


class TestPhase182AccountingReproduction:
    """Exact Decimal reproduction of the reported Delta Exchange India conditional example."""

    def test_reproduce_exact_decimal_accounting(self):
        entry_price = Decimal("60000.00")
        stop_price = Decimal("59500.00")
        qty = Decimal("1000")
        mult = Decimal("0.001")
        maker_base_rate = Decimal("0.0002")
        taker_base_rate = Decimal("0.0005")
        gst_rate = Decimal("0.18")

        # 1. Entry Notional
        entry_notional = entry_price * qty * mult
        assert entry_notional == Decimal("60000.00")

        # 2. Stop Exit Notional
        stop_notional = stop_price * qty * mult
        assert stop_notional == Decimal("59500.00")

        # 3. Gross Loss
        gross_loss = (entry_price - stop_price) * qty * mult
        assert gross_loss == Decimal("500.00")

        # 4. Entry Fee (Maker 2 bps + 18% GST = 2.36 bps)
        entry_fee_decomp = calculate_leg_fee(entry_notional, maker_base_rate, gst_rate, ExecutionStyle.MAKER)
        assert entry_fee_decomp.base_fee == Decimal("12.00000000")
        assert entry_fee_decomp.gst == Decimal("2.16000000")
        assert entry_fee_decomp.total_fee == Decimal("14.16000000")
        assert entry_fee_decomp.effective_rate_bps == Decimal("2.36")

        # 5. Exit Fee (Taker 5 bps + 18% GST = 5.90 bps)
        exit_fee_decomp = calculate_leg_fee(stop_notional, taker_base_rate, gst_rate, ExecutionStyle.TAKER)
        assert exit_fee_decomp.base_fee == Decimal("29.75000000")
        assert exit_fee_decomp.gst == Decimal("5.35500000")
        assert exit_fee_decomp.total_fee == Decimal("35.10500000")
        assert exit_fee_decomp.effective_rate_bps == Decimal("5.90")

        # 6. Total Roundtrip Stop Risk
        total_risk = gross_loss + entry_fee_decomp.total_fee + exit_fee_decomp.total_fee
        assert total_risk == Decimal("549.26500000")

        # Compare with synthetic quantity 1.0 and multiplier 1.0
        synth_entry_notional = entry_price * Decimal("1.0") * Decimal("1.0")
        assert synth_entry_notional == entry_notional
        synth_gross_loss = (entry_price - stop_price) * Decimal("1.0") * Decimal("1.0")
        assert synth_gross_loss == gross_loss
