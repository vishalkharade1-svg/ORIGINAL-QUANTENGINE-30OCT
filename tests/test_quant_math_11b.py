"""
====================================================

QuantEngine -- Phase 11B quantitative recertification.

Action-backed invariant tests over the frozen production
math (no strategy changes, no LIVE, no network):

  A. Position sizing      (core/risk/position_sizer.py)
  B. Trade accounting     (core/backtesting/accounting.py
                           + trade_simulator.py + account.py)
  D. Risk invariants      (sizer + manager + registry,
                           adversarial inputs)
  E. Order lifecycle      (core/execution/order_registry.py
                           bar-anchored sequencing)
  F. Economic dedup       (fingerprint_of / snap_price)
  G. Walk-forward         (core/validation/walk_forward.py)
  H. Performance metrics  (core/analytics/performance.py)

Frozen baseline referenced: ENTRY BREAKOUT_CONTINUATION,
balance 2000, risk 0.01, allocation 500, leverage 10,
MAX_WAIT_BARS 30, ENTRY_DELAY_BARS 1, zero costs.

Conventions: unittest, stdlib only. Every test performs
an action and asserts the measured outcome; critical
formulas carry positive AND adversarial cases.

====================================================
"""

import unittest

from core.backtesting import accounting
from core.backtesting.trade import Trade
from core.backtesting.trade_registry import TradeRegistry
from core.backtesting.trade_simulator import TradeSimulator
from core.risk.account import Account
from core.risk.order_intent import OrderIntent
from core.risk.position_manager import PositionManager
from core.risk.position_sizer import PositionSizer


# ==================================================
# Shared builders
# ==================================================


def buy_intent(**overrides):
    params = {
        "direction": "BULLISH",
        "entry": 100.0,
        "stop_loss": 90.0,
        "take_profit": 110.0,
        "quantity": 2.0,
        "symbol": "TEST",
        "valid": True,
    }
    params.update(overrides)
    return OrderIntent(**params)


class Candle:
    def __init__(self, high, low, close, timestamp=1):
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp


# ==================================================
# 11B-A — Position sizing recertification
# ==================================================


class TestSizerFormulas(unittest.TestCase):

    def test_normal_long_exact_math(self):
        out = PositionSizer().calculate(
            balance=2000.0, entry_price=80000.0, stop_price=79500.0
        )

        # 11E-Prep H1: MAX_ALLOCATION_PER_TRADE is a NOTIONAL
        # cap (position value <= 500), not a margin cap.
        # Requested: risk 2000*0.01=20, dist 500, qty 0.04,
        # PV 3200 > 500 -> scaled to PV 500.
        self.assertAlmostEqual(out.stop_distance, 500.0)
        self.assertAlmostEqual(out.requested_quantity, 0.04)
        self.assertAlmostEqual(out.requested_position_value, 3200.0)
        self.assertTrue(out.capped)
        self.assertAlmostEqual(out.quantity, 0.00625)
        # notional = 0.00625 * 80000 = 500
        self.assertAlmostEqual(out.position_value, 500.0)
        self.assertTrue(out.valid)
        # actual risk = final qty x dist, below nominal 20.
        self.assertAlmostEqual(out.expected_loss, 3.125)
        self.assertAlmostEqual(out.risk_amount, 3.125)

    def test_normal_short_mirrors_long(self):
        out = PositionSizer().calculate(
            balance=2000.0, entry_price=79500.0, stop_price=80000.0
        )

        self.assertAlmostEqual(out.stop_distance, 500.0)
        # Requested qty 0.04 (PV 3180) -> capped to PV 500.
        self.assertAlmostEqual(out.quantity, 500.0 / 79500.0)
        self.assertAlmostEqual(out.position_value, 500.0)
        self.assertTrue(out.valid)

    def test_tiny_stop_hits_allocation_cap(self):
        out = PositionSizer().calculate(
            balance=2000.0, entry_price=80000.0, stop_price=79999.0
        )

        # Uncapped quantity would be 20 / 1 = 20 contracts
        # (notional 1.6M >> allocation 500): must be capped
        # to PV 500 -> qty 0.00625.
        self.assertTrue(out.valid)
        self.assertLess(out.quantity, 20.0)
        self.assertAlmostEqual(out.quantity, 0.00625)
        # Actual risk taken is below the nominal 20.
        self.assertLessEqual(out.expected_loss, 20.0 + 1e-9)
        # Notional after cap fits the allocation.
        self.assertLessEqual(out.position_value, 500.0 + 1e-9)

    def test_large_stop_small_quantity(self):
        out = PositionSizer().calculate(
            balance=2000.0, entry_price=80000.0, stop_price=60000.0
        )

        self.assertAlmostEqual(out.quantity, 20.0 / 20000.0)
        self.assertTrue(out.valid)

    def test_zero_stop_distance_invalid(self):
        out = PositionSizer().calculate(
            balance=2000.0, entry_price=80000.0, stop_price=80000.0
        )

        self.assertFalse(out.valid)
        self.assertEqual(out.quantity, 0)
        self.assertEqual(out.stop_distance, 0)

    def test_zero_balance_invalid(self):
        out = PositionSizer().calculate(
            balance=0.0, entry_price=80000.0, stop_price=79500.0
        )

        self.assertFalse(out.valid)
        self.assertEqual(out.quantity, 0)

    def test_negative_balance_invalid_no_negative_qty(self):
        out = PositionSizer().calculate(
            balance=-500.0, entry_price=80000.0, stop_price=79500.0
        )

        self.assertFalse(out.valid)
        self.assertEqual(out.quantity, 0)
        self.assertGreaterEqual(out.risk_amount, 0)

    def test_zero_multiplier_floors_risk_percent(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=80000.0,
            stop_price=79500.0,
            risk_multiplier=0.0,
        )

        # Floor 0.001: risk can never silently vanish.
        self.assertGreaterEqual(out.risk_percent, 0.001)
        self.assertGreater(out.quantity, 0)

    def test_negative_multiplier_clamped(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=80000.0,
            stop_price=79500.0,
            risk_multiplier=-5.0,
        )

        self.assertGreaterEqual(out.risk_percent, 0.001)
        self.assertGreaterEqual(out.quantity, 0)
        self.assertGreaterEqual(out.risk_amount, 0)

    def test_zero_leverage_resets_to_one(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=80000.0,
            stop_price=79500.0,
            leverage=0.0,
        )

        self.assertEqual(out.leverage, 1.0)
        self.assertTrue(out.valid)

    def test_negative_leverage_resets_to_one(self):
        out = PositionSizer().calculate(
            balance=2000.0,
            entry_price=80000.0,
            stop_price=79500.0,
            leverage=-10.0,
        )

        self.assertEqual(out.leverage, 1.0)
        self.assertTrue(out.valid)

    def test_invalid_entry_price_rejected(self):
        for bad in (0.0, -100.0):
            out = PositionSizer().calculate(
                balance=2000.0,
                entry_price=bad,
                stop_price=79500.0,
            )

            self.assertFalse(out.valid, msg="entry={!r}".format(bad))
            self.assertEqual(out.quantity, 0)


class TestManagerHygiene(unittest.TestCase):

    def test_quantity_rounding_and_purity(self):
        manager = PositionManager(quantity_precision=2)

        order = buy_intent(entry=100.0, quantity=1.23456)
        corrected, reasons = manager.audit(order)

        self.assertAlmostEqual(corrected.quantity, 1.23)
        self.assertTrue(reasons)
        # Input never mutated.
        self.assertAlmostEqual(order.quantity, 1.23456)

    def test_dust_quantity_dropped(self):
        manager = PositionManager()

        corrected, _ = manager.audit(buy_intent(quantity=1e-7))

        self.assertEqual(corrected.quantity, 0.0)
        self.assertFalse(corrected.valid)

    def test_minimum_quantity_boundary(self):
        manager = PositionManager()

        kept, _ = manager.audit(
            buy_intent(entry=100.0, quantity=1e-6)
        )
        self.assertGreater(kept.quantity, 0)

        dropped, _ = manager.audit(
            buy_intent(entry=100.0, quantity=9e-7)
        )
        self.assertEqual(dropped.quantity, 0.0)

    def test_negative_quantity_clamped_fail_closed(self):
        manager = PositionManager()

        corrected, reasons = manager.audit(
            buy_intent(quantity=-3.0)
        )

        self.assertEqual(corrected.quantity, 0.0)
        self.assertFalse(corrected.valid)
        self.assertTrue(reasons)

    def test_non_positive_entry_rejected(self):
        manager = PositionManager()

        for bad in (0.0, -50.0):
            corrected, reasons = manager.audit(
                buy_intent(entry=bad, quantity=1.0)
            )

            self.assertEqual(corrected.quantity, 0.0)
            self.assertFalse(corrected.valid)
            self.assertTrue(reasons)

    def test_notional_cap_enforced(self):
        manager = PositionManager(max_allocation=500.0)

        corrected, _ = manager.audit(
            buy_intent(entry=80000.0, quantity=1.0)
        )

        self.assertLessEqual(
            corrected.quantity * 80000.0, 500.0 + 1e-9
        )

    def test_double_apply_is_noop(self):
        manager = PositionManager(quantity_precision=2)

        once, _ = manager.audit(
            buy_intent(entry=100.0, quantity=1.23456)
        )
        twice, _ = manager.audit(once)

        self.assertAlmostEqual(twice.quantity, once.quantity)


# ==================================================
# 11B-B — Trade accounting
# ==================================================


class TestAccountingFunctions(unittest.TestCase):

    def test_long_win_math(self):
        gross = accounting.gross_pnl("BULLISH", 100.0, 110.0, 2.0)
        self.assertAlmostEqual(gross, 20.0)

        net = accounting.net_pnl(gross, 1.0, 1.0)
        self.assertAlmostEqual(net, 18.0)

        pct = accounting.position_return_percent(18.0, 100.0, 2.0)
        self.assertAlmostEqual(pct, 9.0)

    def test_short_win_math(self):
        gross = accounting.gross_pnl("BEARISH", 100.0, 90.0, 2.0)
        self.assertAlmostEqual(gross, 20.0)

    def test_short_loss_math(self):
        gross = accounting.gross_pnl("BEARISH", 100.0, 110.0, 2.0)
        self.assertAlmostEqual(gross, -20.0)

    def test_long_loss_math(self):
        gross = accounting.gross_pnl("BULLISH", 100.0, 90.0, 2.0)
        self.assertAlmostEqual(gross, -20.0)

    def test_zero_denominators_safe(self):
        self.assertEqual(
            accounting.position_return_percent(5.0, 0.0, 0.0), 0.0
        )
        self.assertEqual(
            accounting.portfolio_return_percent(5.0, 0.0), 0.0
        )
        self.assertEqual(accounting.realized_r(5.0, 0.0), 0.0)
        self.assertEqual(accounting.realized_r(5.0, None), 0.0)

    def test_classification_exact_boundaries(self):
        self.assertEqual(accounting.classify_pnl(0.01), "WIN")
        self.assertEqual(accounting.classify_pnl(-0.01), "LOSS")
        self.assertEqual(accounting.classify_pnl(0.0), "BREAKEVEN")
        # Exact zero tolerance: dust is NOT breakeven.
        self.assertEqual(accounting.classify_pnl(1e-12), "WIN")
        self.assertEqual(accounting.classify_pnl(-1e-12), "LOSS")

    def test_unknown_direction_zero(self):
        self.assertEqual(
            accounting.gross_pnl("SIDEWAYS", 100.0, 110.0, 2.0), 0.0
        )


class TestSimulatorLifecycle(unittest.TestCase):

    def _sim(self):
        return TradeSimulator()

    def test_long_win_full_lifecycle(self):
        # Phase-13 maintenance: the fixture now carries a
        # gate-compliant post-cost RR (costs 1.0+1.0 shift the
        # entry to 100.5: 69.5/10.5 = 6.62 >= 6), so the
        # mandatory post-cost R:R gate admits the fill. Lifecycle,
        # fee-booking, and percent-math intent unchanged (gross
        # 140.0 - 2.0 costs = 138.0; 138/200 = 69.0%).
        sim = self._sim()
        trade = sim.open_trade(
            buy_intent(take_profit=170.0), timestamp=1,
            commission=1.0, slippage=1.0,
        )

        self.assertIsNotNone(trade)

        sim.update(Candle(high=172.0, low=101.0, close=171.0, timestamp=2))

        self.assertIsNone(sim.current_trade)
        self.assertEqual(sim.registry.count(), 1)

        closed = sim.registry.closed()[0]
        self.assertEqual(closed.result, "WIN")
        self.assertAlmostEqual(closed.pnl, 138.0)
        self.assertAlmostEqual(closed.pnl_percent, 69.0)

    def test_long_loss_full_lifecycle(self):
        sim = self._sim()
        sim.open_trade(buy_intent(), timestamp=1)

        sim.update(Candle(high=100.0, low=85.0, close=88.0, timestamp=2))

        closed = sim.registry.closed()[0]
        self.assertEqual(closed.result, "LOSS")
        self.assertAlmostEqual(closed.pnl, -20.0)

    def test_short_win_full_lifecycle(self):
        sim = self._sim()
        sim.open_trade(
            buy_intent(
                direction="BEARISH",
                entry=100.0,
                stop_loss=110.0,
                take_profit=90.0,
            ),
            timestamp=1,
        )

        sim.update(Candle(high=99.0, low=85.0, close=88.0, timestamp=2))

        closed = sim.registry.closed()[0]
        self.assertEqual(closed.result, "WIN")
        self.assertAlmostEqual(closed.pnl, 20.0)

    def test_zero_pnl_is_breakeven_economics(self):
        sim = self._sim()
        # Stop AT entry: trigger label says LOSS but the
        # economics are exactly zero -> BREAKEVEN.
        sim.open_trade(
            buy_intent(stop_loss=100.0, take_profit=200.0),
            timestamp=1,
        )

        sim.update(Candle(high=101.0, low=99.0, close=100.0, timestamp=2))

        closed = sim.registry.closed()[0]
        self.assertAlmostEqual(closed.pnl, 0.0)
        self.assertEqual(
            accounting.classify_pnl(closed.pnl), "BREAKEVEN"
        )

    def test_zero_quantity_never_opens(self):
        sim = self._sim()

        self.assertIsNone(
            sim.open_trade(
                buy_intent(quantity=0.0), timestamp=1
            )
        )
        self.assertEqual(sim.registry.count(), 0)

    def test_single_position_first_wins(self):
        sim = self._sim()
        first = sim.open_trade(buy_intent(), timestamp=1)

        self.assertIsNotNone(first)
        self.assertIsNone(
            sim.open_trade(buy_intent(), timestamp=1)
        )

    def test_consecutive_trades_booked(self):
        sim = self._sim()

        sim.open_trade(buy_intent(), timestamp=1)
        sim.update(Candle(high=112.0, low=101.0, close=111.0, timestamp=2))

        sim.open_trade(buy_intent(), timestamp=3)
        sim.update(Candle(high=100.0, low=85.0, close=88.0, timestamp=4))

        self.assertEqual(sim.registry.count(), 2)
        pnls = [t.pnl for t in sim.registry.closed()]
        self.assertAlmostEqual(pnls[0], 20.0)
        self.assertAlmostEqual(pnls[1], -20.0)


class TestAccountBooking(unittest.TestCase):

    def test_profit_loss_breakeven_sequence(self):
        acc = Account(starting_balance=2000.0)

        acc.book_profit(20.0)
        self.assertAlmostEqual(acc.balance, 2020.0)
        self.assertAlmostEqual(acc.state.realized_pnl, 20.0)
        self.assertEqual(acc.state.winning_trades, 1)
        self.assertEqual(acc.state.consecutive_wins, 1)

        acc.book_loss(8.0)
        self.assertAlmostEqual(acc.balance, 2012.0)
        self.assertAlmostEqual(acc.state.realized_pnl, 12.0)
        self.assertEqual(acc.state.losing_trades, 1)
        self.assertEqual(acc.state.consecutive_wins, 0)
        self.assertEqual(acc.state.consecutive_losses, 1)

        acc.book_breakeven()
        self.assertAlmostEqual(acc.balance, 2012.0)
        self.assertEqual(acc.state.total_trades, 3)
        self.assertEqual(acc.state.breakeven_trades, 1)
        self.assertEqual(acc.state.consecutive_losses, 0)

    def test_balance_equals_starting_plus_realized(self):
        acc = Account(starting_balance=2000.0)
        acc.book_profit(20.0)
        acc.book_loss(8.0)

        self.assertAlmostEqual(
            acc.balance,
            acc.state.starting_balance + acc.state.realized_pnl,
        )

    def test_reset_preserves_identity(self):
        acc = Account(starting_balance=2000.0)
        acc.book_profit(20.0)
        held = acc

        acc.reset()

        self.assertIs(acc, held)
        self.assertAlmostEqual(acc.balance, 2000.0)
        self.assertAlmostEqual(acc.state.realized_pnl, 0.0)
        self.assertEqual(acc.state.total_trades, 0)

    def test_backtester_reset_preserves_account_identity(self):
        from backtesting.backtester import Backtester
        from core.events.event_bus import EventBus
        from core.pipeline.institutional_pipeline import (
            InstitutionalPipeline,
        )
        from core.pipeline.pipeline_context import PipelineContext

        acc = Account(starting_balance=2000.0)
        bt = Backtester(
            pipeline=InstitutionalPipeline(PipelineContext()),
            event_bus=EventBus(),
            simulator=TradeSimulator(),
            account=acc,
        )

        bt.reset()

        # Phase 11B fix: reset() must not swap the object.
        self.assertIs(bt.account, acc)
        self.assertAlmostEqual(bt.account.balance, 2000.0)


# ==================================================
# 11B-D — Risk invariants, adversarial
# ==================================================


class TestRiskInvariants(unittest.TestCase):

    def test_extreme_size_capped_by_allocation(self):
        sizer = PositionSizer()
        out = sizer.calculate(
            balance=2000.0,
            entry_price=80000.0,
            stop_price=79999.99,
        )
        manager = PositionManager()

        corrected, _ = manager.audit(
            buy_intent(
                entry=80000.0,
                quantity=out.quantity,
            )
        )

        self.assertLessEqual(
            corrected.quantity * 80000.0, 500.0 + 1e-9
        )

    def test_tiny_capital_dust_fails_closed(self):
        sizer = PositionSizer()
        out = sizer.calculate(
            balance=0.01, entry_price=80000.0, stop_price=79500.0
        )
        manager = PositionManager()

        corrected, _ = manager.audit(
            buy_intent(entry=80000.0, quantity=out.quantity)
        )

        # 0.01 * 0.01 / 500 = 2e-7 < dust 1e-6 -> dropped.
        self.assertEqual(corrected.quantity, 0.0)
        self.assertFalse(corrected.valid)

    def test_repeated_identical_setup_one_order(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        first = buy_intent()
        first.setup_id = "S-1"

        order_a, id_a = registry.create(first, bar=10, timestamp=10)
        second = buy_intent()
        second.setup_id = "S-1"
        order_b, id_b = registry.create(second, bar=11, timestamp=11)

        self.assertEqual(id_a, id_b)
        self.assertIs(order_a, order_b)
        self.assertEqual(len(registry.all()), 1)

    def test_opposite_directions_are_distinct_ideas(self):
        from core.setup.economic_setup_registry import fingerprint_of

        long_fp = fingerprint_of(
            buy_intent(direction="BULLISH"),
            symbol="T",
            timeframe="1m",
        )
        short_fp = fingerprint_of(
            buy_intent(direction="BEARISH"),
            symbol="T",
            timeframe="1m",
        )

        self.assertNotEqual(long_fp, short_fp)

    def test_leverage_bound_holds_after_cap(self):
        out = PositionSizer().calculate(
            balance=2000.0, entry_price=80000.0, stop_price=79500.0
        )

        self.assertLessEqual(
            out.position_value / out.leverage, 500.0 + 1e-9
        )

    def test_risk_amount_never_exceeds_nominal(self):
        sizer = PositionSizer()

        for stop in (79500.0, 79999.0, 70000.0, 79900.0):
            out = sizer.calculate(
                balance=2000.0,
                entry_price=80000.0,
                stop_price=stop,
            )

            self.assertLessEqual(
                out.expected_loss, 2000.0 * 0.01 + 1e-9
            )


# ==================================================
# 11B-E — Order lifecycle sequencing
# ==================================================


class TestOrderLifecycle(unittest.TestCase):

    def _order(self, setup_id="S-E1"):
        order = buy_intent()
        order.setup_id = setup_id
        return order

    def test_eligibility_window_math(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        order, _ = registry.create(self._order(), bar=10, timestamp=600)

        # ENTRY_DELAY_BARS=1, MAX_WAIT_BARS=30.
        self.assertEqual(order.created_bar, 10)
        self.assertEqual(order.eligible_from_bar, 11)
        self.assertEqual(order.expires_at_bar, 41)
        self.assertEqual(order.status, "PENDING")

    def test_expiry_only_on_expiry_bar(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        order, _ = registry.create(self._order(), bar=10, timestamp=600)

        self.assertEqual(registry.advance(bar=40), [])
        self.assertEqual(order.status, "PENDING")

        expired = registry.advance(bar=41)
        self.assertEqual(expired, [order])
        self.assertEqual(order.status, "EXPIRED")

    def test_fill_consumes_exactly_once(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        order, _ = registry.create(self._order(), bar=10, timestamp=600)
        trade = Trade(direction="BULLISH", entry=100.0, quantity=1.0)

        first = registry.mark_filled(order, trade)
        second = registry.mark_filled(order, trade)

        self.assertTrue(bool(first))
        self.assertFalse(bool(second))
        self.assertEqual(order.status, "FILLED")

    def test_invalidation_is_not_expiry(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        order, _ = registry.create(self._order(), bar=10, timestamp=600)

        self.assertTrue(
            registry.invalidate(
                order, reason="stop breach", bar=15, price=89.0
            )
        )
        self.assertEqual(order.status, "INVALIDATED")
        self.assertEqual(registry.expired(), [])

    def test_no_lookahead_creation_bar_ineligible(self):
        from core.execution.order_registry import OrderRegistry

        registry = OrderRegistry()
        order, _ = registry.create(self._order(), bar=10, timestamp=600)

        # The signal exists at bar 10's close: fills may only
        # be considered from bar 11 on.
        self.assertGreater(order.eligible_from_bar, order.created_bar)

    def test_same_bar_ambiguous_close_is_conservative(self):
        sim = TradeSimulator()
        sim.open_trade(
            buy_intent(stop_loss=90.0, take_profit=110.0),
            timestamp=1,
        )

        # One candle spans both stop and target.
        sim.update(
            Candle(high=115.0, low=85.0, close=100.0, timestamp=2)
        )

        closed = sim.registry.closed()[0]
        self.assertEqual(closed.result, "LOSS")
        self.assertTrue(closed.ambiguous)


# ==================================================
# 11B-F — Economic dedup fingerprint
# ==================================================


class TestEconomicFingerprint(unittest.TestCase):

    def test_exact_duplicates_collapse(self):
        from core.setup.economic_setup_registry import fingerprint_of

        first = fingerprint_of(
            buy_intent(), symbol="T", timeframe="1m"
        )
        second = fingerprint_of(
            buy_intent(), symbol="T", timeframe="1m"
        )

        self.assertEqual(first, second)

    def test_different_structural_ids_same_idea(self):
        from core.setup.economic_setup_registry import fingerprint_of

        first = buy_intent()
        first.setup_id = "OB-954"
        second = buy_intent()
        second.setup_id = "OB-956"

        self.assertEqual(
            fingerprint_of(first, symbol="T", timeframe="1m"),
            fingerprint_of(second, symbol="T", timeframe="1m"),
        )

    def test_different_entries_differ(self):
        from core.setup.economic_setup_registry import fingerprint_of

        first = fingerprint_of(
            buy_intent(entry=100.0), symbol="T", timeframe="1m"
        )
        second = fingerprint_of(
            buy_intent(entry=101.0), symbol="T", timeframe="1m"
        )

        self.assertNotEqual(first, second)

    def test_different_stops_and_targets_differ(self):
        from core.setup.economic_setup_registry import fingerprint_of

        base = fingerprint_of(
            buy_intent(), symbol="T", timeframe="1m"
        )
        stop = fingerprint_of(
            buy_intent(stop_loss=89.0), symbol="T", timeframe="1m"
        )
        target = fingerprint_of(
            buy_intent(take_profit=111.0), symbol="T", timeframe="1m"
        )

        self.assertNotEqual(base, stop)
        self.assertNotEqual(base, target)

    def test_tick_snap_definition(self):
        from core.setup.economic_setup_registry import snap_price

        # 0.5 tick grid: 100.1 (200.2 -> 200) and 100.2
        # (200.4 -> 200) share bucket 100.0; 100.4
        # (200.8 -> 201) sits in bucket 100.5.
        self.assertEqual(snap_price(100.1, 0.5), snap_price(100.2, 0.5))
        self.assertNotEqual(
            snap_price(100.1, 0.5), snap_price(100.4, 0.5)
        )

    def test_fingerprint_is_stable_string(self):
        from core.setup.economic_setup_registry import fingerprint_of

        fp = fingerprint_of(
            buy_intent(), symbol="T", timeframe="1m"
        )

        self.assertIsInstance(fp, str)
        self.assertIn("T", fp)
        self.assertIn("BULLISH", fp)


# ==================================================
# 11B-G — Walk-forward validation
# ==================================================


class TestWalkForward(unittest.TestCase):

    def _runner(self, calls=None):
        from core.risk.account import Account

        def run(bars, config=None):
            if calls is not None:
                calls.append((tuple(bars), config))
            return Account(2000.0), TradeRegistry()

        return run

    def test_chronological_folds_no_overlap(self):
        from core.validation.walk_forward import WalkForwardTester

        history = list(range(100))
        result = WalkForwardTester(
            self._runner(), history, train_size=20, test_size=10
        ).run()

        self.assertGreater(result.fold_count, 0)

        for fold in result.folds:
            train_start, train_end = fold.train_range
            test_start, test_end = fold.test_range

            # Train immediately precedes test, never overlaps.
            self.assertEqual(train_end, test_start)
            self.assertLess(test_start, test_end)

            self.assertEqual(
                fold.train_range[1] - fold.train_range[0], 20
            )
            self.assertEqual(
                fold.test_range[1] - fold.test_range[0], 10
            )

        for first, second in zip(result.folds, result.folds[1:]):
            self.assertLess(first.test_range[0], second.test_range[0])

    def test_runner_sees_only_its_slice(self):
        from core.validation.walk_forward import WalkForwardTester

        seen = []
        history = list(range(50))
        WalkForwardTester(
            self._runner(seen), history, train_size=20, test_size=10
        ).run()

        self.assertTrue(seen)

        for bars, _config in seen:
            self.assertLessEqual(len(bars), 20)
            self.assertEqual(list(bars), sorted(bars))

    def test_deterministic_fold_generation(self):
        from core.validation.walk_forward import WalkForwardTester

        history = list(range(100))

        first = WalkForwardTester(
            self._runner(), history, train_size=20, test_size=10
        ).run()
        second = WalkForwardTester(
            self._runner(), history, train_size=20, test_size=10
        ).run()

        self.assertEqual(
            [f.train_range for f in first.folds],
            [f.train_range for f in second.folds],
        )
        self.assertEqual(
            [f.test_range for f in first.folds],
            [f.test_range for f in second.folds],
        )

    def test_candidate_selection_picks_best_train(self):
        from core.validation.walk_forward import WalkForwardTester

        from core.backtesting.trade_simulator import TradeSimulator

        def runner(bars, config):
            sim = TradeSimulator()
            if config == "win":
                sim.open_trade(buy_intent(), timestamp=1)
                sim.update(
                    Candle(
                        high=112.0, low=101.0, close=111.0,
                        timestamp=2,
                    )
                )
            return Account(2000.0), sim.registry

        result = WalkForwardTester(
            runner,
            list(range(30)),
            train_size=10,
            test_size=10,
            candidates=["lose", "win"],
            metric="net_profit",
        ).run()

        self.assertGreater(result.fold_count, 0)

        for fold in result.folds:
            self.assertEqual(fold.best_config, "win")

    def test_invalid_sizes_rejected(self):
        from core.validation.walk_forward import WalkForwardTester

        with self.assertRaises(ValueError):
            WalkForwardTester(
                self._runner(), list(range(10)),
                train_size=0, test_size=5,
            )


# ==================================================
# 11B-H — Performance metrics
# ==================================================


def _report(pnls, starting=2000.0):
    from core.analytics.performance import PerformanceAnalytics

    account = Account(starting_balance=starting)
    registry = TradeRegistry()

    for n, pnl in enumerate(pnls):
        trade = Trade(
            direction="BULLISH",
            entry=100.0,
            quantity=1.0,
            pnl=pnl,
            pnl_percent=pnl,
            status="CLOSED",
            result=(
                "WIN" if pnl > 0 else "LOSS" if pnl < 0 else ""
            ),
            exit_time=n + 1,
        )
        registry.add(trade)

    return PerformanceAnalytics.analyze(account, registry)


class TestPerformanceMetrics(unittest.TestCase):

    def test_win_rate_loss_expectancy(self):
        report = _report([10.0, 10.0, -5.0, 0.0])

        self.assertEqual(report.total_trades, 4)
        self.assertEqual(report.wins, 2)
        self.assertEqual(report.losses, 1)
        self.assertEqual(report.breakeven, 1)
        self.assertAlmostEqual(report.win_rate, 50.0)
        # Expectancy divides by ALL completed incl. breakeven.
        self.assertAlmostEqual(report.expectancy, 15.0 / 4)

    def test_profit_factor_edges(self):
        only_wins = _report([10.0, 5.0])
        self.assertEqual(only_wins.profit_factor, float("inf"))

        only_losses = _report([-10.0])
        self.assertEqual(only_losses.profit_factor, 0.0)

        empty = _report([])
        self.assertEqual(empty.total_trades, 0)
        self.assertEqual(empty.profit_factor, 0.0)
        self.assertEqual(empty.win_rate, 0.0)

        mixed = _report([20.0, -10.0])
        self.assertAlmostEqual(mixed.profit_factor, 2.0)

    def test_drawdown_math(self):
        from core.backtesting.accounting import classify_pnl

        account = Account(starting_balance=2000.0)
        registry = TradeRegistry()

        for n, pnl in enumerate([100.0, -150.0, 60.0]):
            trade = Trade(
                direction="BULLISH",
                entry=100.0,
                quantity=1.0,
                pnl=pnl,
                pnl_percent=pnl,
                status="CLOSED",
                exit_time=n + 1,
            )
            registry.add(trade)

            kind = classify_pnl(pnl)
            if kind == "WIN":
                account.book_profit(pnl)
            elif kind == "LOSS":
                account.book_loss(pnl)

        from core.analytics.performance import PerformanceAnalytics

        report = PerformanceAnalytics.analyze(account, registry)

        # Equity: 2000 -> 2100 -> 1950 -> 2010. Peak 2100,
        # trough 1950 -> drawdown 150.
        self.assertAlmostEqual(report.max_drawdown, 150.0)
        self.assertAlmostEqual(
            report.max_drawdown_percent, 150.0 / 2100 * 100
        )
        self.assertAlmostEqual(report.net_profit, 10.0)
        # Reconciliation: booked account agrees with report.
        self.assertAlmostEqual(report.final_balance, 2010.0)
        self.assertAlmostEqual(account.balance, 2010.0)

    def test_trade_based_sharpe_definition(self):
        # Position returns: pnl / (entry*qty) = pnl/100.
        report = _report([10.0, -4.0, 6.0, -2.0])

        returns = [0.10, -0.04, 0.06, -0.02]
        mean = sum(returns) / 4
        var = sum((r - mean) ** 2 for r in returns) / 3
        expected = mean / (var ** 0.5) * (4 ** 0.5)

        self.assertAlmostEqual(report.sharpe, expected)
        # Documented: trade-based, NOT annualized.
        self.assertNotEqual(report.sharpe, 0.0)

    def test_sortino_uses_downside_only(self):
        report = _report([10.0, -4.0, 6.0, -2.0])

        returns = [0.10, -0.04, 0.06, -0.02]
        mean = sum(returns) / 4
        downside = [min(0.0, r) for r in returns]
        dmean = sum(downside) / 4
        dvar = sum((r - dmean) ** 2 for r in downside) / 3
        expected = mean / (dvar ** 0.5) * (4 ** 0.5)

        self.assertAlmostEqual(report.sortino, expected)

    def test_single_trade_zero_volatility(self):
        report = _report([10.0])

        self.assertEqual(report.sharpe, 0.0)
        self.assertEqual(report.sortino, 0.0)

    def test_equity_curve_exit_order(self):
        from core.analytics.performance import PerformanceAnalytics

        account = Account(starting_balance=2000.0)
        registry = TradeRegistry()

        late = Trade(
            direction="BULLISH", entry=100.0, quantity=1.0,
            pnl=5.0, status="CLOSED", exit_time=99,
        )
        early = Trade(
            direction="BULLISH", entry=100.0, quantity=1.0,
            pnl=7.0, status="CLOSED", exit_time=5,
        )
        registry.add(late)
        registry.add(early)

        report = PerformanceAnalytics.analyze(account, registry)

        self.assertAlmostEqual(report.net_profit, 12.0)
        curve = report.equity_curve
        self.assertEqual(curve[0][0], 5)
        self.assertAlmostEqual(curve[-1][1], 2012.0)


if __name__ == "__main__":
    unittest.main()
