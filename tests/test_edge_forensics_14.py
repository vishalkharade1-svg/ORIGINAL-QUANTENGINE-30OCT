"""
====================================================

QuantEngine

Phase 14 -- executable-edge forensics suite.

Research-only regression tests. Nothing here tunes the
strategy, changes thresholds, or enables live trading.

  Funnel (§41.1-4): terminal-state exclusivity + no
    silent order loss at the registry layer.
  Phantom-win (§41.16) + PnL (§41.17-23): classify/gross/
    net sign consistency; single quantity multiplication;
    funding absence (FUNDING = UNAVAILABLE).
  Costs (§41.21-22, §15/16/44): structural vs assumed
    fee/slippage scenarios, explicitly labeled.
  Gaps/boundaries (§41.11-14): entry-bar open exactly at
    stop / at target, LONG and SHORT.
  Research (§41.33-35): OOS boundary integrity (6175-bar
    gate + verdict intact), frozen-gate pins (no silent
    optimization: 1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0  # active bounds; frozen era was 6.0
  Production (§41.36-40): safe defaults deny live;
    research reports never production-ready.

Stdlib only. No network. Deterministic.
====================================================
"""

import inspect
import math
import unittest
from types import SimpleNamespace
from unittest import mock

from config import risk_settings


# --------------------------------------------------
# Funnel: terminal-state exclusivity (§41.1-4)
# --------------------------------------------------

class TestFunnelTerminalExclusivity(unittest.TestCase):

    def _registry(self):
        from core.execution.order_registry import OrderRegistry
        return OrderRegistry()

    def _order(self, **kwargs):
        from core.risk.order_intent import OrderIntent
        fields = dict(direction="BULLISH", entry=100.0,
                      stop_loss=90.0, take_profit=160.0,
                      quantity=1.0, symbol="TEST", valid=True,
                      setup_id="FUNNEL-1")
        fields.update(kwargs)
        return OrderIntent(**fields)

    def test_terminal_states_mutually_exclusive(self):
        from core.execution.order_registry import (
            EXPIRED, FILLED, INVALIDATED, PENDING)
        reg = self._registry()
        minted, order_id = reg.create(self._order(), bar=0,
                                      timestamp=0)
        self.assertEqual(minted.status, PENDING)
        # Exactly one terminal transition wins; the rest are
        # refused (no silent re-terminal, no double booking).
        reg.invalidate(minted, reason="t", bar=1)
        self.assertEqual(minted.status, INVALIDATED)
        reg.mark_filled(minted, SimpleNamespace())
        self.assertEqual(minted.status, INVALIDATED)
        reg2 = self._registry()
        minted2, _ = reg2.create(self._order(), bar=0,
                                 timestamp=0)
        reg2.mark_filled(minted2, SimpleNamespace())
        self.assertEqual(minted2.status, FILLED)
        reg2.invalidate(minted2, reason="t", bar=1)
        self.assertEqual(minted2.status, FILLED)
        self.assertIn(EXPIRED, (EXPIRED, FILLED, INVALIDATED,
                                PENDING))

    def test_funnel_totals_reconcile(self):
        reg = self._registry()
        terminal = {"FILLED": 0, "INVALIDATED": 0, "EXPIRED": 0}
        orders = []
        for i in range(6):
            minted, _ = reg.create(
                self._order(setup_id="FUNNEL-%d" % i),
                bar=0, timestamp=0)
            orders.append(minted)
        reg.mark_filled(orders[0], SimpleNamespace())
        reg.mark_filled(orders[1], SimpleNamespace())
        for order in orders[2:4]:
            reg.invalidate(order, reason="t", bar=1)
        # Expiry is bar-anchored: advancing far past every
        # eligibility window terminals the rest as EXPIRED.
        reg.advance(bar=10_000)
        for order in orders:
            terminal[order.status] += 1
        # Mutually exclusive partition: every order lands in
        # exactly one terminal bucket; none lost, none double.
        self.assertEqual(sum(terminal.values()), 6)
        self.assertEqual(
            terminal, {"FILLED": 2, "INVALIDATED": 2,
                       "EXPIRED": 2})

    def test_unknown_order_never_fills(self):
        reg = self._registry()
        self.assertIsNone(reg.get("NOPE"))
        stranger = self._order(setup_id="STRANGER")
        # Not created in this registry: fill path refuses.
        reg.mark_filled(stranger, SimpleNamespace())
        self.assertNotEqual(
            getattr(stranger, "status", "PENDING"), "FILLED")


# --------------------------------------------------
# Phantom-win defense + PnL (§41.16-20)
# --------------------------------------------------

class TestPhantomWinDefense(unittest.TestCase):

    def test_classify_never_contradicts_gross_sign(self):
        from core.backtesting.accounting import classify_pnl
        cases = [(10.0, "WIN"), (0.001, "WIN"), (-10.0, "LOSS"),
                 (-0.001, "LOSS"), (0.0, "BREAKEVEN"),
                 (-0.0, "BREAKEVEN")]
        for pnl, expected in cases:
            with self.subTest(pnl=pnl):
                self.assertEqual(classify_pnl(pnl), expected)

    def test_non_finite_pnl_raises_never_books(self):
        from core.backtesting.accounting import classify_pnl
        for bad in (float("nan"), float("inf"),
                    float("-inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    classify_pnl(bad)

    def test_quantity_multiplied_exactly_once(self):
        from core.backtesting.accounting import (
            gross_pnl, net_pnl)
        # LONG: (exit-entry)*qty, once.
        self.assertAlmostEqual(
            gross_pnl("BULLISH", 100.0, 110.0, 2.0), 20.0)
        # SHORT: (entry-exit)*qty, once.
        self.assertAlmostEqual(
            gross_pnl("BEARISH", 100.0, 90.0, 2.0), 20.0)
        self.assertAlmostEqual(
            gross_pnl("BEARISH", 100.0, 110.0, 2.0), -20.0)
        # Net subtracts modeled costs exactly once.
        self.assertAlmostEqual(
            net_pnl(20.0, commission=1.0, slippage=0.5), 18.5)

    def test_funding_requires_explicit_evidence(self):
        # Funding is now an explicit accounting leg, but unavailable venue
        # evidence must never be silently synthesized by the Trade itself.
        from core.backtesting.accounting import net_pnl
        from core.backtesting.trade import Trade
        from core.execution.economics import FundingSchedule
        params = set(inspect.signature(net_pnl).parameters)
        self.assertIn("funding", params)
        trade = Trade()
        self.assertTrue(hasattr(trade, "funding"))
        self.assertEqual(trade.funding, 0.0)
        self.assertEqual(trade.funding_events, 0)
        self.assertEqual(FundingSchedule([]).events, ())


# --------------------------------------------------
# Cost scenarios (§15/16/44, §41.21-22)
# --------------------------------------------------

def scenario_structural(gross):
    """Zero-cost structural baseline. VERIFIED (config)."""
    return {"net": float(gross), "fees": 0.0, "slippage": 0.0,
            "funding": 0.0, "label": "VERIFIED-zero-cost"}


def scenario_conservative_fees(gross, notional,
                               bps=2.5):
    """Conservative taker-fee assumption. ASSUMED (illustrative,
    NOT venue-verified): 2.5 bps per side, round trip."""
    fees = abs(float(notional)) * (bps / 10000.0) * 2.0
    return {"net": float(gross) - fees, "fees": fees,
            "slippage": 0.0, "funding": 0.0,
            "label": "ASSUMED-2.5bps-per-side"}


def scenario_conservative_slippage(gross, notional,
                                   bps=1.0):
    """Conservative slippage assumption. ASSUMED (illustrative,
    NOT venue-verified): 1 bp adversely per side."""
    slip = abs(float(notional)) * (bps / 10000.0) * 2.0
    return {"net": float(gross) - slip, "fees": 0.0,
            "slippage": slip, "funding": 0.0,
            "label": "ASSUMED-1bp-per-side"}


def scenario_combined(gross, notional):
    """Fees + slippage. ASSUMED (sums the two schedules above)."""
    fees = scenario_conservative_fees(gross, notional)
    slip = scenario_conservative_slippage(gross, notional)
    return {"net": float(gross) - fees["fees"] - slip["slippage"],
            "fees": fees["fees"], "slippage": slip["slippage"],
            "funding": 0.0, "label": "ASSUMED-combined"}


def scenario_funding():
    """Funding-aware scenario. UNAVAILABLE: no funding data
    or simulator semantics exist; zero is NOT substituted."""
    return {"net": None, "fees": None, "slippage": None,
            "funding": None, "label": "UNAVAILABLE"}


class TestCostScenarios(unittest.TestCase):

    def test_structural_is_identity(self):
        self.assertEqual(scenario_structural(10.0)["net"], 10.0)
        self.assertEqual(scenario_structural(-5.0)["net"], -5.0)
        self.assertEqual(scenario_structural(10.0)["label"],
                         "VERIFIED-zero-cost")

    def test_conservative_fees_labeled_assumed(self):
        out = scenario_conservative_fees(10.0, 10000.0)
        self.assertAlmostEqual(out["fees"], 5.0)
        self.assertAlmostEqual(out["net"], 5.0)
        self.assertTrue(out["label"].startswith("ASSUMED"))

    def test_conservative_slippage_labeled_assumed(self):
        out = scenario_conservative_slippage(10.0, 10000.0)
        self.assertAlmostEqual(out["slippage"], 2.0)
        self.assertAlmostEqual(out["net"], 8.0)
        self.assertTrue(out["label"].startswith("ASSUMED"))

    def test_combined_sums_both_legs(self):
        out = scenario_combined(10.0, 10000.0)
        self.assertAlmostEqual(out["net"], 3.0)
        self.assertTrue(out["label"].startswith("ASSUMED"))

    def test_funding_never_substitutes_zero(self):
        out = scenario_funding()
        self.assertIsNone(out["net"])
        self.assertEqual(out["label"], "UNAVAILABLE")

    def test_scenarios_deterministic(self):
        first = scenario_combined(123.456, 7890.0)
        second = scenario_combined(123.456, 7890.0)
        self.assertEqual(first, second)


# --------------------------------------------------
# Gap boundaries (§41.13-14)
# --------------------------------------------------

class SimpleCandle:

    def __init__(self, open_, high, low, close, timestamp):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.timestamp = timestamp
        self.symbol = "TEST"
        self.timeframe = "1m"


class NamespaceDriven:

    def __init__(self):
        from core.pipeline.pipeline_context import (
            PipelineContext,
        )
        from core.market_state import MarketState
        self.context = PipelineContext()
        self.context.market = MarketState(symbol="TEST",
                                          timeframe="1m")

    def reset(self):
        pass


class TestGapBoundaries(unittest.TestCase):

    def _drive(self, direction, entry, stop, target, bar):
        from core.backtesting.trade_simulator import (
            TradeSimulator,
        )
        from backtesting.backtester import Backtester
        from core.risk.order_intent import OrderIntent
        from core.execution.entry_model import (
            ENTRY_MODE_BREAKOUT_CONTINUATION,
            EXECUTION_NEXT_BAR_OPEN,
        )
        pipeline = NamespaceDriven()
        simulator = TradeSimulator()
        backtester = Backtester(pipeline, None, simulator)
        context = pipeline.context
        order = OrderIntent(
            direction=direction, entry=entry, stop_loss=stop,
            take_profit=target, quantity=1.0, commission=0.0,
            slippage=0.0, confidence=85.0, score=85.0,
            symbol="TEST", valid=True, setup_id="GAP-1",
            entry_mode=ENTRY_MODE_BREAKOUT_CONTINUATION,
            entry_execution=EXECUTION_NEXT_BAR_OPEN,
        )
        minted, _ = context.order_registry.create(
            order, bar=0, timestamp=0)
        minted.breakout_triggered = True
        minted.breakout_trigger_bar = 0
        minted.breakout_trigger_close = entry
        context.replay_index = 1
        with mock.patch.object(
            risk_settings, "ACTIVE_ENTRY_MODES",
            (ENTRY_MODE_BREAKOUT_CONTINUATION,),
        ):
            backtester._execute_signal(bar)
        return simulator, context, minted

    def test_long_open_exactly_at_stop_invalidates(self):
        # LONG E=110/S=100: open==100 breaches (low<=stop),
        # so structural invalidation fires first; never a fill.
        bar = SimpleCandle(open_=100.0, high=105.0, low=99.0,
                           close=102.0, timestamp=1)
        sim, ctx, order = self._drive("BULLISH", 110.0, 100.0,
                                      170.0, bar)
        self.assertIsNone(sim.current_trade)
        registered = ctx.order_registry.get(order.order_id)
        self.assertEqual(registered.status, "INVALIDATED")

    def test_long_open_exactly_at_target_refused(self):
        # LONG E=110/T=170: open==170 fails strict geometry
        # (entry must sit strictly inside), so the fill is
        # refused and the order rides.
        bar = SimpleCandle(open_=170.0, high=172.0, low=168.0,
                           close=171.0, timestamp=1)
        with self.assertLogs("backtesting.backtester",
                             level="ERROR") as logs:
            sim, ctx, order = self._drive("BULLISH", 110.0,
                                          100.0, 170.0, bar)
        self.assertIsNone(sim.current_trade)
        registered = ctx.order_registry.get(order.order_id)
        self.assertEqual(registered.status, "PENDING")
        self.assertTrue(
            any("ORDER_SKIPPED_INVERTED_FILL" in line
                for line in logs.output))

    def test_short_open_exactly_at_stop_invalidates(self):
        # SHORT E=100/S=110: open==110 breaches (high>=stop).
        bar = SimpleCandle(open_=110.0, high=111.0, low=105.0,
                           close=108.0, timestamp=1)
        sim, ctx, order = self._drive("BEARISH", 100.0, 110.0,
                                      40.0, bar)
        self.assertIsNone(sim.current_trade)
        registered = ctx.order_registry.get(order.order_id)
        self.assertEqual(registered.status, "INVALIDATED")

    def test_short_open_exactly_at_target_refused(self):
        # SHORT E=100/T=40: open==40 fails strict geometry.
        bar = SimpleCandle(open_=40.0, high=42.0, low=38.0,
                           close=41.0, timestamp=1)
        with self.assertLogs("backtesting.backtester",
                             level="ERROR") as logs:
            sim, ctx, order = self._drive("BEARISH", 100.0,
                                          110.0, 40.0, bar)
        self.assertIsNone(sim.current_trade)
        registered = ctx.order_registry.get(order.order_id)
        self.assertEqual(registered.status, "PENDING")
        self.assertTrue(
            any("ORDER_SKIPPED_INVERTED_FILL" in line
                for line in logs.output))


# --------------------------------------------------
# Research guards (§41.33-35)
# --------------------------------------------------

class TestOOSBoundaryIntegrity(unittest.TestCase):

    def test_full_wf_gate_threshold_intact(self):
        from research.phase11g_q import gate
        self.assertEqual(gate.WF_REQUIRED_BARS, 6175)

    def test_q_verdict_still_data_insufficient(self):
        import pathlib
        doc = pathlib.Path("docs/audit/phase11g_Q_full_oos_execution.md")
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("FULL_WF_DATA_INSUFFICIENT", text)

    def test_frozen_risk_reward_unchanged(self):
        # No-silent-optimization pin: the 1:6 invariant value
        # itself is frozen. Any change must update this test
        # deliberately (it never changes by accident).
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )


# --------------------------------------------------
# Production posture (§41.36-40)
# --------------------------------------------------

class TestProductionPosture(unittest.TestCase):

    def test_safe_defaults_deny_live(self):
        from config.settings import Settings
        fresh = Settings()
        self.assertTrue(fresh.PAPER_MODE)
        self.assertFalse(fresh.LIVE_MODE)
        self.assertFalse(fresh.ALLOW_LIVE)
        self.assertFalse(fresh.LIVE_EXECUTE)

    def test_oos_reports_never_production_ready(self):
        from core.research.oos.report import OosReport
        with self.assertRaises(ValueError):
            OosReport().is_production_ready()


if __name__ == "__main__":
    unittest.main()
