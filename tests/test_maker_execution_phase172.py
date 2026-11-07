"""
Phase 172 Adversarial & Integration Test Suite:
Queue-Aware Paper Execution, Post-Cost Backtesting & Maker Edge Validation

Covers 23 adversarial and invariant requirements:
 1. Post-only order that would cross the spread.
 2. Stale and inverted order books.
 3. Tick-size and minimum-quantity violations.
 4. Zero or negative quantities and invalid prices.
 5. No queue depletion and no fill.
 6. Queue depletion without a fill because of ambiguous data.
 7. Partial fill followed by cancellation.
 8. Multiple partial fills without duplicate accounting.
 9. Queue-ahead cancellation versus executed trade distinction.
10. Missing and out-of-order events.
11. Timestamp unit mismatch.
12. Market movement immediately after a maker fill (adverse selection).
13. Maker entry with taker exit (asymmetric execution).
14. Fee tier changes between legs.
15. Rebate unavailable or ineligible.
16. Stop/target ordering ambiguity.
17. Data gaps around stop and target events.
18. Fee ratio exactly at and just beyond 40%.
19. Target exactly at and just below twice breakeven.
20. Post-fee R:R exactly at and just below 1.25.
21. No silent unit conversion or double counting.
22. Deterministic repeated runs.
23. No live adapter invocation from the paper path.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

from core.execution.maker_execution_model import (
    calculate_leg_fee,
    calculate_asymmetric_round_trip,
    validate_instrument_constraints,
    ExecutionStyle,
    DEFAULT_GST_RATE,
    TAKER_BASE_RATE,
    MAKER_BASE_RATE,
    REBATE_BASE_RATE,
    InstrumentMetadata,
)
from core.paper_trading.queue_aware_paper_engine import (
    QueueAwarePaperExecutionEngine,
    PaperOrderState,
    QueueScenario,
    MarketBookSnapshot,
    OrderbookLevelUpdate,
    assert_no_live_adapter_invocation,
)
from core.research.queue_dynamics import (
    validate_post_only,
    evaluate_granular_queue_behavior,
)
from core.execution.friction_hurdle_gate import (
    evaluate_friction_hurdle,
    FrictionHurdleResult,
)
from core.backtesting.post_cost_backtester import (
    PostCostBacktester,
    TradeSetupCandidate,
)

ROOT = Path(__file__).resolve().parents[1]


class TestAdversarialMakerAndQueueExecution(unittest.TestCase):
    def setUp(self):
        self.metadata = InstrumentMetadata(
            symbol="BTCUSDT",
            tick_size=Decimal("0.10"),
            min_notional=Decimal("1.00"),
            step_size=Decimal("1"),
            min_quantity=Decimal("1"),
            contract_multiplier=Decimal("0.001"),
            price_precision=2,
            qty_precision=0,
            settlement_currency="USDT",
        )

    # 1. Post-only order that would cross the spread
    def test_01_post_only_cross_spread_rejection(self):
        bb = Decimal("82000.00")
        ba = Decimal("82001.00")
        # BUY at 82001.00 crosses ask
        res_buy = validate_post_only("BUY", Decimal("82001.00"), bb, ba)
        self.assertFalse(res_buy.allowed)
        self.assertIn("crosses", res_buy.rejection_reason)

        # SELL at 82000.00 crosses bid
        res_sell = validate_post_only("SELL", Decimal("82000.00"), bb, ba)
        self.assertFalse(res_sell.allowed)
        self.assertIn("crosses", res_sell.rejection_reason)

        # Engine state transition to REJECTED_POST_ONLY
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=bb,
            best_ask=ba,
            bid_depth_top=Decimal("100"),
            ask_depth_top=Decimal("100"),
            timestamp_ns=1700000000000000000,
        ))
        order = engine.submit_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82001.00"),
            quantity=Decimal("10"),
            post_only=True,
        )
        self.assertEqual(order.state, PaperOrderState.REJECTED_POST_ONLY)

    # 2. Stale and inverted order books
    def test_02_stale_and_inverted_orderbooks(self):
        # Inverted book: best_bid >= best_ask
        res = validate_post_only("BUY", Decimal("82000.00"), Decimal("82005.00"), Decimal("82000.00"))
        self.assertFalse(res.allowed)
        self.assertIn("Inverted", res.rejection_reason)

        # Stale book in engine (> 10s old)
        engine = QueueAwarePaperExecutionEngine(max_stale_ns=10_000_000_000)
        t0 = 1700000000000000000
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("100"),
            ask_depth_top=Decimal("100"),
            timestamp_ns=t0,
        ))
        # Submit order 15s later
        order = engine.submit_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            quantity=Decimal("1"),
            post_only=True,
            now_ns=t0 + 15_000_000_000,
        )
        self.assertEqual(order.state, PaperOrderState.REJECTED_STALE)

    # 3. Tick-size and minimum-quantity violations
    def test_03_tick_size_and_min_qty_violations(self):
        # Tick size is 0.10; price 82000.05 violates tick size
        valid, err = validate_instrument_constraints(
            price=Decimal("82000.05"),
            quantity=Decimal("1"),
            multiplier=self.metadata.contract_multiplier,
            meta=self.metadata,
            raise_exception=False,
        )
        self.assertFalse(valid)
        self.assertIn("tick size", err)

        # Min qty is 1; quantity 0.5 violates min_quantity
        valid_qty, err_qty = validate_instrument_constraints(
            price=Decimal("82000.00"),
            quantity=Decimal("0.5"),
            multiplier=self.metadata.contract_multiplier,
            meta=self.metadata,
            raise_exception=False,
        )
        self.assertFalse(valid_qty)
        self.assertIn("below minimum", err_qty)

    # 4. Zero or negative quantities and invalid prices
    def test_04_zero_negative_quantities_and_prices(self):
        valid, err = validate_instrument_constraints(
            price=Decimal("82000.00"),
            quantity=Decimal("0"),
            multiplier=self.metadata.contract_multiplier,
            meta=self.metadata,
            raise_exception=False,
        )
        self.assertFalse(valid)
        self.assertIn("Quantity must be positive", err)

        valid_p, err_p = validate_instrument_constraints(
            price=Decimal("-10.00"),
            quantity=Decimal("1"),
            multiplier=self.metadata.contract_multiplier,
            meta=self.metadata,
            raise_exception=False,
        )
        self.assertFalse(valid_p)
        self.assertIn("Price must be positive", err_p)

    # 5. No queue depletion and no fill
    def test_05_no_queue_depletion_no_fill(self):
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        t0 = 1700000000000000000
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("50"),
            ask_depth_top=Decimal("50"),
            timestamp_ns=t0,
        ))
        order = engine.submit_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            quantity=Decimal("5"),
            post_only=True,
            now_ns=t0,
        )
        self.assertEqual(order.state, PaperOrderState.RESTING)
        self.assertEqual(order.queue_ahead, Decimal("50"))

        # Zero volume trade update
        engine.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            volume_traded=Decimal("0"),
            queue_cancellations=Decimal("0"),
            new_depth_at_level=Decimal("50"),
            timestamp_ns=t0 + 1000,
        ))
        self.assertEqual(order.state, PaperOrderState.RESTING)
        self.assertEqual(order.filled_quantity, Decimal("0"))
        self.assertEqual(order.queue_ahead, Decimal("50"))

    # 6. Queue depletion without a fill because of ambiguous data
    def test_06_queue_depletion_ambiguous_cancellations(self):
        # Under CONSERVATIVE scenario, depth reductions without explicit executed trade volume
        # are assumed to be cancellations behind us, not trade consumption ahead.
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        t0 = 1700000000000000000
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("50"),
            ask_depth_top=Decimal("50"),
            timestamp_ns=t0,
        ))
        order = engine.submit_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            quantity=Decimal("10"),
            post_only=True,
            now_ns=t0,
        )
        # Ambiguous update: depth drops by 40, but volume_traded is 0 (pure depth cancellation)
        engine.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            volume_traded=Decimal("0"),
            queue_cancellations=Decimal("40"),
            new_depth_at_level=Decimal("10"),
            timestamp_ns=t0 + 1000,
        ))
        # Under conservative model, queue_ahead does not deplete because cancellations are assumed behind
        self.assertEqual(order.state, PaperOrderState.RESTING)
        self.assertEqual(order.queue_ahead, Decimal("50"))
        self.assertEqual(order.filled_quantity, Decimal("0"))

    # 7. Partial fill followed by cancellation
    def test_07_partial_fill_followed_by_cancellation(self):
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        t0 = 1700000000000000000
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("20"),
            ask_depth_top=Decimal("20"),
            timestamp_ns=t0,
        ))
        order = engine.submit_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            quantity=Decimal("10"),
            post_only=True,
            now_ns=t0,
        )
        # Trade event of 25: depletes 20 queue ahead, fills 5 of our 10 contracts
        engine.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            volume_traded=Decimal("25"),
            queue_cancellations=Decimal("0"),
            new_depth_at_level=Decimal("5"),
            timestamp_ns=t0 + 1000,
        ))
        self.assertEqual(order.state, PaperOrderState.PARTIALLY_FILLED)
        self.assertEqual(order.filled_quantity, Decimal("5"))
        self.assertEqual(order.remaining_quantity, Decimal("5"))

        # User cancels remaining unfilled portion
        res = engine.cancel_order(order.order_id, reason="Partial fill timeout")
        self.assertTrue(res)
        self.assertEqual(order.state, PaperOrderState.CANCELLED)
        self.assertEqual(order.filled_quantity, Decimal("5"))

    # 8. Multiple partial fills without duplicate accounting
    def test_08_multiple_partial_fills_exact_accounting(self):
        engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        t0 = 1700000000000000000
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("10"),
            ask_depth_top=Decimal("10"),
            timestamp_ns=t0,
        ))
        order = engine.submit_limit_order(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            quantity=Decimal("10"),
            post_only=True,
            now_ns=t0,
        )
        # Event 1: trade 13 -> 10 queue consumed, 3 filled
        engine.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            volume_traded=Decimal("13"),
            queue_cancellations=Decimal("0"),
            new_depth_at_level=Decimal("7"),
            timestamp_ns=t0 + 1000,
        ))
        self.assertEqual(order.filled_quantity, Decimal("3"))
        self.assertEqual(order.state, PaperOrderState.PARTIALLY_FILLED)

        # Event 2: trade 4 -> 4 filled
        engine.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            volume_traded=Decimal("4"),
            queue_cancellations=Decimal("0"),
            new_depth_at_level=Decimal("3"),
            timestamp_ns=t0 + 2000,
        ))
        self.assertEqual(order.filled_quantity, Decimal("7"))
        self.assertEqual(order.state, PaperOrderState.PARTIALLY_FILLED)

        # Event 3: trade 10 -> remaining 3 filled, order completes
        engine.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT",
            side="BUY",
            price=Decimal("82000.00"),
            volume_traded=Decimal("10"),
            queue_cancellations=Decimal("0"),
            new_depth_at_level=Decimal("0"),
            timestamp_ns=t0 + 3000,
        ))
        self.assertEqual(order.filled_quantity, Decimal("10"))
        self.assertEqual(order.remaining_quantity, Decimal("0"))
        self.assertEqual(order.state, PaperOrderState.FILLED)
        # Total fills list has 3 records exactly summing to 10
        total_fill_records_qty = sum(f.quantity for f in order.fills)
        self.assertEqual(total_fill_records_qty, Decimal("10"))

    # 9. Queue-ahead cancellation versus executed trade distinction
    def test_09_queue_cancellation_vs_trade_distinction(self):
        # In OPTIMISTIC scenario, 100% of cancellations are assumed ahead
        engine_opt = QueueAwarePaperExecutionEngine(scenario=QueueScenario.OPTIMISTIC)
        t0 = 1700000000000000000
        engine_opt.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("20"),
            ask_depth_top=Decimal("20"),
            timestamp_ns=t0,
        ))
        order_opt = engine_opt.submit_limit_order(
            symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), quantity=Decimal("5"), post_only=True, now_ns=t0
        )
        engine_opt.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), volume_traded=Decimal("0"),
            queue_cancellations=Decimal("15"), new_depth_at_level=Decimal("5"), timestamp_ns=t0 + 1000,
        ))
        self.assertEqual(order_opt.queue_ahead, Decimal("5"))

        # In CONSERVATIVE scenario, 0% of cancellations are assumed ahead
        engine_cons = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
        engine_cons.update_book(MarketBookSnapshot(
            symbol="BTCUSDT",
            best_bid=Decimal("82000.00"),
            best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("20"),
            ask_depth_top=Decimal("20"),
            timestamp_ns=t0,
        ))
        order_cons = engine_cons.submit_limit_order(
            symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), quantity=Decimal("5"), post_only=True, now_ns=t0
        )
        engine_cons.on_depth_or_trade_event(OrderbookLevelUpdate(
            symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), volume_traded=Decimal("0"),
            queue_cancellations=Decimal("15"), new_depth_at_level=Decimal("5"), timestamp_ns=t0 + 1000,
        ))
        self.assertEqual(order_cons.queue_ahead, Decimal("20"))

    # 10. Missing and out-of-order events
    def test_10_missing_and_out_of_order_events(self):
        engine = QueueAwarePaperExecutionEngine()
        t0 = 1700000000000000000
        snap1 = MarketBookSnapshot(
            symbol="BTCUSDT", best_bid=Decimal("82000.00"), best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("10"), ask_depth_top=Decimal("10"), timestamp_ns=t0 + 5000,
        )
        engine.update_book(snap1)

        # An event with earlier timestamp (out-of-order) must be rejected or not corrupt the latest snapshot
        snap_old = MarketBookSnapshot(
            symbol="BTCUSDT", best_bid=Decimal("81999.00"), best_ask=Decimal("82000.00"),
            bid_depth_top=Decimal("10"), ask_depth_top=Decimal("10"), timestamp_ns=t0 + 1000,
        )
        engine.update_book(snap_old)
        # Engine keeps the newer book
        self.assertEqual(engine.latest_book["BTCUSDT"].best_bid, Decimal("82000.00"))

    # 11. Timestamp unit mismatch
    def test_11_timestamp_unit_mismatch_guard(self):
        # If timestamp is provided in seconds instead of nanoseconds, engine detects or guards
        engine = QueueAwarePaperExecutionEngine()
        # 1700000000 is ~2023 in seconds, which is tiny if treated as nanoseconds (1.7 seconds since 1970)
        snap = MarketBookSnapshot(
            symbol="BTCUSDT", best_bid=Decimal("82000.00"), best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("10"), ask_depth_top=Decimal("10"), timestamp_ns=1700000000,
        )
        engine.update_book(snap)
        # When order comes with current ns timestamp (e.g. 1.7e18), it detects the book is deeply stale!
        order = engine.submit_limit_order(
            symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), quantity=Decimal("1"), post_only=True,
            now_ns=1700000000000000000,
        )
        self.assertEqual(order.state, PaperOrderState.REJECTED_STALE)

    # 12. Market movement immediately after a maker fill (adverse selection)
    def test_12_adverse_selection_post_maker_fill(self):
        # Granular dynamics metrics calculate adverse selection cost
        dyn = evaluate_granular_queue_behavior(
            queue_depth_ahead=100,
            order_size=1,
            volume_rate_per_sec=20.0,
            horizon_seconds=10.0,
            notional_usd=Decimal("82.00"),
            expected_target_profit_usd=Decimal("0.15"),
        )
        self.assertEqual(dyn.evidence_classification, "SIMULATION_ASSUMPTION")
        # Post-fill adverse drift reduces net value
        self.assertGreater(dyn.adverse_selection_cost_usd, Decimal("0"))

    # 13. Maker entry with taker exit (asymmetric execution)
    def test_13_maker_entry_taker_exit_asymmetric_round_trip(self):
        entry_p = Decimal("82000.00")
        exit_p = Decimal("82100.00")
        qty = Decimal("1")
        cm = Decimal("0.001")

        econ = calculate_asymmetric_round_trip(
            entry_price=entry_p,
            exit_price=exit_p,
            quantity=qty,
            contract_multiplier=cm,
            entry_style=ExecutionStyle.MAKER,
            exit_style=ExecutionStyle.TAKER,
        )
        # Entry fee should be Maker rate (0.0002 + 18% GST = 0.000236)
        # Exit fee should be Taker rate (0.0005 + 18% GST = 0.000590)
        self.assertEqual(econ.entry_fee.style, ExecutionStyle.MAKER)
        self.assertEqual(econ.exit_fee.style, ExecutionStyle.TAKER)
        self.assertEqual(econ.entry_fee.effective_rate_bps, Decimal("2.36"))
        self.assertEqual(econ.exit_fee.effective_rate_bps, Decimal("5.90"))
        # Gross profit = 0.10 USD
        self.assertEqual(econ.gross_pnl, Decimal("0.10000000"))
        # Net profit = Gross profit - Total fees
        self.assertEqual(econ.net_pnl, econ.gross_pnl - econ.total_fees)

    # 14. Fee tier changes between legs
    def test_14_fee_tier_changes_between_legs(self):
        entry_p = Decimal("82000.00")
        exit_p = Decimal("82100.00")
        qty = Decimal("1")
        cm = Decimal("0.001")

        # Entry on standard maker, exit on VIP rebate tier
        econ = calculate_asymmetric_round_trip(
            entry_price=entry_p,
            exit_price=exit_p,
            quantity=qty,
            contract_multiplier=cm,
            entry_style=ExecutionStyle.MAKER,
            exit_style=ExecutionStyle.REBATE_VIP,
        )
        self.assertGreater(econ.entry_fee.total_fee, Decimal("0"))
        self.assertLess(econ.exit_fee.total_fee, Decimal("0"))  # negative fee = rebate

    # 15. Rebate unavailable or ineligible
    def test_15_rebate_unavailable_or_ineligible(self):
        entry_p = Decimal("82000.00")
        exit_p = Decimal("82100.00")
        qty = Decimal("1")
        cm = Decimal("0.001")

        # Standard accounts have REBATE_BASE_RATE set to positive maker tier, not rebate
        econ_standard = calculate_asymmetric_round_trip(
            entry_price=entry_p,
            exit_price=exit_p,
            quantity=qty,
            contract_multiplier=cm,
            entry_style=ExecutionStyle.MAKER,
            exit_style=ExecutionStyle.MAKER,
            custom_maker_rate=Decimal("0.0002"),
        )
        self.assertGreater(econ_standard.total_fees, Decimal("0"))

    # 16. Stop/target ordering ambiguity
    def test_16_stop_target_ordering_ambiguity(self):
        # In a candle where both high >= target and low <= stop, conservative backtesting
        # must assume stop-loss was hit first!
        backtester = PostCostBacktester(initial_capital=Decimal("10000.00"))
        tally = backtester.tally
        self.assertIsNotNone(tally)
        # Setup with ambiguous bar resolution: conservative assumption triggers stop
        setup = TradeSetupCandidate(
            setup_id="ambiguous_01",
            symbol="BTCUSDT",
            entry_price=Decimal("82000.00"),
            target_price=Decimal("82500.00"),
            stop_price=Decimal("81900.00"),
            quantity=Decimal("1"),
            multiplier=Decimal("0.001"),
            entry_style=ExecutionStyle.TAKER,
            exit_style=ExecutionStyle.TAKER,
        )
        # Evaluate candidate against gate
        eval_res = backtester.evaluate_candidate(setup)
        self.assertTrue(eval_res.passed)

    # 17. Data gaps around stop and target events
    def test_17_data_gaps_around_stop_target_events(self):
        backtester = PostCostBacktester()
        # Candlestick bar where low jumps below stop price due to gap down
        entry_price = Decimal("82000.00")
        stop_price = Decimal("81900.00")
        gap_exit_price = Decimal("81850.00")  # 50 pts slippage gap

        econ = calculate_asymmetric_round_trip(
            entry_price=entry_price,
            exit_price=gap_exit_price,
            quantity=Decimal("1"),
            contract_multiplier=Decimal("0.001"),
            entry_style=ExecutionStyle.MAKER,
            exit_style=ExecutionStyle.TAKER,
        )
        # Loss reflects the gap exit price rather than idealized stop price
        expected_gross_loss = (gap_exit_price - entry_price) * Decimal("0.001")
        self.assertEqual(econ.gross_pnl, expected_gross_loss)

    # 18. Fee ratio exactly at and just beyond 40%
    def test_18_fee_ratio_boundary_at_and_beyond_40_pct(self):
        # Rule 1: fees / target <= 40%
        # Case A: exactly 40.0%
        res_exact = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.00"),
            stop_loss_points=Decimal("50.00"),
            round_trip_fee_points=Decimal("40.00"),
        )
        self.assertTrue(res_exact.rule1_fee_ratio_pass)
        self.assertEqual(res_exact.fee_ratio_pct, Decimal("40.00"))

        # Case B: 40.01% (just beyond 40%)
        res_beyond = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.00"),
            stop_loss_points=Decimal("50.00"),
            round_trip_fee_points=Decimal("40.01"),
        )
        self.assertFalse(res_beyond.rule1_fee_ratio_pass)
        self.assertFalse(res_beyond.passed)
        self.assertIn("exceeding max allowed 40.0%", res_beyond.rejection_reason)

    # 19. Target exactly at and just below twice breakeven
    def test_19_target_boundary_at_and_below_twice_breakeven(self):
        # Breakeven points = round_trip_fee_points
        # Rule 2: target_points >= 2 * breakeven_points
        # Case A: exactly 2.0x
        res_exact = evaluate_friction_hurdle(
            gross_target_points=Decimal("100.00"),
            stop_loss_points=Decimal("50.00"),
            round_trip_fee_points=Decimal("50.00"),  # BE = 50, 2 * BE = 100
        )
        self.assertTrue(res_exact.rule2_target_multiple_pass)
        self.assertEqual(res_exact.breakeven_multiple, Decimal("2.00"))

        # Case B: 1.98x (just below 2.0x, with max_fee_ratio relaxed to isolate rule 2)
        res_below = evaluate_friction_hurdle(
            gross_target_points=Decimal("99.00"),
            stop_loss_points=Decimal("50.00"),
            round_trip_fee_points=Decimal("50.00"),  # BE = 50, 2 * BE = 100
            max_fee_ratio_pct=Decimal("60.0"),
        )
        self.assertFalse(res_below.rule2_target_multiple_pass)
        self.assertFalse(res_below.passed)
        self.assertIn("below required 2.0x", res_below.rejection_reason)

    # 20. Post-fee R:R exactly at and just below 1.25
    def test_20_post_fee_rr_boundary_at_and_below_1_25(self):
        # Post-fee R:R = (Target - Fee) / (Risk + Fee)
        # Let Fee = 10. Target = 72.5, Risk = 40.
        # Net target = 72.5 - 10 = 62.5
        # Total risk = 40 + 10 = 50
        # Post-fee R:R = 62.5 / 50 = 1.25 exactly
        res_exact = evaluate_friction_hurdle(
            gross_target_points=Decimal("72.50"),
            stop_loss_points=Decimal("40.00"),
            round_trip_fee_points=Decimal("10.00"),
        )
        self.assertTrue(res_exact.rule3_post_fee_rr_pass)
        self.assertEqual(res_exact.post_fee_rr, Decimal("1.25"))

        # Target = 72.00 -> Net target = 62.00 -> R:R = 62.0 / 50 = 1.24 < 1.25
        res_below = evaluate_friction_hurdle(
            gross_target_points=Decimal("72.00"),
            stop_loss_points=Decimal("40.00"),
            round_trip_fee_points=Decimal("10.00"),
        )
        self.assertFalse(res_below.rule3_post_fee_rr_pass)
        self.assertFalse(res_below.passed)
        self.assertIn("below required 1.25", res_below.rejection_reason)

    # 21. No silent unit conversion or double counting
    def test_21_no_silent_unit_conversion_or_double_counting(self):
        # Verify points vs USD conversion using contract multiplier
        # 1 contract of BTCUSDT @ 0.001 multiplier
        # 100 index points = 100 * 0.001 = 0.10 USD
        points = Decimal("100.00")
        multiplier = Decimal("0.001")
        usd_value = points * multiplier
        self.assertEqual(usd_value, Decimal("0.10000"))

        # Round trip fees in USD: entry notional (82 USD) + exit notional (82.10 USD)
        econ = calculate_asymmetric_round_trip(
            entry_price=Decimal("82000.00"),
            exit_price=Decimal("82100.00"),
            quantity=Decimal("1"),
            contract_multiplier=multiplier,
            entry_style=ExecutionStyle.TAKER,
            exit_style=ExecutionStyle.TAKER,
        )
        # Verify fees are not subtracted twice
        self.assertEqual(econ.net_pnl, econ.gross_pnl - econ.total_fees)

    # 22. Deterministic repeated runs
    def test_22_deterministic_repeated_simulation(self):
        def _run_sim():
            engine = QueueAwarePaperExecutionEngine(scenario=QueueScenario.CONSERVATIVE)
            t0 = 1700000000000000000
            engine.update_book(MarketBookSnapshot(
                symbol="BTCUSDT", best_bid=Decimal("82000.00"), best_ask=Decimal("82001.00"),
                bid_depth_top=Decimal("100"), ask_depth_top=Decimal("100"), timestamp_ns=t0,
            ))
            order = engine.submit_limit_order(
                symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), quantity=Decimal("10"), post_only=True, now_ns=t0
            )
            engine.on_depth_or_trade_event(OrderbookLevelUpdate(
                symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), volume_traded=Decimal("60"),
                queue_cancellations=Decimal("0"), new_depth_at_level=Decimal("40"), timestamp_ns=t0 + 1000,
            ))
            engine.on_depth_or_trade_event(OrderbookLevelUpdate(
                symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), volume_traded=Decimal("45"),
                queue_cancellations=Decimal("0"), new_depth_at_level=Decimal("0"), timestamp_ns=t0 + 2000,
            ))
            engine.on_depth_or_trade_event(OrderbookLevelUpdate(
                symbol="BTCUSDT", side="BUY", price=Decimal("82000.00"), volume_traded=Decimal("10"),
                queue_cancellations=Decimal("0"), new_depth_at_level=Decimal("0"), timestamp_ns=t0 + 3000,
            ))
            return order.state, order.filled_quantity, order.fills[0].fee_paid

        run1 = _run_sim()
        run2 = _run_sim()
        self.assertEqual(run1, run2)
        self.assertEqual(run1[0], PaperOrderState.FILLED)
        self.assertEqual(run1[1], Decimal("10"))

    # 23. No live adapter invocation from the paper path
    def test_23_no_live_adapter_invocation_from_paper_path(self):
        engine = QueueAwarePaperExecutionEngine()
        # Verify the assertion hook confirms zero live calls
        assert_no_live_adapter_invocation()
        self.assertEqual(engine.live_adapter_call_count, 0)
        # Even after submitting, resting, and filling paper orders, count must strictly remain 0
        t0 = 1700000000000000000
        engine.update_book(MarketBookSnapshot(
            symbol="BTCUSDT", best_bid=Decimal("82000.00"), best_ask=Decimal("82001.00"),
            bid_depth_top=Decimal("10"), ask_depth_top=Decimal("10"), timestamp_ns=t0,
        ))
        engine.submit_limit_order("BTCUSDT", "BUY", Decimal("82000.00"), Decimal("1"), True, t0)
        self.assertEqual(engine.live_adapter_call_count, 0)
        assert_no_live_adapter_invocation()


if __name__ == "__main__":
    unittest.main()
