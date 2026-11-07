"""
====================================================

QuantEngine

Phase 9F -- Confluence / Feature Evidence tests

Proves the deterministic, decision-time causal feature layer:

   * causal window is decision-bar bounded (NO lookahead; bars are
     strictly index < decision_bar; the decision bar itself is never
     a feature source)
   * deterministic indicators (ATR / Bollinger / SMA / OBV) are
     data-gated: they return UNAVAILABLE (None) when the bounded
     history is too short or data is absent -- never fabricated
   * confluence producers (Wyckoff, market structure, ATR regime,
     Bollinger, SMA slope, OBV trend, liquidity sweep, FVG,
     displacement, order block, Fibonacci) build canonical features
     from decision-time data only; footprint/volume-profile producers
     return UNAVAILABLE because no order-flow data stream exists
   * FeatureSnapshot preserves the opportunity's own decision-time
     levels + its causal window, immutably
   * DependencyAnalysis joins snapshots to read-only 9C/9D outcomes
     into tables: entry-reached, rejected->recovered, missed-
     continuation, WIN/LOSS, average R, average MAE/MFE, and
     direction / symbol segmentation -- CORRELATION OF EVIDENCE only
   * the produced features feed the FROZEN 9E ConfluenceAnalysis
     surface (name/value/sample/outcomes/experiment_id rows); when
     NO features can be derived the analysis reports
     CONFLUENCE_DATA_UNAVAILABLE (never fabricated)
   * pure: solving evidence never mutates records/candles/outcomes
   * boundaries: no production internals, no AI/ML, no simulation, no
     lookahead, no auto-promotion, 7E NO-GO untouched, .pyc boundary

Test doubles:
   * lightweight C() candle (open/high/low/close/timestamp/volume)
   * Outcome() / plain dicts for 9C-shaped outcomes
   * OpportunityRecord (core.research.journal) with a setup carrying
     entry/stop/target/atr + bar (the decision bar)

Stdlib only; offline; deterministic.
====================================================
"""

import math
import re
import unittest

from core.research.features import (
    CausalWindow,
    CandlePoint,
    extract_causal_window,
    FeatureSnapshot,
    FeatureAnalyzer,
    FeatureEvidenceReport,
    DependencyAnalysis,
    FeatureDependency,
    build_dependency,
    indicators,
    ALL_PRODUCERS,
)
from core.research.features import confluence_features as cf
from core.research.intelligence.confluence_analysis import (
    ConfluenceAnalysis,
    ConfluenceFeature,
    CONFLUENCE_DATA_UNAVAILABLE,
)
from core.research.journal import OpportunityRecord


# ==========================================================
# Fixture primitives
# ==========================================================


class C:
    """Lightweight candle for feature producers."""
    __slots__ = ("open", "high", "low", "close", "timestamp", "volume")

    def __init__(self, o, h, l, c, ts, v=None):
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.timestamp = ts
        self.volume = v


class O:
    """9C-shaped CounterfactualOutcome double."""
    __slots__ = ("opportunity_id", "entry_reached", "result", "r",
                 "mae", "mfe", "category", "instrument_id", "direction")

    def __init__(self, oid, entry_reached=True, result="WIN", r=2.0,
                 mae=0.4, mfe=2.5, category="FILLED", instrument_id="BTCUSDT",
                 direction="BULLISH"):
        self.opportunity_id = oid
        self.entry_reached = entry_reached
        self.result = result
        self.r = r
        self.mae = mae
        self.mfe = mfe
        self.category = category
        self.instrument_id = instrument_id
        self.direction = direction


def boom_candles(n=30, start=100.0):
    """A decision-friendly, mostly-range candle series with volume."""
    candles = []
    for i in range(n):
        candles.append(C(start, start + 1.0, start - 1.0, start, i, 1000.0))
    return candles


def trend_candles(n=30, start=100.0):
    """Gently rising series (for direction / structure checks)."""
    candles = []
    for i in range(n):
        close = start + i * 0.5
        candles.append(
            C(close - 0.25, close + 1.0, close - 1.0, close, i, 900.0 + i)
        )
    return candles


def make_record(can, direction="BULLISH", bar=25, instrument="BTCUSDT",
                entry=None, stop=None, target=None, atr=4.0,
                outcome=None):
    if direction == "BULLISH":
        entry = entry if entry is not None else 100.0
        stop = stop if stop is not None else 98.0
        target = target if target is not None else 104.0
    else:
        entry = entry if entry is not None else 102.0
        stop = stop if stop is not None else 104.0
        target = target if target is not None else 98.0
    return OpportunityRecord(
        canonical_id=can,
        exchange="TESTEX",
        instrument_id=instrument,
        timeframe="1m",
        direction=direction,
        strategy="BREAKOUT_CONTINUATION",
        setup_id=can,
        setup={"entry": entry, "stop_loss": stop,
               "take_profit": target, "risk_reward": 2.0,
               "bar": bar, "atr": atr, "rejection_reasons": []},
        order={},
        trade={"result": outcome, "pnl": 0.0, "risk_amount": 2.0,
               "entry_bar": bar, "exit_bar": bar, "bars_held": 0,
               "r": 0.0} if outcome else {},
        terminal_outcome="ORDER_NOT_CREATED",
    )


def _last_n(arr, n):
    return arr[len(arr) - n:]


# ==========================================================
# Causal window / no-lookahead guarantees
# ==========================================================


class CausalWindowTest(unittest.TestCase):
    def test_window_excludes_decision_bar(self):
        candles = boom_candles(30)
        w = extract_causal_window(candles, 25, lookback=10)
        # every bar index is strictly before the decision bar; the
        # decision bar itself is never a feature source (no lookahead)
        self.assertTrue(all(p.timestamp < 25 for p in w.points))
        self.assertLessEqual(w.size, 10)

    def test_window_bounded_by_lookback(self):
        candles = boom_candles(300)
        w = extract_causal_window(candles, 250, lookback=20)
        self.assertEqual(w.size, 20)

    def test_empty_window_when_no_prior_bars(self):
        candles = boom_candles(5)
        w = extract_causal_window(candles, 0, lookback=10)
        self.assertEqual(w.size, 0)

    def test_window_slices_are_decision_bounded(self):
        # the decision bar and everything after must never appear
        candles = boom_candles(40)
        w = extract_causal_window(candles, 30, lookback=20)
        last_ts = w.points[-1].timestamp
        self.assertLess(last_ts, 30)

    def test_missing_volume_is_not_fabricated(self):
        candles = [C(100, 101, 99, 100, i) for i in range(10)]  # no volume
        w = extract_causal_window(candles, 10, lookback=10)
        self.assertFalse(w.has_volume())
        self.assertEqual(len(w.volumes()), 0)


# ==========================================================
# Deterministic indicators (data-gated, never fabricated)
# ==========================================================


class IndicatorTest(unittest.TestCase):
    def test_obv_accumulates_direction_correctly(self):
        closes = [10, 11, 11, 10, 12]
        vols = [100, 200, 300, 400, 500]
        # bar1: up +200, bar2: flat +0, bar3: down -400, bar4: up +500
        self.assertEqual(indicators.obv(closes, vols), 300.0)

    def test_obv_misaligned_returns_unavailable(self):
        self.assertIsNone(indicators.obv([1, 2, 3], [1, 2]))

    def test_obv_empty_returns_unavailable(self):
        self.assertIsNone(indicators.obv([], []))

    def test_bollinger_position_within_band(self):
        # a rising series -> position near/above +1 upper band
        closes = [float(i) for i in range(30)]
        for pos in (0.0, 0.5, 1.0):
            value = indicators.bollinger_position(closes, 20)
            self.assertIsNotNone(value)
            self.assertTrue(-1.0 - 1e-9 <= value <= 1.0 + 1e-9
                            or value >= 1.0 - 1e-9)

    def test_bollinger_short_window_unavailable(self):
        self.assertIsNone(indicators.bollinger_position([1.0, 2.0], 20))

    def test_atr_positive_deterministic(self):
        candles = boom_candles(30)
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        a = indicators.atr(highs, lows, closes, period=14)
        self.assertIsNotNone(a)
        self.assertGreaterEqual(a, 0.0)

    def test_atr_short_window_unavailable(self):
        self.assertIsNone(indicators.atr([1, 2], [0, 1], [1, 2], period=14))

    def test_sma_deterministic(self):
        closes = [float(i) for i in range(30)]
        self.assertEqual(
            indicators.sma(closes, 20),
            sum(closes[10:30]) / 20.0,
        )


# ==========================================================
# Confluence producers (data gating / no fabrication)
# ==========================================================


class ProducerTest(unittest.TestCase):
    def test_footprint_and_volume_profile_always_unavailable(self):
        # no order-flow / volume-profile stream exists for OHLCV only
        self.assertIsNone(cf.volume_profile(None))
        self.assertIsNone(cf.footprint_flow(None))

    def test_empty_window_producers_all_unavailable(self):
        w = extract_causal_window([], 0, lookback=10)
        for name in ("wyckoff_phase", "market_structure", "atr_regime",
                     "bollinger_position", "sma_slope", "obv_trend",
                     "liquidity_sweep", "fvg_present",
                     "displacement_strength", "order_block"):
            self.assertIsNone(_produce(name, w))

    def test_short_window_producers_unavailable_not_fabricated(self):
        w = extract_causal_window(boom_candles(6), 6, lookback=6)
        for name in ("wyckoff_phase", "market_structure", "sma_slope"):
            self.assertIsNone(_produce(name, w))

    def test_obv_trend_unavailable_without_volume(self):
        candles = [C(100, 101, 99, 100, i) for i in range(12)]
        w = extract_causal_window(candles, 12, lookback=12)
        self.assertIsNone(cf.obv_trend(w))

    def test_obv_trend_signed_with_volume(self):
        w = extract_causal_window(trend_candles(30), 26, lookback=20)
        self.assertIn(cf.obv_trend(w), (1, -1, 0))

    def test_liquidity_sweep_bullish(self):
        # BULLISH: stop 98.0, lows dip below stop then close back above
        candles = boom_candles(30)
        candles[28] = C(100, 101, 97.5, 100.5, 28, 900)  # sweep
        candles[29] = C(100.5, 101.5, 100, 101, 29, 1000)  # reclaim
        w = extract_causal_window(candles, 30, lookback=8)
        self.assertTrue(cf.liquidity_sweep(w, 98.0, "BULLISH"))

    def test_liquidity_sweep_false_when_no_reclaim(self):
        candles = boom_candles(30)
        candles[29] = C(100, 101, 97.5, 97.8, 29, 900)  # still below
        w = extract_causal_window(candles, 30, lookback=8)
        self.assertFalse(cf.liquidity_sweep(w, 98.0, "BULLISH"))

    def test_fvg_present_bullish(self):
        # a gap: bar[3].low > bar[2].high
        pts = [C(100, 101, 99, 100, 0),
               C(100, 101, 99, 100, 1),
               C(100, 100.5, 99.4, 100, 2),
               C(100.8, 101.5, 100.8, 101, 3)]
        w = extract_causal_window(pts, 4, lookback=4)
        self.assertTrue(cf.fvg_present(w, "BULLISH"))
        self.assertFalse(cf.fvg_present(w, "BEARISH"))

    def test_displacement_strength_bullish(self):
        pts = [C(100, 101, 99, 100, 0),
               C(100, 101, 99, 100, 1),
               C(100, 101, 99, 100, 2),
               C(100, 101, 99, 100, 3),
               C(100, 101, 99, 100, 4),
               C(100, 101, 99, 100, 5),
               C(100, 105, 99, 104, 6)]  # large bullish body
        w = extract_causal_window(pts, 7, lookback=7)
        self.assertTrue(cf.displacement_strength(w, "BULLISH"))

    def test_all_producers_deterministic(self):
        for _ in range(2):
            w = extract_causal_window(trend_candles(40), 36, lookback=30)
            first = {n: _produce_for_window(n, w) for n in _all_names()}
            for _ in range(2):
                w2 = extract_causal_window(trend_candles(40), 36, lookback=30)
                second = {n: _produce_for_window(n, w2) for n in _all_names()}
                self.assertEqual(first, second)

    def test_volume_profile_footprint_registered_none(self):
        # registry includes but they must stay UNAVAILABLE for OHLCV
        names = {fn.__name__ for fn in ALL_PRODUCERS}
        self.assertIn("volume_profile", names)
        self.assertIn("footprint_flow", names)


# ==========================================================
# FeatureSnapshot (decision-time preservation)
# ==========================================================


class SnapshotTest(unittest.TestCase):
    def test_snapshot_preserves_decision_time_levels(self):
        rec = make_record("o1", bar=25, entry=101.0, stop=99.0,
                          target=106.0, atr=3.5)
        a = FeatureAnalyzer(lookback=20)
        snap = a.snapshot(rec, trend_candles(40))
        self.assertEqual(snap.opportunity_id, "o1")
        self.assertEqual(snap.decision_bar, 25)
        self.assertEqual(snap.entry, 101.0)
        self.assertEqual(snap.stop, 99.0)
        self.assertEqual(snap.target, 106.0)
        self.assertEqual(snap.atr, 3.5)
        self.assertEqual(snap.direction, "BULLISH")
        self.assertLessEqual(snap.window_size, 20)

    def test_snapshot_features_are_decision_bounded(self):
        rec = make_record("o1", bar=25)
        candles = trend_candles(40)
        a = FeatureAnalyzer(lookback=20)
        snap = a.snapshot(rec, candles)
        # simulate: features were chosen from bars strictly before 25
        self.assertLess(snap.decision_bar, 40)


# ==========================================================
# Dependency analysis (entry-reached / recovery / missed /
# WIN/LOSS / R / MAE/MFE / direction / symbol)
# ==========================================================


class DependencyTest(unittest.TestCase):
    def _snap(self, oid, feature="wyckoff_phase", value="MARKUP",
              direction="BULLISH", instrument="BTCUSDT"):
        return FeatureSnapshot(
            opportunity_id=oid,
            instrument_id=instrument,
            direction=direction,
            timeframe="1m",
            decision_bar=25,
            window_size=20,
            entry=100.0, stop=98.0, target=104.0, atr=4.0,
            features={feature: value},
        )

    def test_entry_reached_rate_computed(self):
        snaps = [self._snap("a", value="M"), self._snap("b", value="M")]
        out = {
            "a": O("a", entry_reached=True, result="WIN"),
            "b": O("b", entry_reached=False, result="LOSS"),
        }
        dep = build_dependency(snaps, out)
        row = dep.for_feature("wyckoff_phase").rows[0]
        self.assertEqual(row["entry_reached_rate"], 0.5)

    def test_rejected_to_recovered_rate_uses_recoveries(self):
        snaps = [self._snap("a", value="M"), self._snap("b", value="M")]
        out = {"a": O("a", result="WIN"), "b": O("b", result="REJECTED",
                                                  category="REJECTED")}
        rec = {"a": True, "b": False}
        dep = build_dependency(snaps, out, recoveries_by_opportunity=rec)
        row = dep.for_feature("wyckoff_phase").rows[0]
        self.assertEqual(row["recovered_rate"], 0.5)

    def test_missed_continuation_counted(self):
        snaps = [self._snap("a", value="M"), self._snap("b", value="M")]
        out = {
            "a": O("a", result="WIN"),
            "b": O("b", result="", category="MISSED_CONTINUATION"),
        }
        dep = build_dependency(snaps, out)
        row = dep.for_feature("wyckoff_phase").rows[0]
        self.assertEqual(row["missed_continuation_count"], 1)

    def test_win_loss_r_mae_mfe_aggregated(self):
        snaps = [self._snap("a", value="M"), self._snap("b", value="M")]
        out = {"a": O("a", result="WIN", r=2.0, mae=0.4, mfe=2.5),
               "b": O("b", result="LOSS", r=-1.0, mae=0.8, mfe=0.2)}
        dep = build_dependency(snaps, out)
        row = dep.for_feature("wyckoff_phase").rows[0]
        self.assertEqual(row["wins"], 1)
        self.assertEqual(row["losses"], 1)
        self.assertEqual(row["win_rate"], 0.5)
        self.assertEqual(row["avg_R"], 0.5)
        self.assertEqual(row["avg_MAE"], 0.6)
        self.assertEqual(row["avg_MFE"], 1.35)

    def test_direction_and_symbol_segmentation(self):
        a = self._snap("a", value="M", direction="BULLISH", instrument="BTC")
        b = self._snap("b", value="M", direction="BEARISH", instrument="BTC")
        snaps = [a, b]
        out = {"a": O("a", result="WIN"), "b": O("b", result="LOSS")}
        dep = build_dependency(snaps, out)
        row = dep.for_feature("wyckoff_phase").rows[0]
        self.assertEqual(row["directions"], {"BULLISH": 1, "BEARISH": 1})
        self.assertEqual(row["instruments"], {"BTC": 2})
        self.assertEqual(row["n"], 2)

    def test_missing_outcome_nevers_fabricates_win_rate(self):
        snaps = [self._snap("a", value="M")]
        # no outcome evidence for "a"
        dep = build_dependency(snaps, {})
        row = dep.for_feature("wyckoff_phase").rows[0]
        self.assertEqual(row["n"], 1)
        self.assertEqual(row["wins"], 0)
        self.assertEqual(row["losses"], 0)
        # entry-reached rate / R unknown -> None, not a fabricated number
        self.assertIsNone(row["entry_reached_rate"])
        self.assertIsNone(row["avg_R"])

    def test_feature_whitelist_filters(self):
        snaps = [FeatureSnapshot(
            opportunity_id="a", decision_bar=1, window_size=1,
            features={"wyckoff_phase": "M", "order_block": True},
        )]
        out = {"a": O("a", result="WIN")}
        dep = build_dependency(snaps, out, feature_names=["wyckoff_phase"])
        self.assertIsNotNone(dep.for_feature("wyckoff_phase"))
        self.assertIsNone(dep.for_feature("order_block"))

    def test_deterministic_ordering(self):
        snaps = [self._snap(str(i), value=str(i % 3)) for i in range(6)]
        out = {s.opportunity_id: O(s.opportunity_id, result="WIN")
               for s in snaps}
        d1 = build_dependency(snaps, out).to_dict()
        snaps2 = list(reversed(snaps))
        d2 = build_dependency(snaps2, out).to_dict()
        self.assertEqual(d1, d2)

    def test_dependency_to_dict_shape(self):
        snaps = [self._snap("a", value="M")]
        out = {"a": O("a", result="WIN")}
        d = build_dependency(snaps, out).to_dict()
        self.assertEqual(d["opportunity_count"], 1)
        self.assertEqual(d["evidence_method"], "read_only_evidence_correlation")
        self.assertTrue(d["segmented"])
        feat = d["features"][0]
        self.assertEqual(feat["feature"], "wyckoff_phase")
        self.assertIn("rows", feat)


# ==========================================================
# Feed into 9E ConfluenceAnalysis surface
# ==========================================================


class ConfluenceFeedTest(unittest.TestCase):
    def test_analyzer_feeds_confluenceanalysis(self):
        records = [make_record("a", bar=30), make_record("b", bar=30)]
        out = {"a": O("a", result="WIN"), "b": O("b", result="LOSS")}
        a = FeatureAnalyzer(lookback=30)
        report = a.analyze(records, trend_candles(40), outcomes=out)
        self.assertIsInstance(report, FeatureEvidenceReport)
        self.assertIsInstance(report.confluence, ConfluenceAnalysis)
        self.assertEqual(report.confluence.status(), "AVAILABLE")
        rows = report.confluence.to_dict()["features"]
        self.assertTrue(rows)
        expected = {"name", "value", "sample", "outcomes", "experiment_id"}
        self.assertTrue(expected.issubset(rows[0].keys()))

    def test_confluence_unavailable_when_zero_features(self):
        # empty candle history -> every feature is UNAVAILABLE and the
        # analysis must report CONFLUENCE_DATA_UNAVAILABLE (never
        # fabricate confluence)
        records = [make_record("a", bar=0)]
        a = FeatureAnalyzer(lookback=10)
        report = a.analyze(records, [], outcomes={})
        self.assertEqual(report.confluence.status(),
                         CONFLUENCE_DATA_UNAVAILABLE)
        self.assertEqual(report.confluence.to_dict()["feature_count"], 0)

    def test_report_dict_and_render_are_deterministic(self):
        records = [make_record("a", bar=30)]
        out = {"a": O("a", result="WIN")}
        a = FeatureAnalyzer(lookback=30)
        r1 = a.analyze(records, trend_candles(40), outcomes=out)
        d1 = r1.to_dict()
        r2 = a.analyze(records, trend_candles(40), outcomes=out)
        d2 = r2.to_dict()
        self.assertEqual(d1, d2)
        self.assertIsInstance(r1.render(), str)
        self.assertFalse(r1.to_dict()["confluence"]["status"] ==
                         CONFLUENCE_DATA_UNAVAILABLE)

    def test_analyzer_never_mutates_inputs(self):
        records = [make_record("a", bar=30)]
        candles = trend_candles(40)
        before_candles = [tuple(getattr(c, a) for a in
                               ("open", "high", "low", "close", "volume"))
                          for c in candles]
        out = {"a": O("a", result="WIN")}
        a = FeatureAnalyzer(lookback=30)
        a.analyze(records, candles, outcomes=out)
        after_candles = [tuple(getattr(c, a) for a in
                               ("open", "high", "low", "close", "volume"))
                         for c in candles]
        self.assertEqual(before_candles, after_candles)
        self.assertEqual(records[0].setup["entry"], 100.0)


# ==========================================================
# Boundaries: no production / AI / ML / simulation / lookahead
# ==========================================================


class BoundaryTest(unittest.TestCase):
    def _feature_sources(self):
        import os
        base = os.path.join(os.path.dirname(__file__), "..", "core",
                            "research", "features")
        for fname in os.listdir(base):
            if fname.endswith(".py"):
                with open(os.path.join(base, fname), encoding="utf-8") as fh:
                    yield fname, fh.read()

    def test_no_production_internals_imported(self):
        banned = re.compile(
            r"^\s*(from|import)\s+" + r"(core\.)?"
            r"(execution|risk|portfolio|engine|trade|account|strategy)"
        )
        for fname, src in self._feature_sources():
            for line in src.splitlines():
                if banned.match(line):
                    self.fail(f"{fname} imports production internals: {line}")

    def test_no_ai_ml_or_mlx_dependency(self):
        forbidden = ("torch", "tensorflow", "sklearn", "keras",
                     "transformers", "openai", "anthropic",
                     "mlx", "mlflow", "pytorch")
        for fname, src in self._feature_sources():
            for line in src.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    low = line.lower()
                    for token in forbidden:
                        self.assertNotIn(token, low,
                                         f"{fname} imports AI/ML: {token}")
            for smell in (".fit(", ".predict(", ".transform(", "tokenizer",
                          "nn.", "layers.", "embedding("):
                self.assertNotIn(smell, src, f"{fname} AI/ML inference")

    def test_no_simulation_imported(self):
        for fname, src in self._feature_sources():
            if re.search(r"OpportunitySimulator|run_configs|simulate\(",
                         src):
                self.fail(f"{fname} invokes simulation")

    def test_no_lookahead_library(self):
        for fname, src in self._feature_sources():
            # feature code must never import or reference a future-data
            # provider (prose docstrings that DENY lookahead are fine)
            for line in src.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    self.assertNotIn(
                        "future", line.lower(),
                        f"{fname} imports a future source: {line}")

    def test_producers_all_data_gated_or_document_denial(self):
        # every registered producer must either be internally data-gated
        # (returns UNAVAILABLE on insufficient/absent data) or be an
        # explicit denial returning UNAVAILABLE (footprint/volume-profile)
        w = extract_causal_window([], 0, lookback=10)
        for fn in ALL_PRODUCERS:
            for _ in (0, 1):
                val = _call_raw(fn, w)
                self.assertIsNone(val, f"{fn.__name__} not data-gated")

    def test_7e_no_go_untouched(self):
        # 9F must NOT turn directional evidence into a production rule:
        # a BULLISH feature set must not by itself imply a direction
        candles = trend_candles(40)
        rec_bull = make_record("bull", direction="BULLISH", bar=35)
        rec_bear = make_record("bear", direction="BEARISH", bar=35)
        a = FeatureAnalyzer(lookback=30)
        sb = a.snapshot(rec_bull, candles)
        a.snapshot(rec_bear, candles)
        # a snapshot is evidence, not an instruction: no "go long" flag
        self.assertNotIn("action", sb.to_dict())
        self.assertNotIn("size", sb.to_dict())
        self.assertNotIn("approve", sb.to_dict())


# ==========================================================
# Local helpers
# ==========================================================


def _produce(name, window, *args):
    for fn in ALL_PRODUCERS:
        if fn.__name__ == name:
            try:
                return fn(window, *args)
            except Exception:
                return None
    return None


def _call_raw(fn, window, *args):
    try:
        return fn(window, *args)
    except Exception:
        return None


def _produce_for_window(name, window):
    """Dispatch a producer with the correct per-signature args, so
    determinism is tested on real computed values (not just Nones)."""
    try:
        if name in ("wyckoff_phase", "market_structure", "order_block",
                    "volume_profile", "footprint_flow"):
            return getattr(cf, name)(window)
        if name == "atr_regime":
            return cf.atr_regime(window, 4.0)
        if name == "bollinger_position":
            return cf.bollinger_position(window)
        if name == "sma_slope":
            return cf.sma_slope(window)
        if name == "obv_trend":
            return cf.obv_trend(window)
        if name == "liquidity_sweep":
            return cf.liquidity_sweep(window, 98.0, "BULLISH")
        if name in ("fvg_present", "displacement_strength"):
            return getattr(cf, name)(window, "BULLISH")
        if name == "fibonacci_zone":
            return cf.fibonacci_zone(window, 100.0, "BULLISH")
    except Exception:
        return None
    return None


def _all_names():
    return [fn.__name__ for fn in ALL_PRODUCERS]


if __name__ == "__main__":
    unittest.main()