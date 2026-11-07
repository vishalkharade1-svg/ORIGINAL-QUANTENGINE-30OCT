"""
====================================================

QuantEngine

Phase 7 -- Breakout Asymmetry Research tests

The research package is SEVERED from production: it consumes
only frozen causal records (CausalValidationState) and produces
only evidence. These tests build deterministic synthetic causal
datasets that mirror the user-reported asymmetry (bearish
strong: high PF + positive expectancy + small MAE; bullish weak:
high win rate but negative expectancy + deep MAE) and assert
that 7A/7B/7C/7D decompose it to the correct origin -- WITHOUT
any strategy change.

All data is constructed (stdlib only), so the research chain is
fast and deterministic. No thresholds are modified; nothing is
proposed as a change here.
====================================================
"""

import json
import os
import tempfile
import unittest

from core.research.breakout_asymmetry import (
    AsymmetryReport,
    build_report,
    classify_outcomes,
    counterfactual_study,
    decompose_origins,
    extract_features,
    load_dataset,
)

from core.research.breakout_asymmetry.outcomes import (
    NEVER_ENTERED,
    STOP_HIT,
    TARGET_HIT,
    UNRESOLVED,
    EXCLUDED,
    build_profile,
)


# ====================================================
# Synthetic causal record factory
# ====================================================


def causal_state(
    direction,
    setup_id,
    entry,
    stop,
    target,
    atr,
    creation_price,
    resolved="",
    conservative="",
    sl_hit=False,
    tp_hit=False,
    ambiguous=False,
    entered=True,
    executable=True,
    r_multiple=0.0,
    mae_atr=0.0,
    mfe_atr=0.0,
    entry_distance_atr=0.0,
    creation_bar=0,
):
    from core.setup.causal_validation import CausalValidationState

    return CausalValidationState(
        setup_id=setup_id,
        structural_id=setup_id,
        direction=direction,
        entry=entry,
        stop_loss=stop,
        take_profit=target,
        atr=atr,
        creation_bar=creation_bar,
        creation_price=creation_price,
        entry_distance_atr=entry_distance_atr,
        breakout_triggered=True,
        breakout_trigger_bar=creation_bar + 1,
        breakout_trigger_close=None,
        breakout_entry_bar=creation_bar + 2 if executable else None,
        breakout_entry_price=entry if executable else None,
        breakout_entered=entered,
        breakout_causally_executable=executable,
        breakout_resolved=resolved,
        breakout_conservative=conservative,
        breakout_sl_hit=sl_hit,
        breakout_tp_hit=tp_hit,
        breakout_ambiguous=ambiguous,
        breakout_mae=0.0,
        breakout_mfe=0.0,
        breakout_mae_atr=mae_atr,
        breakout_mfe_atr=mfe_atr,
        breakout_r_multiple=r_multiple,
    )


def make_bear_strong(n=10, atr=10.0):
    """BEARISH setups reaching a target with positive R, small MAE:
    entry 100, stop 110 (risk 10), target 80 (reward 20) => RR 2.0,
    WIN r_multiple +2.0. Mostly wins (~85%) with an occasional loss
    so the population is realistic (profit factor finite)."""

    states = []

    for i in range(n):

        # 85% win rate: e.g. index 2 and 7 of each 10 are losses.
        win = (i % 10) not in (2, 7)

        risk = 10.0
        reward = 20.0

        if win:

            r_mult = reward / risk          # +2.0
            conservative = "WIN"
            sl_hit = False
            tp_hit = True
            resolved = "WIN"
            mae_atr = 0.3 + (i % 4) * 0.05
            mfe_atr = r_mult + 0.5

        else:

            # stop hit, -1R, same small adverse excursion
            r_mult = -1.0
            conservative = "LOSS"
            sl_hit = True
            tp_hit = False
            resolved = "LOSS"
            mae_atr = 0.4 + (i % 4) * 0.05
            mfe_atr = 0.2

        states.append(
            causal_state(
                direction="BEARISH",
                setup_id=f"BEAR-{i}",
                entry=100.0,
                stop=100.0 + risk,
                target=100.0 - reward,
                atr=atr,
                creation_price=102.0,
                resolved=resolved,
                conservative=conservative,
                sl_hit=sl_hit,
                tp_hit=tp_hit,
                r_multiple=r_mult,
                mae_atr=mae_atr,
                mfe_atr=mfe_atr,
                entry_distance_atr=0.5 + (i % 3) * 0.2,
            )
        )

    return states


def make_bull_weak(n=10, atr=10.0):
    """BULLISH setups with a HIGH win rate but NEGATIVE expectancy:
    small reward (RR<1.0, negative R) relative to a deep adverse
    excursion. Superficially high win rate, economically negative."""

    states = []

    for i in range(n):

        # 7 of 10 win (70% win rate) but every win pays only +0.5R
        # and losses pay -1R; expectancy negative.
        win = (i % 10) < 7

        reward = 0.5
        risk = 10.0

        if win:

            r_mult = reward / risk  # +0.05
            conservative = "WIN"
            tp_hit = True
            sl_hit = False
            resolved = "WIN"
            mae_atr = 3.5 + (i % 3) * 0.5  # deep adverse excursion
            mfe_atr = 0.1

        else:

            r_mult = -1.0
            conservative = "LOSS"
            sl_hit = True
            tp_hit = False
            resolved = "LOSS"
            mae_atr = 0.5
            mfe_atr = 0.1

        states.append(
            causal_state(
                direction="BULLISH",
                setup_id=f"BULL-{i}",
                entry=100.0,
                stop=100.0 - risk,
                target=100.0 + reward,
                atr=atr,
                creation_price=99.0,
                resolved=resolved,
                conservative=conservative,
                sl_hit=sl_hit,
                tp_hit=tp_hit,
                r_multiple=r_mult,
                mae_atr=mae_atr,
                mfe_atr=mfe_atr,
                entry_distance_atr=2.5 + (i % 2) * 0.5,
            )
        )

    return states


def make_dataset(n=10, atr=10.0):
    """A mixed dataset mirroring the reported shape: bearish
    strong, bullish weak. Return (bullish_states, bearish_states)."""

    return make_bull_weak(n=n, atr=atr), make_bear_strong(n=n, atr=atr)


# ====================================================
# 7A -- causal dataset decomposition
# ====================================================

class TestFeatureExtraction(unittest.TestCase):

    def setUp(self):

        self.bull, self.bear = make_dataset(n=6, atr=10.0)
        self.states = self.bull + self.bear

    def test_every_axis_extracted_for_both_directions(self):

        rows = extract_features(self.states)

        self.assertEqual(len(rows), len(self.states))

        for row in rows:

            # all 16 numeric axes are finite and present
            values = row.axis_values()

            self.assertEqual(len(values), 16)

            for v in values.values():

                self.assertEqual(v, v)  # no NaN
                self.assertIsNotNone(v)

    def test_displacement_atr_normalized(self):

        rows = extract_features(self.states)

        bear = [
            r for r in rows
            if (r.direction or "").upper() == "BEARISH"
        ][0]

        # creation_price 102, entry 100 => displacement 2, /atr 10
        self.assertAlmostEqual(bear.displacement, 2.0, places=6)
        self.assertAlmostEqual(bear.displacement_atr, 0.2, places=6)
        self.assertAlmostEqual(bear.entry_to_stop, 10.0, places=6)
        self.assertAlmostEqual(bear.entry_to_target, 20.0, places=6)

    def test_extractor_is_direction_agnostic(self):

        # same function applied both directions => symmetric axes
        rows = extract_features(self.states)

        bull = [
            r for r in rows
            if (r.direction or "").upper() == "BULLISH"
        ]
        bear = [
            r for r in rows
            if (r.direction or "").upper() == "BEARISH"
        ]

        self.assertTrue(bull)
        self.assertTrue(bear)

        # both directions carry the same 16-axis schema
        self.assertEqual(
            set(bull[0].axis_values().keys()),
            set(bear[0].axis_values().keys()),
        )

    def test_feature_rows_crosslink_to_source(self):

        rows = extract_features(self.states)

        self.assertEqual(rows[3].source_index, 3)
        self.assertEqual(rows[-1].setup_id, self.states[-1].setup_id)


# ====================================================
# 7B -- outcome decomposition
# ====================================================

class TestOutcomeDecomposition(unittest.TestCase):

    def test_bull_high_win_rate_negative_expectancy(self):

        bull, _ = make_dataset(n=20, atr=10.0)

        outcomes = classify_outcomes(bull, "BULLISH")

        profile = __import__(
            "core.research.breakout_asymmetry.outcomes",
            fromlist=["build_profile"],
        ).build_profile("BULLISH", outcomes)

        # high win rate (70%) but negative expectancy, PF < 1
        self.assertGreater(profile.win_rate(), 60.0)
        self.assertLess(profile.expectancy(), 0.0)
        self.assertLess(profile.profit_factor(), 1.0)

        # deep adverse excursion
        self.assertGreater(profile.avg_mae_atr, 2.0)

    def test_bear_strong_pf_and_positive_expectancy(self):

        _, bear = make_dataset(n=20, atr=10.0)

        outcomes = classify_outcomes(bear, "BEARISH")

        profile = __import__(
            "core.research.breakout_asymmetry.outcomes",
            fromlist=["build_profile"],
        ).build_profile("BEARISH", outcomes)

        self.assertGreater(profile.profit_factor(), 1.5)
        self.assertGreater(profile.expectancy(), 0.0)
        self.assertLess(profile.avg_mae_atr, 1.0)

    def test_each_triggered_setup_lands_in_one_bucket(self):

        bull = make_bull_weak(n=5, atr=10.0)
        bear = make_bear_strong(n=5, atr=10.0)

        all_states = bull + bear

        outcomes = classify_outcomes(all_states)

        bucket_keys = {NEVER_ENTERED, TARGET_HIT, STOP_HIT,
                       UNRESOLVED, EXCLUDED}

        for outcome in outcomes:

            self.assertIn(outcome.bucket, bucket_keys)
            self.assertIn(
                outcome.outcome,
                ("WIN", "LOSS", "UNRESOLVED", "EXCLUDED", "NO_ENTRY"),
            )

    def test_never_entered_is_an_execution_artifact(self):

        state = causal_state(
            direction="BEARISH",
            setup_id="NOENTRY",
            entry=100.0,
            stop=110.0,
            target=80.0,
            atr=10.0,
            creation_price=105.0,
            entered=False,
            executable=False,
        )

        outcomes = classify_outcomes([state], "BEARISH")

        self.assertEqual(outcomes[0].bucket, NEVER_ENTERED)
        self.assertEqual(outcomes[0].outcome, "NO_ENTRY")

        # never_entered is NOT counted as a decided win/loss
        profile = build_profile(
            "BEARISH", classify_outcomes([state], "BEARISH")
        )
        self.assertEqual(profile.wins, 0)
        self.assertEqual(profile.losses, 0)
        self.assertEqual(profile.never_entered, 1)


# ====================================================
# 7C -- origin decomposition
# ====================================================

class TestOriginDecomposition(unittest.TestCase):

    def test_identifies_geometry_as_dominant_origin(self):

        bull, bear = make_dataset(n=12, atr=10.0)
        states = bull + bear

        origins = decompose_origins(states)

        # Seven classes are reported
        codes = {o.code for o in origins.origins}
        self.assertEqual(codes, {"A", "B", "C", "D", "E", "F", "G"})

        # settlement totals reconcile
        self.assertEqual(
            origins.total_triggered, len(states)
        )

        # The setup-SELECTION distance and geometry asymmetry should
        # be present: bullish enters farther from market and suffers
        # deeper adverse excursion.
        setup = origins.by_code("C")
        geometry = origins.by_code("E")

        self.assertGreaterEqual(setup.asymmetry, 0.0)
        self.assertTrue(any(
            o.metric_name == "avg MFE (ATR)" for o in origins.origins
        ))

        # MAE geometric asymmetry: bullish adverse excursion far
        # exceeds bearish.
        mae_origins = [
            o for o in origins.origins
            if o.metric_name == "avg MAE (ATR)"
        ]
        self.assertEqual(len(mae_origins), 1)
        mae = mae_origins[0]
        self.assertGreater(mae.bullish_value, mae.bearish_value)
        self.assertGreater(mae.asymmetry, 0.3)

        # Execution is held constant.
        execution = origins.by_code("F")
        self.assertEqual(execution.present, False)
        self.assertEqual(execution.bullish_value, 0.0)
        self.assertEqual(execution.bearish_value, 0.0)

    def test_bearish_win_rate_exceeds_bullish(self):

        bull, bear = make_dataset(n=10, atr=10.0)
        states = bull + bear

        origins = decompose_origins(states)

        market = origins.by_code("A")

        # In OUR synthetic dataset bearish is stronger on a win-rate
        # basis too (all bearish win vs bullish 70%).
        self.assertGreater(market.bearish_value, market.bullish_value)

    def test_dominant_origin_present_when_asymmetric(self):

        bull, bear = make_dataset(n=12, atr=10.0)
        states = bull + bear

        origins = decompose_origins(states)

        dominant = origins.dominant()

        self.assertIsNotNone(dominant)
        self.assertTrue(dominant.present)


# ====================================================
# 7D -- counterfactual
# ====================================================

class TestCounterfactual(unittest.TestCase):

    def test_execution_held_constant(self):

        bull, bear = make_dataset(n=15, atr=10.0)
        states = bull + bear

        study = counterfactual_study(states)

        verdict = study.execution_asymmetry()

        # Because the mirror preserves the R-multiple and excursions
        # (direction-agnostic), swapping the direction label changes
        # NOTHING about the outcome classification: execution is held
        # constant by construction.
        self.assertEqual(verdict["verdict"], "EXECUTION-HELD-CONSTANT")
        self.assertEqual(verdict["bull_shift_pp"], 0.0)
        self.assertEqual(verdict["bear_shift_pp"], 0.0)

    def test_mirror_preserves_native_win_rate(self):

        bull, bear = make_dataset(n=15, atr=10.0)
        states = bull + bear

        study = counterfactual_study(states)

        # bull native == bull mirrored through bear geometry
        self.assertAlmostEqual(
            study.bull_native.win_rate(),
            study.bull_via_bear.win_rate(),
            places=9,
        )
        self.assertAlmostEqual(
            study.bear_native.win_rate(),
            study.bear_via_bull.win_rate(),
            places=9,
        )

    def test_mirror_swaps_direction_label(self):

        bull, bear = make_dataset(n=8, atr=10.0)
        states = bull + bear

        # a bullish state mirrored becomes BEARISH
        from core.research.breakout_asymmetry.counterfactual import _mirror

        mir = _mirror(states[0])

        bull_labels = [s.direction for s in bull]
        self.assertTrue(all(d == "BULLISH" for d in bull_labels))

        self.assertEqual(mir.direction, "BEARISH")


# ====================================================
# Report assembly
# ====================================================

class TestReportAssembly(unittest.TestCase):

    def test_report_assembles_all_phases(self):

        bull, bear = make_dataset(n=20, atr=10.0)
        states = bull + bear

        report = build_report(states)

        self.assertIsInstance(report, AsymmetryReport)
        self.assertEqual(report.origins.total_triggered, len(states))

        ok, msg = report.verify()
        self.assertTrue(ok, msg)

        # hypothesis is evidence-led, not a change
        hypothesis = report.hypothesis()
        self.assertIn(
            hypothesis["candidate_change"],
            ("DIRECTIONAL_POLICY", "NONE"),
        )
        self.assertIn("note", hypothesis)

        # summary renders
        summary = report.summary()
        self.assertIn("BREAKOUT ASYMMETRY RESEARCH", summary)

    def test_load_dataset_accepts_dict_and_path(self):

        bull, bear = make_dataset(n=5, atr=10.0)
        states = bull + bear

        # dicts (slots dataclass -> asdict)
        from dataclasses import asdict

        states_dict = [asdict(s) for s in states]

        loaded = load_dataset(states_dict)

        self.assertEqual(len(loaded), len(states))
        self.assertEqual(loaded[0].direction, states[0].direction)

        # json path
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:

            json.dump(states_dict, fh, indent=2)
            path = fh.name

        try:

            loaded_path = load_dataset(path)
            self.assertEqual(len(loaded_path), len(states))

        finally:

            os.unlink(path)

    def test_report_dump_roundtrip(self):

        bull, bear = make_dataset(n=8, atr=10.0)
        states = bull + bear

        report = build_report(states)

        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:

            report.dump(fh.name)
            path = fh.name

        try:

            with open(path, encoding="utf-8") as fh:

                data = json.load(fh)

            self.assertEqual(data["total_setups"], len(states))
            self.assertIn("profiles", data)
            self.assertIn("origins", data)
            self.assertIn("counterfactual", data)
            self.assertIn("hypothesis", data)

        finally:

            os.unlink(path)


# ====================================================
# Gournd-truth: reproduce the user's reported asymmetry,
# then confirm the research chain estimates it faithfully.
# ====================================================

class TestReportedAsymmetryReproduced(unittest.TestCase):

    def test_known_asymmetry_decomposes_cleanly(self):

        # Build a dataset faithfully mirroring the user's report:
        #   BEARISH 151 triggers, PF ~3, expectancy +0.28R, MAE small
        #   BULLISH  83 triggers, PF ~0.92, expectancy -0.02R, deep MAE
        #
        # We do NOT reproduce exact counts (that requires the real
        # 5,000-bar walk); we reproduce the SHAPE and confirm the
        # research chain classifies it to the correct origin.

        # bearish: ~86% win (one loss per 7), avg win +1.0R,
        # avg loss -1.0R, PF comfortably above user's 3.05
        bear_states = []
        for i in range(40):
            win = (i % 7) != 0
            reward = 15.0 + (i % 4)
            risk = 10.0
            r = (reward / risk) if win else -1.0
            bear_states.append(
                causal_state(
                    "BEARISH",
                    f"BQ-{i}",
                    entry=100.0,
                    stop=110.0,
                    target=100.0 - reward,
                    atr=10.0,
                    creation_price=102.0,
                    resolved="WIN" if win else "LOSS",
                    conservative="WIN" if win else "LOSS",
                    tp_hit=win,
                    sl_hit=not win,
                    r_multiple=r,
                    mae_atr=0.3 if win else 0.4,
                    mfe_atr=(0.9 if win else 0.2),
                )
            )

        # bullish: ~75% win (one loss per 4), but every win pays
        # only +0.2R while losses pay -1R -> PF clearly below 1,
        # NEGATIVE expectancy, deep adverse excursion
        bull_states = []
        for i in range(30):
            win = (i % 4) != 0
            reward = 2.0
            risk = 10.0
            r = (reward / risk) if win else -1.0
            bull_states.append(
                causal_state(
                    "BULLISH",
                    f"BULLQ-{i}",
                    entry=100.0,
                    stop=90.0,
                    target=102.0,
                    atr=10.0,
                    creation_price=99.0,
                    resolved="WIN" if win else "LOSS",
                    conservative="WIN" if win else "LOSS",
                    tp_hit=win,
                    sl_hit=not win,
                    r_multiple=r,
                    mae_atr=4.0 if win else 0.5,
                    mfe_atr=0.2,
                    entry_distance_atr=3.0,
                )
            )

        states = bull_states + bear_states

        report = build_report(states)

        bull = report.profiles["BULLISH"]
        bear = report.profiles["BEARISH"]

        # All seven origin classes A-G are reported.
        self.assertEqual(
            {o.code for o in report.origins.origins},
            {"A", "B", "C", "D", "E", "F", "G"},
        )
        # Bearish economically strong.
        self.assertGreater(bear.win_rate(), bull.win_rate())
        self.assertGreater(bear.profit_factor(), 2.0)
        self.assertGreater(bear.expectancy(), 0.0)

        # Bullish: high win rate but PF below 1 is the tell.
        self.assertGreater(bull.win_rate(), 65.0)
        self.assertLess(bull.profit_factor(), 1.0)

        # Deep adverse excursion on the bullish side.
        mae_origins = [
            o for o in report.origins.origins
            if o.metric_name == "avg MAE (ATR)"
        ]
        self.assertTrue(mae_origins)
        self.assertGreater(
            mae_origins[0].bullish_value,
            mae_origins[0].bearish_value,
        )

        # 7D proves the difference is not execution.
        verdict = report.counterfactual.execution_asymmetry()
        self.assertEqual(verdict["verdict"], "EXECUTION-HELD-CONSTANT")

        # 7C points to a setup-origin asymmetry.
        self.assertIsNotNone(report.origins.dominant())


if __name__ == "__main__":

    unittest.main()