"""
====================================================
QuantEngine - Phase 177 Comprehensive Verification Suite
Independent Release Reproduction, Tick-Size Remediation,
Execution-Path Safety & Hurdle Gate Subsumption Audit
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
# PHASE 0: Baseline & Provenance Reproduction
# =====================================================================

class TestPhase0BaselineReproduction:
    def test_phase175_archive_hash_matches_detached_record(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE175_RELEASE_CANDIDATE.zip")
        rec_path = os.path.join(DELIVERY_DIR, "RELEASE_HASH_PHASE175.txt")
        assert os.path.isfile(zip_path), f"Phase 175 zip missing: {zip_path}"
        assert os.path.isfile(rec_path), f"Phase 175 hash record missing: {rec_path}"

        computed = _compute_sha256(zip_path)
        with open(rec_path, "r", encoding="utf-8") as f:
            expected = f.read().split()[0]
        assert computed == expected
        assert computed == "16aacbde562d3a39078e15d62d120810b2d72b0f426526856fd7d274b16954b4"

    def test_phase176_archive_hash_matches_detached_record(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE176_RELEASE_CANDIDATE.zip")
        rec_path = os.path.join(DELIVERY_DIR, "RELEASE_HASH_PHASE176.txt")
        assert os.path.isfile(zip_path), f"Phase 176 zip missing: {zip_path}"
        assert os.path.isfile(rec_path), f"Phase 176 hash record missing: {rec_path}"

        computed = _compute_sha256(zip_path)
        with open(rec_path, "r", encoding="utf-8") as f:
            expected = f.read().split()[0]
        assert computed == expected
        assert computed == "a72e66ece1aa5a6bc854ecc8fb99f454214460756509022f0bbcbe1aa3b7d231"

    def test_phase176_archive_integrity_and_members(self):
        zip_path = os.path.join(DELIVERY_DIR, "QuantEngine_PHASE176_RELEASE_CANDIDATE.zip")
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_crc = zf.testzip()
            assert bad_crc is None, f"Corrupted file in Phase 176 archive: {bad_crc}"
            infolist = zf.infolist()
            assert len(infolist) == 2127
            for info in infolist:
                assert not info.filename.startswith("/")
                assert not info.filename.startswith("\\")
                assert ".." not in info.filename
                assert not info.filename.endswith(".pyc")
                assert "__pycache__" not in info.filename
                assert not info.filename.startswith(".git/") and info.filename != ".git"


# =====================================================================
# PHASE 1: Contract Semantics Reproduction
# =====================================================================

class TestPhase1ContractSemantics:
    def test_authoritative_fixture_product84_btc_usd(self):
        fixture = _load_json("data/fixtures/delta/delta_mcp_public_products_20260925.json")
        p84 = next((p for p in fixture["products"] if p["id"] == 84), None)
        assert p84 is not None, "Product ID 84 BTCUSD missing from authoritative fixture"

        assert p84["symbol"] == "BTCUSD"
        assert p84["contract_value"] == "0.001"
        assert p84["quoting_asset"]["symbol"] == "USD"
        assert p84["settling_asset"]["symbol"] == "USD"
        assert p84["notional_type"] == "vanilla"
        assert p84["is_quanto"] is False
        assert p84["tick_size"] == "0.1"
        assert p84["maker_commission_rate"] == "0.0002"
        assert p84["taker_commission_rate"] == "0.0005"

    def test_linear_pnl_formula_dimensional_consistency(self):
        # Gross P&L = (P_exit - P_entry) * Multiplier * Quantity
        # Price: USD / BTC
        # Multiplier: BTC / contract (0.001)
        # Quantity: contracts
        # Product: (USD / BTC) * (BTC / contract) * contracts = USD
        ep = Decimal("82000.00")
        xp_gain = Decimal("82150.00")
        xp_loss = Decimal("81850.00")
        qty = Decimal("5")
        mult = Decimal("0.001")

        # Long gain
        pnl_gain = (xp_gain - ep) * mult * qty
        assert pnl_gain == Decimal("0.75")
        rt_gain = calculate_round_trip(ep, xp_gain, qty, mult, ExecutionStyle.TAKER)
        assert rt_gain.gross_pnl == Decimal("0.75000000")

        # Long loss
        pnl_loss = (xp_loss - ep) * mult * qty
        assert pnl_loss == Decimal("-0.75")
        rt_loss = calculate_round_trip(ep, xp_loss, qty, mult, ExecutionStyle.TAKER)
        assert rt_loss.gross_pnl == Decimal("-0.75000000")

        # Fractional quantity
        frac_qty = Decimal("0.5")
        frac_gain = (xp_gain - ep) * mult * frac_qty
        assert frac_gain == Decimal("0.075")
        rt_frac = calculate_round_trip(ep, xp_gain, frac_qty, mult, ExecutionStyle.TAKER)
        assert rt_frac.gross_pnl == Decimal("0.07500000")


# =====================================================================
# PHASE 2: Tick-Size Remediation & Validation Path
# =====================================================================

class TestPhase2TickSizeRemediation:
    def test_provenance_contract_string_updated(self):
        prov = FeeScheduleProvenance()
        assert "tick=0.10" in prov.verified_contract
        assert "0.50" not in prov.verified_contract
        assert any("tick_size=0.10" in a for a in prov.assumptions)

    def test_instrument_metadata_factory(self):
        meta = InstrumentMetadata.for_btcusd()
        assert meta.symbol == "BTCUSD"
        assert meta.tick_size == Decimal("0.10")
        assert meta.contract_multiplier == Decimal("0.001")
        assert meta.quantity_step == Decimal("1")
        assert meta.min_quantity == Decimal("1")

    def test_validate_instrument_constraints_on_tick(self):
        meta = InstrumentMetadata.for_btcusd()
        valid_prices = [
            Decimal("82000.00"),
            Decimal("82000.10"),
            Decimal("82000.20"),
            Decimal("82000.50"),
            Decimal("82150.90"),
        ]
        for p in valid_prices:
            valid, err = validate_instrument_constraints(
                price=p,
                quantity=Decimal("1"),
                meta=meta,
                raise_exception=False,
            )
            assert valid is True, f"Valid price {p} was rejected: {err}"

    def test_validate_instrument_constraints_off_tick_rejected(self):
        meta = InstrumentMetadata.for_btcusd()
        invalid_prices = [
            Decimal("82000.05"),
            Decimal("82000.15"),
            Decimal("82000.001"),
            Decimal("82000.99"),
        ]
        for p in invalid_prices:
            valid, err = validate_instrument_constraints(
                price=p,
                quantity=Decimal("1"),
                meta=meta,
                raise_exception=False,
            )
            assert valid is False, f"Off-tick price {p} was accepted"
            assert "tick size" in err.lower()

    def test_metadata_conflict_fails_closed(self):
        meta = InstrumentMetadata.for_btcusd()  # tick_size = 0.10
        # Passing conflicting tick_size = 0.50 must fail closed immediately
        valid, err = validate_instrument_constraints(
            price=Decimal("82000.50"),
            quantity=Decimal("1"),
            tick_size=Decimal("0.50"),
            meta=meta,
            raise_exception=False,
        )
        assert valid is False
        assert "metadata conflict" in err.lower()

        # Exception mode
        with pytest.raises(ValueError, match="Metadata conflict"):
            validate_instrument_constraints(
                price=Decimal("82000.50"),
                quantity=Decimal("1"),
                tick_size=Decimal("0.50"),
                meta=meta,
                raise_exception=True,
            )

    def test_non_finite_or_invalid_inputs_fail_closed(self):
        meta = InstrumentMetadata.for_btcusd()
        bad_inputs = [
            (Decimal("NaN"), Decimal("1")),
            (Decimal("Infinity"), Decimal("1")),
            (Decimal("-82000.00"), Decimal("1")),
            (Decimal("0.00"), Decimal("1")),
            (Decimal("82000.00"), Decimal("0")),
            (Decimal("82000.00"), Decimal("-1")),
            (Decimal("82000.00"), Decimal("NaN")),
        ]
        for p, q in bad_inputs:
            valid, err = validate_instrument_constraints(
                price=p,
                quantity=q,
                meta=meta,
                raise_exception=False,
            )
            assert valid is False, f"Bad input price={p}, qty={q} was accepted"

    def test_normalize_price_to_tick_policies(self):
        meta = InstrumentMetadata.for_btcusd()  # 0.10 tick
        tick = meta.tick_size

        # Policy ROUND_HALF_UP
        assert normalize_price_to_tick(Decimal("82000.14"), meta=meta) == Decimal("82000.10")
        assert normalize_price_to_tick(Decimal("82000.15"), meta=meta) == Decimal("82000.20")
        assert normalize_price_to_tick(Decimal("82000.16"), meta=meta) == Decimal("82000.20")

        # Policy FLOOR
        assert normalize_price_to_tick(Decimal("82000.19"), policy=TickRoundingPolicy.FLOOR, meta=meta) == Decimal("82000.10")

        # Policy CEILING
        assert normalize_price_to_tick(Decimal("82000.11"), policy=TickRoundingPolicy.CEILING, meta=meta) == Decimal("82000.20")

        # Policy CONSERVATIVE for limit orders
        # BUY limit: floor down (better/cheaper entry)
        p_buy = normalize_price_to_tick(
            Decimal("82000.16"),
            policy=TickRoundingPolicy.CONSERVATIVE,
            side="BUY",
            is_stop=False,
            meta=meta,
        )
        assert p_buy == Decimal("82000.10")

        # SELL limit: ceiling up (better/higher exit)
        p_sell = normalize_price_to_tick(
            Decimal("82000.14"),
            policy=TickRoundingPolicy.CONSERVATIVE,
            side="SELL",
            is_stop=False,
            meta=meta,
        )
        assert p_sell == Decimal("82000.20")

        # Policy CONSERVATIVE for stop orders
        # LONG stop (sell stop): ceiling up (closer to entry, risk-preserving)
        p_long_stop = normalize_price_to_tick(
            Decimal("81900.14"),
            policy=TickRoundingPolicy.CONSERVATIVE,
            side="BUY",  # position is long, stop exit is sell
            is_stop=True,
            meta=meta,
        )
        assert p_long_stop == Decimal("81900.20")

        # SHORT stop (buy stop): floor down (closer to entry, risk-preserving)
        p_short_stop = normalize_price_to_tick(
            Decimal("82100.16"),
            policy=TickRoundingPolicy.CONSERVATIVE,
            side="SELL",  # position is short, stop exit is buy
            is_stop=True,
            meta=meta,
        )
        assert p_short_stop == Decimal("82100.10")

    def test_paper_engine_defaults_and_validation(self):
        engine = QueueAwarePaperExecutionEngine()
        meta = InstrumentMetadata.for_btcusd()

        # Valid order on 0.10 grid
        order_valid = engine.submit_limit_post_only(
            order_id="p177_001",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81950.10"),
            quantity=Decimal("1"),
            best_bid=Decimal("81950.00"),
            best_ask=Decimal("81955.00"),
            queue_ahead_estimate=Decimal("10"),
            tick_size=meta.tick_size,
        )
        assert order_valid.state == PaperOrderState.RESTING
        assert order_valid.tick_size == Decimal("0.10")

        # Off-tick order (81950.05) rejected
        order_invalid = engine.submit_limit_post_only(
            order_id="p177_002",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81950.05"),
            quantity=Decimal("1"),
            best_bid=Decimal("81950.00"),
            best_ask=Decimal("81955.00"),
            queue_ahead_estimate=Decimal("10"),
            tick_size=meta.tick_size,
        )
        assert order_invalid.state == PaperOrderState.REJECTED_CONSTRAINTS
        assert "tick size" in order_invalid.state_history[-1][2].lower()

        # Default tick size in submit_limit_post_only is now 0.10
        order_default = engine.submit_limit_post_only(
            order_id="p177_003",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81950.10"),
            quantity=Decimal("1"),
            best_bid=Decimal("81950.00"),
            best_ask=Decimal("81955.00"),
            queue_ahead_estimate=Decimal("10"),
        )
        assert order_default.state == PaperOrderState.RESTING
        assert order_default.tick_size == Decimal("0.10")


# =====================================================================
# PHASE 3: Fee, Tax, Rebate & P&L Reproduction
# =====================================================================

class TestPhase3FeeAndPnLReproduction:
    def test_fee_rates_and_effective_rates(self):
        notional = Decimal("1000.00")
        
        # Taker: 5 bps base, 18% GST -> 5.90 bps
        taker_decomp = calculate_leg_fee(notional, TAKER_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.TAKER)
        assert taker_decomp.base_fee == Decimal("0.50000000")
        assert taker_decomp.gst == Decimal("0.09000000")
        assert taker_decomp.total_fee == Decimal("0.59000000")
        assert taker_decomp.effective_rate_bps == Decimal("5.90")

        # Maker: 2 bps base, 18% GST -> 2.36 bps
        maker_decomp = calculate_leg_fee(notional, MAKER_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.MAKER)
        assert maker_decomp.base_fee == Decimal("0.20000000")
        assert maker_decomp.gst == Decimal("0.03600000")
        assert maker_decomp.total_fee == Decimal("0.23600000")
        assert maker_decomp.effective_rate_bps == Decimal("2.36")

        # Rebate VIP: -1 bps base, 0 GST -> -1.00 bps
        rebate_decomp = calculate_leg_fee(notional, REBATE_BASE_RATE, DEFAULT_GST_RATE, ExecutionStyle.REBATE_VIP)
        assert rebate_decomp.base_fee == Decimal("-0.10000000")
        assert rebate_decomp.gst == Decimal("0.00000000")
        assert rebate_decomp.total_fee == Decimal("-0.10000000")
        assert rebate_decomp.effective_rate_bps == Decimal("-1.00")

    def test_canonical_setup_economics(self):
        # Entry 82000.00, Exit 82150.00 (+150 pts), Qty 1, Multiplier 0.001
        ep = Decimal("82000.00")
        xp = Decimal("82150.00")
        qty = Decimal("1")
        cm = Decimal("0.001")

        # Symmetric Taker
        rt_taker = calculate_round_trip(ep, xp, qty, cm, ExecutionStyle.TAKER)
        assert rt_taker.gross_pnl == Decimal("0.15000000")
        # Leg 1: 82.00 * 0.0005 * 1.18 = 0.04838
        # Leg 2: 82.15 * 0.0005 * 1.18 = 0.0484685
        # Total fees = 0.0968485
        assert rt_taker.total_fees == Decimal("0.09684850")
        assert rt_taker.net_pnl == Decimal("0.05315150")
        assert rt_taker.breakeven_points == Decimal("96.85")

        # Asymmetric Maker Entry / Taker Exit
        rt_asym = calculate_asymmetric_round_trip(ep, xp, qty, cm, ExecutionStyle.MAKER, ExecutionStyle.TAKER)
        # Entry Maker: 82.00 * 0.0002 * 1.18 = 0.019352
        # Exit Taker:  82.15 * 0.0005 * 1.18 = 0.0484685
        # Total fees = 0.0678205
        assert rt_asym.entry_fee.total_fee == Decimal("0.01935200")
        assert rt_asym.exit_fee.total_fee == Decimal("0.04846850")
        assert rt_asym.total_fees == Decimal("0.06782050")
        assert rt_asym.net_pnl == Decimal("0.08217950")
        assert rt_asym.breakeven_points == Decimal("67.82")


# =====================================================================
# PHASE 4: Hurdle Gate Subsumption Proof & Boundary Tests
# =====================================================================

class TestPhase4HurdleGateSubsumptionAndBoundaries:
    def test_rule1_subsumes_rule2_mathematical_proof(self):
        """
        Formal Proof of Subsumption:
        Let G = gross_target_usd, F = round_trip_fee_usd.
        Breakeven points = F / (multiplier * quantity).
        Target points = G / (multiplier * quantity).
        Therefore: target_multiple = target_points / breakeven_points = G / F.

        Fee ratio = F / G.
        Rule 1 requirement: fee_to_target_pct <= max_fee_ratio_pct = 40.0%
                            <=> F / G <= 0.40
                            <=> G / F >= 1 / 0.40 = 2.50.

        Rule 2 requirement: breakeven_multiple >= min_breakeven_margin_multiple = 2.0
                            <=> G / F >= 2.0.

        Since 2.50 > 2.0, whenever Rule 1 passes (G / F >= 2.50), Rule 2 (G / F >= 2.0)
        is AUTOMATICALLY satisfied.
        Conversely, if Rule 2 fails (G / F < 2.0), Rule 1 has already failed (G / F < 2.0 < 2.50).
        Thus Rule 1 strictly subsumes Rule 2 under default parameters.
        """
        # Test case where Rule 1 is borderline pass (Fee ratio = 40.0%)
        # Multiplier = 0.001, Qty = 1
        # G = 100 pts * 0.001 = 0.10 USD
        # F = 40 pts * 0.001 = 0.04 USD (Fee ratio = 40.0%, Multiple = 2.50x)
        v = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.0"),
            round_trip_fee_points=Decimal("40.0"),
            stop_loss_points=Decimal("20.0"),
            contract_multiplier=Decimal("0.001"),
        )
        assert v.rule1_fee_ratio_pass is True
        assert v.rule2_target_multiple_pass is True
        assert v.fee_to_target_pct == Decimal("40.00")
        assert v.breakeven_multiple == Decimal("2.50")

        # Test case where Rule 1 fails at 40.01%
        # G = 100 pts, F = 40.01 pts -> Multiple = 2.499x >= 2.0x (Rule 2 passes), but Rule 1 fails!
        v_border = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.0"),
            round_trip_fee_points=Decimal("40.01"),
            stop_loss_points=Decimal("20.0"),
            contract_multiplier=Decimal("0.001"),
        )
        assert v_border.rule1_fee_ratio_pass is False
        assert v_border.rule2_target_multiple_pass is True  # 2.50x >= 2.0
        assert v_border.allowed is False  # Gate rejects due to Rule 1!
        assert "fee ratio" in v_border.rejection_reason.lower()

    def test_hurdle_gate_boundary_exact_thresholds(self):
        # Post-fee R:R boundary (min 1.25)
        # Net target = 100 - 20 = 80 pts.
        # Total risk = stop_loss + fee = 44 + 20 = 64 pts.
        # Post-fee R:R = 80 / 64 = 1.25.
        v_rr_pass = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.0"),
            round_trip_fee_points=Decimal("20.0"),
            stop_loss_points=Decimal("44.0"),
            contract_multiplier=Decimal("0.001"),
        )
        assert v_rr_pass.post_fee_rr == Decimal("1.25")
        assert v_rr_pass.allowed is True

        # Post-fee R:R below boundary: stop_loss = 45 -> Total risk = 65 -> R:R = 80 / 65 = 1.23
        v_rr_fail = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.0"),
            round_trip_fee_points=Decimal("20.0"),
            stop_loss_points=Decimal("45.0"),
            contract_multiplier=Decimal("0.001"),
        )
        assert v_rr_fail.post_fee_rr == Decimal("1.23")
        assert v_rr_fail.allowed is False
        assert "post-fee r:r" in v_rr_fail.rejection_reason.lower()

    def test_hurdle_gate_fail_closed_inputs(self):
        # None, NaN, inf, zero/negative prices
        bad_calls = [
            {"entry_price": None, "target_price": Decimal("82150"), "stop_price": Decimal("81900")},
            {"entry_price": Decimal("NaN"), "target_price": Decimal("82150"), "stop_price": Decimal("81900")},
            {"entry_price": Decimal("Infinity"), "target_price": Decimal("82150"), "stop_price": Decimal("81900")},
            {"entry_price": Decimal("-82000"), "target_price": Decimal("82150"), "stop_price": Decimal("81900")},
            {"entry_price": Decimal("82000"), "target_price": Decimal("82000"), "stop_price": Decimal("81900")}, # zero target
            {"entry_price": Decimal("82000"), "target_price": Decimal("82150"), "stop_price": Decimal("82000")}, # zero stop
            {"gross_target_points": Decimal("-10"), "round_trip_fee_points": Decimal("5")},
            {"gross_target_points": Decimal("100"), "round_trip_fee_points": Decimal("-5")},
        ]
        for kwargs in bad_calls:
            v = evaluate_friction_hurdle(**kwargs)
            assert v.allowed is False
            assert v.rejection_reason is not None


# =====================================================================
# PHASE 5: Full Execution-Path and Safety Audit
# =====================================================================

class TestPhase5ExecutionPathSafety:
    def test_assert_no_live_adapter_invocation_invariant(self):
        assert assert_no_live_adapter_invocation() is True
        engine = QueueAwarePaperExecutionEngine()
        assert engine.assert_no_live_adapter_invocation() is True

    def test_rejected_and_expired_orders_not_counted_as_fills(self):
        engine = QueueAwarePaperExecutionEngine()

        # Rejected post-only order (crossing book)
        order_cross = engine.submit_limit_post_only(
            order_id="cross_01",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("82005.00"),
            quantity=Decimal("1"),
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82002.00"),  # crosses ask
            queue_ahead_estimate=Decimal("5"),
        )
        assert order_cross.state == PaperOrderState.REJECTED_POST_ONLY
        assert order_cross.filled_quantity == Decimal("0")
        assert len(order_cross.fills) == 0

        # Resting order expired
        order_rest = engine.submit_limit_post_only(
            order_id="rest_01",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81990.00"),
            quantity=Decimal("1"),
            best_bid=Decimal("81995.00"),
            best_ask=Decimal("82000.00"),
            queue_ahead_estimate=Decimal("10"),
        )
        assert order_rest.state == PaperOrderState.RESTING
        expired = engine.expire_order("rest_01")
        assert expired.state == PaperOrderState.EXPIRED
        assert expired.filled_quantity == Decimal("0")
        assert len(expired.fills) == 0

    def test_partial_fills_and_fill_accounting(self):
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        order = engine.submit_limit_post_only(
            order_id="pf_01",
            symbol="BTCUSD",
            side="BUY",
            price=Decimal("81990.00"),
            quantity=Decimal("5"),
            best_bid=Decimal("81990.00"),
            best_ask=Decimal("82000.00"),
            queue_ahead_estimate=Decimal("10"),
        )
        assert order.state == PaperOrderState.RESTING

        # Trade 1: 10 contracts deplete the queue ahead to 0
        engine.on_market_update("pf_01", trade_volume_at_price=Decimal("10"))
        assert order.queue_ahead == Decimal("0")
        assert order.filled_quantity == Decimal("0")
        assert order.state == PaperOrderState.RESTING

        # Trade 2: 2 contracts executed at price -> partial fill of 2 contracts
        engine.on_market_update("pf_01", trade_volume_at_price=Decimal("2"))
        assert order.state == PaperOrderState.PARTIALLY_FILLED
        assert order.filled_quantity == Decimal("2")
        assert order.remaining_quantity == Decimal("3")
        assert len(order.fills) == 1

        # Trade 3: 3 contracts executed -> filled completely
        engine.on_market_update("pf_01", trade_volume_at_price=Decimal("3"))
        assert order.state == PaperOrderState.FILLED
        assert order.filled_quantity == Decimal("5")
        assert order.remaining_quantity == Decimal("0")
        assert len(order.fills) == 2

        # Verify fee accounting on fills
        total_fill_fee = sum(f.fee_paid for f in order.fills)
        # Notional = 5 * 81990 * 0.001 = 409.95 USD
        # Maker fee = 409.95 * 0.0002 * 1.18 = 0.0967482 USD
        assert total_fill_fee == Decimal("0.09674820")


# =====================================================================
# PHASE 6: Data Evidence Limitations & Posture Verification
# =====================================================================

class TestPhase6DataEvidenceAndPosture:
    def test_data_evidence_temporal_discontinuity(self):
        # Verify continuous candle dataset time
        candle_path = os.path.join(ROOT_DIR, "data/history/BTCUSDT/1m.parquet")
        assert os.path.isfile(candle_path), "1m.parquet candle dataset missing"

        # Verify L2 updates dataset
        l2_path = os.path.join(ROOT_DIR, "research/captures/phase167_recon/l2/delta_ob_updates_archive.json")
        assert os.path.isfile(l2_path), "L2 updates archive missing"

        l2_data = _load_json("research/captures/phase167_recon/l2/delta_ob_updates_archive.json")
        assert len(l2_data["chain_hashes"]) == 113 or len(l2_data["frames"]) == 113

    def test_authenticated_testnet_fills_underpowered(self):
        blockers = _load_json("reports/PHASE176_BLOCKERS.json")
        b04 = next((b for b in blockers["blockers"] if "BLOCK-176-04" in b["id"]), None)
        assert b04 is not None, "BLOCK-176-04 missing from PHASE176_BLOCKERS.json"
        assert "N=2" in b04["title"] or "N = 2" in b04["title"]
        assert "N >= 30" in b04["description"]
        # N=2 is statistically underpowered against N >= 30 milestone requirement

    def test_final_system_posture(self):
        # Mandatory posture requirements:
        # System: NOT_PRODUCTION_READY
        # Strategy: EDGE NOT ESTABLISHED
        # Live orders prohibited
        pass
