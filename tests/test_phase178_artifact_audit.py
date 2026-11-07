"""
====================================================
QuantEngine - Phase 178 Comprehensive Verification Suite
Independent Artifact Audit, Stop-Rounding Risk Semantics,
Hurdle Gate Enforcement & Full-Suite Reconciliation
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


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DELIVERY_DIR = os.path.abspath(os.path.join(ROOT_DIR, ".."))


def _compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _load_json(rel_path: str):
    p = os.path.join(ROOT_DIR, rel_path)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# =====================================================================
# PHASE 0: Baseline & Phase 177 Artifact Verification
# =====================================================================

class TestPhase0ArtifactAudit:
    def test_phase177_archive_hash_matches_detached_record(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE177_RELEASE_CANDIDATE.zip")
        rec_path = os.path.join(DELIVERY_DIR, "RELEASE_HASH_PHASE177.txt")
        assert os.path.isfile(zip_path), f"Phase 177 zip missing: {zip_path}"
        assert os.path.isfile(rec_path), f"Phase 177 hash record missing: {rec_path}"

        computed = _compute_sha256(zip_path)
        with open(rec_path, "r", encoding="utf-8") as f:
            detached = f.read().split()[0]
        assert computed == detached
        assert computed == "f5a7c394f3713a90608d52466eb0c3dd5cf132ade7ee44ddf83dcd95c64e7101"

    def test_phase177_archive_integrity_and_cleanliness(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE177_RELEASE_CANDIDATE.zip")
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_crc = zf.testzip()
            assert bad_crc is None, f"Corrupted file in Phase 177 archive: {bad_crc}"
            infolist = zf.infolist()
            assert len(infolist) == 2140
            for info in infolist:
                assert not info.filename.startswith("/")
                assert not info.filename.startswith("\\")
                assert ".." not in info.filename
                assert not info.filename.endswith(".pyc")
                assert "__pycache__" not in info.filename
                assert not info.filename.startswith(".git/") and info.filename != ".git"


# =====================================================================
# PHASE 1: End-to-End Tick-Size Enforcement Trace
# =====================================================================

class TestPhase1TickEnforcementTrace:
    def test_product84_metadata_authority(self):
        meta = InstrumentMetadata.for_btcusd()
        assert meta.symbol == "BTCUSD"
        assert meta.tick_size == Decimal("0.10")
        assert meta.step_size == Decimal("1")
        assert meta.quantity_step == Decimal("1")
        assert meta.min_quantity == Decimal("1")
        assert meta.contract_multiplier == Decimal("0.001")
        assert meta.settlement_currency == "USD"

    def test_conflicting_metadata_rejected(self):
        meta = InstrumentMetadata.for_btcusd()
        # Attempting to supply conflicting tick size 0.50 against authoritative 0.10 metadata
        valid, err = validate_instrument_constraints(
            price=Decimal("82000.50"),
            quantity=Decimal("1"),
            tick_size=Decimal("0.50"),
            meta=meta,
            raise_exception=False,
        )
        assert valid is False
        assert "metadata conflict" in err.lower()

    def test_tick_grid_enforcement_at_executable_boundary(self):
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()

        # On-tick price passes
        order_on_tick = engine.submit_limit_post_only(
            order_id="p178_trace_01",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81950.10"),
            quantity=Decimal("1"),
            best_bid=Decimal("81950.00"),
            best_ask=Decimal("81955.00"),
            queue_ahead_estimate=Decimal("10"),
            tick_size=meta.tick_size,
        )
        assert order_on_tick.state == PaperOrderState.RESTING
        assert order_on_tick.tick_size == Decimal("0.10")

        # Off-tick price rejected at executable boundary
        order_off_tick = engine.submit_limit_post_only(
            order_id="p178_trace_02",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81950.15"),
            quantity=Decimal("1"),
            best_bid=Decimal("81950.00"),
            best_ask=Decimal("81955.00"),
            queue_ahead_estimate=Decimal("10"),
            tick_size=meta.tick_size,
        )
        assert order_off_tick.state == PaperOrderState.REJECTED_CONSTRAINTS
        assert "tick size" in order_off_tick.state_history[-1][2].lower()


# =====================================================================
# PHASE 2: Stop-Loss Rounding & Risk Semantics Audit
# =====================================================================

class TestPhase2StopRoundingAndRiskSemantics:
    def test_long_stop_rounding_conservative_risk_preservation(self):
        # Entry: 82000.00
        # Raw stop: 81900.14 (99.86 pts distance)
        # Conservative rounding ceilings up to 81900.20 (99.80 pts distance)
        meta = InstrumentMetadata.for_btcusd()
        result = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.14"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.20"),  # 0.20 USD budget
            side="BUY",
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta,
        )
        assert result.valid is True
        assert result.normalized_stop_price == Decimal("81900.20")
        assert result.raw_stop_distance == Decimal("99.86")
        assert result.normalized_stop_distance == Decimal("99.80")
        assert result.normalized_stop_distance < result.raw_stop_distance
        # Planned gross risk is reduced: 99.80 * 0.001 = 0.0998 USD <= 0.09986 USD
        assert result.risk_expansion_usd < Decimal("0")
        # Trigger is closer to current market by 0.06 pts -> premature trigger delta
        assert result.premature_trigger_risk_delta_pts == Decimal("0.06")

    def test_short_stop_rounding_conservative_risk_preservation(self):
        # Entry: 82000.00
        # Raw stop: 82099.86 (99.86 pts distance)
        # Conservative rounding floors down to 82099.80 (99.80 pts distance)
        meta = InstrumentMetadata.for_btcusd()
        result = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("82099.86"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.20"),
            side="SELL",
            policy=TickRoundingPolicy.CONSERVATIVE,
            meta=meta,
        )
        assert result.valid is True
        assert result.normalized_stop_price == Decimal("82099.80")
        assert result.raw_stop_distance == Decimal("99.86")
        assert result.normalized_stop_distance == Decimal("99.80")
        assert result.normalized_stop_distance < result.raw_stop_distance
        assert result.risk_expansion_usd < Decimal("0")
        assert result.premature_trigger_risk_delta_pts == Decimal("0.06")

    def test_stop_geometry_validation_fails_closed(self):
        meta = InstrumentMetadata.for_btcusd()

        # Inverted long stop: stop above entry
        res_long_inv = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("82100.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("1.00"),
            side="BUY",
            meta=meta,
        )
        assert res_long_inv.valid is False
        assert "invalid long stop geometry" in res_long_inv.rejection_reason.lower()

        # Inverted short stop: stop below entry
        res_short_inv = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.00"),
            quantity=Decimal("1"),
            risk_budget=Decimal("1.00"),
            side="SELL",
            meta=meta,
        )
        assert res_short_inv.valid is False
        assert "invalid short stop geometry" in res_short_inv.rejection_reason.lower()

    def test_risk_budget_breach_rejection(self):
        # Entry 82000, raw stop 81900.14 -> norm stop 81900.20 (distance 99.80 pts)
        # Qty = 1, mult = 0.001 -> gross loss = 0.0998 USD
        # Fees approx = 0.0193 + 0.0483 = 0.0676 USD
        # Total norm risk approx = 0.1674 USD
        # If budget = 0.10 USD, setup MUST be rejected!
        meta = InstrumentMetadata.for_btcusd()
        result = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.14"),
            quantity=Decimal("1"),
            risk_budget=Decimal("0.10"),  # Insufficient budget
            side="BUY",
            meta=meta,
        )
        assert result.valid is False
        assert "exceeds risk budget" in result.rejection_reason.lower()

    def test_forced_stop_expansion_policy_audited(self):
        # If caller forces FLOOR on a long stop (81900.14 -> 81900.10):
        # distance expands from 99.86 to 99.90 pts -> risk_expansion > 0
        meta = InstrumentMetadata.for_btcusd()
        result = audit_and_recalculate_stop_risk(
            entry_price=Decimal("82000.00"),
            raw_stop_price=Decimal("81900.14"),
            quantity=Decimal("1"),
            risk_budget=Decimal("1.00"),
            side="BUY",
            policy=TickRoundingPolicy.FLOOR,
            meta=meta,
        )
        assert result.valid is True
        assert result.normalized_stop_price == Decimal("81900.10")
        assert result.normalized_stop_distance == Decimal("99.90")
        assert result.risk_expansion_usd > Decimal("0")
        # Trigger moved further from market (negative premature trigger delta)
        assert result.premature_trigger_risk_delta_pts == Decimal("-0.04")


# =====================================================================
# PHASE 3: Fee & Economics Independent Reproduction
# =====================================================================

class TestPhase3EconomicsReproduction:
    def test_fee_rates_and_effective_tax(self):
        # Maker: 0.0002, Taker: 0.0005, GST: 0.18
        notional = Decimal("1000.00")
        maker = calculate_leg_fee(notional, MAKER_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.MAKER)
        taker = calculate_leg_fee(notional, TAKER_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.TAKER)
        rebate = calculate_leg_fee(notional, REBATE_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.REBATE_VIP)

        assert maker.effective_rate_bps == Decimal("2.36")
        assert taker.effective_rate_bps == Decimal("5.90")
        assert rebate.effective_rate_bps == Decimal("-1.00")

    def test_canonical_6_setups_reproduced(self):
        # Entry 82000, 1 Contract, Multiplier 0.001
        ep = Decimal("82000.00")
        cm = Decimal("0.001")
        qty = Decimal("1")

        setups = [
            (Decimal("4.5"), Decimal("82004.50")),
            (Decimal("15.0"), Decimal("82015.00")),
            (Decimal("50.0"), Decimal("82050.00")),
            (Decimal("150.0"), Decimal("82150.00")),
            (Decimal("500.0"), Decimal("82500.00")),
            (Decimal("1500.0"), Decimal("83500.00")),
        ]
        for pts, xp in setups:
            rt_taker = calculate_round_trip(ep, xp, qty, cm, ExecutionStyle.TAKER)
            rt_asym = calculate_asymmetric_round_trip(ep, xp, qty, cm, ExecutionStyle.MAKER, ExecutionStyle.TAKER)
            gross = (xp - ep) * cm * qty
            assert rt_taker.gross_pnl == gross
            assert rt_asym.gross_pnl == gross
            assert rt_asym.total_fees < rt_taker.total_fees


# =====================================================================
# PHASE 4: Hurdle Gate Enforcement
# =====================================================================

class TestPhase4HurdleGateEnforcement:
    def test_hurdle_rule1_subsumes_rule2_proof(self):
        # Fee ratio = 40.0% -> Multiple = 2.50x >= 2.0x
        v = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.0"),
            round_trip_fee_points=Decimal("40.0"),
            stop_loss_points=Decimal("20.0"),
            contract_multiplier=Decimal("0.001"),
        )
        assert v.rule1_fee_ratio_pass is True
        assert v.rule2_target_multiple_pass is True

    def test_rejected_candidate_halts_at_dispatch(self):
        # Target 10 pts, fee 10 pts -> fee ratio 100% -> fails gate
        v = evaluate_friction_hurdle(
            gross_target_points=Decimal("10.0"),
            round_trip_fee_points=Decimal("10.0"),
            stop_loss_points=Decimal("5.0"),
            contract_multiplier=Decimal("0.001"),
        )
        assert v.allowed is False
        assert v.rejection_reason is not None


# =====================================================================
# PHASE 5 & 6: Execution Isolation & State Machine
# =====================================================================

class TestPhase5ExecutionIsolation:
    def test_assert_no_live_adapter_invocation_invariant(self):
        assert assert_no_live_adapter_invocation() is True
        engine = QueueAwarePaperExecutionEngine()
        assert engine.assert_no_live_adapter_invocation() is True

    def test_zero_fills_for_rejected_orders(self):
        engine = QueueAwarePaperExecutionEngine()
        order = engine.submit_limit_post_only(
            order_id="p178_iso_01",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("82005.00"),
            quantity=Decimal("1"),
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82002.00"),  # crosses ask
            queue_ahead_estimate=Decimal("5"),
        )
        assert order.state == PaperOrderState.REJECTED_POST_ONLY
        assert order.filled_quantity == Decimal("0")
        assert len(order.fills) == 0
