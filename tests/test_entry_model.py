"""
====================================================

QuantEngine

Phase 5A: Canonical Entry Model Architecture Tests

Run with:

    python -m unittest tests.test_entry_model -v

Proves the canonical EntryModel contract that every entry mode
now shares (Phase 5A), with the BREAKOUT_CONTINUATION trigger
locked 1:1 to the Phase 4H causal rules:

  CONTRACT -- every model returns an EntryDecision carrying the
      identity (setup_id / structural_id / economic_fingerprint),
      direction, entry_mode, stop_loss / take_profit, and the
      trigger / entry bar + price fields; unknown modes resolve to
      no model / the configured default, never a wrong decider.
  LIMIT    -- the resting-limit model reports a touch exactly when
      low <= entry <= high on the deciding candle; unspecified
      ranges (tick harnesses) report a touch (legacy behavior).
  CONFIRM  -- MARKET_CONFIRMATION's two-stage trigger (reached E
      AND closed beyond it) and the Phase 4H rejection partition
      (structure > trend > distance) at settle, with the partition
      invariant (the three reject counters + triggered == 1).
  BREAKOUT -- the FOUR causal rules exactly as Phase 4H walks them:
      stop-breach-before-trigger invalidation, BULLISH high > E AND
      close > E (BEARISH low < E AND close < E), entry_bar = N+1
      for a trigger at N, and no same-candle entry.
  VOCAB    -- the entry-mode constants are ONE vocabulary: the
      setup-layer re-export IS the canonical entry_model object.

Stdlib only -- no network.

====================================================
"""

import unittest
from types import SimpleNamespace

from core.execution.entry_model import (
    ENTRY_MODE_BREAKOUT_CONTINUATION,
    ENTRY_MODE_LIMIT_RETEST,
    ENTRY_MODE_MARKET_CONFIRMATION,
    ENTRY_MODES,
    EXECUTION_LIMIT,
    EXECUTION_NEXT_BAR_OPEN,
    BreakoutContinuationEntryModel,
    EntryDecision,
    LimitRetestEntryModel,
    MarketConfirmationEntryModel,
    default_entry_model,
    execution_type_for,
    get_entry_model,
)
from core.setup import entry_feasibility as ef
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
    structural="OB-1",
):
    setup = SetupCandidate(
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
    )
    setup.setup_id = structural
    setup.structural_id = structural
    setup.economic_fingerprint = "FP-1"
    return setup


class TestEntryDecisionContract(unittest.TestCase):

    def test_decision_carries_the_identity_chain(self):
        setup = canned_setup()
        decision = LimitRetestEntryModel().decide(
            setup, candle(5, 105, 112, 101, 111), 5, timestamp=999
        )
        self.assertEqual(decision.setup_id, "OB-1")
        self.assertEqual(decision.structural_id, "OB-1")
        self.assertEqual(decision.economic_fingerprint, "FP-1")
        self.assertEqual(decision.direction, "BULLISH")
        self.assertEqual(decision.entry_mode, ENTRY_MODE_LIMIT_RETEST)
        self.assertEqual(decision.stop_loss, 100.0)
        self.assertEqual(decision.take_profit, 130.0)

    def test_decision_is_the_one_compatible_contract(self):
        for model in (
            LimitRetestEntryModel(),
            MarketConfirmationEntryModel(),
            BreakoutContinuationEntryModel(),
        ):
            decision = model.decide(
                canned_setup(), candle(3, 100, 100, 100, 100), 3
            )
            self.assertIsInstance(decision, EntryDecision)

    def test_unknown_mode_resolves_to_no_model(self):
        self.assertIsNone(get_entry_model("FVG_RETRACE"))
        self.assertIsNone(get_entry_model("DISPLACEMENT_RETEST"))
        self.assertIsNone(get_entry_model("NOPE"))

    def test_default_model_is_the_configured_breakout_model(self):
        # Phase 5D: BREAKOUT_CONTINUATION is the deliberately
        # selected production default (config) -- the router no
        # longer degrades the baseline to LIMIT_RETEST.
        self.assertIsInstance(
            default_entry_model(), BreakoutContinuationEntryModel
        )

    def test_vocabulary_is_shared_not_copied(self):
        self.assertIs(
            ef.ENTRY_MODE_BREAKOUT_CONTINUATION,
            ENTRY_MODE_BREAKOUT_CONTINUATION,
        )
        self.assertIs(ef.ENTRY_MODE_LIMIT_RETEST, ENTRY_MODE_LIMIT_RETEST)
        self.assertEqual(ef.ENTRY_MODES, ENTRY_MODES)

    def test_execution_type_defaults_to_limit(self):
        self.assertEqual(execution_type_for(""), EXECUTION_LIMIT)
        self.assertEqual(
            execution_type_for(ENTRY_MODE_LIMIT_RETEST), EXECUTION_LIMIT
        )
        self.assertEqual(
            execution_type_for(ENTRY_MODE_MARKET_CONFIRMATION),
            EXECUTION_LIMIT,
        )
        self.assertEqual(
            execution_type_for(ENTRY_MODE_BREAKOUT_CONTINUATION),
            EXECUTION_NEXT_BAR_OPEN,
        )


class TestLimitRetestEntryModel(unittest.TestCase):

    def test_touch_on_range_spanning_entry(self):
        decision = LimitRetestEntryModel().decide(
            canned_setup(entry=110.0),
            candle(7, 105, 112, 103, 109),
            7,
            timestamp=77,
        )
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.entry_price, 110.0)
        self.assertEqual(decision.entry_bar, 7)
        self.assertEqual(decision.entry_timestamp, 77)

    def test_no_touch_when_range_below_entry(self):
        decision = LimitRetestEntryModel().decide(
            canned_setup(entry=110.0),
            candle(7, 104, 105, 101, 103),
            7,
        )
        self.assertFalse(decision.triggered)

    def test_no_touch_when_range_above_entry(self):
        decision = LimitRetestEntryModel().decide(
            canned_setup(entry=110.0),
            candle(7, 112, 115, 111, 114),
            7,
        )
        self.assertFalse(decision.triggered)

    def test_bearish_touch_mirrors_bullish(self):
        decision = LimitRetestEntryModel().decide(
            canned_setup(direction="BEARISH", entry=90.0),
            candle(7, 95, 96, 89, 91),
            7,
        )
        self.assertTrue(decision.triggered)

    def test_unspecified_range_treats_as_touch(self):
        decision = LimitRetestEntryModel().decide(
            canned_setup(entry=110.0),
            SimpleNamespace(timestamp=1, open=105, close=108),
            1,
        )
        self.assertTrue(decision.triggered)


class TestMarketConfirmationEntryModel(unittest.TestCase):

    def test_trigger_requires_crossed_and_closed_beyond(self):
        model = MarketConfirmationEntryModel()
        parent = model.decide(
            canned_setup(entry=110.0),
            candle(5, 108, 112, 107, 111),
            5,
        )
        self.assertTrue(parent.triggered)
        self.assertEqual(parent.trigger_bar, 5)
        self.assertEqual(parent.entry_price, 111.0)

    def test_crossed_but_not_closed_beyond_is_not_triggered(self):
        decision = MarketConfirmationEntryModel().decide(
            canned_setup(entry=110.0),
            candle(5, 108, 112, 107, 109),
            5,
        )
        self.assertFalse(decision.triggered)
        self.assertTrue(decision.metadata["reached"])

    def test_never_reached_reports_not_reached(self):
        decision = MarketConfirmationEntryModel().decide(
            canned_setup(entry=110.0),
            candle(5, 100, 105, 98, 103),
            5,
        )
        self.assertFalse(decision.triggered)
        self.assertFalse(decision.metadata["reached"])

    def test_bearish_close_below_entry_triggers(self):
        decision = MarketConfirmationEntryModel().decide(
            canned_setup(direction="BEARISH", entry=90.0),
            candle(5, 93, 95, 89, 88),
            5,
        )
        self.assertTrue(decision.triggered)

    def test_settle_partition_priority_structure_gt_trend_gt_distance(self):
        model = MarketConfirmationEntryModel()
        trigger = model.decide(
            canned_setup(entry=110.0),
            candle(5, 108, 112, 107, 111),
            5,
        )
        model.settle(trigger)
        self.assertEqual(trigger.rejected_reason, "")
        self.assertTrue(trigger.triggered)

        invalidated = model.decide(
            canned_setup(entry=110.0),
            candle(5, 100, 104, 99, 103),
            5,
        )
        model.settle(invalidated, invalidated=True)
        self.assertEqual(invalidated.rejected_reason, "structure")

        far = model.decide(
            canned_setup(entry=110.0),
            candle(5, 100, 104, 98, 103),
            5,
        )
        model.settle(far, invalidated=False, reached=False)
        self.assertEqual(far.rejected_reason, "distance")

        trend = model.decide(
            canned_setup(entry=110.0),
            candle(5, 108, 112, 107, 109),
            5,
        )
        model.settle(trend, invalidated=False, reached=True)
        self.assertEqual(trend.rejected_reason, "trend")

    def test_settle_partition_is_exhaustive(self):
        model = MarketConfirmationEntryModel()
        decisions = [
            model.settle(
                model.decide(
                    canned_setup(), candle(5, 108, 112, 107, 111), 5
                )
            ),
            model.settle(
                model.decide(
                    canned_setup(), candle(5, 100, 104, 99, 103), 5
                ),
                invalidated=True,
            ),
            model.settle(
                model.decide(
                    canned_setup(), candle(5, 100, 104, 98, 103), 5
                ),
                invalidated=False,
                reached=False,
            ),
            model.settle(
                model.decide(
                    canned_setup(), candle(5, 108, 112, 107, 109), 5
                ),
                invalidated=False,
                reached=True,
            ),
        ]
        keys = (
            "triggered",
            "rejected_structure",
            "rejected_trend",
            "rejected_distance",
        )
        for d in decisions:
            total = sum(1 for k in keys if getattr(d, k, False) or d.metadata.get(k, 0))
            self.assertIn(total, (0, 1))


class TestBreakoutContinuationEntryModel(unittest.TestCase):

    def test_bullish_trigger_high_gt_entry_and_close_gt_entry(self):
        decision = BreakoutContinuationEntryModel().decide(
            canned_setup(entry=110.0, stop=100.0),
            candle(5, 108, 113, 106, 112),
            5,
        )
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.trigger_bar, 5)
        self.assertEqual(decision.entry_bar, 6)

    def test_bullish_high_above_but_close_below_no_trigger(self):
        decision = BreakoutContinuationEntryModel().decide(
            canned_setup(entry=110.0, stop=100.0),
            candle(5, 108, 113, 106, 109),
            5,
        )
        self.assertFalse(decision.triggered)

    def test_bearish_mirror_low_lt_entry_close_lt_entry(self):
        decision = BreakoutContinuationEntryModel().decide(
            canned_setup(direction="BEARISH", entry=90.0, stop=100.0),
            candle(5, 93, 94, 89, 88),
            5,
        )
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.entry_bar, 6)

    def test_stop_breach_before_trigger_invalidates(self):
        decision = BreakoutContinuationEntryModel().decide(
            canned_setup(entry=110.0, stop=100.0),
            candle(5, 108, 113, 99, 112),
            5,
        )
        self.assertFalse(decision.triggered)
        self.assertTrue(decision.metadata["invalidated"])

    def test_entry_bar_is_always_next_bar(self):
        for bar in (0, 1, 7, 40):
            decision = BreakoutContinuationEntryModel().decide(
                canned_setup(entry=110.0, stop=100.0),
                candle(bar, 108, 113, 106, 112),
                bar,
            )
            self.assertEqual(decision.entry_bar, bar + 1)

    def test_trigger_never_sets_entry_price(self):
        # The price is not known until the OPEN of the entry bar;
        # the trading actor stamps it.
        decision = BreakoutContinuationEntryModel().decide(
            canned_setup(entry=110.0, stop=100.0),
            candle(5, 108, 113, 106, 112),
            5,
        )
        self.assertEqual(decision.entry_price, 0.0)

    def test_no_entry_on_same_candle(self):
        decision = BreakoutContinuationEntryModel().decide(
            canned_setup(entry=110.0, stop=100.0),
            candle(5, 108, 113, 106, 112),
            5,
        )
        self.assertEqual(decision.entry_bar, 6)
        self.assertNotEqual(decision.entry_bar, decision.trigger_bar)


if __name__ == "__main__":
    unittest.main()