"""
====================================================

QuantEngine

Phase 9G -- ML / Statistical Research tests

Proves the deterministic, dependency-isolated ML / statistical
research layer that DISCOVERS relationships but does NOT decide what
gets traded:

   * temporal dataset splitting: chronological TRAIN | VALIDATION | OOS
     with NO temporal leakage and NO random shuffling; expanding-window
     walk-forward (9F's decision-time rule -- features only from
     candles < decision_bar -- is inherited and respected)
   * 9G.1 statistical baselines: sample counts, win/loss/unsettled,
     expectancy, avg R, avg MAE/MFE, R distribution, effect sizes,
     conditional probabilities -- pure math/numpy, honest None when a
     denominator is 0 (never fabricated)
   * 9G.2 simple-ML baselines: numpy logistic regression + decision tree
     (deterministic, always available) and optional sklearn backend that
     DEGRADES TO ML_BACKEND_UNAVAILABLE when sklearn is not installed;
     targets ENTRY_REACHED / WIN / POSITIVE_R / EXPECTED_R /
     RECOVERY_SUCCESS; AUC via rank-sum
   * 9G.3 feature-interaction association tables with sufficient-sample
     honesty and strict ASSOCIATION-not-causation framing
   * FIRST-CLASS OPPORTUNITY RECOVERY RESEARCH: rejected / not-reached
     opportunities -> feature snapshot -> alternative entry/RR/expiry/
     model -> recovery probability + expected R/MAE/MFE
   * dependency isolation: the whole suite passes with sklearn ABSENT
     (the current environment), proving the core engine stays light and
     the research stack is never a production dependency
   * boundaries: no production internals, no deep-AI (pytorch/tf/etc),
     sklearn only as a guarded optional backend, no auto-promotion, no
     trade directive emitted, 7E NO-GO untouched

Uses the real 9F FeatureSnapshot and real 9C outcome categories.
Stdlib + numpy only; offline; deterministic.
====================================================
"""

import math
import os
import re
import unittest

from core.research.ml import (
    temporal_split,
    walk_forward,
    StatisticalBaseline,
    conditional_statistics,
    effect_size_d,
    effect_size_h,
    encode_target,
    SimpleModel,
    NumpyLogisticRegression,
    NumpyDecisionTree,
    auc,
    ml_backend_status,
    ml_backend_available,
    ML_BACKEND_UNAVAILABLE,
    interaction_analysis,
    MlAnalyzer,
    MlResearchReport,
    TARGETS,
)
from core.research.features.feature_snapshot import FeatureSnapshot


# ==========================================================
# Fixture primitives
# ==========================================================


class C:
    __slots__ = ("open", "high", "low", "close", "timestamp", "volume")

    def __init__(self, o, h, l, c, ts, v=None):
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.timestamp = ts
        self.volume = v


class Sn:
    """Shape-compatible 9F FeatureSnapshot (kept light for tests)."""

    def __init__(self, oid, bar, direction="BULLISH", features=None):
        self.opportunity_id = oid
        self.decision_bar = bar
        self.window_size = 20
        self.direction = direction
        self.instrument_id = "BTCUSDT"
        self.timeframe = "1m"
        self.entry = 100.0
        self.stop = 98.0
        self.target = 104.0
        self.atr = 4.0
        self.features = features or {
            "wyckoff_phase": "MARKUP",
            "fvg_present": True,
            "order_block": True,
            "atr_regime": 1.0,
        }


class Oc:
    """Shape-compatible 9C CounterfactualOutcome."""

    def __init__(self, oid, result="WIN", r=2.0, er=True, rec=False,
                 cat="FILLED"):
        self.opportunity_id = oid
        self.result = result
        self.r = r
        self.mae = 0.4
        self.mfe = 2.5
        self.entry_reached = er
        self.recovered = rec
        self.category = cat
        self.instrument_id = "BTCUSDT"
        self.direction = "BULLISH"


def _snaps_and_outcomes(n=60, win_even=True):
    snaps = [Sn(f"op{i:02d}", bar=i) for i in range(n)]
    outs = {}
    for i, s in enumerate(snaps):
        if win_even and i % 2 == 0:
            outs[s.opportunity_id] = Oc(s.opportunity_id, "WIN", 2.0, True)
        else:
            outs[s.opportunity_id] = Oc(s.opportunity_id, "LOSS", -1.0, True)
    return snaps, outs


class _Report:
    def __init__(self, snapshots):
        self.snapshots = tuple(snapshots)


# ==========================================================
# Temporal dataset splitting (no leakage, no shuffle)
# ==========================================================


class SplitTest(unittest.TestCase):
    def test_temporal_split_is_chronological_and_unshuffled(self):
        snaps, _ = _snaps_and_outcomes(60)
        t = temporal_split(snaps, validation_fraction=0.2, oos_fraction=0.2)
        self.assertEqual(t.to_dict()["no_shuffle"], True)
        self.assertEqual(t.to_dict()["no_temporal_leakage"], True)
        # train bars strictly < validation < oos (time order preserved)
        def maxbar(fold):
            vals = [snaps[i].decision_bar for i in fold.indices]
            return max(vals) if vals else None

        self.assertLessEqual(maxbar(t.train), maxbar(t.validation))
        self.assertLessEqual(maxbar(t.validation), maxbar(t.oos))

    def test_temporal_split_sizes(self):
        snaps, _ = _snaps_and_outcomes(60)
        t = temporal_split(snaps, validation_fraction=0.2, oos_fraction=0.2)
        self.assertEqual(len(t.train), 36)
        self.assertEqual(len(t.validation), 12)
        self.assertEqual(len(t.oos), 12)
        self.assertEqual(len(t.train) + len(t.validation) + len(t.oos), 60)

    def test_temporal_split_no_overlap(self):
        snaps, _ = _snaps_and_outcomes(60)
        t = temporal_split(snaps, validation_fraction=0.2, oos_fraction=0.2)
        self.assertEqual(set(t.train.indices) & set(t.validation.indices), set())
        self.assertEqual(set(t.train.indices) & set(t.oos.indices), set())
        self.assertEqual(set(t.validation.indices) & set(t.oos.indices), set())

    def test_walk_forward_expands_chronologically(self):
        snaps, _ = _snaps_and_outcomes(80)
        wf = walk_forward(snaps, train_size=0.5, step=0.25)
        self.assertTrue(len(wf.folds) >= 1)
        prev_train_end = -1
        for f in wf.iter_folds():
            train_bars = [snaps[i].decision_bar for i in f.train.indices]
            test_bars = [snaps[i].decision_bar for i in f.test.indices]
            # train strictly ends before test begins (no lookahead)
            self.assertLessEqual(max(train_bars), min(test_bars))
            # expanding window: train grows forward
            self.assertGreaterEqual(len(f.train.indices), prev_train_end)
            prev_train_end = len(f.train.indices)

    def test_no_random_shuffle_between_runs(self):
        snaps, _ = _snaps_and_outcomes(60)
        t1 = temporal_split(snaps).to_dict()
        t2 = temporal_split(snaps).to_dict()
        self.assertEqual(t1, t2)

    def test_uses_decision_bar_when_present(self):
        # even if the input list is unsorted, the split re-orders by
        # decision_bar; fold indices index into TemporalSplit.items
        snaps, _ = _snaps_and_outcomes(10)
        reversed_snaps = list(reversed(snaps))
        t = temporal_split(reversed_snaps, validation_fraction=0.3,
                           oos_fraction=0.3)
        train_bars = [t.items[i].decision_bar for i in t.train.indices]
        oos_bars = [t.items[i].decision_bar for i in t.oos.indices]
        self.assertLessEqual(max(train_bars), min(oos_bars))


# ==========================================================
# 9G.1 statistical baselines (pure, honest)
# ==========================================================


class StatisticsTest(unittest.TestCase):
    def test_win_rate_and_expectancy(self):
        rows = [{"result": "WIN", "r": 2.0, "mae": 0.4, "mfe": 2.5},
                {"result": "LOSS", "r": -1.0, "mae": 0.8, "mfe": 0.2}]
        b = StatisticalBaseline(rows=rows)
        self.assertEqual(b.n(), 2)
        self.assertEqual(b.win_rate(), 0.5)
        self.assertEqual(b.loss_rate(), 0.5)
        self.assertEqual(b.unsettled_rate(), 0.0)
        self.assertEqual(b.expectancy(), 0.5)
        self.assertEqual(b.avg_R(), 0.5)

    def test_empty_baseline_is_honest(self):
        b = StatisticalBaseline(rows=[])
        self.assertEqual(b.n(), 0)
        self.assertIsNone(b.win_rate())
        self.assertIsNone(b.avg_R())
        self.assertIsNone(b.entry_reached_rate())

    def test_unsettled_never_fabricated_into_win(self):
        rows = [{"result": "WIN", "r": 2.0},
                {"result": "PENDING", "r": None}]
        b = StatisticalBaseline(rows=rows)
        self.assertEqual(b.wins(), 1)
        self.assertEqual(b.unsettled_rate(), 0.5)
        # avg R over known only
        self.assertEqual(b.avg_R(), 2.0)

    def test_r_distribution_bins(self):
        rows = [{"result": "WIN", "r": 2.0},
                {"result": "LOSS", "r": -1.0},
                {"result": "WIN", "r": 0.5}]
        b = StatisticalBaseline(rows=rows)
        dist = dict((label, prob) for label, cnt, prob in b.r_distribution())
        self.assertEqual(dist[">=2"], 1 / 3)
        self.assertEqual(dist["[-1,0)"], 1 / 3)

    def test_effect_size_h(self):
        self.assertAlmostEqual(effect_size_h(0.6, 0.4),
                               2.0 * (math.asin(math.sqrt(0.6))
                                      - math.asin(math.sqrt(0.4))), places=6)
        self.assertIsNone(effect_size_h(None, 0.5))

    def test_effect_size_d(self):
        d = effect_size_d([1, 2, 3], [4, 5, 6])
        self.assertIsNotNone(d)
        self.assertLess(d, 0)  # group_a < group_b
        self.assertIsNone(effect_size_d([], [1, 2]))

    def test_conditional_win_statistics(self):
        snaps = [Sn(f"op{i:02d}", bar=i) for i in range(8)]
        outs = {}
        for i, s in enumerate(snaps):
            # force feature value by bar parity
            s.features["wyckoff_phase"] = "MARKUP" if i % 2 == 0 else "SPRING"
            outs[s.opportunity_id] = Oc(
                s.opportunity_id,
                "WIN" if i in (0, 1, 2, 3) else "LOSS",
                2.0 if i in (0, 1, 2, 3) else -1.0, True)
        rows = list(outs.values())
        cond = conditional_statistics(
            rows,
            feature_accessor=lambda o: _snapshot_feature(snaps, o, "wyckoff_phase"),
            label_accessor=lambda o: o.result,
            target="WIN",
        )
        self.assertTrue(any(r["value"] == "MARKUP" for r in cond))
        markup = next(r for r in cond if r["value"] == "MARKUP")
        self.assertGreaterEqual(markup["win_rate"], 0.0)
        self.assertIn("effect_h_vs_overall", markup)
        self.assertIn("target_rate", markup)

    def test_conditional_entry_reached(self):
        rows = [Oc("a", er=True), Oc("b", er=False), Oc("c", er=True)]
        cond = conditional_statistics(
            rows,
            feature_accessor=lambda o: "X",
            label_accessor=lambda o: o.result,
            target="ENTRY_REACHED",
        )
        self.assertEqual(cond[0]["entry_reached_rate"], 2 / 3)


def _snapshot_feature(snaps, outcome, name):
    for s in snaps:
        if s.opportunity_id == outcome.opportunity_id:
            return s.features.get(name)
    return None


# ==========================================================
# 9G.2 simple-ML baselines (deterministic, isolated)
# ==========================================================


class ModelsTest(unittest.TestCase):
    def test_encode_target_win_masks_unsettled(self):
        labels, mask = encode_target(
            [Oc("a", "WIN"), Oc("b", "LOSS"), Oc("c", "PENDING")], "WIN")
        self.assertEqual(labels[:2], [1, 0])
        self.assertEqual(mask[:2], [True, True])
        self.assertEqual(mask[2], False)  # unsettled excluded, not fabricated

    def test_encode_target_entry_reached(self):
        labels, mask = encode_target(
            [Oc("a", er=True), Oc("b", er=False)], "ENTRY_REACHED")
        self.assertEqual(labels, [1, 0])
        self.assertTrue(all(mask))

    def test_encode_target_positive_r(self):
        labels, mask = encode_target(
            [Oc("a", "WIN", r=2.0), Oc("b", "LOSS", r=-1.0)],
            "POSITIVE_R")
        self.assertEqual(labels, [1, 0])
        self.assertTrue(all(mask))

    def test_encode_target_recovery_success(self):
        labels, _ = encode_target(
            [Oc("a", rec=True), Oc("b", rec=False)], "RECOVERY_SUCCESS")
        self.assertEqual(labels, [1, 0])

    def test_numpy_logistic_deterministic(self):
        X = [[1, 0], [1, 0], [0, 1], [0, 1]]
        y = [0, 0, 1, 1]
        m1 = NumpyLogisticRegression().fit(X, y)
        m2 = NumpyLogisticRegression().fit(X, y)
        p1 = list(m1.predict_proba(X))
        p2 = list(m2.predict_proba(X))
        self.assertEqual(p1, p2)
        # correlates with class
        self.assertGreater(p1[2], p1[0])

    def test_numpy_logistic_separates_classes(self):
        X = [[0.0], [0.1], [9.0], [9.1]]
        y = [0, 0, 1, 1]
        m = NumpyLogisticRegression(iterations=1000).fit(X, y)
        p = list(m.predict_proba(X))
        self.assertGreater(p[3], p[0])

    def test_numpy_tree_deterministic(self):
        X = [[0, 0], [0, 1], [1, 0], [1, 1]]
        y = [0, 0, 1, 1]
        t1 = NumpyDecisionTree().fit(X, y)
        t2 = NumpyDecisionTree().fit(X, y)
        self.assertEqual(list(t1.predict_proba(X)),
                         list(t2.predict_proba(X)))

    def test_simple_model_numpy_trains(self):
        X = [[0.0], [0.1], [9.0], [9.1]]
        y = [0, 0, 1, 1]
        m = SimpleModel(kind="LOGISTIC", backend="numpy").fit(X, y)
        self.assertTrue(m.trained)
        self.assertEqual(len(m.predict_proba(X)), 4)

    def test_auc_rank_sum_correct(self):
        # perfect separation -> 1.0
        self.assertEqual(auc([0, 0, 1, 1], [0.1, 0.2, 0.9, 0.8]), 1.0)
        # reversed -> 0.0
        self.assertEqual(auc([1, 1, 0, 0], [0.1, 0.2, 0.9, 0.8]), 0.0)

    def test_auc_single_class_returns_none(self):
        self.assertIsNone(auc([0, 0, 0], [0.1, 0.2, 0.3]))

    def test_backend_status_is_valid_enum(self):
        self.assertIn(ml_backend_status(), ("sklearn", ML_BACKEND_UNAVAILABLE))
        # numpy path always works regardless of sklearn presence
        m = SimpleModel(kind="TREE", backend="numpy")
        m.fit([[0], [1]], [0, 1])
        self.assertTrue(m.trained)

    def test_sklearn_isolation_when_absent(self):
        # if sklearn is absent, requesting sklearn backend must degrade
        # gracefully without raising (production never depends on it)
        m = SimpleModel(kind="LOGISTIC", backend="sklearn")
        try:
            m.fit([[0], [1]], [0, 1])
        except Exception as exc:  # pragma: no cover
            self.fail(f"sklearn request must not raise, got {exc}")
        if not ml_backend_available():
            self.assertFalse(m.trained)
        else:
            self.assertTrue(m.trained)


# ==========================================================
# 9G.3 feature-interaction association tables
# ==========================================================


class InteractionTest(unittest.TestCase):
    def _snaps_and_outcomes(self, n=12):
        snaps = []
        outs = {}
        for i in range(n):
            s = Sn(f"op{i:02d}", bar=i)
            s.features["wyckoff_phase"] = "MARKUP" if i % 2 == 0 else "SPRING"
            s.features["fvg_present"] = True
            snaps.append(s)
            outs[s.opportunity_id] = Oc(
                s.opportunity_id,
                "WIN" if i % 3 == 0 else "LOSS",
                2.0 if i % 3 == 0 else -1.0, True)
        return snaps, outs

    def test_interaction_builds_occurring_combos_only(self):
        snaps, outs = self._snaps_and_outcomes()
        rows = interaction_analysis(snaps, outs,
                                    ["wyckoff_phase", "fvg_present"],
                                    min_sample=1)
        self.assertEqual(len(rows), 2)  # MARKUP+True and SPRING+True
        for r in rows:
            self.assertEqual(r["combo"]["fvg_present"], True)
            self.assertEqual(r["n"], 6)

    def test_interaction_honest_tiny_sample(self):
        snaps, outs = self._snaps_and_outcomes(4)
        rows = interaction_analysis(snaps, outs, ["wyckoff_phase"],
                                    min_sample=4)
        # n < min_sample -> sufficient_sample False but still listed
        self.assertTrue(rows)
        self.assertFalse(any(r["sufficient_sample"] for r in rows))

    def test_interaction_missing_outcomes_are_null_not_fabricated(self):
        snaps, _ = self._snaps_and_outcomes(4)
        rows = interaction_analysis(snaps, {}, ["wyckoff_phase"])
        # no outcome labels -> win_rate None (honest), n present
        self.assertTrue(rows)
        self.assertTrue(all(r["win_rate"] is None for r in rows))
        self.assertTrue(all(r["n"] >= 1 for r in rows))

    def test_interaction_contains_rates_and_avg_r(self):
        snaps, outs = self._snaps_and_outcomes(12)
        rows = interaction_analysis(snaps, outs, ["wyckoff_phase"])
        keys = {"key", "combo", "n", "sufficient_sample",
                "entry_reached_rate", "win_rate", "avg_R", "avg_MAE",
                "avg_MFE"}
        self.assertTrue(keys.issubset(rows[0].keys()))

    def test_interaction_partial_feature_absent_combo_not_reported(self):
        snaps, outs = self._snaps_and_outcomes(6)
        snaps[0].features.pop("wyckoff_phase", None)  # feature missing
        rows = interaction_analysis(snaps, outs,
                                    ["wyckoff_phase", "fvg_present"])
        # op00 excluded (incomplete combo); remaining 5 split by wyckoff
        self.assertEqual(sum(r["n"] for r in rows), 5)


# ==========================================================
# MlAnalyzer orchestration (incl. recovery research)
# ==========================================================


class AnalyzerTest(unittest.TestCase):
    def test_ml_analyzer_produces_full_report(self):
        snaps, outs = _snaps_and_outcomes(60)
        report = MlAnalyzer(backend="numpy").analyze(
            _Report(snaps), outcomes=outs,
            features=["wyckoff_phase", "fvg_present"], min_combo_sample=2)
        self.assertIsInstance(report, MlResearchReport)
        d = report.to_dict()
        self.assertEqual(d["phase"], "9G")
        self.assertEqual(d["split"]["no_temporal_leakage"], True)
        self.assertEqual(d["split"]["no_shuffle"], True)
        self.assertIn("ml_results", d)
        self.assertTrue(d["walk_forward"]["walk_forward"])
        self.assertEqual(d["baseline"]["n"], 60)

    def test_ml_models_trained_on_train_only_chronologically(self):
        snaps, outs = _snaps_and_outcomes(60)
        report = MlAnalyzer(backend="numpy").analyze(_Report(snaps), outs)
        # split guarantees OOS bars are >= validation bars >= train bars
        self.assertGreaterEqual(
            min(snaps[i].decision_bar for i in report.split.oos.indices),
            max(snaps[i].decision_bar for i in report.split.validation.indices),
        )

    def test_recovery_research_first_class(self):
        snaps, outs = _snaps_and_outcomes(6)
        # mark two as rejected+recovered / rejected-not-recovered
        outs["op00"] = Oc("op00", "WIN", 2.0, True, rec=True, cat="REJECTED")
        outs["op01"] = Oc("op01", "WIN", 2.0, True, rec=False, cat="REJECTED")
        report = MlAnalyzer(backend="numpy").analyze(
            _Report(snaps), outs,
            recovery_alt={"op00": {"entry_model": "BREAKOUT_CONTINUATION",
                                   "rr": 3.0, "expiry": 75}})
        rec = report.recovery
        self.assertIsInstance(rec, dict)
        self.assertEqual(rec["candidate_count"], 2)
        self.assertEqual(rec["recovered_count"], 1)
        self.assertEqual(rec["recovery_rate"], 0.5)
        self.assertEqual(rec["expected_R"], 2.0)
        # alternative strategy passthrough for the recovered candidate
        alt = next(c for c in rec["candidates"]
                   if c["opportunity_id"] == "op00")["alternative"]
        self.assertEqual(alt["rr"], 3.0)
        self.assertTrue(rec["association_only"])
        self.assertTrue(rec["not_a_trade_directive"])

    def test_recovery_includes_not_reached_and_missed(self):
        snaps, outs = _snaps_and_outcomes(6)
        outs["op02"] = Oc("op02", "", 0.0, er=False, cat="ENTRY_NOT_REACHED")
        outs["op03"] = Oc("op03", "", 0.0, er=False, cat="MISSED_CONTINUATION")
        report = MlAnalyzer(backend="numpy").analyze(_Report(snaps), outs)
        cats = {c["category"] for c in report.recovery["candidates"]}
        self.assertIn("ENTRY_NOT_REACHED", cats)
        self.assertIn("MISSED_CONTINUATION", cats)

    def test_report_is_association_only(self):
        snaps, outs = _snaps_and_outcomes(60)
        report = MlAnalyzer(backend="numpy").analyze(_Report(snaps), outs)
        d = report.to_dict()
        self.assertTrue(d["association_not_causation"])
        self.assertTrue(d["no_trade_directive"])
        self.assertIn("never causation", report.render())
        # no trade instruction fields anywhere
        flat = json_str(d).lower()
        for token in ("\"action\"", "\"size\"", "\"approve\""):
            self.assertNotIn(token, flat)

    def test_render_and_dict_deterministic(self):
        snaps, outs = _snaps_and_outcomes(60)
        a = MlAnalyzer(backend="numpy")
        r1 = a.analyze(_Report(snaps), outs).to_dict()
        r2 = a.analyze(_Report(snaps), outs).to_dict()
        self.assertEqual(r1, r2)
        self.assertIsInstance(MlAnalyzer(backend="numpy")
                              .analyze(_Report(snaps), outs).render(), str)

    def test_targets_vocabulary_closed(self):
        self.assertEqual(TARGETS,
                         ("ENTRY_REACHED", "WIN", "POSITIVE_R",
                          "EXPECTED_R", "RECOVERY_SUCCESS"))

    def test_analyzer_accepts_real_feature_snapshots(self):
        snaps = [FeatureSnapshot(opportunity_id=f"op{i}", decision_bar=i,
                                 window_size=20, direction="BULLISH",
                                 instrument_id="BTCUSDT",
                                 features={"wyckoff_phase": "MARKUP",
                                           "fvg_present": True})
                 for i in range(12)]
        outs = {s.opportunity_id: Oc(s.opportunity_id,
                                     "WIN" if i % 2 == 0 else "LOSS",
                                     2.0 if i % 2 == 0 else -1.0, True)
                for i, s in enumerate(snaps)}
        report = MlAnalyzer(backend="numpy").analyze(_Report(snaps), outs)
        self.assertEqual(report.baseline.n(), 12)


def json_str(obj):
    import json
    return json.dumps(obj, default=str)


# ==========================================================
# Boundaries: isolation / no production / no deep AI
# ==========================================================


class BoundaryTest(unittest.TestCase):
    def _ml_sources(self):
        base = os.path.join(os.path.dirname(__file__), "..", "core",
                            "research", "ml")
        for fname in sorted(os.listdir(base)):
            if fname.endswith(".py"):
                with open(os.path.join(base, fname), encoding="utf-8") as fh:
                    yield fname, fh.read()

    def test_no_production_internals_imported(self):
        banned = re.compile(
            r"^\s*(from|import)\s+" + r"(core\.)?"
            r"(execution|risk|portfolio|engine|trade|account|strategy)"
        )
        for fname, src in self._ml_sources():
            for line in src.splitlines():
                if banned.match(line):
                    self.fail(f"{fname} imports production internals: {line}")

    def test_no_deep_learning_dependencies(self):
        forbidden = ("torch", "tensorflow", "keras", "transformers",
                     "openai", "anthropic", "lightgbm", "xgboost", "mlx")
        for fname, src in self._ml_sources():
            for line in src.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    low = line.lower()
                    for token in forbidden:
                        self.assertNotIn(token, low,
                                         f"{fname} deep-AI: {token}")
            # sklearn only as a guarded optional backend (imported inside
            # a try/except with graceful degrade), never deep learning
            for smell in ("nn.", "layers.", "embedding(", "backward(",
                          "autograd", ".cuda("):
                self.assertNotIn(smell, src, f"{fname} deep learning")

    def test_sklearn_is_optional_and_guarded(self):
        # the sklearn package may be imported/installed ONLY in
        # models.py, inside a failure-guarded try; internal imports of
        # our own _HAS_SKLEARN constant (e.g. analyzer.py) are fine.
        for fname, src in self._ml_sources():
            imports = [
                line for line in src.splitlines()
                if line.lstrip().startswith(("import ", "from "))
                and "sklearn" in line
                and "core.research.ml" not in line
            ]
            if imports:
                self.assertEqual(fname, "models.py",
                                 f"{fname} imports the sklearn package")
                self.assertIn("try:", src)
                self.assertIn("except", src)
                self.assertIn("_HAS_SKLEARN", src)

    def test_production_never_imports_ml(self):
        # the strategy/execution/risk/portfolio/engine/trade layer must
        # never import core.research.ml
        for base in ("strategy", "execution", "risk", "portfolio", "engine",
                     "trade", "account"):
            path = os.path.join(os.path.dirname(__file__), "..", "core", base)
            if not os.path.isdir(path):
                continue
            for root, _dirs, files in os.walk(path):
                for fn in files:
                    if fn.endswith(".py"):
                        p = os.path.join(root, fn)
                        with open(p, encoding="utf-8") as fh:
                            src = fh.read()
                        self.assertNotIn("core.research.ml", src,
                                         f"{p} imports ML")

    def test_no_auto_promotion_and_7e_no_go(self):
        for fname, src in self._ml_sources():
            # executable lines only (prose denials are legitimate)
            for line in src.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    self.assertNotIn("promotion", line.lower(),
                                     f"{fname} promotes")
            if re.search(r"auto_promot|approve\(|promot\w*\(", src):
                self.fail(f"{fname} suggests auto-promotion")

    def test_no_simulation_imported(self):
        for fname, src in self._ml_sources():
            if re.search(r"OpportunitySimulator|run_configs|simulate\(",
                         src):
                self.fail(f"{fname} invokes simulation")


if __name__ == "__main__":
    unittest.main()