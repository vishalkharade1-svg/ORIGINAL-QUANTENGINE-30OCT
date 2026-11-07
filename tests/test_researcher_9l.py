"""
====================================================================

QuantEngine

Phase 9L -- Advanced ML + Regime / Opportunity Discovery tests

Proves the deterministic, research-only conditional-opportunity layer
(AI/ML-probability evidence over the frozen 9A-9K stack):

   * the FIXED alternative grid (LIMIT_RETEST / MARKET_CONFIRMATION /
     BREAKOUT_CONTINUATION) is exactly the production-supported
     vocabulary -- never an auto-ML search over 100k combinations;
   * generate -> filter -> temporal VALIDATION/OOS -> multiple-testing
     correction -> robustness -> economic significance -> minimum
     sample -> confidence/calibration -> limitations pipeline is
     exposed by the frozen ConditionalMlReport;
   * every discovery surface (recovery / entry-model selection /
     feature interactions / regime transition / symbol segmentation /
     OOS calibration) retains EVERY finding -- INCONCLUSIVE included;
   * the GLOBAL familywise guard is stricter than any per-surface
     gate (Sidak over the TOTAL enumerated hypothesis family, Holm
     within the interaction family);
   * two-proportion / mean-difference p-values are proper two-sided
     tails (strong evidence -> small p, never inverted);
   * feature interaction combos never mix two values of the SAME
     feature (structurally impossible rows are not tested);
   * outcome = byte-repeatable: two identical runs produce identical
     frozen reports; divergent FUTURE bars beyond every decision/fill
     produce byte-identical reports (decision-time only, no lookahead);
   * end-to-end synthetic trend/range fixture: deterministic cell
     economics encoded exactly (54 opportunities, 223 hypotheses,
     corrected alpha 0.00023, recovery pool 14 TREND / 19 RANGE misses
     under a 10-bar expiry, RANGE|BULLISH entry-selection inconclusive,
     RANGE->RANGE / TREND->TREND stable transitions, CALIBRATION_GAP
     OOS surfaces) -- CHANGED / SUPPORTED / justified outcomes are
     exercised by focused unit fixtures;
   * production guard: is_production_ready is permanently False
     (raises on True), no NEVER_EMITTED promotion tokens, no
     randomness/uuid/datetime, no scipy, no production imports.

Uses ONLY the real 9A-9K machinery and genuine counterfactual
simulation. Stdlib only; offline; deterministic.
====================================================================
"""

import math
import os
import re
import sys
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from core.research.conditional_ml import (
    CANDIDATE_ALTERNATIVES,
    CALIBRATED,
    CALIBRATION_GAP,
    ENTRY_SELECTION_SUPPORTED,
    ENTRY_SELECTION_INCONCLUSIVE,
    RECOVERY_SUPPORTED,
    RECOVERY_INCONCLUSIVE,
    INTERACTION_SUPPORTED,
    INTERACTION_INCONCLUSIVE,
    TRANSITION_STABLE,
    TRANSITION_CHANGED,
    TRANSITION_INCONCLUSIVE,
    UNAVAILABLE,
    OutcomeModel,
    ConditionalMlEngine,
    ConditionalMlReport,
    DEFAULT_GATES,
    recovery_probabilities,
    entry_selection,
    interaction_analysis,
    transitions,
    symbol_behaviour,
    calibration_summary,
    familywise_alpha,
    holm_survives,
    required_min_n,
)
from core.research.conditional_ml.guards import z_prop_win, z_mean_diff
from core.research.conditional_ml.engine import _binom_z, _mean_z
from core.research.discovery.constants import NEVER_EMITTED
from core.research.journal import OpportunityRecord
from core.research.ml.split import temporal_split


ALTS = list(CANDIDATE_ALTERNATIVES)
LIM, MKT, BRK = ALTS


class _C(object):
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open, self.high, self.low = o, h, l
        self.close, self.timestamp = c, ts


def build_series():
    bars = [_C(94.0, 94.5, 93.5, 94.0, i) for i in range(140)]
    # TREND ramp bars 14..53: close climbs 95.0 -> 97.5 (below the
    # 100.0 BREAKOUT trigger until the spike).
    for i in range(14, 54):
        c = 95.0 + (i - 14) * 0.09
        bars[i] = _C(c, c + 0.5, c - 0.6, c, i)
    bars[54] = _C(100.0, 103.0, 99.0, 105.0, 54)
    bars[55] = _C(100.0, 102.0, 99.5, 102.0, 55)
    bars[56] = _C(102.0, 102.6, 96.0, 101.0, 56)
    bars[57] = _C(100.0, 114.0, 100.0, 113.0, 57)
    for i in range(58, 70):
        c = 99.3 + (i - 58) * 0.1
        bars[i] = _C(c, c + 0.5, c - 0.6, c, i)
    # RANGE oscillation bars 70..130.
    seed = 99.2
    for i in range(70, 131):
        seed = seed + (0.3 if i % 2 else -0.3)
        seed = max(98.5, min(99.9, seed))
        bars[i] = _C(seed - 0.5, seed + 0.75, seed - 0.75, seed, i)
    bars[113] = _C(100.0, 103.0, 99.0, 104.0, 113)
    bars[114] = _C(100.0, 104.5, 99.5, 104.0, 114)
    bars[115] = _C(104.0, 105.0, 92.0, 101.0, 115)
    return bars


SERIES = build_series()


def mk_record(seq, decision, symbol="X", direction="BULLISH"):
    trade = {
        "result": "UNSETTLED", "pnl": 0.0, "risk_amount": 2.0,
        "entry_bar": decision + 1, "exit_bar": decision + 1,
        "bars_held": 1, "r": 0.0, "exit_price": 0.0,
    }
    return OpportunityRecord(
        canonical_id="r-%s-%02d" % (symbol, seq),
        exchange="TESTEX", instrument_id=symbol, timeframe="1m",
        direction=direction, strategy="BREAKOUT_CONTINUATION",
        setup_id="r-%s-%02d" % (symbol, seq),
        setup={
            "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
            "risk_reward": 2.0, "bar": decision, "atr": 4.0,
            "rejection_reasons": [],
        },
        order={}, trade=trade, terminal_outcome="ORDER_NOT_CREATED",
    )


def e2e_records():
    out = []
    for i in range(24):
        out.append(mk_record(i, 30 + i, symbol="X"))
    for i in range(17):
        out.append(mk_record(100 + i, 96 + i, symbol="X"))
    for i in range(13):
        out.append(mk_record(200 + i, 99 + i, symbol="Y"))
    return out


E2E_CONFIG = {
    "rr": 2.0, "stop_mode": "EXISTING_STOP",
    "target_mode": "FIXED_RR", "expiry": 10,
}


def e2e_run(candles=None):
    return ConditionalMlEngine().run(
        e2e_records(), candles if candles is not None else SERIES,
        config=E2E_CONFIG,
    )


def divergent_future_series():
    bars = [_C(b.open, b.high, b.low, b.close, b.timestamp)
            for b in SERIES]
    for i in range(130, 140):
        bars[i].close = bars[i].close + 5.0
    return bars


# -------------------------------------------------
# unit-mode fake context / rows for the surface tests
# -------------------------------------------------

class _Ctx(object):
    def __init__(self, regime, direction, tokens=None, symbol="X",
                 filled=None, baseline_filled=True):
        self._g = regime
        self._d = direction.upper()
        self._t = dict(tokens or {})
        self.symbol = symbol
        self._f = filled if filled is not None else regime
        self.baseline_filled = baseline_filled
        self.direction = self._d

    def primary_generated(self):
        return self._g

    def primary_filled(self):
        return self._f

    def tokens(self):
        return dict(self._t)


def unit_row(regime, direction, bar, rs=None, base_r=None,
             base_filled=True, known=False, tokens=None, symbol="X",
             filled=None):
    rs = rs if rs is not None else {a: None for a in ALTS}
    labels = {a: (1 if rs.get(a) is not None and rs[a] > 0 else
                  (0 if rs.get(a) is not None else None)) for a in ALTS}
    maes = {a: (0.5 if rs.get(a) is not None else None) for a in ALTS}
    rec = {a: None for a in ALTS}
    if known:
        for a in ALTS:
            v = rs.get(a)
            rec[a] = 1 if (v is not None and v > 0) else 0
    return SimpleNamespace(
        ctx=_Ctx(regime, direction, tokens, symbol, filled=filled,
                 baseline_filled=base_filled),
        alt_filled={a: True for a in ALTS},
        labels=labels, rs=rs, maes=maes, recovery=rec,
        baseline_filled=base_filled, baseline_r=base_r,
        known=bool(known), decision_bar=bar, entry_state="FILLED",
    )


UNIT_GATES = {"min_entries_n": 5, "min_interaction_n": 5,
              "economic_delta_r": 0.5}
CALIB_PAIRS = [(0.8, 1)] * 5 + [(0.8, 0)] + [(0.2, 0)] * 5 + [(0.2, 1)]


class TestPackageSurface(unittest.TestCase):
    def test_exports_and_alphabet(self):
        self.assertEqual(
            CANDIDATE_ALTERNATIVES,
            ("LIMIT_RETEST", "MARKET_CONFIRMATION", "BREAKOUT_CONTINUATION"))
        self.assertIsInstance(UNAVAILABLE, str)
        self.assertEqual(ConditionalMlReport(phase="9L").phase, "9L")

    def test_engine_default_gates(self):
        for key in ("min_recovery_n", "min_entries_n", "min_interaction_n",
                    "min_symbol_n", "min_transition_n", "min_calibration_n",
                    "economic_delta_r", "alpha", "validation_fraction",
                    "oos_fraction", "lookback"):
            self.assertIn(key, DEFAULT_GATES)
        self.assertEqual(DEFAULT_GATES["alpha"], 0.05)
        self.assertEqual(DEFAULT_GATES["economic_delta_r"], 0.5)


class TestGatesAndCorrections(unittest.TestCase):
    def test_required_min_n_grows_with_hypotheses(self):
        self.assertEqual(required_min_n(6, 1), 7)
        self.assertEqual(required_min_n(6, 223), 14)
        self.assertEqual(required_min_n(5, 223), 13)
        self.assertEqual(required_min_n(5, 1), 6)

    def test_sidak_familywise(self):
        a = familywise_alpha(0.05, 223)
        self.assertAlmostEqual(a, 0.00022998832166853944, places=12)
        self.assertAlmostEqual(familywise_alpha(0.05, 1), 0.05, places=12)
        self.assertLess(a, 0.00023)

    def test_holm_stepdown(self):
        flags, n = holm_survives([0.01, 0.02, 0.5])
        self.assertEqual(n, 3)
        self.assertEqual(flags, [True, True, False])

    def test_two_proportion_tail_is_not_inverted(self):
        p = z_prop_win(8, 8, 8, 0)
        self.assertIsNotNone(p)
        self.assertLess(p, 0.001)

    def test_mean_diff_expectancy_direction(self):
        strong = z_mean_diff([2.0] * 5 + [-1.0] * 3, [-1.0] * 8)
        weak = z_mean_diff([0.2, 0.3, 0.4], [0.25, 0.35, 0.3])
        self.assertIsNotNone(strong)
        self.assertLess(strong, 0.001)
        self.assertGreater(weak, 0.9)

    def test_tail_p_value_helpers(self):
        self.assertIsNone(_binom_z(14, 14))
        self.assertLess(_binom_z(290, 300), 1e-9)
        self.assertLess(_mean_z(2.0, 18, 1.5), 1e-6)


class TestOutcomeModel(unittest.TestCase):
    def _row(self, tokens, label, r):
        return SimpleNamespace(tokens=tokens, label=label, r=r,
                               known=True)

    def test_fit_predict_deterministic_and_clipped(self):
        rows = [self._row({"v": "H"}, 1, 2.0)] * 6 + \
               [self._row({"v": "H"}, 0, -1.0)] * 2
        m = OutcomeModel().fit(rows)
        p = m.predict_p({"v": "H"})
        self.assertEqual(p, OutcomeModel().fit(rows).predict_p({"v": "H"}))
        self.assertGreaterEqual(p, 0.02)
        self.assertLessEqual(p, 0.98)
        self.assertEqual(m.predict_expected_r({"v": "H"}), 1.25)

    def test_never_fitted_model_predicts_none(self):
        m = OutcomeModel()
        self.assertFalse(m.fitted())
        self.assertIsNone(m.predict_p({}))
        self.assertIsNone(m.predict_expected_r({}))


class TestCalibrationUnit(unittest.TestCase):
    def test_calibrated_summary(self):
        c = calibration_summary(CALIB_PAIRS, surface="WIN:X", min_n_gate=10)
        self.assertEqual(c.status, CALIBRATED)
        self.assertEqual(c.oos_n, 12)
        self.assertEqual(c.ece, 0.0333)
        self.assertEqual(c.brier, 0.14)
        self.assertAlmostEqual(c.slope, 0.240449, places=5)

    def test_gap_when_sample_too_small(self):
        c = calibration_summary([(0.8, 1)] * 3, min_n_gate=10)
        self.assertEqual(c.status, CALIBRATION_GAP)
        self.assertEqual(c.oos_n, 3)

    def test_empty_inputs_no_fabrication(self):
        c = calibration_summary([], min_n_gate=10)
        self.assertEqual(c.status, CALIBRATION_GAP)
        self.assertEqual(c.bins, ())
        self.assertIsNone(c.ece)


class TestEntrySelectionUnit(unittest.TestCase):
    def _rows(self):
        rows = []
        for i in range(24):
            rows.append(unit_row(
                "TREND", "BULLISH", i,
                rs={LIM: 2.0, MKT: -1.0, BRK: 2.0}, base_r=-1.5,
                tokens={"atr_regime": "HIGH"}))
        for i in range(8):
            rows.append(unit_row(
                "TREND", "BULLISH", 100 + i,
                rs={LIM: 2.0, MKT: -1.0, BRK: 2.0}, base_r=-1.5,
                tokens={"atr_regime": "HIGH"}))
        for i in range(8):
            rows.append(unit_row(
                "TREND", "BULLISH", 200 + i,
                rs={LIM: 2.0, MKT: -1.0, BRK: 2.0}, base_r=-1.5,
                tokens={"atr_regime": "HIGH"}))
        return rows

    def test_supported_conditional_selection(self):
        rows = self._rows()
        split = temporal_split(rows, 0.2, 0.2)
        es = entry_selection(rows, split, ALTS, [("TREND", "BULLISH")],
                             UNIT_GATES, n_hypotheses=1)[0]
        self.assertEqual(es.status, ENTRY_SELECTION_SUPPORTED)
        self.assertEqual(es.selected, "LIMIT_RETEST")
        self.assertEqual(es.min_oos_n_gate, 6)
        by_alt = {a.alternative: a for a in es.alternatives}
        lim = by_alt["LIMIT_RETEST"]
        self.assertEqual(lim.n_train, 24)
        self.assertEqual(lim.n_oos, 8)
        self.assertEqual(lim.expected_r_oos, 2.0)
        self.assertEqual(lim.baseline_expectancy_oos, -1.5)
        self.assertEqual(lim.delta_expectancy_oos, 3.5)
        self.assertLess(lim.p_two_sided, 0.001)

    def test_all_alternatives_are_retained(self):
        rows = self._rows()
        split = temporal_split(rows, 0.2, 0.2)
        es = entry_selection(rows, split, ALTS, [("TREND", "BULLISH")],
                             UNIT_GATES, n_hypotheses=1)[0]
        self.assertEqual(
            {a.alternative for a in es.alternatives}, set(ALTS))


class TestRecoveryUnit(unittest.TestCase):
    def _rows(self):
        return [unit_row(
            "TREND", "BULLISH", i,
            rs={LIM: 2.0, MKT: -1.0, BRK: -1.0},
            base_r=None, base_filled=False, known=True,
            tokens={"atr_regime": "HIGH"}) for i in range(14)]

    def test_supported_recovery_and_retention(self):
        findings = recovery_probabilities(
            self._rows(), ALTS, min_n=6, n_hypotheses=1)
        self.assertEqual(len(findings), 3)
        by_alt = {f.alternative: f for f in findings}
        self.assertEqual(by_alt["LIMIT_RETEST"].status, RECOVERY_SUPPORTED)
        lim = by_alt["LIMIT_RETEST"]
        self.assertEqual(lim.regime, "TREND")
        self.assertEqual(lim.n, 14)
        self.assertEqual(lim.recovered, 14)
        self.assertEqual(lim.p_recovery, 1.0)
        self.assertEqual(lim.expected_r, 2.0)
        self.assertEqual(lim.expected_drawdown, 0.5)
        self.assertEqual(lim.loss_probability, 0.0)
        self.assertEqual(lim.min_n_gate, 7)
        for alt in ("MARKET_CONFIRMATION", "BREAKOUT_CONTINUATION"):
            self.assertEqual(by_alt[alt].status, RECOVERY_INCONCLUSIVE)

    def test_empty_pool(self):
        self.assertEqual(recovery_probabilities(
            [unit_row("TREND", "BULLISH", 0, base_filled=True)],
            ALTS, min_n=6), [])


class TestInteractionsUnit(unittest.TestCase):
    def _rows(self):
        rows = []
        for i in range(12):
            rows.append(unit_row(
                "TREND", "BULLISH", i, base_r=2.0,
                tokens={"wyckoff": "MARKUP", "atr_regime": "HIGH"}))
        for i in range(12):
            rows.append(unit_row(
                "TREND", "BULLISH", 50 + i, base_r=-1.0,
                tokens={"wyckoff": "ACCUMULATION", "atr_regime": "LOW"}))
        for i in range(4):
            rows.append(unit_row(
                "TREND", "BULLISH", 200 + i, base_r=2.0,
                tokens={"wyckoff": "MARKUP", "atr_regime": "HIGH"}))
        for i in range(4):
            rows.append(unit_row(
                "TREND", "BULLISH", 220 + i, base_r=-1.0,
                tokens={"wyckoff": "ACCUMULATION", "atr_regime": "LOW"}))
        return rows

    def test_supported_interaction_carries_to_oos(self):
        rows = self._rows()
        split = temporal_split(rows, 0.2, 0.2)
        findings = interaction_analysis(rows, split, ["TREND"],
                                        UNIT_GATES, n_hypotheses=1)
        supported = [f for f in findings
                     if f.status == INTERACTION_SUPPORTED]
        self.assertTrue(supported)
        best = max(supported, key=lambda f: f.n_train)
        self.assertEqual(best.regime, "TREND")
        self.assertEqual(best.features, ("atr_regime", "wyckoff"))
        self.assertEqual(best.n_train, 12)
        self.assertEqual(best.n_oos, 2)
        self.assertEqual(best.effect_d_train, 1.0)
        self.assertAlmostEqual(best.effect_d_oos, 1.4142, places=4)
        self.assertLess(best.p_value, 0.01)

    def test_no_combo_mixes_same_feature(self):
        rows = self._rows()
        split = temporal_split(rows, 0.2, 0.2)
        findings = interaction_analysis(rows, split, ["TREND"],
                                        UNIT_GATES, n_hypotheses=1)
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(len(set(f.features)), len(f.features))


class TestSymbolUnit(unittest.TestCase):
    def _rows(self):
        rows = []
        for i in range(18):
            rows.append(unit_row("TREND", "BULLISH", i, base_r=2.0, symbol="Z"))
        for i in range(18):
            rows.append(unit_row("RANGE", "NEUTRAL", 50 + i, base_r=-1.0,
                                 symbol="W"))
        return rows

    def test_symbol_justification_gated_by_delta(self):
        findings = symbol_behaviour(
            self._rows(), min_n=12, delta_r=0.5, n_hypotheses=1)
        by_key = {(s.symbol, s.regime): s for s in findings}
        z = by_key[("Z", "TREND")]
        self.assertTrue(z.justified)
        self.assertEqual(z.n, 18)
        self.assertEqual(z.global_avg_r, 0.5)
        self.assertEqual(z.delta_expectancy, 1.5)
        self.assertFalse(by_key[("W", "RANGE")].justified)


class TestTransitionUnit(unittest.TestCase):
    def _rows(self):
        rows = []
        for i in range(6):
            rows.append(unit_row("TREND", "BULLISH", i, base_filled=True,
                                 base_r=-1.0, filled="TREND"))
        for i in range(6):
            rows.append(unit_row("RANGE", "NEUTRAL", 50 + i,
                                 base_filled=True, base_r=-1.0,
                                 filled="RANGE"))
        for i in range(6):
            rows.append(unit_row("TREND", "BULLISH", 100 + i,
                                 base_filled=True, base_r=2.0,
                                 filled="RANGE"))
        return rows

    def test_changed_transition_and_stable_buckets(self):
        findings = transitions(self._rows(), min_n=3, delta_r=0.5)
        by_bucket = {(t.generated_regime, t.filled_regime): t
                     for t in findings}
        self.assertEqual(by_bucket[("TREND", "RANGE")].status,
                         TRANSITION_CHANGED)
        self.assertEqual(by_bucket[("TREND", "RANGE")].avg_r, 2.0)
        self.assertEqual(by_bucket[("TREND", "RANGE")].expectancy_delta_vs_stable,
                         3.0)
        self.assertEqual(by_bucket[("RANGE", "RANGE")].status,
                         TRANSITION_STABLE)
        self.assertEqual(by_bucket[("TREND", "TREND")].status,
                         TRANSITION_STABLE)


class TestEngineE2E(unittest.TestCase):
    def test_engine_end_to_end_overview(self):
        rep = e2e_run()
        ov = rep.overview()
        self.assertEqual(ov["report_id"], "Leb8e4313e7")
        self.assertEqual(ov["opportunities"], 54)
        self.assertEqual(ov["recovery_findings"], 6)
        self.assertEqual(ov["entry_selection_cells"], 2)
        self.assertEqual(ov["interaction_findings"], 0)
        self.assertEqual(ov["transition_buckets"], 2)
        self.assertEqual(ov["symbol_cells"], 3)
        self.assertEqual(ov["calibration_surfaces"], 3)
        self.assertEqual(ov["total_hypotheses"], 223)
        self.assertEqual(ov["corrected_alpha"], 0.00023)
        self.assertEqual(ov["n_survive_familywise"], 0)
        self.assertFalse(ov["is_production_ready"])

    def test_engine_recovery_surface(self):
        findings = e2e_run().recovery
        self.assertEqual(len(findings), 6)
        rows = [(f.alternative, f.regime, f.n, f.recovered, f.p_recovery)
                for f in findings]
        self.assertEqual(rows[0], ("LIMIT_RETEST", "RANGE", 19, 0, 0.0))
        self.assertEqual(rows[1], ("LIMIT_RETEST", "TREND", 6, 0, 0.0))
        self.assertEqual(rows[2], ("MARKET_CONFIRMATION", "RANGE", 19, 0, 0.0))
        self.assertEqual(rows[3], ("MARKET_CONFIRMATION", "TREND", 6, 0, 0.0))
        self.assertEqual(rows[4], ("BREAKOUT_CONTINUATION", "RANGE", 19, 0, 0.0))
        self.assertEqual(rows[5], ("BREAKOUT_CONTINUATION", "TREND", 6, 0, 0.0))
        for f in findings:
            self.assertEqual(f.status, RECOVERY_INCONCLUSIVE)
            self.assertEqual(f.min_n_gate, 14)
            self.assertFalse(f.survives_familywise)

    def test_engine_entry_selection_surface(self):
        cells = e2e_run().entry_selection
        self.assertEqual(len(cells), 2)
        self.assertEqual([c.cell_id for c in cells],
                         ["RANGE|BULLISH", "TREND|BULLISH"])
        for c in cells:
            self.assertIsNone(c.selected)
            self.assertEqual(c.status, ENTRY_SELECTION_INCONCLUSIVE)
            self.assertEqual(c.min_oos_n_gate, 13)
            self.assertFalse(c.survives_familywise)
        range_cell = cells[0]
        by_alt = {a.alternative: a for a in range_cell.alternatives}
        self.assertEqual(by_alt["LIMIT_RETEST"].n_train, 1)
        self.assertEqual(by_alt["LIMIT_RETEST"].n_oos, 9)
        self.assertEqual(by_alt["LIMIT_RETEST"].p_win_oos, 0.98)
        self.assertEqual(by_alt["LIMIT_RETEST"].expected_r_oos, 2.0)
        self.assertEqual(by_alt["LIMIT_RETEST"].delta_expectancy_oos, 0.0)
        self.assertIsNone(by_alt["LIMIT_RETEST"].p_two_sided)
        self.assertEqual(by_alt["MARKET_CONFIRMATION"].expected_r_oos, 0.0)
        self.assertEqual(by_alt["MARKET_CONFIRMATION"].delta_expectancy_oos, -2.0)
        trend_cell = cells[1]
        for a in trend_cell.alternatives:
            self.assertEqual(a.n_train, 10)
            self.assertEqual(a.n_oos, 0)
            self.assertIsNone(a.expected_r_oos)
            self.assertIsNone(a.delta_expectancy_oos)

    def test_engine_transitions_surface(self):
        findings = e2e_run().transitions
        rows = [(t.generated_regime, t.filled_regime, t.n, t.avg_r)
                for t in findings]
        self.assertEqual(rows[0], ("RANGE", "RANGE", 19, 2.0))
        self.assertEqual(rows[1], ("TREND", "TREND", 10, -1.0))
        self.assertEqual(findings[0].status, TRANSITION_STABLE)
        self.assertEqual(findings[1].status, TRANSITION_STABLE)

    def test_engine_symbol_surface(self):
        findings = e2e_run().symbols
        rows = [(s.symbol, s.regime, s.n, s.avg_r, s.justified)
                for s in findings]
        self.assertEqual(rows[0], ("X", "RANGE", 10, 2.0, False))
        self.assertEqual(rows[1], ("X", "TREND", 10, -1.0, False))
        self.assertEqual(rows[2], ("Y", "RANGE", 9, 2.0, False))

    def test_engine_calibration_surface(self):
        surfaces = e2e_run().calibration
        self.assertEqual(len(surfaces), 3)
        by_surf = {c.surface: c for c in surfaces}
        for alt in ("LIMIT_RETEST", "MARKET_CONFIRMATION",
                    "BREAKOUT_CONTINUATION"):
            c = by_surf["WIN:" + alt]
            self.assertEqual(c.status, CALIBRATION_GAP)
            self.assertEqual(c.oos_n, 9)
            self.assertEqual(c.ece, 0.02)
            self.assertEqual(c.brier, 0.0004)
            self.assertIsNone(c.slope)
            self.assertEqual(c.min_n_gate, 10)

    def test_engine_multiple_testing_and_robustness(self):
        rep = e2e_run()
        mt = rep.multiple_testing
        self.assertEqual(mt["total_hypotheses"], 223)
        self.assertEqual(mt["alpha"], 0.05)
        self.assertEqual(mt["corrected_alpha"], 0.00023)
        self.assertEqual(mt["n_survive"], 0)
        self.assertIn("sidak_global", mt["method"])
        self.assertEqual(rep.robustness["pipeline"],
                         ("generate", "filter", "temporal_split",
                          "conditional_probability", "recovery",
                          "entry_selection", "interactions",
                          "transitions", "symbols", "calibration",
                          "multiple_testing", "robustness",
                          "economic_significance", "minimum_sample",
                          "limitations"))
        self.assertEqual(rep.robustness["alternatives_grid"], ALTS)
        self.assertTrue(rep.robustness["fixed_grid"])
        self.assertEqual(rep.robustness["combinatorial_cap"], 100)
        self.assertEqual(rep.robustness["survives_global_familywise"], 0)
        split = rep.robustness["chronological_split"]
        self.assertEqual((split["train_size"], split["validation_size"],
                          split["oos_size"]), (32, 11, 11))
        self.assertTrue(split["no_shuffle"])
        self.assertTrue(split["no_temporal_leakage"])

    def test_engine_limitations_never_hidden(self):
        limitations = e2e_run().limitations
        self.assertTrue(limitations)
        self.assertIn("is_production_ready is permanently False", limitations)

    def test_engine_per_surface_present_equal_counts(self):
        rep = e2e_run()
        self.assertEqual(len(rep.recovery), 6)
        self.assertEqual(len(rep.entry_selection), 2)
        self.assertEqual(len(rep.transitions), 2)
        self.assertEqual(len(rep.symbols), 3)
        self.assertEqual(len(rep.calibration), 3)


class TestEngineGuarantees(unittest.TestCase):
    def test_byte_repeatable_determinism(self):
        a = e2e_run()
        b = e2e_run()
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.render(), b.render())
        self.assertEqual(a.report_id, b.report_id)

    def test_decision_time_only_no_lookahead(self):
        base = e2e_run(SERIES)
        future = e2e_run(divergent_future_series())
        self.assertEqual(base.to_dict(), future.to_dict())

    def test_report_is_frozen(self):
        rep = e2e_run()
        with self.assertRaises(FrozenInstanceError):
            rep.is_production_ready = True

    def test_production_ready_raises(self):
        with self.assertRaises(ValueError):
            ConditionalMlReport(is_production_ready=True)
        self.assertFalse(ConditionalMlReport().is_production_ready)
        self.assertTrue(ConditionalMlReport().research_only)

    def test_emission_check_is_clean(self):
        result = e2e_run().emission_check()
        self.assertTrue(result["clean"])
        self.assertEqual(list(result["never_emitted"]), list(NEVER_EMITTED))
        self.assertEqual(result["present"], [])

    def test_empty_inputs_honest_report(self):
        rep = ConditionalMlEngine().run([], [])
        self.assertEqual(len(rep.recovery), 0)
        self.assertEqual(len(rep.entry_selection), 0)
        self.assertEqual(len(rep.interactions), 0)
        self.assertEqual(len(rep.transitions), 0)
        self.assertEqual(len(rep.symbols), 0)
        self.assertTrue(rep.limitations)
        self.assertFalse(rep.is_production_ready)
        self.assertTrue(rep.emission_check()["clean"])

    def test_report_render_contains_fixed_grid(self):
        text = e2e_run().render()
        self.assertIn("LIMIT_RETEST", text)
        self.assertIn("NEVER production-ready", text)
        self.assertIn("Recovery probability", text)
        self.assertIn("Entry-model selection", text)
        self.assertIn("Regime transitions", text)
        self.assertIn("Symbol segmentation", text)
        self.assertIn("Confidence / calibration", text)
        self.assertIn("emission_check", text)


class TestBoundaries(unittest.TestCase):
    _FORBIDDEN_MODULES = (
        "scipy", "sklearn", "pandas", "torch", "random", "uuid",
        "datetime", "core.quant", "core.execution", "core.strategies",
        "core.broker",
    )

    def test_no_production_or_forbidden_imports(self):
        pkg = os.path.join(
            os.path.dirname(__file__), os.pardir,
            "core", "research", "conditional_ml")
        pkg = os.path.normpath(pkg)
        sources = []
        for root, _, files in os.walk(pkg):
            for name in files:
                if name.endswith(".py"):
                    sources.append(os.path.join(root, name))
        self.assertTrue(sources)
        for path in sources:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            imports = re.findall(
                r"^\s*(?:import\s+([\w\.,\s]+)|from\s+([\w\.]+)\s+import\s+.+)$",
                text, re.MULTILINE)
            for a, b in imports:
                clause = (a or "").strip() + (b or "")
                for module in clause.replace(",", " ") \
                        .replace(" as ", " ") \
                        .split():
                    head = module.split(".")[0]
                    if head == "core":
                        self.assertTrue(
                            module.startswith("core.research."),
                            "%s imports outside core.research.*: %r"
                            % (path, module))
                    else:
                        self.assertNotIn(
                            head, self._FORBIDDEN_MODULES,
                            "%s imports forbidden %r" % (path, head))

    def test_promotion_tokens_absent_from_report_body(self):
        import json
        rep = e2e_run()
        body = json.dumps(rep.to_dict(), sort_keys=True)
        for tok in NEVER_EMITTED:
            self.assertNotIn(tok, body)


if __name__ == "__main__":
    unittest.main(verbosity=2)