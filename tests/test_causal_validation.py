"""
====================================================

QuantEngine

Phase 4H: Causal Breakout Continuation Validation Tests

Run with:

    python -m unittest tests.test_causal_validation -v

Proves the FOUR causal guarantees plus the Phase 4H reporting
(diagnostic only -- this validator produces no executable order):

  RULE 1  -- FREEZE AT CREATION: observe() snapshots entry / stop /
            target / direction / identity / creation state, and
            mutating the setup object afterwards changes nothing.
  RULE 2  -- TRIGGER AT CLOSE: the breakout trigger uses ONLY the
            trigger candle's own range + close
            (BULLISH high > E and close > E; BEARISH low < E and
            close < E); the structural stop breach is checked
            BEFORE the trigger on every candle.
  RULE 3  -- NEXT-BAR EXECUTION: a trigger at bar N fills at the OPEN
            of bar N+1 -- never inside the trigger candle; a trigger
            on the last in-window bar is non-executable and counted
            as a trigger without an entry.
  RULE 4  -- DETERMINISTIC INTRABAR RESOLUTION: CONSERVATIVE (stop
            first) / OPTIMISTIC (target first) / EXCLUDE all render
            from one walk whose CONSERVATIVE outcome is always
            recorded; ambiguous candles are flagged.
  PERFORM -- win/loss/unresolved/excluded counts, win rate, profit
            factor, gross P/L, expectancy / average R, max drawdown
            (R and %), avg bars to entry, and MAE/MFE in ATR --
            computed in R multiples (LOSS pays -1R, WIN pays the
            reward/risk ratio from the actual open fill).
  STEP 8  -- MARKET_CONFIRMATION rejection-stage diagnosis with the
            candidates / structure / trend / distance / volume /
            orderflow / triggered counters and the partition
            invariant (sum of rejects + triggered == candidates).
  NO LEAK -- mutating candles AFTER the decision bar and mutating the
            setup after observe() alter neither the trigger nor the
            entry signal; disabling the validator leaves no traces.

Stdlib only -- no network.

====================================================
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from config import risk_settings

from core.setup.causal_validation import (
    CAUSAL_EXECUTION_NEXT_BAR_OPEN,
    CONFIRM_REJECT_DISTANCE,
    CONFIRM_REJECT_STRUCTURE,
    CONFIRM_REJECT_TREND,
    INTRABAR_CONSERVATIVE,
    INTRABAR_EXCLUDE,
    INTRABAR_OPTIMISTIC,
    CausalValidator,
    format_causal_report,
)
from core.setup.entry_feasibility import create_entry_feasibility
from core.setup.setup_candidate import SetupCandidate


def candle(bar, open_, high, low, close):
    return SimpleNamespace(
        timestamp=bar, open=open_, high=high, low=low, close=close,
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
    c.entry_feasibility = create_entry_feasibility(
        c,
        creation_price=observed,
        atr=atr,
        creation_bar=creation_bar,
    )
    return c


def _state(validator):
    return validator.states()[0]


def _snapshot_breakout(state):
    return {
        "triggered": state.breakout_triggered,
        "trigger_bar": state.breakout_trigger_bar,
        "trigger_close": state.breakout_trigger_close,
        "entry_bar": state.breakout_entry_bar,
        "entered": state.breakout_entered,
        "entry_price": state.breakout_entry_price,
        "executable": state.breakout_causally_executable,
        "resolved": state.breakout_resolved,
        "conservative": state.breakout_conservative,
        "sl_hit": state.breakout_sl_hit,
        "tp_hit": state.breakout_tp_hit,
        "ambiguous": state.breakout_ambiguous,
        "r_multiple": state.breakout_r_multiple,
    }


def _trigger_entry_candles():
    """BULLISH trigger at bar 1, entry bar 2, hold bars after."""
    return [
        candle(1, 111.0, 116.0, 105.0, 114.0),
        candle(2, 108.0, 113.0, 103.0, 110.0),
        candle(3, 109.0, 112.0, 104.0, 108.0),
        candle(4, 108.0, 111.0, 104.0, 107.0),
        candle(5, 107.0, 110.0, 103.0, 106.0),
    ]


# ==========================================================
# RULE 1: freeze at creation
# ==========================================================


class TestCausalFreeze(unittest.TestCase):

    def test_setup_mutation_does_not_change_frozen_economics(self):
        setup = canned_setup()
        validator = CausalValidator(window_bars=10)
        validator.observe(setup, 0)
        state = _state(validator)

        setup.entry = 999.0
        setup.stop_loss = 1.0
        setup.take_profit = 9999.0
        setup.direction = "BEARISH"
        setup.structural_id = "OB-MUTATED"

        self.assertEqual(state.entry, 110.0)
        self.assertEqual(state.stop_loss, 100.0)
        self.assertEqual(state.take_profit, 130.0)
        self.assertEqual(state.direction, "BULLISH")
        self.assertEqual(state.structural_id, "OB-1")

    def test_feasibility_mutation_does_not_change_creation_state(self):
        setup = canned_setup(creation_bar=0)
        validator = CausalValidator(window_bars=10)
        validator.observe(setup, 0)
        state = _state(validator)

        setup.entry_feasibility.creation_bar = 999
        setup.entry_feasibility.entry_distance_atr = 999.0
        setup.observed_price = 999.0

        self.assertEqual(state.creation_bar, 0)
        self.assertEqual(state.creation_price, 100.0)


# ==========================================================
# RULE 2: trigger at the trigger candle's close
# ==========================================================


class TestCausalTrigger(unittest.TestCase):

    def test_bullish_trigger(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 115.0, 105.0, 112.0), bar=1)
        state = _state(validator)

        self.assertTrue(state.breakout_triggered)
        self.assertEqual(state.breakout_trigger_bar, 1)
        self.assertEqual(state.breakout_trigger_close, 112.0)
        self.assertEqual(state.breakout_entry_bar, 2)
        self.assertTrue(state.breakout_causally_executable)

    def test_bearish_trigger(self):
        setup = canned_setup(
            direction="BEARISH", entry=90.0, stop=100.0, target=70.0,
        )
        validator = CausalValidator(window_bars=10)
        validator.observe(setup, 0)
        validator.advance(candle(1, 90.0, 95.0, 85.0, 88.0), bar=1)
        state = _state(validator)

        self.assertTrue(state.breakout_triggered)
        self.assertEqual(state.breakout_trigger_bar, 1)
        self.assertEqual(state.breakout_entry_bar, 2)

    def test_high_past_e_but_close_below_does_not_trigger(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 110.0, 115.0, 105.0, 110.0), bar=1)
        state = _state(validator)

        self.assertFalse(state.breakout_triggered)

    def test_close_past_e_but_high_not_past_does_not_trigger(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 110.0, 110.0, 105.0, 112.0), bar=1)
        state = _state(validator)

        self.assertFalse(state.breakout_triggered)

    def test_structural_stop_breach_before_same_bar_trigger(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 99.0, 114.0), bar=1)
        state = _state(validator)

        self.assertTrue(state.idea_invalidated)
        self.assertTrue(state.idea_invalidated_bar, 1)
        self.assertFalse(state.breakout_triggered)


# ==========================================================
# RULE 3: next-bar execution at the OPEN
# ==========================================================


class TestCausalNextBarExecution(unittest.TestCase):

    def test_trigger_bar_itself_never_enters(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        state = _state(validator)

        self.assertTrue(state.breakout_triggered)
        self.assertFalse(state.breakout_entered)
        self.assertIsNone(state.breakout_entry_price)

    def test_entry_happens_at_open_of_trigger_plus_one(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        for c in _trigger_entry_candles():
            validator.advance(c, bar=c.timestamp)
        state = _state(validator)

        self.assertTrue(state.breakout_entered)
        self.assertEqual(state.breakout_entry_bar, 2)
        self.assertEqual(state.breakout_entry_price, 108.0)

    def test_entry_executes_even_when_entry_bar_gaps_against(self):
        # The signal was decided at the trigger close; the next open
        # is filled as a market order regardless of how it prints.
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(
            candle(2, 50.0, 200.0, 0.0, 100.0), bar=2
        )
        state = _state(validator)

        self.assertTrue(state.breakout_entered)
        self.assertEqual(state.breakout_entry_price, 50.0)
        self.assertTrue(state.breakout_resolved)

    def test_trigger_on_last_in_window_bar_is_not_executable(self):
        validator = CausalValidator(window_bars=3)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 110.0, 108.0, 104.0, 105.0), bar=1)
        validator.advance(candle(2, 110.0, 109.0, 104.0, 105.0), bar=2)
        validator.advance(candle(3, 112.0, 116.0, 108.0, 114.0), bar=3)
        state = _state(validator)

        self.assertTrue(state.breakout_triggered)
        self.assertFalse(state.breakout_causally_executable)
        self.assertFalse(state.breakout_entered)

        report = validator.report()
        brk = report["breakout"][INTRABAR_CONSERVATIVE]
        self.assertEqual(brk["triggers"], 1)
        self.assertEqual(brk["fills"], 0)
        self.assertEqual(
            brk["triggers_without_executable_next_bar"], 1
        )


# ==========================================================
# RULE 4: deterministic intrabar resolution
# ==========================================================


AMBIGUOUS_ENTRY_CANDLES = [
    candle(1, 111.0, 116.0, 105.0, 114.0),
    candle(2, 111.0, 131.0, 99.0, 105.0),
]


class TestCausalIntrabarPolicies(unittest.TestCase):

    def test_conservative_resolves_stop_first(self):
        validator = CausalValidator(
            window_bars=10, intrabar_policy=INTRABAR_CONSERVATIVE
        )
        validator.observe(canned_setup(), 0)
        for c in AMBIGUOUS_ENTRY_CANDLES:
            validator.advance(c, bar=c.timestamp)
        state = _state(validator)

        self.assertTrue(state.breakout_ambiguous)
        self.assertEqual(state.breakout_resolved, "LOSS")
        self.assertEqual(state.breakout_conservative, "LOSS")
        self.assertTrue(state.breakout_sl_hit)
        self.assertFalse(state.breakout_tp_hit)

    def test_optimistic_resolves_target_first(self):
        validator = CausalValidator(
            window_bars=10, intrabar_policy=INTRABAR_OPTIMISTIC
        )
        validator.observe(canned_setup(), 0)
        for c in AMBIGUOUS_ENTRY_CANDLES:
            validator.advance(c, bar=c.timestamp)
        state = _state(validator)

        self.assertTrue(state.breakout_ambiguous)
        self.assertEqual(state.breakout_resolved, "WIN")
        self.assertEqual(state.breakout_conservative, "LOSS")
        self.assertTrue(state.breakout_tp_hit)

    def test_exclude_drops_the_trade(self):
        validator = CausalValidator(
            window_bars=10, intrabar_policy=INTRABAR_EXCLUDE
        )
        validator.observe(canned_setup(), 0)
        for c in AMBIGUOUS_ENTRY_CANDLES:
            validator.advance(c, bar=c.timestamp)
        state = _state(validator)

        self.assertEqual(state.breakout_resolved, "EXCLUDED")
        self.assertEqual(state.breakout_conservative, "LOSS")

        report = validator.report()
        brk = report["breakout"][INTRABAR_EXCLUDE]
        self.assertEqual(brk["excluded"], 1)
        self.assertEqual(brk["settled"], 0)
        self.assertEqual(brk["wins"], 0)
        self.assertEqual(brk["losses"], 0)
        self.assertEqual(brk["win_rate"], 0.0)

    def test_clean_win_recorded_ambiguous_false(self):
        validator = CausalValidator(
            window_bars=10, intrabar_policy=INTRABAR_CONSERVATIVE
        )
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(candle(2, 108.0, 113.0, 103.0, 110.0), bar=2)
        validator.advance(candle(3, 109.0, 135.0, 104.0, 131.0), bar=3)
        state = _state(validator)

        self.assertFalse(state.breakout_ambiguous)
        self.assertEqual(state.breakout_resolved, "WIN")
        self.assertEqual(state.breakout_conservative, "WIN")
        self.assertTrue(state.breakout_tp_hit)

    def test_clean_loss_recorded_ambiguous_false(self):
        validator = CausalValidator(
            window_bars=10, intrabar_policy=INTRABAR_CONSERVATIVE
        )
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(candle(2, 108.0, 113.0, 95.0, 101.0), bar=2)
        state = _state(validator)

        self.assertFalse(state.breakout_ambiguous)
        self.assertEqual(state.breakout_resolved, "LOSS")
        self.assertEqual(state.breakout_conservative, "LOSS")
        self.assertTrue(state.breakout_sl_hit)


# ==========================================================
# MAE / MFE (entry bar included) and R multiples
# ==========================================================


class TestCausalExcursionsAndR(unittest.TestCase):

    def test_mae_mfe_include_the_entry_bar_post_open_range(self):
        # The entry bar wicks beyond both levels; the excursions must
        # show the POST-OPEN extremes, not the capped levels.
        # window=2 so the walk settles on the entry bar itself.
        validator = CausalValidator(window_bars=2)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(
            candle(2, 108.0, 135.0, 95.0, 105.0), bar=2
        )
        state = _state(validator)

        self.assertEqual(state.breakout_mae, 13.0)
        self.assertEqual(state.breakout_mfe, 27.0)
        self.assertEqual(state.breakout_mae_atr, 1.3)
        self.assertEqual(state.breakout_mfe_atr, 2.7)

    def test_r_multiple_win_is_reward_over_risk_from_open_fill(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(candle(2, 108.0, 113.0, 103.0, 110.0), bar=2)
        validator.advance(candle(3, 112.0, 135.0, 105.0, 131.0), bar=3)
        state = _state(validator)

        # entry 108, stop 100 -> risk 8; target 130 -> reward 22.
        self.assertEqual(state.breakout_resolved, "WIN")
        self.assertAlmostEqual(state.breakout_r_multiple, 2.75, 6)

    def test_r_multiple_loss_is_negative_one(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(candle(2, 108.0, 113.0, 95.0, 101.0), bar=2)
        state = _state(validator)

        self.assertEqual(state.breakout_resolved, "LOSS")
        self.assertEqual(state.breakout_r_multiple, -1.0)

    def test_unresolved_settles_zero_r(self):
        validator = CausalValidator(window_bars=6)
        validator.observe(canned_setup(), 0)
        for c in _trigger_entry_candles():
            validator.advance(c, bar=c.timestamp)
        validator.advance(candle(6, 107.0, 110.0, 103.0, 106.0), bar=6)
        state = _state(validator)

        self.assertEqual(state.breakout_resolved, "UNRESOLVED")
        self.assertEqual(state.breakout_conservative, "UNRESOLVED")
        self.assertEqual(state.breakout_r_multiple, 0.0)


# ==========================================================
# Performance report math (step 9)
# ==========================================================


class TestCausalReportMetrics(unittest.TestCase):

    def _run_three_state_walk(self):
        """Three bull setups over ONE shared candle sequence:

        A stop 95  target 130  -> clean WIN   R = 19/16 = 1.1875
        B stop 99  target 140  -> clean LOSS
        C stop 99  target 130  -> ambiguous   (SL + TP on bar 3)
        """
        validator = CausalValidator(window_bars=10)
        for tag, stop, target in (("A", 95.0, 130.0),
                                  ("B", 99.0, 140.0),
                                  ("C", 99.0, 130.0)):
            s = canned_setup(
                structural="OB-" + tag, stop=stop, target=target,
            )
            validator.observe(s, 0)

        candles = [
            candle(1, 111.0, 116.0, 100.0, 114.0),
            candle(2, 111.0, 113.0, 109.0, 112.0),
            candle(3, 112.0, 135.0, 98.0, 133.0),
        ]
        candles += [candle(9, 100.0, 100.0, 100.0, 100.0)]
        for b in range(4, 9):
            candles.append(candle(b, 100.0, 100.0, 100.0, 100.0))
        candles.append(candle(10, 100.0, 100.0, 100.0, 100.0))
        for c in candles:
            validator.advance(c, bar=c.timestamp)
        return validator, validator.report()

    def test_conservative_primary_metrics(self):
        _, report = self._run_three_state_walk()
        brk = report["breakout"][INTRABAR_CONSERVATIVE]

        self.assertEqual(report["eligible_setups"], 3)
        self.assertEqual(report["execution"], CAUSAL_EXECUTION_NEXT_BAR_OPEN)
        self.assertEqual(report["intrabar_policy"], INTRABAR_CONSERVATIVE)
        self.assertEqual(brk["triggers"], 3)
        self.assertEqual(brk["fills"], 3)
        self.assertEqual(brk["ambiguous_trades"], 1)
        self.assertEqual(brk["wins"], 1)
        self.assertEqual(brk["losses"], 2)
        self.assertEqual(brk["settled"], 3)
        self.assertAlmostEqual(brk["win_rate"], 0.333333, 6)
        self.assertAlmostEqual(brk["gross_profit_r"], 1.1875, 6)
        self.assertAlmostEqual(brk["gross_loss_r"], 2.0, 6)
        self.assertAlmostEqual(brk["profit_factor"], 0.59375, 6)
        self.assertAlmostEqual(brk["expectancy_r"], -0.270833, 5)
        self.assertAlmostEqual(brk["average_r"], -0.270833, 5)
        self.assertAlmostEqual(brk["max_drawdown_r"], 2.0, 6)
        self.assertAlmostEqual(
            brk["max_drawdown_pct"],
            100.0 * 2.0 / 1.1875,
            5,
        )
        self.assertAlmostEqual(brk["avg_bars_to_entry"], 2.0, 6)
        self.assertAlmostEqual(brk["avg_mae_atr"], 1.4, 6)
        self.assertAlmostEqual(brk["avg_mfe_atr"], 2.566667, 5)

    def test_optimistic_row_renders_from_the_same_walk(self):
        _, report = self._run_three_state_walk()
        brk = report["breakout"][INTRABAR_OPTIMISTIC]

        self.assertEqual(brk["fills"], 3)
        self.assertEqual(brk["wins"], 2)
        self.assertEqual(brk["losses"], 1)
        self.assertEqual(brk["excluded"], 0)
        self.assertAlmostEqual(brk["win_rate"], 2.0 / 3.0, 6)
        self.assertAlmostEqual(brk["profit_factor"], 2.770833, 6)
        self.assertAlmostEqual(brk["expectancy_r"], 0.590278, 5)

    def test_exclude_row_drops_the_ambiguous_trade(self):
        _, report = self._run_three_state_walk()
        brk = report["breakout"][INTRABAR_EXCLUDE]

        self.assertEqual(brk["excluded"], 1)
        self.assertEqual(brk["wins"], 1)
        self.assertEqual(brk["losses"], 1)
        self.assertEqual(brk["settled"], 2)
        self.assertAlmostEqual(brk["win_rate"], 0.5, 6)
        self.assertAlmostEqual(brk["profit_factor"], 1.1875, 6)
        self.assertAlmostEqual(brk["expectancy_r"], 0.09375, 6)


# ==========================================================
# STEP 8: MARKET_CONFIRMATION rejection-stage diagnosis
# ==========================================================


class TestConfirmationDiagnosis(unittest.TestCase):

    def _run_confirmation_walk(self):
        """Four states over ONE shared candle sequence:

        structure  stop 102, E 110 -> invalidated at bar 1
        trend      E 115           -> crosses E, never closes beyond
        distance   E 200           -> never reaches E
        triggered  E 110, stop 70  -> confirms at bar 1
        """
        validator = CausalValidator(window_bars=10)
        for tag, entry, stop in (
            ("S", 110.0, 102.0),
            ("T", 115.0, 70.0),
            ("D", 200.0, 70.0),
            ("G", 110.0, 70.0),
        ):
            s = canned_setup(
                structural="OB-" + tag, entry=entry, stop=stop,
            )
            validator.observe(s, 0)

        candles = [candle(1, 112.0, 116.0, 100.0, 114.0)]
        candles += [
            candle(b, 104.0, 108.0, 102.0, 106.0)
            for b in range(2, 11)
        ]
        for c in candles:
            validator.advance(c, bar=c.timestamp)
        return validator.report()

    def test_rejection_stage_counters_partition_the_population(self):
        report = self._run_confirmation_walk()
        conf = report["confirmation"]

        self.assertEqual(conf["candidates"], 4)
        self.assertEqual(conf["rejected_structure"], 1)
        self.assertEqual(conf["rejected_trend"], 1)
        self.assertEqual(conf["rejected_distance"], 1)
        self.assertEqual(conf["rejected_volume"], 0)
        self.assertEqual(conf["rejected_orderflow"], 0)
        self.assertEqual(conf["triggered"], 1)
        self.assertEqual(
            conf["rejected_structure"]
            + conf["rejected_trend"]
            + conf["rejected_distance"]
            + conf["triggered"],
            conf["candidates"],
        )

    def test_confirmation_independent_of_breakout(self):
        # The triggered state also produced a breakout trigger on the
        # same candle: the two signals legally co-exist, so the market
        # primitive is NEVER cancelled by the breakout life.
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        validator.advance(candle(1, 111.0, 116.0, 105.0, 114.0), bar=1)
        validator.advance(candle(2, 108.0, 113.0, 99.0, 110.0), bar=2)
        state = _state(validator)

        self.assertTrue(state.confirmation_triggered)
        self.assertTrue(state.breakout_triggered)


# ==========================================================
# Population and gating
# ==========================================================


class TestCausalPopulationAndGating(unittest.TestCase):

    def test_deduplicated_on_first_appearance_per_structural_id(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(structural="OB-1"), 0)
        validator.observe(
            canned_setup(structural="OB-1", stop=90.0), 0
        )
        validator.observe(canned_setup(structural="OB-2"), 0)

        self.assertEqual(validator.count(), 2)

    def test_trade_ineligible_candidates_are_skipped(self):
        validator = CausalValidator(window_bars=10)
        setup = canned_setup()
        setup.trade_eligible = False
        validator.observe(setup, 0)

        self.assertEqual(validator.count(), 0)

    def test_order_context_attached_when_the_setup_minted_an_order(self):
        order = SimpleNamespace(
            order_id="ORD-1",
            created_bar=5,
            expires_at_bar=35,
        )

        class FakeRegistry:
            def get_by_setup_id(self, sid):
                return order if sid == "OB-1" else None

        validator = CausalValidator(window_bars=10)
        validator.observe(
            canned_setup(), 0, order_registry=FakeRegistry()
        )
        state = _state(validator)

        self.assertEqual(state.order_id, "ORD-1")
        self.assertEqual(state.order_created_bar, 5)
        self.assertEqual(state.order_expires_bar, 35)

    def test_disabling_leaves_no_traces(self):
        validator = CausalValidator(window_bars=10)
        with mock.patch.object(
            risk_settings, "ENABLE_CAUSAL_VALIDATION", False
        ):
            validator.observe(canned_setup(), 0)
            for c in _trigger_entry_candles():
                validator.advance(c, bar=c.timestamp)

        self.assertEqual(validator.count(), 0)
        self.assertEqual(validator.states(), [])


# ==========================================================
# No look-ahead (rule 5): post-decision mutations change nothing
# ==========================================================


class TestCausalNoLookAhead(unittest.TestCase):

    def _run(self, candles):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        for c in candles:
            validator.advance(c, bar=c.timestamp)
        return _snapshot_breakout(_state(validator))

    def _candles(self):
        return [
            candle(1, 111.0, 116.0, 105.0, 114.0),
            candle(2, 108.0, 113.0, 103.0, 110.0),
            candle(3, 109.0, 112.0, 101.0, 107.0),
            candle(4, 107.0, 111.0, 99.0, 102.0),
            candle(5, 106.0, 110.0, 104.0, 105.0),
        ]

    def test_mutating_candles_after_the_decision_bar_changes_nothing(self):
        base = self._candles()
        run_a = self._run(base)

        # Resolved at bar 4 (SL); mutating bars AFTER the resolution
        # candle changes nothing: no field of the state moves.
        mutated = self._candles()
        mutated[4] = candle(5, 500.0, 9999.0, 0.0, 9000.0)
        run_b = self._run(mutated)

        self.assertEqual(run_a, run_b)
        self.assertEqual(run_b["resolved"], "LOSS")
        self.assertFalse(run_b["ambiguous"])

    def test_mutating_the_setup_after_observe_changes_nothing(self):
        base = self._candles()
        run_a = self._run(base)

        setup = canned_setup()
        validator = CausalValidator(window_bars=10)
        validator.observe(setup, 0)
        setup.entry = 300.0
        setup.stop_loss = 1.0
        setup.take_profit = 9999.0
        setup.direction = "BEARISH"
        for c in base:
            validator.advance(c, bar=c.timestamp)
        run_b = _snapshot_breakout(_state(validator))

        self.assertEqual(run_a, run_b)


class TestCausalReportFormat(unittest.TestCase):

    def test_render_contains_phase_blocks(self):
        validator = CausalValidator(window_bars=10)
        validator.observe(canned_setup(), 0)
        for c in _trigger_entry_candles():
            validator.advance(c, bar=c.timestamp)

        out = format_causal_report(
            validator.report(),
            "PHASE 4H CAUSAL BREAKOUT VALIDATION (ALL)",
            setups_discovered=98,
        )

        self.assertIn(
            "PHASE 4H CAUSAL BREAKOUT VALIDATION (ALL)", out
        )
        self.assertIn("Setups Discovered / Eligible : 98 / 1", out)
        self.assertIn(
            f"  {INTRABAR_CONSERVATIVE}", out
        )
        self.assertIn(
            "PRIMARY INTRABAR POLICY          : CONSERVATIVE", out
        )
        self.assertIn("rejected_structure", out)
        self.assertIn("rejected_orderflow", out)


if __name__ == "__main__":
    unittest.main()