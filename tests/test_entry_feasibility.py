"""
====================================================

QuantEngine

Phase 4F: Entry Feasibility, Retracement Analysis and
Multi-Mode Entry Architecture Tests

Run with:

    python -m unittest tests.test_entry_feasibility -v

Proves (mapped to the Phase 4F steps):

  STEP 1-2  -- entry distance is measured on four normalization
               axes (absolute / percent-of-price / ATR multiples /
               ticks) and classified IMMEDIATE / NEAR / RETRACE /
               DEEP_RETRACE / TOO_FAR via configurable ATR-normalized
               thresholds (never a symbol-specific point distance).
  STEP 3    -- the EntryTracker measures what price ACTUALLY did
               after the creating candle: retracement toward the
               entry, entry touch (low <= entry <= high), bars until
               the nearest approach / the touch, and the largest
               continuation in the TARGET direction.
  STEP 5    -- MISSED_CONTINUATION: entry never touched yet price
               ran >= 50% of the way from entry to target in the
               trade direction (diagnostic only).
  STEP 7    -- the tracker is DIAGNOSTIC: disabling it leaves every
               order outcome byte-identical (no look-ahead leak).
  STEP 6    -- the entry mode is preserved end-to-end
               (SetupCandidate -> OrderIntent -> Trade).
  STEP 8    -- pending capacity: one canonical per execution cluster
               and an explicit per-direction budget so correlated
               same-direction ideas cannot consume every slot.
  STEP 9    -- economic re-entry cooldown: an EXPIRED / INVALIDATED
               idea may not re-order identical economics during the
               cooldown window, and a NEW structural discovery of the
               same economics is legal again after it lapses.

Stdlib only -- no network.

====================================================
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from config import risk_settings

from core.setup.entry_feasibility import (
    ENTRY_DEEP_RETRACE,
    ENTRY_IMMEDIATE,
    ENTRY_NEAR,
    ENTRY_RETRACE,
    ENTRY_TOO_FAR,
    classify_entry_feasibility,
    create_entry_feasibility,
)
from core.setup.entry_tracker import EntryTracker
from core.setup.setup_candidate import SetupCandidate

from core.setup.economic_setup_registry import (
    EconomicSetupRegistry,
    fingerprint_of,
)

from tests.test_economic_setup_dedup import candidate
from tests.test_execution_lifecycle import (
    hold_candle,
    miss_candle,
    run_world,
    tp_candle,
    touch_candle,
)


def bar(ts, high, low):
    return SimpleNamespace(timestamp=ts, high=high, low=low)


def canned_setup(
    direction="BULLISH",
    entry=110.0,
    stop=100.0,
    target=130.0,
    observed=100.0,
    atr=10.0,
    structural="OB-1",
    entry_mode="LIMIT_RETEST",
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
    c.entry_mode = entry_mode
    c.entry_feasibility = create_entry_feasibility(
        c,
        creation_price=observed,
        atr=atr,
    )
    return c


# ==========================================================
# STEP 1: entry distance calculation
# ==========================================================


class TestEntryDistanceCalculation(unittest.TestCase):

    def test_entry_distance_calculation(self):
        # entry 110 vs creating price 100, ATR 10, tick 0.5:
        #   absolute 10.0, 10% of price, 1.0 ATRs, 20 ticks.
        setup = canned_setup(entry=110.0, observed=100.0, atr=10.0)

        f = create_entry_feasibility(
            setup,
            creation_price=100.0,
            atr=10.0,
            tick=0.5,
            creation_bar=7,
        )

        self.assertEqual(f.entry_distance, 10.0)
        self.assertEqual(f.entry_distance_pct, 10.0)
        self.assertEqual(f.entry_distance_atr, 1.0)
        self.assertEqual(f.entry_distance_ticks, 20.0)
        self.assertEqual(f.classification, ENTRY_DEEP_RETRACE)
        self.assertEqual(f.creation_bar, 7)
        self.assertEqual(f.direction, "BULLISH")
        self.assertEqual(f.entry_mode, "LIMIT_RETEST")

    def test_entry_distance_is_symmetric_in_direction(self):
        # A bearish entry BELOW the creating price has the same
        # distance magnitude as a bullish entry above it.
        bull = canned_setup(entry=110.0, observed=100.0, atr=10.0)
        bear = canned_setup(
            direction="BEARISH", entry=90.0, observed=100.0,
            atr=10.0,
        )

        fb = create_entry_feasibility(
            bull, creation_price=100.0, atr=10.0, tick=0.5
        )
        fs = create_entry_feasibility(
            bear, creation_price=100.0, atr=10.0, tick=0.5
        )

        self.assertEqual(fb.entry_distance, 10.0)
        self.assertEqual(fs.entry_distance, 10.0)
        self.assertEqual(fb.entry_distance_atr, 1.0)
        self.assertEqual(fs.entry_distance_atr, 1.0)

    # --------------------------------------------------

    def test_atr_normalized_entry_distance(self):
        # The SAME absolute distance normalizes differently as ATR
        # changes; absolute / percent / ticks stay fixed.
        setup = canned_setup(entry=110.0, observed=100.0, atr=10.0)

        low_atr = create_entry_feasibility(
            setup, creation_price=100.0, atr=10.0, tick=0.5
        )
        high_atr = create_entry_feasibility(
            setup, creation_price=100.0, atr=20.0, tick=0.5
        )

        self.assertEqual(low_atr.entry_distance_atr, 1.0)
        self.assertEqual(high_atr.entry_distance_atr, 0.5)
        self.assertEqual(
            low_atr.entry_distance, high_atr.entry_distance
        )
        self.assertEqual(
            low_atr.entry_distance_ticks, high_atr.entry_distance_ticks
        )
        self.assertEqual(low_atr.entry_distance_pct, high_atr.entry_distance_pct)

    # --------------------------------------------------

    def test_entry_feasibility_classification(self):
        # Configurable ATR-normalized boundaries (inclusive on the
        # boundary), symbol-agnostic -- no hard-coded BTC points.
        self.assertEqual(
            classify_entry_feasibility(0.0), ENTRY_IMMEDIATE
        )
        self.assertEqual(
            classify_entry_feasibility(0.05), ENTRY_IMMEDIATE
        )
        self.assertEqual(
            classify_entry_feasibility(0.10), ENTRY_IMMEDIATE
        )
        self.assertEqual(
            classify_entry_feasibility(0.25), ENTRY_NEAR
        )
        self.assertEqual(
            classify_entry_feasibility(0.35), ENTRY_NEAR
        )
        self.assertEqual(
            classify_entry_feasibility(0.60), ENTRY_RETRACE
        )
        self.assertEqual(
            classify_entry_feasibility(0.75), ENTRY_RETRACE
        )
        self.assertEqual(
            classify_entry_feasibility(1.20), ENTRY_DEEP_RETRACE
        )
        self.assertEqual(
            classify_entry_feasibility(1.50), ENTRY_DEEP_RETRACE
        )
        self.assertEqual(
            classify_entry_feasibility(1.51), ENTRY_TOO_FAR
        )
        self.assertEqual(
            classify_entry_feasibility(4.0), ENTRY_TOO_FAR
        )

    def test_entry_feasibility_classification_custom_thresholds(self):
        custom = {
            ENTRY_IMMEDIATE: 0.05,
            ENTRY_NEAR: 0.20,
            ENTRY_RETRACE: 0.50,
            ENTRY_DEEP_RETRACE: 1.00,
        }
        self.assertEqual(
            classify_entry_feasibility(0.30, custom), ENTRY_RETRACE
        )
        self.assertEqual(
            classify_entry_feasibility(0.10, custom), ENTRY_NEAR
        )
        self.assertEqual(
            classify_entry_feasibility(0.02, custom), ENTRY_IMMEDIATE
        )
        self.assertEqual(
            classify_entry_feasibility(2.00, custom), ENTRY_TOO_FAR
        )


# ==========================================================
# STEP 3: retracement / continuation tracking
# ==========================================================


class TestRetracementTracking(unittest.TestCase):

    # --------------------------------------------------

    def test_bullish_retracement_tracking(self):
        # BULLISH entry 110 retested UP from a 100 creating price;
        # price climbs through 105 -> 108 -> [110, 112] (touch on
        # bar 4). The tracker records the retrace fraction, the
        # nearest approach (capped at the entry) and the touch bar.
        setup = canned_setup(entry=110.0, stop=100.0, target=130.0,
                             observed=100.0, atr=10.0)

        tracker = EntryTracker(window_bars=5, missed_target_fraction=0.5)

        tracker.track([setup], bar=1)

        tracker.advance(bar(2, 105.0, 102.0), bar=2)
        tracker.advance(bar(3, 108.0, 104.0), bar=3)
        tracker.advance(bar(4, 112.0, 110.0), bar=4)

        state = tracker.states()[0]

        self.assertFalse(state._resolved)
        self.assertTrue(state.entry_touched)
        self.assertEqual(state.entry_touch_bar, 4)
        self.assertEqual(state.bars_until_entry_touch, 3)
        self.assertEqual(state.min_low_after, 102.0)
        self.assertEqual(state.max_high_after, 112.0)
        self.assertEqual(state.nearest_approach_price, 110.0)
        self.assertEqual(state.retracement_toward_entry, 1.0)
        self.assertEqual(state.classification, ENTRY_DEEP_RETRACE)
        self.assertEqual(state.entry_distance_atr, 1.0)

        # Finish the window: the state resolves (no registry -> a
        # never-ordered record) and the target-direction continuation
        # extreme is the lifetime high.
        tracker.advance(bar(5, 108.0, 101.0), bar=5)
        tracker.advance(bar(6, 108.0, 101.0), bar=6)

        self.assertTrue(state._resolved)
        self.assertEqual(state.terminal_state, "NEVER_ORDERED")
        self.assertEqual(state.target_direction_extreme, 112.0)
        self.assertFalse(state.missed_continuation)
        self.assertEqual(state.distance_remaining_at_terminal, 0.0)

    # --------------------------------------------------

    def test_bearish_retracement_tracking(self):
        # BEARISH entry 90 retested DOWN from a 100 creating price;
        # price falls 93 -> 91 -> [88, 92] (touch on bar 4). The
        # nearest approach is the LUCID lowest low, floored at the
        # entry (90), and the target-direction continuation is the
        # lifetime low.
        setup = canned_setup(
            direction="BEARISH", entry=90.0, stop=105.0,
            target=70.0, observed=100.0, atr=10.0,
        )

        tracker = EntryTracker(window_bars=5, missed_target_fraction=0.5)

        tracker.track([setup], bar=1)

        tracker.advance(bar(2, 98.0, 93.0), bar=2)
        tracker.advance(bar(3, 96.0, 91.0), bar=3)
        tracker.advance(bar(4, 92.0, 88.0), bar=4)

        state = tracker.states()[0]

        self.assertFalse(state._resolved)
        self.assertTrue(state.entry_touched)
        self.assertEqual(state.entry_touch_bar, 4)
        self.assertEqual(state.min_low_after, 88.0)
        self.assertEqual(state.nearest_approach_price, 90.0)
        self.assertEqual(state.retracement_toward_entry, 1.0)

        tracker.advance(bar(5, 99.0, 92.0), bar=5)
        tracker.advance(bar(6, 99.0, 92.0), bar=6)

        self.assertTrue(state._resolved)
        self.assertEqual(state.target_direction_extreme, 88.0)
        self.assertFalse(state.missed_continuation)

    # --------------------------------------------------

    def test_retracement_fraction_tracks_the_approach(self):
        # Before the touch the retracement fraction is the share of
        # the entry distance already covered back toward the entry.
        setup = canned_setup(entry=110.0, stop=100.0, target=130.0,
                             observed=100.0, atr=10.0)

        tracker = EntryTracker(window_bars=5, missed_target_fraction=0.5)

        tracker.track([setup], bar=1)

        tracker.advance(bar(2, 104.0, 101.0), bar=2)
        tracker.advance(bar(3, 108.0, 103.0), bar=3)

        state = tracker.states()[0]

        # live high 108, capped at the entry 110 -> retracement
        # (108 - 100) / (110 - 100) = 0.8 toward the entry.
        self.assertEqual(
            state.retracement_toward_entry, 0.8
        )


# ==========================================================
# STEP 5: missed continuation detection
# ==========================================================


class TestMissedContinuation(unittest.TestCase):

    def test_missed_continuation_detection(self):
        # BULLISH entry 110 vs creating price 100 -- a DEEP retrace
        # is due. Instead price RUNS UP through the entry zone from
        # BELOW the entry's low without a single candle bracketing
        # 110 (lows stay >= 111.5): the market continued toward the
        # 130 target and never retraced. The tracker flags the idea
        # as a MISSED continuation.
        setup = canned_setup(entry=110.0, stop=100.0, target=130.0,
                             observed=100.0, atr=10.0)

        tracker = EntryTracker(window_bars=3, missed_target_fraction=0.5)

        tracker.track([setup], bar=1)

        tracker.advance(bar(2, 112.0, 111.5), bar=2)
        tracker.advance(bar(3, 118.0, 112.0), bar=3)
        tracker.advance(bar(4, 125.0, 114.0), bar=4)

        state = tracker.states()[0]

        self.assertTrue(state._resolved)
        self.assertFalse(state.entry_touched)
        self.assertEqual(state.target_direction_extreme, 125.0)
        # entry -> target = 20; 125 - 110 = 15 >= 0.5 * 20.
        self.assertTrue(state.missed_continuation)
        # Distance to the entry at the window end: nearest extreme
        # 111.5 (lowest low) -> 1.5.
        self.assertEqual(
            state.distance_remaining_at_terminal, 1.5
        )

    # --------------------------------------------------

    def test_no_missed_continuation_without_move_to_target(self):
        # Same DEEP setup but price grinds DOWN toward the stop
        # (never toward the 130 target): continuation toward the
        # target is zero -> NOT a missed continuation (it is heading
        # the wrong way / would have invalidated).
        setup = canned_setup(entry=110.0, stop=100.0, target=130.0,
                             observed=100.0, atr=10.0)

        tracker = EntryTracker(window_bars=3, missed_target_fraction=0.5)

        tracker.track([setup], bar=1)

        tracker.advance(bar(2, 105.0, 102.0), bar=2)
        tracker.advance(bar(3, 104.0, 101.0), bar=3)
        tracker.advance(bar(4, 103.0, 100.5), bar=4)

        state = tracker.states()[0]

        self.assertTrue(state._resolved)
        self.assertFalse(state.entry_touched)
        self.assertFalse(state.missed_continuation)

    # --------------------------------------------------

    def test_entry_touch_clears_missed_continuation(self):
        # The same run but bar 3 DOES bracket the entry (low 110):
        # the idea was reachable, so it can never be classified as a
        # missed continuation even though price later ran to 125.
        setup = canned_setup(entry=110.0, stop=100.0, target=130.0,
                             observed=100.0, atr=10.0)

        tracker = EntryTracker(window_bars=3, missed_target_fraction=0.5)

        tracker.track([setup], bar=1)

        tracker.advance(bar(2, 111.0, 110.0), bar=2)
        tracker.advance(bar(3, 118.0, 112.0), bar=3)
        tracker.advance(bar(4, 125.0, 114.0), bar=4)

        state = tracker.states()[0]

        self.assertTrue(state._resolved)
        self.assertTrue(state.entry_touched)
        self.assertFalse(state.missed_continuation)


# ==========================================================
# STEP 7: diagnostics are inert (no look-ahead leak)
# ==========================================================


class TestNoLeak(unittest.TestCase):

    def test_future_diagnostics_do_not_affect_live_signals(self):
        # The identical world, run once WITH the Phase 4F tracker and
        # once with ENABLE_ENTRY_DIAGNOSTICS=False. Every live order
        # outcome (mint, status, fill bar, trade) must be identical:
        # tracking measures future price, it never influences it.
        candles = [
            miss_candle(1),
            touch_candle(2),
            hold_candle(3),
            tp_candle(4),
        ]

        with mock.patch.object(
            risk_settings, "ENABLE_ENTRY_DIAGNOSTICS", True
        ):
            backtester_on, sim_on, pipe_on, reg_on = run_world(candles)

        with mock.patch.object(
            risk_settings, "ENABLE_ENTRY_DIAGNOSTICS", False
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

        # The tracker itself is the only observable difference.
        self.assertEqual(pipe_on.context.entry_tracker.count(), 1)
        self.assertEqual(pipe_off.context.entry_tracker.count(), 0)


# ==========================================================
# STEP 6: entry mode preserved end-to-end
# ==========================================================


class TestEntryModePreserved(unittest.TestCase):

    def test_entry_mode_is_preserved_from_setup_to_order(self):
        # SetupCandidate -> OrderIntent -> Trade must all carry the
        # SAME entry mode (the canonical BREAKOUT_CONTINUATION
        # production default), and the ORDER carries the feasibility
        # class computed at its CREATION bar (bar 1: entry 110 vs
        # miss close 107.5, ATR 15 -> 2.5 / 15 = 0.1667 ATRs ->
        # ENTRY_NEAR).
        # Phase 12: the entry bar opens AT E (110.0, actual RR
        # exactly 6.0) -- the shared tp_candle has no open leg,
        # so its close-fallback (170.8) would erode actual RR to
        # ~0 and the fill would be (correctly) refused.
        entry_candle = SimpleNamespace(
            open=110.0, high=112.0, low=109.5, close=111.0,
            timestamp=3, symbol="TEST", timeframe="1m")
        _, simulator, pipeline, registry = run_world(
            [
                miss_candle(1),
                hold_candle(2),   # trigger: close 110.5 beyond E
                entry_candle,     # entry at next-bar open (110)
            ],
            entry_mode="BREAKOUT_CONTINUATION",
        )

        order = registry.all()[0]
        # The fill lands on the LAST candle, so the position
        # is still OPEN (closed registry empty by design --
        # no force-close at an imagined price).
        trade = simulator.current_trade
        self.assertIsNotNone(trade)

        self.assertEqual(order.entry_mode, "BREAKOUT_CONTINUATION")
        self.assertEqual(trade.entry_mode, "BREAKOUT_CONTINUATION")
        self.assertEqual(order.entry_feasibility, ENTRY_NEAR)

        # The builder stamps the feasibility on every candidate it
        # produces: the snapshot distance must equal
        # entry - observed_price of that candidate (self-consistent),
        # and the entry mode + ATR stack are live.
        for setup in pipeline.context.trade_setups:
            self.assertEqual(setup.entry_mode, "BREAKOUT_CONTINUATION")
            self.assertEqual(setup.atr, 15.0)
            self.assertAlmostEqual(
                setup.entry_feasibility.entry_distance,
                abs(setup.entry - setup.observed_price),
            )


# ==========================================================
# STEP 8: pending capacity -- one idea per cluster + a
# per-direction budget
# ==========================================================


class TestPendingCapacityPolicy(unittest.TestCase):

    def test_pending_order_limit_per_cluster(self):
        # (a) Per-cluster = 1: two OBs with IDENTICAL economics form
        # ONE execution zone; even with a 4-slot total budget exactly
        # ONE order is minted -- structurally guaranteed by the
        # EconomicSetupRegistry (never an invisible loop in an
        # execution function).
        with mock.patch.object(
            risk_settings, "MAX_PENDING_ORDERS_TOTAL", 4
        ):
            _, _, pipeline, registry = run_world(
                [miss_candle(1)], world="same"
            )

        self.assertEqual(len(registry.all()), 1)
        self.assertEqual(
            pipeline.context.trade_setups[0].entry_feasibility
            is not None,
            True,
        )

        # (b) Per-DIRECTION budget: two genuinely independent
        # BULLISH clusters (A and B never cluster under Phase 4E).
        # With the direction budget at 1, only the best-scoring
        # (OB-5) may sit pending -- the second same-direction idea
        # queues even though the TOTAL budget (8) has room.
        with mock.patch.object(
            risk_settings, "MAX_PENDING_ORDERS_TOTAL", 8
        ), mock.patch.object(
            risk_settings, "MAX_PENDING_ORDERS_PER_DIRECTION", 1
        ):
            _, _, _, registry2 = run_world(
                [miss_candle(1)], world="distinct"
            )

        self.assertEqual(len(registry2.all()), 1)
        self.assertIn("OB-5", registry2.all()[0].setup_id)

    # --------------------------------------------------

    def test_direction_budget_allows_one_per_direction(self):
        # With the direction budget at 1, a BULLISH and a BEARISH
        # idea may coexist (different directions never contend).
        # Seeded distinct world is BULLISH-only, so the second
        # independent bullish idea is blocked -- one pending.
        with mock.patch.object(
            risk_settings, "MAX_PENDING_ORDERS_PER_DIRECTION", 1
        ):
            _, _, _, registry = run_world(
                [miss_candle(1)], world="distinct"
            )

        self.assertEqual(len(registry.all()), 1)
        self.assertIn("OB-5", registry.all()[0].setup_id)


# ==========================================================
# STEP 9: economic re-entry cooldown
# ==========================================================


class TestReentryCooldown(unittest.TestCase):

    # NOTE (Phase 4G STEP 9): since structural clustering now
    # collapses identical-geometry twins to ONE canonical zone at
    # the builder, the identical-economics cooldown is exercised
    # at the ECONOMIC registry boundary -- the direct-API path the
    # re-entry cooldown (Phase 4F STEP 9) actually lives on. A
    # later structural discovery of the same fingerprint while the
    # idea is EXPIRED/INVALIDATED is suppressed for
    # REENTRY_COOLDOWN_BARS and is legal the moment the window
    # lapses (time-based only).

    @staticmethod
    def _same_economics(structural):
        return candidate(
            structural=structural,
            entry=110.0,
            stop=100.0,
            target=130.0,
        )

    def test_expired_economic_idea_respects_cooldown(self):
        # OB-5's idea EXPIRES: every later structural re-discovery
        # of the SAME fingerprint is suppressed during the cooldown
        # window (exactly ONE order ever exists), and the GENUINELY
        # new discovery is legal once the window passes.
        with mock.patch.object(risk_settings, "REENTRY_COOLDOWN_BARS", 3):
            registry = EconomicSetupRegistry()

            first = self._same_economics("OB-5")
            registry.observe([first], order_registry=None, bar=1)

            fp = fingerprint_of(first, symbol="TEST", timeframe="1m")
            self.assertTrue(fp)
            registry.mark_terminal(fp, "EXPIRED", terminal_bar=4)

            re_discovery = self._same_economics("OB-6")
            reps = registry.observe(
                [re_discovery], order_registry=None, bar=5)
            self.assertEqual(reps, [])
            self.assertTrue(re_discovery.reentry_cooldown_suppressed)
            self.assertEqual(registry.reentry_cooldown_suppressed, 1)

        # Control: with the cooldown OFF (0 bars) the same economics
        # genuinely re-mints on bar 5 -- proving the suppression is
        # the cooldown, not an artifact.
        with mock.patch.object(risk_settings, "REENTRY_COOLDOWN_BARS", 0):
            registry2 = EconomicSetupRegistry()

            first = self._same_economics("OB-5")
            registry2.observe([first], order_registry=None, bar=1)

            fp = fingerprint_of(first, symbol="TEST", timeframe="1m")
            registry2.mark_terminal(fp, "EXPIRED", terminal_bar=4)

            re_discovery = self._same_economics("OB-6")
            reps = registry2.observe(
                [re_discovery], order_registry=None, bar=5)
            self.assertEqual(len(reps), 1)
            self.assertFalse(re_discovery.reentry_cooldown_suppressed)
            self.assertEqual(registry2.reentry_cooldown_suppressed, 0)

    # --------------------------------------------------

    def test_new_structural_setup_can_exist_after_cooldown(self):
        # A SHORT cooldown (3 bars): the idea EXPIRES end-of-bar 4,
        # so its re-discovery on OB-6 is suppressed on bars 5, 6, 7
        # and a NEW structural setup of the same economics is legal
        # again on bar 8 (time-based only).
        with mock.patch.object(risk_settings, "REENTRY_COOLDOWN_BARS", 3):
            registry = EconomicSetupRegistry()

            first = self._same_economics("OB-5")
            registry.observe([first], order_registry=None, bar=1)

            fp = fingerprint_of(first, symbol="TEST", timeframe="1m")
            registry.mark_terminal(fp, "EXPIRED", terminal_bar=4)

            for bar in (5, 6, 7):
                rediscovery = self._same_economics("OB-6")
                reps = registry.observe(
                    [rediscovery], order_registry=None, bar=bar)
                self.assertEqual(reps, [])

            # Bars 5, 6, 7 suppressed the cooldown window exactly.
            self.assertEqual(
                registry.reentry_cooldown_suppressed, 3)

            # The moment the cooldown lapses the same economics on a
            # NEW structural setup is a real, fillable opportunity.
            later = self._same_economics("OB-7")
            reps = registry.observe(
                [later], order_registry=None, bar=8)
            self.assertEqual(len(reps), 1)
            self.assertFalse(later.reentry_cooldown_suppressed)
            self.assertIn("OB-7", reps[0].structural_id)


if __name__ == "__main__":

    unittest.main()