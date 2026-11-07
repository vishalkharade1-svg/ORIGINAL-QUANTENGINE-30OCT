"""
====================================================
QuantEngine - Phase 179 Comprehensive Verification Suite
End-to-End Risk Enforcement, Stop-Rounding Adversarial Audit,
Execution Boundary Isolation & Full-Suite Reconciliation
====================================================
"""

import hashlib
import json
import os
import zipfile
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING
import pytest

from core.execution.maker_execution_model import (
    InstrumentMetadata,
    validate_instrument_constraints,
    normalize_price_to_tick,
    TickRoundingPolicy,
    FeeScheduleProvenance,
    calculate_round_trip,
    calculate_asymmetric_round_trip,
    calculate_leg_fee,
    ExecutionStyle,
    DEFAULT_GST_RATE,
    MAKER_BASE_RATE,
    TAKER_BASE_RATE,
    REBATE_BASE_RATE,
    audit_and_recalculate_stop_risk,
    StopRiskAuditResult,
)
from core.execution.friction_hurdle_gate import (
    FrictionHurdleGate,
    evaluate_friction_hurdle,
    HurdleVerdict,
)
from core.paper_trading.queue_aware_paper_engine import (
    QueueAwarePaperExecutionEngine,
    PaperOrder,
    PaperOrderState,
    QueueScenario,
    assert_no_live_adapter_invocation,
)
from core.backtesting.post_cost_backtester import (
    PostCostBacktester,
    TradeSetupCandidate,
)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DELIVERY_DIR = os.path.abspath(os.path.join(ROOT_DIR, ".."))


def _compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# =====================================================================
# PHASE 0: Baseline & Phase 178 Artifact Audit
# =====================================================================

class TestPhase0BaselineAudit:
    def test_phase178_archive_and_detached_record_match(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE178_RELEASE_CANDIDATE.zip")
        rec_path = os.path.join(DELIVERY_DIR, "RELEASE_HASH_PHASE178.txt")
        assert os.path.isfile(zip_path), f"Phase 178 zip missing: {zip_path}"
        assert os.path.isfile(rec_path), f"Phase 178 hash record missing: {rec_path}"

        computed = _compute_sha256(zip_path)
        with open(rec_path, "r", encoding="utf-8") as f:
            detached = f.read().split()[0].lower()
        assert computed == detached
        assert computed == "d1027ad727b539514fe3ceba2cee45976b69f465da53703bc176d17af2096c9c"

    def test_phase178_archive_integrity_and_cleanliness(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE178_RELEASE_CANDIDATE.zip")
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_crc = zf.testzip()
            assert bad_crc is None, f"Corrupted file in Phase 178 archive: {bad_crc}"
            infolist = zf.infolist()
            assert len(infolist) == 2155
            for info in infolist:
                assert not info.filename.startswith("/")
                assert not info.filename.startswith("\\")
                assert ".." not in info.filename.split("/")
                assert not info.filename.endswith(".pyc")
                assert "__pycache__" not in info.filename
                assert not info.filename.startswith(".git/") and info.filename != ".git"


# =====================================================================
# PHASE 1: Adversarial Tests for Stop-Risk Calculation
# =====================================================================

class TestPhase1AdversarialStopRisk:
    def test_long_and_short_within_budget(self):
        meta = InstrumentMetadata.for_btcusd()
        
        # Long position: Entry $82,000, Stop $81,950 (50 pts = $0.05 gross loss)
        # Entry fee: 82000 * 0.001 * 1 * 0.000236 = $0.019352
        # Exit fee: 81950 * 0.001 * 1 * 0.000590 = $0.0483505 -> total friction ~$0.0677
        # Total risk ~$0.1177 USD. Budget $0.1500 USD -> PASS
        res_long = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81950.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.1500"),
            side="BUY",
            meta=meta,
        )
        assert res_long.valid is True
        assert res_long.normalized_stop_price == Decimal("81950.00")
        assert res_long.total_normalized_risk_usd < Decimal("0.1500")

        # Short position: Entry $82,000, Stop $82,050 (50 pts = $0.05 gross loss)
        res_short = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("82050.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.1500"),
            side="SELL",
            meta=meta,
        )
        assert res_short.valid is True
        assert res_short.normalized_stop_price == Decimal("82050.00")
        assert res_short.total_normalized_risk_usd < Decimal("0.1500")

    def test_raw_stop_within_budget_but_normalized_exceeds_budget(self):
        """
        Adversarial test: Under FLOOR policy on Long, stop rounds down away from entry,
        expanding risk distance and breaching a tight budget.
        """
        meta = InstrumentMetadata.for_btcusd()
        # Entry 82,000, raw stop 81,900.09.
        # Under FLOOR policy, stop rounds down to 81,900.00 (expanding gross loss from 99.91 pts to 100.00 pts)
        # Raw gross: 0.09991 USD; Norm gross: 0.10000 USD.
        # Fees: ~0.06767 USD.
        # Total raw risk = 0.09991 + 0.06767 = 0.16758 USD.
        # Total norm risk = 0.10000 + 0.06767 = 0.16767 USD.
        # Set budget = 0.16760 USD: raw stop is within budget, but normalized stop breaches!
        res_expand = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.09"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.16760"),
            side="BUY",
            policy=TickRoundingPolicy.FLOOR,
            meta=meta,
        )
        assert res_expand.valid is False
        assert res_expand.risk_expansion_usd > Decimal("0")
        assert "exceeds risk budget" in res_expand.rejection_reason

    def test_raw_stop_already_outside_budget(self):
        meta = InstrumentMetadata.for_btcusd()
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81000.00"),  # 1000 pts = $1.00 gross risk
            quantity=Decimal("1"),
            risk_budget=Decimal("0.2000"),
            side="BUY",
            meta=meta,
        )
        assert res.valid is False
        assert "exceeds risk budget" in res.rejection_reason

    def test_exact_tick_boundaries_both_directions(self):
        meta = InstrumentMetadata.for_btcusd()
        # Long on tick
        res_long = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81950.10"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.2000"),
            side="LONG",
            meta=meta,
        )
        assert res_long.valid is True
        assert res_long.normalized_stop_price == Decimal("81950.10")
        assert res_long.premature_trigger_risk_delta_pts == Decimal("0.00")

        # Short on tick
        res_short = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("82050.50"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.2000"),
            side="SHORT",
            meta=meta,
        )
        assert res_short.valid is True
        assert res_short.normalized_stop_price == Decimal("82050.50")
        assert res_short.premature_trigger_risk_delta_pts == Decimal("0.00")

    def test_multiple_quantities_and_contract_multipliers(self):
        # Qty = 10, Multiplier = 0.001 -> Notional = 820 USD per leg
        res_10q = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81950.00"),
            quantity=Decimal("10"),
            risk_budget=Decimal("1.5000"),
            side="BUY",
            contract_multiplier=Decimal("0.001"),
        )
        assert res_10q.valid is True
        assert res_10q.normalized_gross_risk_usd == Decimal("0.50000000")  # 50 pts * 0.001 * 10 = $0.50

        # Multiplier = 0.01, Qty = 1 -> Notional = 820 USD
        res_01m = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81950.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("1.5000"),
            side="BUY",
            contract_multiplier=Decimal("0.01"),
        )
        assert res_01m.valid is True
        assert res_01m.normalized_gross_risk_usd == Decimal("0.50000000")

    def test_alternative_execution_styles_pricing(self):
        meta = InstrumentMetadata.for_btcusd()
        # Maker entry + Taker stop exit
        res_maker_taker = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.5000"),
            side="BUY",
            meta=meta,
            estimated_entry_style=ExecutionStyle.MAKER,
            estimated_exit_style=ExecutionStyle.TAKER,
        )
        # Taker entry + Taker stop exit
        res_taker_taker = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.5000"),
            side="BUY",
            meta=meta,
            estimated_entry_style=ExecutionStyle.TAKER,
            estimated_exit_style=ExecutionStyle.TAKER,
        )
        # Rebate entry + Maker stop exit
        res_rebate_maker = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.5000"),
            side="BUY",
            meta=meta,
            estimated_entry_style=ExecutionStyle.REBATE_VIP,
            estimated_exit_style=ExecutionStyle.MAKER,
        )
        # Taker entry has higher friction than Maker entry
        assert res_taker_taker.estimated_stop_fees_usd > res_maker_taker.estimated_stop_fees_usd
        # Rebate entry has lowest friction
        assert res_rebate_maker.estimated_stop_fees_usd < res_maker_taker.estimated_stop_fees_usd

    def test_zero_negative_and_non_finite_inputs_fail_closed(self):
        meta = InstrumentMetadata.for_btcusd()
        # Zero entry price
        assert audit_and_recalculate_stop_risk(0, 81900, 1, 0.50, meta=meta).valid is False
        # Negative stop price
        assert audit_and_recalculate_stop_risk(82000, -81900, 1, 0.50, meta=meta).valid is False
        # Zero quantity
        assert audit_and_recalculate_stop_risk(82000, 81900, 0, 0.50, meta=meta).valid is False
        # Negative risk budget
        assert audit_and_recalculate_stop_risk(82000, 81900, 1, -0.50, meta=meta).valid is False
        # Non-finite NaN
        assert audit_and_recalculate_stop_risk(82000, float("nan"), 1, 0.50, meta=meta).valid is False
        # Non-finite Inf
        assert audit_and_recalculate_stop_risk(82000, float("inf"), 1, 0.50, meta=meta).valid is False
        # None
        assert audit_and_recalculate_stop_risk(82000, None, 1, 0.50, meta=meta).valid is False

    def test_metadata_conflict_fails_closed(self):
        meta = InstrumentMetadata.for_btcusd()
        # Pass conflicting tick size 0.50 vs authoritative 0.10
        res = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.50"),
            side="BUY",
            tick_size=Decimal("0.50"),
            meta=meta,
        )
        assert res.valid is False
        assert "metadata conflict" in res.rejection_reason.lower()


# =====================================================================
# PHASE 2: Risk Enforcement at the Execution Boundary
# =====================================================================

class TestPhase2ExecutionBoundaryRiskEnforcement:
    def test_submit_candidate_trade_end_to_end_pass(self):
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()

        # Valid candidate: 150 pt target, 50 pt stop, budget $0.1500 USD
        order = engine.submit_candidate_trade(
            order_id="cand_pass_001",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("82000.00"),
            stop_price=Decimal("81950.00"),
            target_price=Decimal("82150.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.1500"),
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82005.00"),
            queue_ahead_estimate=Decimal("10"),
            meta=meta,
        )
        assert order.state == PaperOrderState.RESTING
        assert order.order_id in engine.active_orders
        assert order.stop_price == Decimal("81950.00")
        assert order.risk_audit is not None
        assert order.risk_audit.valid is True
        assert order.hurdle_verdict is not None
        assert order.hurdle_verdict.allowed is True

    def test_submit_candidate_trade_risk_budget_breach_blocks_dispatch(self):
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()

        # Candidate with stop risk ~$0.1177 USD, but budget is only $0.0500 USD
        order = engine.submit_candidate_trade(
            order_id="cand_fail_risk_002",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("82000.00"),
            stop_price=Decimal("81950.00"),
            target_price=Decimal("82150.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.0500"),  # Tight budget breached!
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82005.00"),
            queue_ahead_estimate=Decimal("10"),
            meta=meta,
        )
        assert order.state == PaperOrderState.REJECTED_RISK
        assert "exceeds risk budget" in order.state_history[-1][2]
        # Crucial invariant: rejected candidate NEVER enters active orders or reaches order dispatch
        assert order.order_id not in engine.active_orders
        assert order.order_id in engine.completed_orders

    def test_submit_candidate_trade_hurdle_failure_blocks_dispatch(self):
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()

        # 50 pt scalp: fails friction hurdle (fee ratio 77.43% > 40%)
        order = engine.submit_candidate_trade(
            order_id="cand_fail_hurdle_003",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("82000.00"),
            stop_price=Decimal("81950.00"),
            target_price=Decimal("82050.00"),  # Scalp target fails hurdle!
            quantity=Decimal("1"),
            risk_budget=Decimal("0.5000"),
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82005.00"),
            queue_ahead_estimate=Decimal("10"),
            meta=meta,
        )
        assert order.state == PaperOrderState.REJECTED_RISK
        assert "Friction hurdle failed" in order.state_history[-1][2] or "Hurdle" in order.state_history[-1][2]
        assert order.order_id not in engine.active_orders
        assert order.order_id in engine.completed_orders

    def test_amend_order_risk_breach_cancels_active_order(self):
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()

        # 1. Submit passing candidate
        order = engine.submit_candidate_trade(
            order_id="cand_amend_004",
            symbol="BTCUSD",
            side="BUY",
            entry_price=Decimal("82000.00"),
            stop_price=Decimal("81950.00"),
            target_price=Decimal("82150.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.1500"),
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82005.00"),
            queue_ahead_estimate=Decimal("10"),
            meta=meta,
        )
        assert order.state == PaperOrderState.RESTING
        assert order.order_id in engine.active_orders

        # 2. Amend quantity from 1 to 5 contracts without increasing budget ($0.1500)
        # 5 contracts expand gross loss from $0.05 to $0.25 USD -> breaches budget!
        amended = engine.amend_order_risk(
            order_id="cand_amend_004",
            new_quantity=Decimal("5"),
            meta=meta,
        )
        assert amended.state == PaperOrderState.REJECTED_RISK
        assert amended.order_id not in engine.active_orders
        assert amended.order_id in engine.completed_orders
        assert "Amendment rejected" in amended.state_history[-1][2]

    def test_post_cost_backtester_risk_budget_enforcement(self):
        tester = PostCostBacktester(execution_style=ExecutionStyle.MAKER)
        
        # Candidate within risk budget
        cand_pass = TradeSetupCandidate(
            setup_id="s_pass",
            symbol="BTCUSD",
            entry_price=Decimal("82000.00"),
            target_price=Decimal("82150.00"),
            stop_price=Decimal("81950.00"),
            quantity=Decimal("1"),
            multiplier=Decimal("0.001"),
            entry_style=ExecutionStyle.MAKER,
            exit_style=ExecutionStyle.TAKER,
            risk_budget=Decimal("0.1500"),
        )
        verdict_pass = tester.evaluate_candidate(cand_pass)
        assert verdict_pass.allowed is True

        # Candidate exceeding risk budget
        cand_breach = TradeSetupCandidate(
            setup_id="s_breach",
            symbol="BTCUSD",
            entry_price=Decimal("82000.00"),
            target_price=Decimal("82150.00"),
            stop_price=Decimal("81950.00"),
            quantity=Decimal("1"),
            multiplier=Decimal("0.001"),
            entry_style=ExecutionStyle.MAKER,
            exit_style=ExecutionStyle.TAKER,
            risk_budget=Decimal("0.0500"),  # Breaches budget!
        )
        verdict_breach = tester.evaluate_candidate(cand_breach)
        assert verdict_breach.allowed is False
        assert "Stop risk budget breached" in verdict_breach.rejection_reason

    def test_execution_isolation_maintained(self):
        engine = QueueAwarePaperExecutionEngine()
        assert engine.assert_no_live_adapter_invocation() is True
        assert assert_no_live_adapter_invocation() is True


# =====================================================================
# PHASE 3: Stop-Rounding Policy Trade-offs
# =====================================================================

class TestPhase3StopRoundingTradeoffs:
    def test_conservative_rounding_long_and_short_invariants(self):
        meta = InstrumentMetadata.for_btcusd()
        
        # Long position: Entry $82,000, raw stop $81,900.04
        # Conservative rounds ceiling up to $81,900.10 (closer to entry)
        norm_long = normalize_price_to_tick(
            Decimal("81900.04"),
            meta.tick_size,
            policy=TickRoundingPolicy.CONSERVATIVE,
            side="LONG",
            is_stop=True,
            meta=meta,
        )
        assert norm_long == Decimal("81900.10")
        raw_gross_loss_long = (Decimal("82000.00") - Decimal("81900.04")) * Decimal("0.001")
        norm_gross_loss_long = (Decimal("82000.00") - norm_long) * Decimal("0.001")
        # Invariant: Planned gross loss strictly preserved or reduced
        assert norm_gross_loss_long <= raw_gross_loss_long

        # Short position: Entry $82,000, raw stop $82,099.96
        # Conservative rounds floor down to $82,099.90 (closer to entry)
        norm_short = normalize_price_to_tick(
            Decimal("82099.96"),
            meta.tick_size,
            policy=TickRoundingPolicy.CONSERVATIVE,
            side="SHORT",
            is_stop=True,
            meta=meta,
        )
        assert norm_short == Decimal("82099.90")
        raw_gross_loss_short = (Decimal("82099.96") - Decimal("82000.00")) * Decimal("0.001")
        norm_gross_loss_short = (norm_short - Decimal("82000.00")) * Decimal("0.001")
        assert norm_gross_loss_short <= raw_gross_loss_short

    def test_premature_trigger_displacement_bounded_by_tick_size(self):
        meta = InstrumentMetadata.for_btcusd()
        # For long stop, ceiling up moves trigger up by at most 0.10 USD
        for offset in ["0.01", "0.05", "0.09"]:
            raw_sp = Decimal("81900.00") + Decimal(offset)
            norm_sp = normalize_price_to_tick(raw_sp, meta.tick_size, policy=TickRoundingPolicy.CONSERVATIVE, side="LONG", is_stop=True, meta=meta)
            delta = norm_sp - raw_sp
            assert Decimal("0") < delta <= Decimal("0.10")
