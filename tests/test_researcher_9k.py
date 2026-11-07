"""
====================================================================

QuantEngine

Phase 9K -- Regime / Conditional Opportunity Discovery tests

Proves the deterministic, research-only "under-which-conditions"
engine over the frozen 9A-9J layers:

   * indicators: every regime indicator is pure, decision-time,
     data-gated and closed-vocabulary (never invents a label, returns
     UNAVAILABLE on thin windows);
   * detector/segmenter: MarketRegime windows END at the decision bar
     (no lookahead -- identical decision bar on two divergent futures
     yields byte-identical regimes), closed vocabulary validation,
     honest empty-regime handling;
   * conditional: strict 9B candidate vocabulary (loud failure on
     unsupported axes), candidate-vs-frozen-baseline INSIDE every
     regime cell, recoveries, delta and split breadth; every cell and
     finding retained (INCONCLUSIVE / NOT_SUPPORTED included) -- no
     hiding of negative results;
   * walk-forward: chronological expanding-train / trailing-test
     validation, no shuffle, majority-of-adequate-windows survival
     with a minimum validation sample;
   * multiple-testing: Sidak familywise correction + sample
     requirement that grows with the number of tested hypotheses;
   * engine/report: deterministic byte-repeatable RegimeReport
     (frozen, NEVER production-ready, emission-check clean), honest
     empty-dataset limitations, robustness coverage;
   * end-to-end: a realistic synthetic trend/range candle series where
     an ATR-stop candidate beats the frozen baseline inside TREND
     (fixed stop gets stopped out on a pullback that the ATR stop
     survives) and loses inside RANGE (wider stop bleeds against
     smaller targets) -- yielding a genuine CONDITIONAL finding with
     the split -- plus the exact expected cell economics (+2.0 vs
     -1.0 in trend, -1.0 vs +2.0 in range, split breadth 6.0);
   * boundaries: no production imports, no randomness/uuid/datetime,
     no auto-promotion tokens, ConditionalFinding can never be a
     production directive.

Uses ONLY the real 9A-9I machinery and genuine counterfactual
simulation. Stdlib only; offline; deterministic.
====================================================================
"""

import math
import os
import re
import sys
import unittest
from dataclasses import FrozenInstanceError

from core.research.journal import OpportunityRecord
from core.research.researcher import DEFAULT_BASE_CONFIG
from core.research.dataset import (
    ResearchDataset,
    ResearchRow,
    DatasetSource,
)
from core.research.regime import (
    TREND,
    RANGE,
    BULLISH,
    BEARISH,
    NEUTRAL,
    HIGH,
    NORMAL,
    LOW,
    EXPANSION,
    CONTRACTION,
    STRONG,
    ABSENT,
    SWEEPED,
    PRESENT,
    MARKUP,
    MARKDOWN,
    UNAVAILABLE,
    REGIME_DIMENSIONS,
    PRIMARY_REGIME_DIMENSIONS,
    MarketRegime,
    RegimeObservation,
    ConditionalCell,
    ConditionalFinding,
    FeatureSplit,
    WalkForwardWindow,
    WalkForwardSummary,
    trend_vs_range,
    direction_structure,
    volatility_regime,
    atr_regime,
    displacement_strength,
    liquidity,
    fvg,
    order_block,
    wyckoff_phase,
    detect_regime,
    regime_dimensions,
    primary_regime_dimensions,
    dimension_vocabulary,
    validate_dimension,
    segment_observations,
    decision_bar,
    in_cell,
    cell_labels,
    regime_coverage,
    by_category,
    conditional_discovery,
    feature_splits,
    temporal_windows,
    validate_conditional,
    sidak_alpha,
    required_min_n,
    multiple_testing_summary,
    OpportunityDiscoveryEngine,
    RegimeReport,
)
from core.research.discovery.constants import NEVER_EMITTED
from core.research.regime.regime_types import short_id, stable_json

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REGIME_DIR = os.path.join(_REPO, "core", "research", "regime")


# ==================================================================
# Fixtures
# ==================================================================

class _C:
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open, self.high, self.low = o, h, l
        self.close, self.timestamp = c, ts


def build_split_series():
    """Synthetic trend/range series carrying the 9K e2e fixture.

    Phase A (bars 14..57): a rising ramp that stays below the entry
    trigger (close < 100) so BREAKOUT fills happen ONLY on the shared
    trigger bar 54 (fill bar 55 at open 100), then a pullback to 96
    (kills the frozen 98 stop) and a rally to 114 (hits the ATR-stop
    candidate's 112 target). Regime windows ending at bars 44..53 are
    TREND.
    Phase B (bars 65..129): an oscillating narrow band below the entry
    trigger until the shared trigger bar 113 (fill 114 at open 100,
    baseline 104 target hit) followed by a crash to 92 (breaches the
    ATR stop at 94). Regime windows ending at bars 108..112 are RANGE.
    """
    bars = [_C(94.0, 94.5, 93.5, 94.0, i) for i in range(130)]
    for i in range(14, 54):
        c = 95.0 + (i - 14) * 0.125
        bars[i] = _C(c, c + 0.5, c - 0.6, c, i)
    bars[54] = _C(100.0, 103.0, 99.0, 105.0, 54)
    bars[55] = _C(100.0, 102.0, 99.5, 102.0, 55)
    bars[56] = _C(102.0, 102.6, 96.0, 101.0, 56)
    bars[57] = _C(100.0, 114.0, 100.0, 113.0, 57)
    for i in range(58, 65):
        c = 99.3 + (i - 58) * 0.1
        bars[i] = _C(c, c + 0.5, c - 0.6, c, i)
    seed = 99.2
    for i in range(65, 130):
        if i in (113, 114, 115):
            continue
        seed = seed + (0.3 if i % 2 else -0.3)
        seed = max(98.5, min(99.9, seed))
        bars[i] = _C(seed - 0.5, seed + 0.75, seed - 0.75, seed, i)
    bars[113] = _C(100.0, 103.0, 99.0, 104.0, 113)
    bars[114] = _C(100.0, 104.5, 99.5, 104.0, 114)
    bars[115] = _C(104.0, 105.0, 92.0, 101.0, 115)
    return bars


SPLIT_SERIES = build_split_series()


def _mk_record(i, decision, result="WIN", r=0.5, symbol="X"):
    """One filled 9A opportunity record (BREAKOUT_CONTINUATION,
    bull 100/98/104, rr 2, ATR 4)."""
    trade = {
        "result": result,
        "pnl": 2.0,
        "risk_amount": 4.0,
        "entry_bar": decision + 2,
        "exit_bar": decision + 2,
        "bars_held": 1,
        "r": r,
        "exit_price": 104.0,
    }
    return OpportunityRecord(
        canonical_id="r-%s-%02d" % (symbol, i),
        exchange="TESTEX",
        instrument_id=symbol,
        timeframe="1m",
        direction="BULLISH",
        strategy="BREAKOUT_CONTINUATION",
        setup_id="r-%s-%02d" % (symbol, i),
        setup={
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "risk_reward": 2.0,
            "bar": decision,
            "atr": 4.0,
            "rejection_reasons": [],
        },
        order={},
        trade=trade,
        terminal_outcome="FILLED_CLOSED",
    )


def split_records():
    """10 TREND decisions (bars 44..53) + 5 RANGE decisions
    (bars 108..112)."""
    return [_mk_record(i, 44 + i) for i in range(10)] + \
        [_mk_record(i, 108 + (i - 10)) for i in range(10, 15)]


def engine(min_cell_n=5):
    return OpportunityDiscoveryEngine(
        candles=SPLIT_SERIES, min_cell_n=min_cell_n)


def _atr_stop_candidate():
    return [{"stop_mode": "ATR"}]


# ==================================================================
# Indicator unit tests
# ==================================================================

class TrendVsRangeTests(unittest.TestCase):
    def test_steep_ramp_is_trend(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, 0)]
        for i in range(1, 40):
            c = 100.0 + 0.25 * i
            pts.append(_C(c, c + 1.0, c - 1.0, c, i))
        self.assertEqual(trend_vs_range(pts), TREND)

    def test_flat_band_is_range(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(40)]
        self.assertEqual(trend_vs_range(pts), RANGE)

    def test_short_window_is_unavailable(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(10)]
        self.assertIs(trend_vs_range(pts), UNAVAILABLE)

    def test_empty_window_is_unavailable(self):
        self.assertIs(trend_vs_range([]), UNAVAILABLE)

    def test_deterministic(self):
        pts = [_C(100.0 + 0.25 * i, 101.0 + 0.25 * i,
                  99.0 + 0.25 * i, 100.0 + 0.25 * i, i)
               for i in range(40)]
        self.assertEqual(trend_vs_range(pts), trend_vs_range(list(pts)))


class DirectionStructureTests(unittest.TestCase):
    def _series(self, ascending):
        # 14 bars with genuine local peaks/lows; the last two peak highs
        # and the last two trough lows are what the indicator reads.
        if ascending:
            rows = [
                (100.0, 101.0, 99.0, 100.0),
                (100.0, 102.0, 100.0, 101.0),
                (101.0, 101.5, 99.0, 99.5),
                (99.5, 100.0, 98.0, 98.5),
                (98.5, 100.5, 98.5, 100.0),
                (100.0, 103.0, 100.0, 101.5),
                (101.5, 102.0, 99.0, 99.5),
                (99.5, 100.0, 97.5, 98.0),
                (98.0, 101.0, 98.0, 100.0),
                (100.0, 104.0, 99.0, 102.0),
                (102.0, 102.5, 100.0, 100.5),
                (100.5, 101.0, 98.0, 98.5),
                (98.5, 102.0, 98.0, 101.0),
                (101.0, 105.0, 100.0, 103.0),
            ]
        else:
            rows = [
                (100.0, 105.0, 100.0, 103.0),
                (103.0, 104.0, 101.0, 101.5),
                (101.5, 102.0, 99.0, 99.5),
                (99.5, 101.0, 98.0, 99.0),
                (99.0, 105.0, 99.0, 103.0),
                (103.0, 103.5, 100.0, 100.5),
                (100.5, 101.0, 98.0, 98.5),
                (98.5, 103.0, 98.0, 101.0),
                (101.0, 102.0, 99.0, 99.5),
                (99.5, 100.5, 97.0, 98.0),
                (98.0, 102.0, 98.0, 100.0),
                (100.0, 101.0, 98.0, 98.5),
                (98.5, 101.0, 97.5, 98.0),
                (98.0, 100.5, 97.0, 98.5),
            ]
        return [_C(*r, i) for i, r in enumerate(rows)]

    def test_rising_peaks_and_lows_bullish(self):
        self.assertEqual(direction_structure(self._series(True)), BULLISH)

    def test_falling_peaks_and_lows_bearish(self):
        self.assertEqual(direction_structure(self._series(False)), BEARISH)

    def test_short_window_unavailable(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(6)]
        self.assertIs(direction_structure(pts), UNAVAILABLE)


class VolatilityRegimeTests(unittest.TestCase):
    def _pts(self, older_closes, recent_closes):
        pts = []
        for i, c in enumerate(older_closes + recent_closes):
            pts.append(_C(c, c + 1.0, c - 1.0, c, i))
        return pts

    def test_high(self):
        older = [100.0 + (0.2 if i % 2 else -0.2) for i in range(20)]
        recent = [100.0 + (4.0 if i % 2 else -4.0) for i in range(20)]
        self.assertEqual(volatility_regime(self._pts(older, recent)), HIGH)

    def test_low(self):
        older = [100.0 + (4.0 if i % 2 else -4.0) for i in range(20)]
        recent = [100.0 + (0.2 if i % 2 else -0.2) for i in range(20)]
        self.assertEqual(volatility_regime(self._pts(older, recent)), LOW)

    def test_normal(self):
        older = [100.0 + (2.0 if i % 2 else -2.0) for i in range(20)]
        recent = [100.0 + (2.5 if i % 2 else -2.5) for i in range(20)]
        self.assertEqual(volatility_regime(self._pts(older, recent)), NORMAL)

    def test_short_window_unavailable(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(10)]
        self.assertIs(volatility_regime(pts), UNAVAILABLE)


class AtrRegimeTests(unittest.TestCase):
    def _pts(self, first, second):
        pts = []
        for i in range(14):
            pts.append(_C(100.0, 100.0 + first, 100.0 - first, 100.0, i))
        for i in range(16):
            pts.append(_C(100.0, 100.0 + second, 100.0 - second, 100.0, i))
        return pts

    def test_expansion(self):
        self.assertEqual(atr_regime(self._pts(0.5, 4.0)), EXPANSION)

    def test_contraction(self):
        self.assertEqual(atr_regime(self._pts(4.0, 0.5)), CONTRACTION)

    def test_neutral(self):
        self.assertEqual(atr_regime(self._pts(2.0, 2.4)), NEUTRAL)

    def test_short_window_unavailable(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(8)]
        self.assertIs(atr_regime(pts), UNAVAILABLE)


class DisplacementTests(unittest.TestCase):
    def test_strong_bullish_body(self):
        pts = [_C(100.0, 104.0, 99.0, 103.9, i) for i in range(4)]
        self.assertEqual(displacement_strength(pts, BULLISH), STRONG)

    def test_absent_small_bodies(self):
        pts = [_C(100.0, 100.5, 99.5, 100.2, i) for i in range(4)]
        self.assertEqual(displacement_strength(pts, BULLISH), ABSENT)

    def test_unavailable_without_direction(self):
        pts = [_C(100.0, 104.0, 99.0, 103.9, i) for i in range(4)]
        self.assertIs(displacement_strength(pts, None), UNAVAILABLE)
        self.assertIs(displacement_strength(pts, "SIDEWAYS"), UNAVAILABLE)

    def test_bearish_body_detected(self):
        pts = [_C(103.9, 104.0, 99.0, 100.1, i) for i in range(4)]
        self.assertEqual(displacement_strength(pts, BEARISH), STRONG)


class LiquidityTests(unittest.TestCase):
    def test_bull_sweep_reclaimed(self):
        pts = [_C(101.0, 101.5, 99.0, 101.2, i) for i in range(6)]
        self.assertEqual(liquidity(pts, BULLISH, 100.0), SWEEPED)

    def test_swept_not_reclaimed(self):
        pts = [_C(101.0, 101.5, 99.0, 99.8, i) for i in range(6)]
        self.assertEqual(liquidity(pts, BULLISH, 100.0), NORMAL)

    def test_no_breach_normal(self):
        pts = [_C(101.0, 101.5, 100.5, 101.2, i) for i in range(6)]
        self.assertEqual(liquidity(pts, BULLISH, 100.0), NORMAL)

    def test_unavailable_without_stop(self):
        pts = [_C(101.0, 101.5, 100.5, 101.2, i) for i in range(6)]
        self.assertIs(liquidity(pts, BULLISH, None), UNAVAILABLE)

    def test_bearish_sweep(self):
        pts = [_C(99.0, 101.0, 98.5, 99.2, i) for i in range(6)]
        self.assertEqual(liquidity(pts, BEARISH, 100.0), SWEEPED)


class FvgTests(unittest.TestCase):
    def test_bullish_gap_present(self):
        pts = [_C(99.0, 100.0, 98.5, 99.9, 0),
               _C(100.0, 101.0, 99.0, 100.0, 1),
               _C(102.0, 103.0, 101.5, 102.5, 2),
               _C(102.5, 103.5, 102.0, 103.0, 3)]
        self.assertEqual(fvg(pts, BULLISH), PRESENT)

    def test_no_gap_absent(self):
        pts = [_C(99.0, 100.0, 98.5, 99.9, i) for i in range(4)]
        self.assertEqual(fvg(pts, BULLISH), ABSENT)

    def test_unavailable_short(self):
        pts = [_C(99.0, 100.0, 98.5, 99.9, i) for i in range(2)]
        self.assertIs(fvg(pts, BULLISH), UNAVAILABLE)

    def test_bearish_gap_present(self):
        pts = [_C(102.0, 103.0, 101.5, 102.5, 0),
               _C(102.0, 102.0, 101.0, 101.5, 1),
               _C(99.0, 100.0, 98.5, 99.5, 2),
               _C(100.0, 101.0, 99.5, 100.5, 3)]
        self.assertEqual(fvg(pts, BEARISH), PRESENT)


class OrderBlockTests(unittest.TestCase):
    def test_breakout_present(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(6)]
        pts.append(_C(100.5, 103.0, 100.0, 102.5, 6))
        pts.append(_C(102.5, 103.5, 102.0, 103.0, 7))
        self.assertEqual(order_block(pts), PRESENT)

    def test_no_breakout_absent(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(8)]
        self.assertEqual(order_block(pts), ABSENT)

    def test_short_window_unavailable(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(4)]
        self.assertIs(order_block(pts), UNAVAILABLE)


class WyckoffPhaseTests(unittest.TestCase):
    def test_markup(self):
        pts = [_C(100.0 + 0.4 * i, 101.0 + 0.4 * i, 99.0 + 0.4 * i,
                  100.0 + 0.4 * i, i) for i in range(50)]
        self.assertEqual(wyckoff_phase(pts), MARKUP)

    def test_markdown(self):
        pts = [_C(200.0 - 0.4 * i, 201.0 - 0.4 * i, 199.0 - 0.4 * i,
                  200.0 - 0.4 * i, i) for i in range(50)]
        self.assertEqual(wyckoff_phase(pts), MARKDOWN)

    def test_short_window_unavailable(self):
        pts = [_C(100.0, 101.0, 99.0, 100.0, i) for i in range(20)]
        self.assertIs(wyckoff_phase(pts), UNAVAILABLE)


class IndicatorVocabularyTests(unittest.TestCase):
    def test_source_has_no_production_imports(self):
        forbidden = (
            "core.execution", "core.trading", "core.ledger",
            "core.account", "core.portfolio", "core.risk",
            "core.market_data", "core.pipeline", "core.setup",
        )
        for name in os.listdir(_REGIME_DIR):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(_REGIME_DIR, name),
                      encoding="utf-8") as fh:
                src = fh.read()
            for tok in forbidden:
                self.assertNotIn(tok, src, "...%s" % name)

    def test_source_has_no_random_wrongness(self):
        forbidden_modules = {
            "random", "uuid", "datetime", "time", "sklearn", "scipy",
        }
        forbidden_prefix = (
            "core.execution", "core.trading", "core.ledger",
            "core.account", "core.portfolio", "core.risk",
            "core.market_data", "core.pipeline", "core.setup",
        )
        for name in os.listdir(_REGIME_DIR):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(_REGIME_DIR, name),
                      encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line.startswith("import ") and not \
                            line.startswith("from "):
                        continue
                    for tok in forbidden_modules:
                        self.assertNotIn(
                            " %s" % tok, " %s" % line,
                            "%s:%d uses %s" % (name, lineno, tok))
                    for mod in re.split(r"[ ,]", line.replace(
                            "import", " ").replace("from", " ")):
                        if not mod or mod.startswith("."):
                            continue
                        for pref in forbidden_prefix:
                            self.assertFalse(
                                mod.startswith(pref),
                                "%s:%d imports %s" % (name, lineno, mod))


# ==================================================================
# Detector tests
# ==================================================================

class DetectorTests(unittest.TestCase):
    def test_trend_windows(self):
        for d in range(44, 54):
            self.assertEqual(
                detect_regime(SPLIT_SERIES, d).available()["trend_vs_range"],
                TREND)

    def test_range_windows(self):
        for d in range(108, 113):
            self.assertEqual(
                detect_regime(SPLIT_SERIES, d).available()["trend_vs_range"],
                RANGE)

    def test_early_windows_never_fabricate(self):
        for d in (0, 1, 2, 3):
            mr = detect_regime(SPLIT_SERIES, d)
            self.assertEqual(mr.available(), {})

    def test_empty_candles_safe(self):
        mr = detect_regime([], 5)
        self.assertEqual(mr.available(), {})

    def test_no_lookahead(self):
        # Future absolutely identical up through the decision bar; the
        # regime label may only depend on that prefix.
        prefix = list(SPLIT_SERIES[:56])
        crash_future = list(SPLIT_SERIES)
        calm_future = list(SPLIT_SERIES)
        for i in range(56, 130):
            crash_future[i] = _C(60.0, 61.0, 59.0, 60.0, i)
            calm_future[i] = _C(99.0, 100.0, 98.0, 99.0, i)
        a = detect_regime(prefix, 53)
        b = detect_regime(crash_future, 53)
        c = detect_regime(calm_future, 53)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.to_dict(), c.to_dict())
        self.assertEqual(a.available()["trend_vs_range"], TREND)

    def test_market_regime_available_only(self):
        mr = detect_regime(SPLIT_SERIES, 50)
        d = mr.available()
        for dim in REGIME_DIMENSIONS:
            if dim in d:
                self.assertIsNot(d[dim], UNAVAILABLE)

    def test_closed_vocabulary(self):
        vocab = dimension_vocabulary()
        self.assertEqual(set(vocab), set(REGIME_DIMENSIONS))
        for dim, labels in vocab.items():
            self.assertIsInstance(labels, tuple)
            self.assertTrue(labels)
            validate_dimension(dim)

    def test_primary_dimensions(self):
        self.assertEqual(PRIMARY_REGIME_DIMENSIONS, primary_regime_dimensions())
        self.assertTrue(set(PRIMARY_REGIME_DIMENSIONS) <= set(REGIME_DIMENSIONS))

    def test_validate_dimension(self):
        with self.assertRaises(ValueError):
            validate_dimension("not_a_regime_dimension")
        for dim in ("trend_vs_range", "liquidity"):
            vocabulary = dimension_vocabulary()[dim]
            self.assertTrue(vocabulary)
            validate_dimension(dim)


# ==================================================================
# Segmenter tests
# ==================================================================

class SegmenterTests(unittest.TestCase):
    def _obs(self):
        return segment_observations(split_records(), SPLIT_SERIES)

    def test_segmentation_counts(self):
        obs = self._obs()
        self.assertEqual(len(obs), 15)
        labels = cell_labels(obs, "trend_vs_range")
        self.assertEqual(labels, ("RANGE", "TREND"))
        self.assertEqual(len(in_cell(obs, "trend_vs_range", TREND)), 10)
        self.assertEqual(len(in_cell(obs, "trend_vs_range", RANGE)), 5)

    def test_observation_fields(self):
        o = segment_observations(
            [_mk_record(0, 44)], SPLIT_SERIES)[0]
        self.assertEqual(o.observation_id, "r-X-00")
        self.assertEqual(o.decision_bar, 44)
        self.assertEqual(o.direction, "BULLISH")
        self.assertEqual(o.symbol, "X")
        self.assertEqual(o.result, "WIN")
        self.assertEqual(o.r, 0.5)
        self.assertEqual(o.source, "JOURNAL")
        self.assertEqual(o.regime["trend_vs_range"], TREND)

    def test_no_decision_bar_honest(self):
        rec = _mk_record(0, 0)
        rec = OpportunityRecord(
            canonical_id="r-X-00", exchange="TESTEX",
            instrument_id="X", timeframe="1m", direction="BULLISH",
            strategy="BREAKOUT_CONTINUATION", setup_id="r-X-00",
            setup={}, order={}, trade={}, terminal_outcome="FILLED_CLOSED")
        o = segment_observations([rec], SPLIT_SERIES)[0]
        self.assertEqual(o.regime, {})
        self.assertEqual(o.decision_bar, None)

    def test_decision_bar_prefers_filled(self):
        rec = OpportunityRecord(
            canonical_id="r-X-00", exchange="TESTEX",
            instrument_id="X", timeframe="1m", direction="BULLISH",
            strategy="BREAKOUT_CONTINUATION", setup_id="r-X-00",
            setup={"bar": 3}, order={"filled_bar": 7}, trade={},
            terminal_outcome="FILLED_CLOSED")
        self.assertEqual(decision_bar(rec), 7)
        self.assertIsNone(decision_bar(
            OpportunityRecord(
                canonical_id="r-X-01", exchange="TESTEX",
                instrument_id="X", timeframe="1m", direction="BULLISH",
                strategy="S", setup_id="s", setup={}, order={}, trade={},
                terminal_outcome="")))

    def test_observed_result_normalisation(self):
        from core.research.regime.segmenter import observed_result, observed_r
        rec = _mk_record(0, 44, result="lost", r=None)
        self.assertEqual(observed_result(rec), "")
        win = _mk_record(1, 44, result="WIN", r=1.25)
        self.assertEqual(observed_result(win), "WIN")
        self.assertEqual(observed_r(win), 1.25)
        self.assertIsNone(observed_r(_mk_record(2, 44, r=None)))

    def test_regime_coverage_and_categories(self):
        obs = self._obs()
        cov = regime_coverage(obs)
        self.assertEqual(cov["observations"], 15)
        self.assertEqual(cov["trend_vs_range"]["available"], 15)
        self.assertIsInstance(cov["displacement"]["rate"], float)
        cats = by_category(obs)
        self.assertEqual(sum(cats.values()), 15)
        self.assertEqual(list(cats.keys()), sorted(cats.keys()))

    def test_deterministic(self):
        a = segment_observations(split_records(), SPLIT_SERIES)
        b = segment_observations(split_records(), list(SPLIT_SERIES))
        self.assertEqual(
            [o.to_dict() for o in a], [o.to_dict() for o in b])

    def test_regime_observation_frozen(self):
        o = self._obs()[0]
        with self.assertRaises(FrozenInstanceError):
            o.result = "LOSS"


# ==================================================================
# Conditional discovery tests
# ==================================================================

class ConditionalTests(unittest.TestCase):
    def _obs(self):
        return segment_observations(split_records(), SPLIT_SERIES)

    def test_split_fixture_cells_exact(self):
        obs = self._obs()
        cells, _ = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        by = {(c.dimension, c.label): c for c in cells}
        trend = by[("trend_vs_range", TREND)]
        self.assertEqual(trend.n, 10)
        self.assertEqual(trend.wins, 10)
        self.assertEqual(trend.expectancy, 2.0)
        self.assertEqual(trend.baseline_expectancy, -1.0)
        self.assertEqual(trend.delta_expectancy, 3.0)
        self.assertEqual(trend.recovered, 10)
        rng = by[("trend_vs_range", RANGE)]
        self.assertEqual(rng.n, 5)
        self.assertEqual(rng.expectancy, -1.0)
        self.assertEqual(rng.baseline_expectancy, 2.0)
        self.assertEqual(rng.delta_expectancy, -3.0)
        self.assertEqual(rng.recovered, 0)

    def test_conditional_and_not_supported_findings(self):
        obs = self._obs()
        _, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        by = {(f.dimension, f.label): f for f in findings}
        trend = by[("trend_vs_range", TREND)]
        self.assertEqual(trend.status, "CONDITIONAL")
        self.assertEqual(trend.within_expectancy, 2.0)
        self.assertEqual(trend.global_expectancy, 1.0)
        self.assertEqual(round(trend.delta, 6), 1.0)
        self.assertEqual(trend.split_breadth, 6.0)
        rng = by[("trend_vs_range", RANGE)]
        self.assertEqual(rng.status, "NOT_SUPPORTED")
        self.assertEqual(rng.within_expectancy, -1.0)

    def test_every_regime_label_cell_retained(self):
        obs = self._obs()
        cells, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        by_cell = {(c.dimension, c.label) for c in cells}
        for label in (TREND, RANGE):
            self.assertIn(("trend_vs_range", label), by_cell)
        by_finding = {(f.dimension, f.label) for f in findings}
        for label in (TREND, RANGE):
            self.assertIn(("trend_vs_range", label), by_finding)

    def test_min_sample_gate_makes_inconclusive_not_hidden(self):
        obs = self._obs()
        _, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=12)
        by = {(f.dimension, f.label): f for f in findings}
        self.assertEqual(by[("trend_vs_range", TREND)].status, "INCONCLUSIVE")
        self.assertIn("below the minimum-sample", by[("trend_vs_range", TREND)].min_sample_note)

    def test_default_gate_rejects_small_population(self):
        records = [_mk_record(i, 44 + i) for i in range(6)]
        obs = segment_observations(records, SPLIT_SERIES)
        _, findings = conditional_discovery(
            records, SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs)
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f.status, "INCONCLUSIVE")

    def test_loud_failure_on_unknown_axis(self):
        obs = self._obs()
        with self.assertRaises(ValueError):
            conditional_discovery(
                split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
                [{"not_a_real_axis": 7}], obs, min_cell_n=5)

    def test_loud_failure_on_unsupported_entry_model(self):
        obs = self._obs()
        with self.assertRaises(ValueError):
            conditional_discovery(
                split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
                [{"entry_model": "MADE_UP_MODEL"}], obs, min_cell_n=5)

    def test_invalid_module_never_survives(self):
        obs = self._obs()
        _, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        for f in findings:
            self.assertFalse(f.is_production_directive)
            for tok in NEVER_EMITTED:
                self.assertNotIn(tok, f.statement)

    def test_finding_id_deterministic_and_prefixed(self):
        obs = self._obs()
        _, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        f = [x for x in findings if (x.dimension, x.label) ==
             ("trend_vs_range", TREND)][0]
        self.assertTrue(f.finding_id.startswith("K"))
        _, findings2 = conditional_discovery(
            split_records(), list(SPLIT_SERIES), DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        f2 = [x for x in findings2 if (x.dimension, x.label) ==
              ("trend_vs_range", TREND)][0]
        self.assertEqual(f.finding_id, f2.finding_id)
        want = short_id("K", "conditional", "trend_vs_range",
                        TREND, f.config_id, "CONDITIONAL")
        self.assertEqual(f.finding_id, want)

    def test_finding_cannot_be_production_directive(self):
        with self.assertRaises(ValueError):
            ConditionalFinding(
                dimension="trend_vs_range", label=TREND,
                config_id="c", config_params={},
                within_expectancy=1.0, global_expectancy=0.5,
                delta=0.5, cell_n=10, status="CONDITIONAL",
                split_breadth=1.0, min_sample_note="",
                statement="", is_production_directive=True)

    def test_cell_frozen(self):
        obs = self._obs()
        cells, _ = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        with self.assertRaises(FrozenInstanceError):
            cells[0].n = 7


# ==================================================================
# Feature-split tests
# ==================================================================

class FeatureSplitTests(unittest.TestCase):
    def _obs(self):
        # 6 WIN + 4 LOSS observations with decision bars in the trend
        # region (labels exist; only results feed the split anyway).
        records = [_mk_record(i, 44 + i, result="WIN", r=1.0)
                   for i in range(6)] + \
            [_mk_record(i, 44 + (i - 6), result="LOSS", r=-1.0)
             for i in range(6, 10)]
        obs = segment_observations(records, SPLIT_SERIES)
        return obs

    def test_groups_gated_and_computed(self):
        obs = self._obs()
        dataset = ResearchDataset(rows=[
            ResearchRow(source=DatasetSource.FEATURE,
                        observation_id="r-X-%02d" % i, kv={"mfi_state": "HIGH"})
            for i in range(6)
        ] + [
            ResearchRow(source=DatasetSource.FEATURE,
                        observation_id="r-X-%02d" % i, kv={"mfi_state": "MID"})
            for i in range(6, 10)
        ] + [
            ResearchRow(source=DatasetSource.FEATURE,
                        observation_id="r-X-99",
                        kv={"mfi_state": "LONE"})
        ])
        splits = feature_splits(dataset, obs, min_n_gate=5)
        by = {(s.feature, s.value): s for s in splits}
        high = by[("mfi_state", "HIGH")]
        self.assertEqual(high.n, 6)
        self.assertEqual(high.win_rate, 1.0)
        self.assertEqual(high.avg_r, 1.0)
        self.assertEqual(high.overall_win_rate, 0.6)
        self.assertGreater(high.effect_h, 0)
        self.assertEqual(high.min_n_gate, 5)
        self.assertNotIn(("mfi_state", "MID"), by)
        self.assertNotIn(("mfi_state", "LONE"), by)

    def test_none_dataset_honest(self):
        self.assertEqual(feature_splits(None, self._obs()), ())

    def test_unknown_observation_skipped(self):
        dataset = ResearchDataset(rows=[
            ResearchRow(source=DatasetSource.FEATURE,
                        observation_id="does-not-exist",
                        kv={"mfi_state": "HIGH"})
        ])
        self.assertEqual(feature_splits(dataset, self._obs()), ())


# ==================================================================
# Walk-forward tests
# ==================================================================

class WalkForwardTests(unittest.TestCase):
    def _obs(self):
        return segment_observations(split_records(), SPLIT_SERIES)

    def test_temporal_windows_chronological_no_shuffle(self):
        windows = temporal_windows(self._obs(), 3)
        self.assertEqual(len(windows), 2)
        for w in windows:
            bars = []
            for g in ("train", "validate"):
                bars.extend(o.decision_bar for o in w[g])
            self.assertEqual(bars, sorted(bars))
            self.assertLess(
                max(o.decision_bar for o in w["train"]),
                min(o.decision_bar for o in w["validate"]))

    def test_too_few_observations_empty(self):
        self.assertEqual(temporal_windows([], 3), ())
        small = segment_observations(
            [_mk_record(i, 44 + i) for i in range(5)], SPLIT_SERIES)
        self.assertEqual(temporal_windows(small, 3), ())

    def test_trend_finding_survives(self):
        obs = self._obs()
        _, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        f = [x for x in findings if (x.dimension, x.label) ==
             ("trend_vs_range", TREND) and x.status == "CONDITIONAL"][0]
        summ = validate_conditional(
            f, obs, split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            n_windows=3, min_validation_n=3)
        self.assertTrue(summ.survived)
        self.assertTrue(summ.no_shuffle)
        self.assertTrue(summ.chronological)
        self.assertEqual(summ.validation_n, 5)
        first = summ.windows[0]
        self.assertEqual(first.validation_n, 5)
        self.assertEqual(first.validation_expectancy, 2.0)
        self.assertEqual(first.validation_delta, 3.0)

    def test_thin_validation_windows_counted(self):
        obs = self._obs()
        _, findings = conditional_discovery(
            split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            _atr_stop_candidate(), obs, min_cell_n=5)
        f = [x for x in findings if (x.dimension, x.label) ==
             ("trend_vs_range", TREND)][0]
        summ = validate_conditional(
            f, obs, split_records(), SPLIT_SERIES, DEFAULT_BASE_CONFIG,
            n_windows=3, min_validation_n=3)
        self.assertEqual(len(summ.windows), 2)
        self.assertEqual(summ.windows[1].validation_n, 0)
        self.assertLess(summ.windows[1].survived, True)
        self.assertIn("below", summ.windows[1].note)

    def test_empty_population_survive_false(self):
        f = ConditionalFinding(
            dimension="trend_vs_range", label=TREND, config_id="c",
            config_params={"stop_mode": "ATR"}, within_expectancy=1.0,
            global_expectancy=0.5, delta=0.5, cell_n=0,
            status="CONDITIONAL", split_breadth=1.0,
            min_sample_note="", statement="")
        summ = validate_conditional(
            f, [], [], SPLIT_SERIES, DEFAULT_BASE_CONFIG)
        self.assertFalse(summ.survived)
        self.assertIn("too small", summ.windows[0].note)

    def test_engine_runs_walk_forward_only_for_material(self):
        rep = engine().run(
            split_records(), DEFAULT_BASE_CONFIG, _atr_stop_candidate(),
            symbol="X")
        wf = rep.walk_forward
        self.assertTrue(wf)
        rid = [f.finding_id for f in rep.findings
               if (f.dimension, f.label) == ("trend_vs_range", TREND)][0]
        self.assertIn(rid, wf)
        self.assertTrue(wf[rid]["survived"])
        rng_id = [f.finding_id for f in rep.findings
                  if (f.dimension, f.label) == ("trend_vs_range", RANGE)][0]
        self.assertNotIn(rng_id, wf)
        for fid, summ in wf.items():
            self.assertIn(fid, {f.finding_id for f in rep.findings
                                if f.status in ("CONDITIONAL",
                                                "CONDITIONAL_WEAK")})


# ==================================================================
# Multiple-testing tests
# ==================================================================

class MultipleTestingTests(unittest.TestCase):
    def test_sidak_math(self):
        self.assertEqual(sidak_alpha(0.05, 0), 0.05)
        self.assertAlmostEqual(sidak_alpha(0.05, 1), 0.05, places=12)
        self.assertAlmostEqual(sidak_alpha(0.05, 2),
                               1.0 - math.sqrt(0.95), places=12)
        self.assertLess(sidak_alpha(0.05, 10), 0.05)

    def test_required_min_n_math(self):
        self.assertEqual(required_min_n(10, 0), 10)
        self.assertEqual(required_min_n(10, 1), 11)
        self.assertEqual(required_min_n(10, 3), 12)
        self.assertEqual(required_min_n(10, 7), 13)

    def test_e2e_guard(self):
        rep = engine().run(
            split_records(), DEFAULT_BASE_CONFIG, _atr_stop_candidate(),
            symbol="X")
        mt = rep.multiple_testing
        self.assertEqual(mt["n_hypotheses_tested"], 5)
        self.assertEqual(mt["alpha"], 0.05)
        self.assertEqual(mt["required_min_n"],
                         required_min_n(5, mt["n_hypotheses_tested"]))
        self.assertEqual(mt["n_survive"], 1)
        surv_id = [f.finding_id for f in rep.findings
                   if (f.dimension, f.label) == ("trend_vs_range", TREND)][0]
        rng_id = [f.finding_id for f in rep.findings
                  if (f.dimension, f.label) == ("trend_vs_range", RANGE)][0]
        self.assertTrue(mt["per_finding"][surv_id]["survives"])
        self.assertFalse(mt["per_finding"][rng_id]["survives"])

    def test_every_finding_retained_in_guard(self):
        rep = engine().run(
            split_records(), DEFAULT_BASE_CONFIG, _atr_stop_candidate(),
            symbol="X")
        ids = {f.finding_id for f in rep.findings}
        self.assertEqual(set(rep.multiple_testing["per_finding"]), ids)


# ==================================================================
# Engine / report tests
# ==================================================================

class EngineTests(unittest.TestCase):
    def _run(self, **kw):
        e = engine(**kw)
        return e.run(split_records(), DEFAULT_BASE_CONFIG,
                     _atr_stop_candidate(), symbol="X")

    def test_end_to_end_conditional_report(self):
        rep = self._run()
        self.assertTrue(rep.report_id.startswith("K"))
        self.assertEqual(rep.phase, "9K")
        self.assertEqual(rep.dataset_shape["observations"], 15)
        labels = {f.label for f in rep.findings if f.dimension ==
                  "trend_vs_range"}
        self.assertEqual(labels, {TREND, RANGE})
        statuses = {(f.dimension, f.label, f.status) for f in rep.findings
                    if f.dimension == "trend_vs_range"}
        self.assertIn(("trend_vs_range", TREND, "CONDITIONAL"), statuses)
        self.assertIn(("trend_vs_range", RANGE, "NOT_SUPPORTED"), statuses)
        self.assertEqual(rep.multiple_testing["n_survive"], 1)

    def test_repeatable_byte_identical(self):
        a = self._run().to_dict()
        b = self._run().to_dict()
        self.assertEqual(a, b)
        self.assertEqual(stable_json(a), stable_json(b))

    def test_report_frozen_and_never_production_ready(self):
        rep = self._run()
        with self.assertRaises(FrozenInstanceError):
            rep.symbol = "Y"
        self.assertFalse(rep.is_production_ready)
        self.assertTrue(rep.research_only)
        with self.assertRaises(ValueError):
            RegimeReport(is_production_ready=True)

    def test_emission_check_clean(self):
        rep = self._run()
        check = rep.emission_check()
        self.assertTrue(check["clean"])
        self.assertEqual(check["present"], [])

    def test_availability_contract(self):
        av = OpportunityDiscoveryEngine.availability()
        self.assertEqual(av["phase"], "9K")
        self.assertFalse(av["requires_external_sdk"])
        self.assertEqual(av["never_emits"], list(NEVER_EMITTED))
        self.assertTrue(av["research_only"])

    def test_robustness_coverage(self):
        rep = self._run()
        self.assertEqual(rep.robustness["directions"], ["BULLISH"])
        self.assertEqual(rep.robustness["symbols"], ["X"])
        f = [f for f in rep.findings
             if (f.dimension, f.label) == ("trend_vs_range", TREND)][0]
        cov = rep.robustness["per_finding_coverage"][f.finding_id]
        self.assertEqual(cov["n"], 10)
        self.assertEqual(cov["directions"]["BULLISH"], 10)

    def test_empty_dataset_honest(self):
        rep = engine().run([], DEFAULT_BASE_CONFIG, _atr_stop_candidate(),
                           symbol="X")
        self.assertEqual(rep.dataset_shape["observations"], 0)
        self.assertEqual(rep.cells, ())
        self.assertEqual(rep.findings, ())
        joined = "\n".join(rep.limitations)
        self.assertIn("no regime cells", joined)

    def test_no_records_no_candidates_safe(self):
        rep = engine().run([], DEFAULT_BASE_CONFIG, [], symbol="X")
        self.assertEqual(rep.dataset_shape["observations"], 0)
        self.assertFalse(rep.report_id == "")

    def test_render_notes_research_only(self):
        text = self._run().render()
        self.assertIn("NEVER production-ready", text)
        self.assertIn("emission_check", text)
        self.assertIn("stop_mode=ATR", text)

    def test_import_boundary_no_production_modules(self):
        before = set(sys.modules)
        import core.research.regime  # noqa: F401
        loaded = set(sys.modules) - before
        for name in loaded:
            self.assertNotIn(
                name.split(".")[1],
                {"execution", "trading", "ledger", "account",
                 "portfolio", "risk", "market_data", "pipeline", "setup"},
                "regime package pulled in %s" % name)


class ReportTypeTests(unittest.TestCase):
    def test_walk_forward_window_to_dict(self):
        w = WalkForwardWindow(
            window_index=0, dimension="trend_vs_range", label=TREND,
            config_id="c", train_n=5, train_expectancy=1.0,
            validation_n=5, validation_expectancy=2.0,
            validation_delta=3.0, survived=True, note="ok")
        d = w.to_dict()
        self.assertEqual(d["survived"], True)
        self.assertEqual(d["validation_n"], 5)

    def test_summary_validation_count(self):
        s = WalkForwardSummary(survived=True, windows=(
            WalkForwardWindow(0, "trend_vs_range", TREND, "c", 5, 1.0,
                              5, 2.0, 3.0, True, ""),
            WalkForwardWindow(1, "trend_vs_range", TREND, "c", 10, 1.0,
                              0, None, None, False, "thin"),
        ))
        self.assertEqual(s.validation_n, 5)
        self.assertIn("no_shuffle", s.to_dict())

    def test_feature_split_to_dict(self):
        s = FeatureSplit(feature="mfi_state", value="HIGH", n=6,
                         win_rate=1.0, avg_r=1.0, overall_win_rate=0.6,
                         effect_h=0.7, min_n_gate=5)
        d = s.to_dict()
        self.assertEqual(d["feature"], "mfi_state")
        self.assertEqual(d["n"], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)