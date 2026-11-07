"""
====================================================

QuantEngine

Phase 4H: Entry Model Shadow Comparison Tests

Run with:

    python -m unittest tests.test_entry_shadow -v

Proves (mapped to the Phase 4H steps):

  STEP 1  -- the three entry models trigger on their own
             operational primitives, deterministically:
               LIMIT_RETEST            candle trades through E
                                       (low <= E <= high)
               MARKET_CONFIRMATION     reach E AND close beyond E
                                       toward the direction
               BREAKOUT_CONTINUATION   exceed E AND close beyond on
                                       the trade side
             and the STRUCTURAL STOP breach is checked BEFORE any
             same-bar fill (the backtester's step-3-before-step-4).
  STEP 2  -- hypothetical outcomes mirror TradeSimulator's exact
             win/loss convention: stop checked before target on
             every candle (a candle that hits both resolves LOSS at
             the stop level); MAE / MFE are measured from the first
             bar AFTER the entry bar and capped at the stop/target
             levels; unresolved windows settle UNRESOLVED.
  STEP 3  -- missed continuations per model (entry never reached
             yet price ran >= fraction of the way to the target).
  STEP 4  -- the ATR-distance vs MAX_WAIT_BARS-expiry relationship:
             distance buckets (0-1/1-2/2-5/5-10/10-15/15-30/30+)
             with reached-within-expiry / reached-within-window /
             never counts, avg bars to reach, and the point-biserial
             correlation -- the Phase 4H question, measured before
             either threshold moves.
  STEP 5  -- the shadow's population rule: every TRADE-ELIGIBLE
             canonical setup is captured (first appearance per
             structural_id), carrying the same economics and order
             context as the minted order.
  STEP 6  -- SHADOW_ENTRY_MODES gates which shadow models are
             measured (LIMIT_RETEST is always measured).
  STEP 7  -- the shadow is DIAGNOSTIC: disabling it leaves every
             order outcome byte-identical (no look-ahead leak).

Stdlib only -- no network.

====================================================
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from config import risk_settings

from core.setup.entry_shadow import (
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    SHADOW_MODES,
    EntryShadow,
    format_shadow_report,
)
from core.setup.entry_feasibility import (
    ENTRY_TOO_FAR,
    create_entry_feasibility,
)
from core.setup.setup_candidate import SetupCandidate

from tests.test_execution_lifecycle import (
    hold_candle,
    miss_candle,
    run_world,
    tp_candle,
    touch_candle,
)


def candle(bar, high, low, close):
    return SimpleNamespace(
        timestamp=bar, open=close, high=high, low=low, close=close,
    )


def canned_setup(
    direction="BULLISH",
    entry=110.0,
    stop=100.0,
    target=130.0,
    observed=100.0,
    atr=10.0,
    structural="OB-1",
    creation_bar=0,
):
    rr = (
        abs(target - entry) / abs(entry - stop)
        if abs(entry - stop) > 0
        else 0.0
    )
    c = SetupCandidate(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        risk_reward=rr,
        confidence=85.0,
        score=85.0,
    )
    c.setup_id = structural
    c.structural_id = structural
    c.observed_price = observed
    c.atr = atr
    c.entry_mode = ENTRY_MODE_LIMIT_RETEST
    c.entry_feasibility = create_entry_feasibility(
        c,
        creation_price=observed,
        atr=atr,
        creation_bar=creation_bar,
    )
    return c


def _state(shadow):
    return shadow.states()[0]


# ==========================================================
# STEP 1: three models, one operational primitive each
# ==========================================================


class TestShadowTriggers(unittest.TestCase):

    def test_limit_fills_on_reach_through_only(self):
        # BULLISH bar reaches through 110 but CLOSES below it
        # (high 112 / low 108 / close 109): the LIMIT rests at 110
        # and fills; the market confirmation needs a close >= E and
        # the breakout needs high AND close > E -- neither is given.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 112.0, 108.0, 109.0), bar=1)

        state = _state(shadow)

        self.assertTrue(state.limit.triggered)

        self.assertEqual(state.limit.entry_bar, 1)

        self.assertEqual(state.limit.entry_price, 110.0)

        self.assertFalse(state.market.triggered)

        self.assertFalse(state.breakout.triggered)

    def test_market_confirmation_requires_close_beyond(self):
        # Bar 1 reaches 110 but closes on the WRONG side (109):
        # not confirmed. Bar 2 reaches 110 and closes exactly at the
        # level (Close == E): confirmed -- the market order enters at
        # the close 110. Breakout needs a close/high STRICTLY beyond
        # E, so it stays quiet on both bars.
        shadow = EntryShadow(window_bars=5)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 112.0, 108.0, 109.0), bar=1)

        self.assertFalse(_state(shadow).market.triggered)

        shadow.advance(candle(2, 110.0, 109.0, 110.0), bar=2)

        state = _state(shadow)

        self.assertTrue(state.market.triggered)

        self.assertEqual(state.market.entry_bar, 2)

        self.assertEqual(state.market.entry_price, 110.0)

        self.assertFalse(state.breakout.triggered)

    def test_breakout_fires_only_when_price_leaves_the_zone(self):
        # A wick above E that CLOSES below it is a rejection, not a
        # continuation. A candle above E that also closes above E is
        # a real breakout -- price moved on without the retest (low
        # stays above E, so LIMIT and MARKET are never filled).
        shadow = EntryShadow(window_bars=5)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 115.0, 113.0, 109.0), bar=1)

        self.assertFalse(_state(shadow).breakout.triggered)

        shadow.advance(candle(2, 116.0, 114.0, 114.5), bar=2)

        state = _state(shadow)

        self.assertTrue(state.breakout.triggered)

        self.assertEqual(state.breakout.entry_bar, 2)

        self.assertEqual(state.breakout.entry_price, 114.5)

        self.assertFalse(state.limit.triggered)

        self.assertFalse(state.market.triggered)

    def test_stop_breach_precedes_any_same_bar_fill(self):
        # The candle trades through the entry 110 AND breaches the
        # structural stop 100 in the SAME bar (high 112 / low 99).
        # The backtester's step-3-before-step-4 ordering resolves it
        # as an invalidation: NO model fills, the idea is dead.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 112.0, 99.0, 105.0), bar=1)

        state = _state(shadow)

        self.assertTrue(state.idea_invalidated)

        self.assertEqual(state.idea_invalidated_bar, 1)

        self.assertFalse(state.limit.triggered)

        self.assertFalse(state.market.triggered)

        self.assertFalse(state.breakout.triggered)

    def test_bearish_models_trigger(self):
        # BEARISH mirrors: entry 90, stop 105, target 70. The bar
        # reaches through 90 and closes below it -- all three models
        # trigger on their primitives.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup(
            direction="BEARISH", entry=90.0, stop=105.0,
            target=70.0, observed=100.0,
        ))

        shadow.advance(candle(1, 91.0, 88.0, 88.5), bar=1)

        state = _state(shadow)

        self.assertTrue(state.limit.triggered)

        self.assertTrue(state.market.triggered)

        self.assertTrue(state.breakout.triggered)

    def test_bearish_invalidation_and_rejection(self):
        # A bearish wick ABOVE E with a close above it never reaches
        # 90 (low stays above 90): no fills. Then a bar that breaches
        # the bearish stop 105 invalidates the idea before anything.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup(
            direction="BEARISH", entry=90.0, stop=105.0,
            target=70.0, observed=100.0,
        ))

        shadow.advance(candle(1, 92.0, 91.0, 92.5), bar=1)

        state = _state(shadow)

        self.assertFalse(state.limit.triggered)

        shadow.advance(candle(2, 107.0, 100.0, 106.0), bar=2)

        self.assertTrue(state.idea_invalidated)

        self.assertFalse(state.limit.triggered)

    def test_trade_ineligible_observations_are_excluded(self):
        # The population is TRADE-ELIGIBLE setups: ineligible
        # candidates are never captured (the builder path only calls
        # observe() for candidates; the shadow filters again).
        shadow = EntryShadow(window_bars=4)

        c = canned_setup()
        c.trade_eligible = False
        shadow.observe(c)

        shadow.advance(candle(1, 112.0, 108.0, 110.0), bar=1)

        self.assertEqual(shadow.count(), 0)


# ==========================================================
# STEP 2: outcomes mirror TradeSimulator (SL before TP)
# ==========================================================


class TestShadowOutcomes(unittest.TestCase):

    def test_sl_resolves_loss_before_target_same_bar(self):
        # Fill at 110 on bar 1; bar 2 hits BOTH the stop 100 and the
        # target 130 (high 131 / low 99). TradeSimulator checks the
        # stop first: LOSS, MAE capped at |110 - 100| = 10.0.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 112.0, 108.0, 110.5), bar=1)

        shadow.advance(candle(2, 131.0, 99.0, 120.0), bar=2)

        state = _state(shadow)

        self.assertEqual(state.limit.resolved, "LOSS")

        self.assertTrue(state.limit.sl_hit)

        self.assertFalse(state.limit.tp_hit)

        self.assertEqual(state.limit.bars_until_sl, 1)

        self.assertEqual(state.limit.mae, 10.0)

    def test_tp_wins_and_mfe_capped_at_target(self):
        # Fill at 110; bar 3 reaches far past the target 130. MFE is
        # capped at the target distance |130 - 110| = 20.0 the way a
        # real limit order's take-profit would fill.
        shadow = EntryShadow(window_bars=5)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 112.0, 108.0, 110.0), bar=1)

        shadow.advance(candle(2, 112.0, 109.0, 110.5), bar=2)

        shadow.advance(candle(3, 140.0, 130.0, 132.0), bar=3)

        state = _state(shadow)

        self.assertEqual(state.limit.resolved, "WIN")

        self.assertTrue(state.limit.tp_hit)

        self.assertEqual(state.limit.bars_until_tp, 2)

        self.assertEqual(state.limit.mfe, 20.0)

    def test_mae_favourable_excursion_start_after_entry_bar(self):
        # The entry bar itself is excluded: a fill at close 110 on a
        # bar whose low dug to 100.5 must not count that pre-entry lot
        # as adverse excursion. MAE therefore starts from bar 2.
        shadow = EntryShadow(window_bars=5)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 110.0, 100.5, 110.0), bar=1)

        shadow.advance(candle(2, 112.0, 105.0, 111.0), bar=2)

        state = _state(shadow)

        self.assertEqual(state.limit.mae, 5.0)

    def test_unresolved_when_window_ends_without_exit(self):
        # Filled but the window closes before either level: settled
        # UNRESOLVED with MAE / MFE recorded from the excursion.
        shadow = EntryShadow(window_bars=3)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 112.0, 108.0, 110.0), bar=1)

        state = _state(shadow)

        self.assertFalse(state._settled)

        shadow.advance(candle(2, 112.0, 105.0, 111.0), bar=2)

        shadow.advance(candle(3, 114.0, 104.0, 113.0), bar=3)

        self.assertTrue(state._settled)

        self.assertEqual(state.limit.resolved, "UNRESOLVED")

        self.assertEqual(state.limit.mae, 6.0)


# ==========================================================
# STEP 3: missed continuations per model
# ==========================================================


class TestMissedContinuationShadow(unittest.TestCase):

    def test_market_misses_a_clean_continuation(self):
        # A gap-runner: price never prints a bar that brackets E
        # (bar 1 closes below it, bar 2 GAPS above it), so neither
        # the LIMIT retest nor the MARKET confirmation ever gets its
        # signal -- yet price runs >= 50% of the way from 110 to the
        # 130 target. The BREAKOUT model caught the same move (high
        # AND close beyond E): its fill cleared the flag.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 109.0, 107.0, 108.0), bar=1)

        shadow.advance(candle(2, 122.0, 111.5, 120.0), bar=2)

        state = _state(shadow)

        self.assertFalse(state.market.triggered)

        self.assertFalse(state.limit.triggered)

        self.assertTrue(state.breakout.triggered)

        shadow.advance(candle(3, 124.0, 118.0, 122.0), bar=3)

        shadow.advance(candle(4, 126.0, 120.0, 124.0), bar=4)

        self.assertTrue(state.market.missed_continuation)

        self.assertTrue(state.limit.missed_continuation)

        self.assertFalse(state.breakout.missed_continuation)

    def test_no_missing_when_price_heads_to_the_stop(self):
        # No signal AND no progress toward the target: nothing is
        # ever flagged as a missed continuation.
        shadow = EntryShadow(window_bars=4)

        shadow.observe(canned_setup())

        shadow.advance(candle(1, 105.0, 101.0, 103.0), bar=1)

        shadow.advance(candle(2, 104.0, 100.5, 102.0), bar=2)

        shadow.advance(candle(3, 104.0, 100.5, 102.0), bar=3)

        shadow.advance(candle(4, 104.0, 100.5, 102.0), bar=4)

        state = _state(shadow)

        self.assertFalse(state.limit.missed_continuation)

        self.assertFalse(state.market.missed_continuation)

        self.assertFalse(state.breakout.missed_continuation)


# ==========================================================
# STEP 4: ATR distance vs MAX_WAIT_BARS expiry
# ==========================================================


class TestAtrDistanceVsExpiry(unittest.TestCase):

    def test_distance_expiry_relationship_BEFORE_tuning(self):
        # Five trade-eligible setups at 0.25 / 1.5 / 12 / 25 / 40
        # ATRs from their entries, walked through a market that
        # reaches them at bars 1 / 2 / 6 / 35 / never, with a
        # MAX_WAIT_BARS expiry of 5 (eligible window ends at bar 6).
        # Distance vs expiry: the 12-ATR setup is just inside the
        # expiry, the 25-ATR one arrives only after it, the 40-ATR
        # one never arrives at all.
        shadow = EntryShadow(
            window_bars=40, max_wait_bars=5, missed_target_fraction=0.5,
        )

        shadow.observe(canned_setup(
            structural="S1", entry=102.5, observed=100.0, atr=10.0))
        shadow.observe(canned_setup(
            structural="S2", entry=115.0, observed=100.0, atr=10.0))
        shadow.observe(canned_setup(
            structural="S3", entry=220.0, observed=100.0, atr=10.0))
        shadow.observe(canned_setup(
            structural="S4", entry=350.0, observed=100.0, atr=10.0))
        shadow.observe(canned_setup(
            structural="S5", entry=500.0, observed=100.0, atr=10.0))

        seq = [
            candle(1, 103.0, 102.0, 102.5),
            candle(2, 116.0, 102.5, 115.0),
            candle(3, 140.0, 115.0, 138.0),
            candle(4, 162.0, 138.0, 160.0),
            candle(5, 180.0, 160.0, 178.0),
            candle(6, 221.0, 178.0, 220.0),
            candle(7, 240.0, 220.0, 238.0),
            candle(8, 258.0, 238.0, 256.0),
            candle(20, 300.0, 256.0, 298.0),
            candle(34, 340.0, 298.0, 338.0),
            candle(35, 351.0, 338.0, 350.0),
            candle(36, 368.0, 350.0, 366.0),
            candle(40, 430.0, 366.0, 428.0),
        ]
        for c in seq:
            shadow.advance(c, bar=c.timestamp)

        # S3 reached on bar 6 -- exactly the last eligible bar
        # (creation 0, expiry 0 + 1 + 5 = 6).
        self.assertTrue(
            _state_by_id(shadow, "S3").reached_within_expiry
        )
        # S4 reached on bar 35: inside the 40-bar tracking window but
        # AFTER the 6-bar order expiry.
        self.assertFalse(
            _state_by_id(shadow, "S4").reached_within_expiry
        )
        self.assertEqual(
            _state_by_id(shadow, "S4").limit.entry_bar, 35
        )
        # S5 (40 ATR) never reached at all.
        self.assertIsNone(_state_by_id(shadow, "S5").limit.entry_bar)

        rep = shadow.report()

        exp = rep["atr_versus_expiry"]

        by = {b["bucket"]: b for b in exp["buckets"]}

        self.assertEqual(by["0-1"]["count"], 1)
        self.assertEqual(by["0-1"]["reached_within_expiry"], 1)
        self.assertEqual(by["0-1"]["avg_bars_to_reach"], 1.0)

        self.assertEqual(by["1-2"]["count"], 1)
        self.assertEqual(by["1-2"]["reached_within_expiry"], 1)

        for bucket in ("2-5", "5-10"):
            self.assertEqual(by[bucket]["count"], 0)

        self.assertEqual(by["10-15"]["count"], 1)
        self.assertEqual(by["10-15"]["reached_within_expiry"], 1)
        self.assertEqual(by["10-15"]["avg_bars_to_reach"], 6.0)

        self.assertEqual(by["15-30"]["count"], 1)
        self.assertEqual(by["15-30"]["reached_within_expiry"], 0)
        self.assertEqual(by["15-30"]["reached_within_window"], 1)
        self.assertEqual(by["15-30"]["never_reached"], 0)
        self.assertEqual(by["15-30"]["avg_bars_to_reach"], 35.0)

        self.assertEqual(by["30+"]["count"], 1)
        self.assertEqual(by["30+"]["reached_within_expiry"], 0)
        self.assertEqual(by["30+"]["reached_within_window"], 0)
        self.assertEqual(by["30+"]["never_reached"], 1)
        self.assertEqual(by["30+"]["avg_bars_to_reach"], 0.0)

        # The whole point: 3 of 5 reached inside the expiry, 1 more
        # came only after it, 1 never came.
        self.assertAlmostEqual(exp["reached_within_expiry_share"], 0.6)

        self.assertAlmostEqual(
            exp["avg_entry_distance_atr_filled"], 38.75 / 4.0
        )

        self.assertAlmostEqual(
            exp["avg_entry_distance_atr_unfilled"], 40.0
        )

        # Farther entries reached within expiry LESS often: the
        # point-biserial correlation is negative.
        self.assertLess(exp["correlation_fill_within_expiry"], 0.0)

    def test_unfilled_order_uses_default_horizon(self):
        # With no order registry the expiry horizon defaults to
        # created + 1 + MAX_WAIT_BARS (a never-reached 40-ATR entry
        # against a tight 3-bar expiry).
        shadow = EntryShadow(window_bars=5, max_wait_bars=3)

        shadow.observe(canned_setup(
            structural="SX", entry=500.0, observed=100.0, atr=10.0))

        shadow.advance(candle(1, 103.0, 102.0, 102.0), bar=1)
        shadow.advance(candle(2, 105.0, 103.0, 104.0), bar=2)
        shadow.advance(candle(3, 108.0, 105.0, 107.0), bar=3)
        shadow.advance(candle(4, 110.0, 108.0, 109.0), bar=4)
        shadow.advance(candle(5, 112.0, 110.0, 111.0), bar=5)

        state = _state(shadow)

        self.assertFalse(state.reached_within_expiry)

        self.assertIsNone(state.limit.entry_bar)

        self.assertIsNone(state.order_expires_bar)

        rep = shadow.report()

        self.assertEqual(rep["atr_versus_expiry"]["buckets"][-1]["never_reached"], 1)


# ==========================================================
# STEP 5: the population rule + order context
# ==========================================================


class TestShadowPopulation(unittest.TestCase):

    def test_shadow_captures_the_trade_eligible_population(self):
        # The seeded world mints exactly one BULLISH eligible setup.
        # The shadow's population rule (first appearance per
        # structural_id, trade-eligible only) must match the
        # ZoneEligibilityLog's trade-eligible count, and the captured
        # state must carry the SAME economics and order context as
        # the order that was actually minted. The world runs a full
        # tracking window so the state settles and the
        # reached-within-expiry decision is final.
        candles = (
            [miss_candle(1), touch_candle(2)]
            + [hold_candle(i) for i in range(3, 64)]
        )

        _, _, pipeline, registry = run_world(candles)

        shadow = pipeline.context.entry_shadow

        self.assertEqual(
            shadow.count(),
            pipeline.context.zone_eligibility.report()["trade_eligible"],
        )

        self.assertEqual(shadow.count(), 1)

        order = registry.all()[0]

        state = _state(shadow)

        self.assertAlmostEqual(state.entry, order.entry)

        self.assertAlmostEqual(state.stop_loss, order.stop_loss)

        self.assertAlmostEqual(state.take_profit, order.take_profit)

        # Feasibility snapshot self-consistency: creating price was
        # the first candle's close (107.5) and the ATR stack was 15.
        self.assertAlmostEqual(
            state.entry_distance_atr,
            round(abs(110.0 - 107.5) / 15.0, 6),
        )

        # The shadow learned the order's REAL eligible window.
        self.assertEqual(state.order_id, getattr(order, "order_id", ""))

        self.assertEqual(
            state.order_expires_bar,
            getattr(order, "expires_at_bar", None),
        )

        self.assertTrue(state._settled)

        # The entry was genuinely reached on bar 2 (touch_candle) and
        # that bar sat inside the order's eligible window, so the
        # LIMIT ordering captured the 30-bar-expiry question as a hit.
        self.assertEqual(state.limit.entry_bar, 2)

        self.assertTrue(state.reached_within_expiry)

    def test_report_direction_views(self):
        # BULLISH / BEARISH views partition the population, and the
        # ALL view is the sum of the two in this single-direction world.
        _, _, pipeline, _ = run_world(
            [miss_candle(1), touch_candle(2), tp_candle(3)]
        )

        shadow = pipeline.context.entry_shadow

        rep_all = shadow.report()
        rep_bull = shadow.report("BULLISH")
        rep_bear = shadow.report("BEARISH")

        self.assertEqual(rep_all["total_setups"], 1)
        self.assertEqual(rep_bull["total_setups"], 1)
        self.assertEqual(rep_bear["total_setups"], 0)

        # format_shadow_report renders without error for all three.
        self.assertTrue(format_shadow_report(rep_all, "ALL"))
        self.assertTrue(format_shadow_report(rep_bull, "BULLISH"))
        self.assertTrue(format_shadow_report(rep_bear, "BEARISH"))


# ==========================================================
# STEP 6: SHADOW_ENTRY_MODES measurement gate
# ==========================================================


class TestShadowModeGating(unittest.TestCase):

    def test_shadow_modes_selectively_measured(self):
        # With only MARKET_CONFIRMATION demanded, the breakout model
        # stays quiet even though its primitive fires on every bar.
        with mock.patch.object(
            risk_settings,
            "SHADOW_ENTRY_MODES",
            (ENTRY_MODE_MARKET_CONFIRMATION,),
        ):
            shadow = EntryShadow(window_bars=4)

            shadow.observe(canned_setup())

            shadow.advance(candle(1, 112.0, 108.0, 110.0), bar=1)

            shadow.advance(candle(2, 120.0, 114.0, 118.0), bar=2)

            state = _state(shadow)

            self.assertTrue(state.market.triggered)

            self.assertFalse(state.breakout.triggered)

            self.assertTrue(state.limit.triggered)

    def test_default_gates_measure_all_shadow_models(self):
        self.assertEqual(
            SHADOW_MODES,
            (ENTRY_MODE_MARKET_CONFIRMATION,
             ENTRY_MODE_BREAKOUT_CONTINUATION),
        )

        shadow = EntryShadow(window_bars=4)

        self.assertTrue(
            shadow._shadow_mode_enabled(ENTRY_MODE_MARKET_CONFIRMATION)
        )
        self.assertTrue(
            shadow._shadow_mode_enabled(ENTRY_MODE_BREAKOUT_CONTINUATION)
        )


# ==========================================================
# STEP 7: diagnostics are inert (no look-ahead leak)
# ==========================================================


class TestNoLeakShadow(unittest.TestCase):

    def test_shadow_diagnostics_do_not_affect_live_signals(self):
        # The identical world, run once WITH the entry shadow and once
        # with ENABLE_ENTRY_SHADOW=False. Every live order outcome must
        # be identical: the shadow measures future price, it never
        # influences order minting, expiry, fills or trades.
        candles = [
            miss_candle(1),
            touch_candle(2),
            hold_candle(3),
            tp_candle(4),
        ]

        with mock.patch.object(
            risk_settings, "ENABLE_ENTRY_SHADOW", True
        ):
            backtester_on, sim_on, pipe_on, reg_on = run_world(candles)

        with mock.patch.object(
            risk_settings, "ENABLE_ENTRY_SHADOW", False
        ):
            backtester_off, sim_off, pipe_off, reg_off = run_world(candles)

        def fingerprint(backtester, sim, reg):
            return (
                [o.status for o in reg.all()],
                [getattr(o, "filled_bar", None) for o in reg.all()],
                len(reg.all()),
                sim.registry.count(),
                backtester.pending_orders_max,
            )

        self.assertEqual(
            fingerprint(backtester_on, sim_on, reg_on),
            fingerprint(backtester_off, sim_off, reg_off),
        )

        # The shadow itself is the only observable difference.
        self.assertEqual(pipe_on.context.entry_shadow.count(), 1)
        self.assertEqual(pipe_off.context.entry_shadow.count(), 0)


def _state_by_id(shadow, structural_id):
    for s in shadow.states():
        if s.structural_id == structural_id:
            return s
    raise AssertionError(f"no shadow state for {structural_id}")


if __name__ == "__main__":

    unittest.main()