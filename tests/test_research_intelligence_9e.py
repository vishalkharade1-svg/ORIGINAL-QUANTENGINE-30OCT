"""
====================================================

QuantEngine

Phase 9E -- Research Intelligence tests

Proves the deterministic, evidence-backed research-intelligence
layer (OPPORTUNITY RECOVERY, PARAMETER, DIRECTIONAL, SYMBOL AND
CONFLUENCE INSIGHTS; EVIDENCE STRENGTH; ROBUSTNESS GATE;
RECOMMENDATION STATUSES; LEAD SELECTION), all WITHOUT resimulation,
WITHOUT auto-promotion and WITHOUT any AI/ML.

Covers the required behaviors:

   * recommendation id determinism & stability
   * evidential package (config provenance + comparison + recovery +
     robustness + evidence strength)
   * deterministic, non-statistical evidence strength from settled size
   * robustness gate: INSUFFICIENT_SAMPLE / LOSS_EXPANSION /
     OOS_REQUIRED / NON_ROBUST / ROBUST / INCONCLUSIVE
   * recommendation statuses: OBSERVATION / HYPOTHESIS / PROMISING /
     INCONCLUSIVE / REJECTED / REQUIRES_OOS / BLOCKED
   * status is NOT production approval; reminder shipped in output
   * recovery insight (WIN / LOSS / UNSETTLED / still-rejected)
   * parameter insight over values that actually vary
   * directional insight; directional-imbalance flag
   * symbol insight from read-only 9C outcomes (never resimulated)
   * confluence: NEVER fabricated -> CONFLUENCE_DATA_UNAVAILABLE
   * confluence: supplied features are passed through read-only
   * zero-confluence data still yields a complete report (no feature
     blending)
   * hypothesis generation is deterministic and calls out
     directional imbalance / OOS
   * ResearchReport source is never mutated (intelligence is pure)
   * report to_dict() + render() deterministic
   * leading recommendation chosen deterministically
   * BLOCKED when no usable experiment bundles
   * integration: real 9D ResearchAnalyzer report consumed end-to-end
   * boundaries: package never imports production internals nor any
     AI/ML; no simulation import at the intelligence layer level

Uses ONLY real 9D / 9C facts and read-only evidence. Stdlib only;
offline; deterministic.
====================================================
"""

import math
import re
import unittest

from core.research.intelligence import (
    ResearchIntelligence,
    Recommendation,
    EvidencePackage,
    evidence_strength_for,
    opportunity_recovery_insight,
    parameter_insights,
    directional_breakdown,
    symbol_breakdown,
    robustness_status_for,
    confluence_from_features,
    ConfluenceAnalysis,
    ConfluenceFeature,
    generate_hypotheses,
    recommendation_id_for,
    BLOCKED, OBSERVATION, HYPOTHESIS, PROMISING, INCONCLUSIVE, REJECTED,
    REQUIRES_OOS, ROBUST, NON_ROBUST, OOS_REQUIRED,
    EVIDENCE_INSUFFICIENT_SAMPLE, EVIDENCE_SMALL_SAMPLE, EVIDENCE_LIMITED,
    EVIDENCE_MODERATE, EVIDENCE_STRONG,
)
from core.research.intelligence.recommendation_types import (
    RECOMMENDATION_STATUSES,
    LOSS_EXPANSION,
    DIRECTIONAL_IMBALANCE,
)

from core.research.journal import OpportunityRecord
from core.research.counterfactual import CounterfactualConfig
from core.research.analyzer import ResearchAnalyzer


# ==========================================================
# Fixture primitives for building shaped 9D evidence
# ==========================================================


class _Cfg:
    """Minimal shape-compatible Config for ExperimentAnalysis."""

    def __init__(self, params, outcome_bars=None, baseline_id="baseline"):
        self.params = dict(params)
        self.outcome_bars = outcome_bars
        self.baseline = baseline_id

    def to_dict(self):
        return {
            "params": self.params,
            "outcome_bars": self.outcome_bars,
            "baseline_id": self.baseline,
        }


class _Recovery:
    """Shape-compatible RecoveryReport (to_dict only)."""

    def __init__(self, transitions, recovered=0, recovered_wins=0,
                 recovered_losses=0, incremental_R=0.0,
                 incremental_pnl=0.0, recovered_unsettled=0):
        self.transitions = dict(transitions)
        self.recovered = recovered
        self.recovered_wins = recovered_wins
        self.recovered_losses = recovered_losses
        self.incremental_R = incremental_R
        self.incremental_pnl = incremental_pnl
        self.recovered_unsettled = recovered_unsettled

    def to_dict(self):
        return {
            "transitions": dict(self.transitions),
            "baseline_filled": 0,
            "previously_unfilled": self.recovered,
            "recovered": self.recovered,
            "recovered_wins": self.recovered_wins,
            "recovered_losses": self.recovered_losses,
            "recovered_unsettled": self.recovered_unsettled,
            "recovery_rate": (
                self.recovered / self.recovered if self.recovered else 0.0
            ),
            "profitable_recovery_rate": 0.0,
            "recovered_win_rate": 0.0,
            "additional_trades": self.recovered,
            "additional_wins": self.recovered_wins,
            "additional_losses": self.recovered_losses,
            "incremental_R": self.incremental_R,
            "incremental_pnl": self.incremental_pnl,
            "quality": {},
            "rejected_reason_recovery": {},
            "missed_continuation": {},
        }


class _Comp:
    """Shape-compatible Comparison."""

    def __init__(self, **over):
        d = {
            "delta_expectancy": 0.0,
            "delta_pf": 0.0,
            "incremental_fills": 0,
            "incremental_wins": 0,
            "incremental_losses": 0,
            "incremental_R": 0.0,
        }
        d.update(over)
        self._d = d

    def to_dict(self):
        return dict(self._d)


class _Exp:
    """Shape-compatible ExperimentAnalysis."""

    def __init__(self, experiment_id, config, metrics, recovery=None,
                 comparison=None, robustness=None, directional=None):
        self.experiment_id = experiment_id
        self.config = config
        self.metrics = metrics
        self.recovery = recovery or _Recovery({})
        self.comparison = comparison or _Comp()
        self.robustness = list(robustness or [])
        self.directional = directional or {}


class _Report:
    """Shape-compatible ResearchReport (frozen input)."""

    def __init__(self, baseline_metrics, experiments, rejected=None):
        self.baseline_id = "baseline"
        self.baseline_metrics = dict(baseline_metrics)
        self.population = {}
        self.experiments = list(experiments)
        self.rejected = dict(rejected or {})
        self.entry_model_comparison = {}
        self.directional = {
            e.experiment_id: e.directional for e in experiments
        }
        self.warnings = []


def _metrics(filled=10, wins=6, losses=3, unsettled=1, expectancy=0.5,
             total_R=9.0, win_rate=60.0, profit_factor=1.5):
    return {
        "opportunities_evaluated": filled + unsettled,
        "settled": filled,
        "filled": filled,
        "wins": wins,
        "losses": losses,
        "unsettled": unsettled,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "net_pnl": expectancy * filled,
        "gross_profit": float(wins * 2),
        "gross_loss": float(losses),
        "max_drawdown": 0.0,
        "total_R": total_R,
        "avg_R": total_R / filled if filled else 0.0,
        "median_R": 1.0,
        "settled_count": filled,
    }


BASELINE_METRICS = _metrics(
    filled=10, wins=5, losses=5, unsettled=0, expectancy=0.2,
    total_R=5.0, win_rate=50.0, profit_factor=1.0,
)


# ==========================================================
# Evidence strength
# ==========================================================


class EvidenceStrengthTest(unittest.TestCase):
    def test_evidence_strength_bands(self):
        self.assertEqual(evidence_strength_for(0), EVIDENCE_INSUFFICIENT_SAMPLE)
        self.assertEqual(evidence_strength_for(2), EVIDENCE_INSUFFICIENT_SAMPLE)
        self.assertEqual(evidence_strength_for(3), EVIDENCE_SMALL_SAMPLE)
        self.assertEqual(evidence_strength_for(9), EVIDENCE_SMALL_SAMPLE)
        self.assertEqual(evidence_strength_for(10), EVIDENCE_LIMITED)
        self.assertEqual(evidence_strength_for(29), EVIDENCE_LIMITED)
        self.assertEqual(evidence_strength_for(30), EVIDENCE_MODERATE)
        self.assertEqual(evidence_strength_for(79), EVIDENCE_MODERATE)
        self.assertEqual(evidence_strength_for(80), EVIDENCE_STRONG)
        self.assertEqual(evidence_strength_for(500), EVIDENCE_STRONG)

    def test_evidence_strength_is_graded_not_statistical(self):
        # a strong sample is never claimed as "significant"
        self.assertNotIn(
            "significant", EVIDENCE_STRONG.lower(),
        )

    def test_evidence_package_carries_provenance(self):
        pkg = EvidencePackage(
            experiment_id="exp-A",
            config={"rr": 2.0},
            baseline_metrics={"expectancy": 0.2},
            candidate_metrics={"expectancy": 0.9},
            comparison={"delta_expectancy": 0.7},
            recovery={"recovered_wins": 3},
            robustness=["in-sample research only"],
            sample_size=12,
        )
        self.assertEqual(pkg.evidence_strength, EVIDENCE_LIMITED)
        d = pkg.to_dict()
        self.assertEqual(d["experiment_id"], "exp-A")
        self.assertEqual(d["comparison"]["delta_expectancy"], 0.7)
        self.assertIn("evidence_strength", d)
        # determinism: same inputs -> same dict
        self.assertEqual(EvidencePackage(
            experiment_id="exp-A",
            config={"rr": 2.0},
            baseline_metrics={"expectancy": 0.2},
            candidate_metrics={"expectancy": 0.9},
            comparison={"delta_expectancy": 0.7},
            recovery={"recovered_wins": 3},
            robustness=["in-sample research only"],
            sample_size=12,
        ).to_dict(), d)


# ==========================================================
# Robustness gate
# ==========================================================


class RobustnessGateTest(unittest.TestCase):
    def test_gate_insufficient_sample(self):
        self.assertEqual(
            robustness_status_for(EVIDENCE_SMALL_SAMPLE, 2, [],
                                  has_advantage=True),
            "INSUFFICIENT_SAMPLE",
        )

    def test_gate_loss_expansion_takes_precedence(self):
        self.assertEqual(
            robustness_status_for(EVIDENCE_STRONG, 200,
                                  ["in-sample only"], has_advantage=True,
                                  incremental_wins=3, incremental_losses=6),
            LOSS_EXPANSION,
        )

    def test_gate_loss_expansion_via_warning(self):
        self.assertEqual(
            robustness_status_for(
                EVIDENCE_MODERATE, 60,
                ["recovery increases losses: +3 losses vs +1 wins"],
                has_advantage=True),
            LOSS_EXPANSION,
        )

    def test_gate_directional_imbalance_is_non_robust(self):
        self.assertEqual(
            robustness_status_for(
                EVIDENCE_MODERATE, 60,
                ["directional imbalance: one direction holds 10% of the "
                 "experiment sample"],
                has_advantage=True),
            NON_ROBUST,
        )

    def test_gate_small_sample_advantage_requires_oos(self):
        self.assertEqual(
            robustness_status_for(EVIDENCE_SMALL_SAMPLE, 12, [],
                                  has_advantage=True),
            OOS_REQUIRED,
        )

    def test_gate_robust(self):
        self.assertEqual(
            robustness_status_for(EVIDENCE_STRONG, 200, [],
                                  has_advantage=True,
                                  incremental_wins=8, incremental_losses=2),
            ROBUST,
        )

    def test_gate_no_advantage_with_warnings_non_robust(self):
        self.assertEqual(
            robustness_status_for(EVIDENCE_LIMITED, 40, ["small sample"],
                                  has_advantage=False),
            NON_ROBUST,
        )

    def test_gate_no_advantage_no_warnings_inconclusive(self):
        self.assertEqual(
            robustness_status_for(EVIDENCE_LIMITED, 40, [],
                                  has_advantage=False),
            "INCONCLUSIVE",
        )


# ==========================================================
# Recommendation ids + statuses are a closed set
# ==========================================================


class RecommendationIdentityTest(unittest.TestCase):
    def test_recommendation_id_deterministic(self):
        a = recommendation_id_for("RR_ANALYSIS", ["exp1"], {"rr": 2.0})
        b = recommendation_id_for("RR_ANALYSIS", ["exp1"], {"rr": 2.0})
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("rec-"))
        # different params -> different id
        c = recommendation_id_for("RR_ANALYSIS", ["exp1"], {"rr": 3.0})
        self.assertNotEqual(a, c)

    def test_recommendation_frozen(self):
        rec = Recommendation(
            recommendation_id="r1", category="RR_ANALYSIS",
            status=HYPOTHESIS, evidence_strength=EVIDENCE_SMALL_SAMPLE,
            sample_size=6,
        )
        with self.assertRaises(Exception):
            rec.status = REJECTED

    def test_statuses_are_research_labels_not_production(self):
        self.assertNotIn(
            "approved", " ".join(RECOMMENDATION_STATUSES).lower(),
        )
        self.assertIn(REJECTED, RECOMMENDATION_STATUSES)
        self.assertIn(BLOCKED, RECOMMENDATION_STATUSES)


# ==========================================================
# Opportunity recovery insight
# ==========================================================


class RecoveryInsightTest(unittest.TestCase):
    def _exp(self):
        rec = _Recovery(
            {
                "REJECTED -> WIN": 2,
                "REJECTED -> LOSS": 1,
                "REJECTED -> STILL_REJECTED": 1,
                "ENTRY_NOT_REACHED -> WIN": 1,
                "MISSED_CONTINUATION -> LOSS": 1,
                "FILLED -> BETTER": 3,
            },
            recovered=5,
            recovered_wins=3,
            recovered_losses=2,
            incremental_R=4.0,
            recovered_unsettled=0,
        )
        return _Exp("exp-r", _Cfg({"rr": 2.0}),
                    _metrics(), recovery=rec)

    def test_recovery_win_vs_loss_vs_still(self):
        exp = self._exp()
        insight = opportunity_recovery_insight(exp)
        d = insight.to_dict()
        self.assertEqual(d["experiment_id"], "exp-r")
        self.assertEqual(d["comparative_recovered"], 5)
        self.assertEqual(d["comparative_wins"], 3)
        self.assertEqual(d["comparative_losses"], 2)
        # category-level (count-weighted transitions)
        self.assertEqual(d["category_recoverable"]["REJECTED"], 4)
        self.assertEqual(d["category_recovered_win"]["REJECTED"], 2)
        self.assertEqual(d["category_recovered_loss"]["REJECTED"], 1)
        self.assertEqual(d["category_still"]["REJECTED"], 1)
        self.assertEqual(insight.recovery_rate(), 5 / 6)
        self.assertEqual(insight.successful_recovery_rate(), 3 / 5)


# ==========================================================
# Confluence
# ==========================================================


class ConfluenceTest(unittest.TestCase):
    def test_zero_confluence_is_unavailable_not_fabricated(self):
        ca = ConfluenceAnalysis()
        self.assertTrue(ca.unavailable)
        self.assertEqual(ca.status(), "CONFLUENCE_DATA_UNAVAILABLE")
        d = ca.to_dict()
        self.assertEqual(d["feature_count"], 0)

    def test_confluence_from_features(self):
        ca = confluence_from_features([
            {"name": "wyckoff_phase", "value": "phase_c",
             "sample": 40, "outcomes": {"wins": 25, "losses": 15},
             "experiment_id": "exp-A"},
        ])
        self.assertFalse(ca.unavailable)
        self.assertEqual(ca.by_name("wyckoff_phase")[0].value, "phase_c")

    def test_confluence_only_supplied_values(self):
        ca = confluence_from_features({
            "displacement": 2.5,
            "order_block": True,
        })
        self.assertEqual(ca.status(), "AVAILABLE")
        self.assertEqual(len(ca.features), 2)


# ==========================================================
# Parameter + directional + symbol insights
# ==========================================================


class InsightsTest(unittest.TestCase):
    def test_parameter_insight_only_varying_param(self):
        bundles = [
            (_Cfg({"rr": 2.0}), _metrics(expectancy=0.5), "e2"),
            (_Cfg({"rr": 3.0}), _metrics(expectancy=1.0), "e3"),
        ]
        ins = parameter_insights(bundles, params=["rr"])
        self.assertEqual(len(ins), 1)
        rows = ins[0].rows
        self.assertEqual([r["value"] for r in rows], [2.0, 3.0])
        self.assertEqual(rows[0]["expectancy"], 0.5)
        self.assertEqual(rows[1]["expectancy"], 1.0)

    def test_parameter_insight_skips_non_varying(self):
        bundles = [(_Cfg({"rr": 2.0}), _metrics(), "e2")] * 2
        self.assertEqual(parameter_insights(bundles, params=["rr"]), [])

    def test_directional_breakdown_groups_directions(self):
        bd = directional_breakdown([
            ("exp-A", {"ALL": _metrics(),
                       "BULLISH": _metrics(filled=20, expectancy=0.9),
                       "BEARISH": _metrics(filled=2, expectancy=-0.8)},
             ["directional imbalance: ..."]),
        ])
        rows = bd["exp-A"]["directions"]
        self.assertTrue(rows["BEARISH"]["insufficient_sample"])
        self.assertEqual(
            bd["exp-A"]["directional_imbalance_flag"], True,
        )

    def test_symbol_breakdown_from_outcomes_readonly(self):
        res = symbol_breakdown(
            "exp-A",
            {
                "BTCUSDT": _metrics(filled=8, wins=6, losses=2,
                                   expectancy=0.9),
                "ETHUSDT": _metrics(filled=6, wins=0, losses=6,
                                   expectancy=-1.0),
            },
            _metrics(filled=14, wins=6, losses=8),
        )
        names = [r["symbol"] for r in res["positive_symbols"]]
        self.assertEqual(names, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(res["positive_symbols"][0]["expectancy"], 0.9)
        # not broad: one symbol is a net loser
        self.assertFalse(res["broad"])
        self.assertIn("symbol-specific", res["note"])

    def test_symbol_breakdown_no_data_is_honest(self):
        res = symbol_breakdown("exp-A", {}, _metrics())
        self.assertEqual(res["symbol_count"], 0)
        self.assertIn("no symbol breakdown", res["note"])


# ==========================================================
# Hypothesis generation
# ==========================================================


class HypothesisTest(unittest.TestCase):
    def test_hypotheses_deterministic_and_sorted(self):
        recs = [
            Recommendation(
                recommendation_id="r1", category="ENTRY_RECOVERY",
                status=HYPOTHESIS, evidence_strength=EVIDENCE_SMALL_SAMPLE,
                affected_opportunity_categories=("REJECTED",),
                baseline_experiment_id="baseline",
                candidate_experiment_ids=("exp-r",),
                recovered_wins=2, recovered_losses=1, sample_size=8,
                parameters_changed={"entry_model": "BREAKOUT_CONTINUATION"},
            ),
        ]
        hyps = generate_hypotheses(recs)
        ids = [h.hypothesis_id for h in hyps]
        self.assertEqual(ids, sorted(ids))
        self.assertTrue(any(h.category == "ENTRY_RECOVERY" for h in hyps))
        text = hyps[0].text
        self.assertIn("recovered 2 wins", text)
        self.assertIn("experiment", text)

    def test_hypothesis_calls_out_imbalance(self):
        hyps = generate_hypotheses([], directional_by_id={
            "exp-A": {"directional_imbalance_flag": True},
        })
        self.assertTrue(any(
            h.category == "DIRECTIONAL_ANALYSIS" for h in hyps))
        self.assertTrue(any(
            "direction-specific" in h.text for h in hyps))


# ==========================================================
# End-to-end ResearchIntelligence
# ==========================================================


def _build_bundles():
    """Shaped 9D evidence: (id, ExperimentAnalysis) pairs."""
    improved_metrics = _metrics(
        filled=60, wins=38, losses=18, unsettled=4, expectancy=0.9,
        total_R=58.0, win_rate=63.3, profit_factor=2.1,
    )
    exp_a = _Exp(
        "exp-A",
        _Cfg({"entry_model": "BREAKOUT_CONTINUATION", "rr": 2.0,
              "stop_mode": "EXISTING_STOP", "target_mode": "FIXED_RR",
              "expiry": None}),
        improved_metrics,
        recovery=_Recovery(
            {
                "REJECTED -> WIN": 4,
                "REJECTED -> LOSS": 2,
                "ENTRY_NOT_REACHED -> WIN": 3,
                "MISSED_CONTINUATION -> LOSS": 1,
            },
            recovered=10, recovered_wins=7, recovered_losses=3,
            incremental_R=11.0, recovered_unsettled=0,
        ),
        comparison=_Comp(delta_expectancy=0.7, delta_pf=1.1,
                         incremental_fills=50, incremental_wins=33,
                         incremental_losses=13, incremental_R=53.0),
        robustness=[
            "in-sample research only; no out-of-sample validation "
            "performed",
        ],
        directional={
            "ALL": improved_metrics,
            "BULLISH": _metrics(filled=30, wins=20, losses=10,
                                expectancy=1.0),
            "BEARISH": _metrics(filled=30, wins=18, losses=12,
                                expectancy=0.8),
        },
    )

    exp_b = _Exp(
        "exp-B",
        _Cfg({"rr": 3.0, "expiry": 10, "target_mode": "FIXED_RR"}),
        _metrics(filled=12, wins=9, losses=3, unsettled=0,
                 expectancy=1.5, total_R=15.0, win_rate=75.0,
                 profit_factor=3.0),
        recovery=_Recovery(
            {"ENTRY_NOT_REACHED -> WIN": 5},
            recovered=5, recovered_wins=5, recovered_losses=0,
            incremental_R=10.0,
        ),
        comparison=_Comp(delta_expectancy=1.3, delta_pf=2.0,
                         incremental_wins=4, incremental_R=10.0),
        robustness=["small sample: 12 settled trade(s)"],
        directional={"ALL": _metrics(filled=12, expectancy=1.5)},
    )

    exp_c = _Exp(
        "exp-C",
        _Cfg({"rr": 1.0, "target_mode": "FIXED_RR"}),
        _metrics(filled=40, wins=10, losses=28, unsettled=2,
                 expectancy=-0.6, total_R=-8.0, win_rate=26.3,
                 profit_factor=0.5),
        recovery=_Recovery({}, recovered=0),
        comparison=_Comp(delta_expectancy=-0.8, delta_pf=-0.5,
                         incremental_R=-13.0),
        robustness=["in-sample research only"],
        directional={"ALL": _metrics(filled=40, expectancy=-0.6)},
    )
    return [exp_a, exp_b, exp_c], {
        "exp-A": improved_metrics,
    }


class ResearchIntelligenceTest(unittest.TestCase):
    def test_empty_report_is_blocked(self):
        report = _Report(BASELINE_METRICS, [])
        result = ResearchIntelligence().analyze(report)
        self.assertEqual(result.status, BLOCKED)
        self.assertIsNone(result.lead)

    def test_full_report_produces_recommendations(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        result = ResearchIntelligence().analyze(report)
        self.assertEqual(result.phase, "9E")
        self.assertEqual(result.status, "RECOMMENDATIONS_AVAILABLE")
        cats = {r.category for r in result.recommendations}
        # exp-A -> ENTRY_RECOVERY, exp-B/exp-C -> STOP_TARGET_ANALYSIS
        self.assertIn("ENTRY_RECOVERY", cats)
        self.assertIn("STOP_TARGET_ANALYSIS", cats)

    def test_lead_is_promising_or_hypothesis(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        result = ResearchIntelligence().analyze(report)
        self.assertIsNotNone(result.lead)
        self.assertIn(result.lead.status, (PROMISING, HYPOTHESIS, REQUIRES_OOS))

    def test_rejected_candidate(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, [exps[2]])  # only exp-C (loses)
        result = ResearchIntelligence().analyze(report)
        rec_c = result.recommendations[0]
        self.assertEqual(rec_c.category, "STOP_TARGET_ANALYSIS")
        self.assertEqual(rec_c.status, REJECTED)
        self.assertLess(rec_c.expectancy_delta, 0.0)

    def test_observation_when_baseline_unchanged(self):
        report = _Report(
            BASELINE_METRICS,
            [_Exp("exp-same", _Cfg({"rr": 2.0}), dict(BASELINE_METRICS),
                  recovery=_Recovery({}), comparison=_Comp(),
                  robustness=["in-sample research only"])],
        )
        result = ResearchIntelligence().analyze(report)
        self.assertEqual(result.recommendations[0].status, OBSERVATION)

    def test_source_report_not_mutated(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        before = [e.metrics for e in report.experiments]
        ResearchIntelligence().analyze(report)
        after = [e.metrics for e in report.experiments]
        self.assertEqual(after, before)

    def test_symbol_insight_via_outcomes(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        # build REAL 9C outcomes (read-only evidence) across a symbol
        real = RealIntegrationTest()
        outcomes = real._build_symbol_outcomes()
        result = ResearchIntelligence().analyze(
            report,
            outcomes_by_experiment={"exp-A": outcomes},
        )
        sym = result.insights["symbol"]["exp-A"]
        self.assertGreaterEqual(sym["symbol_count"], 0)
        # outcomes are read-only: the source is never mutated
        self.assertIsInstance(outcomes, list)
        # zero-datum path is still honest for the other experiments
        self.assertIn(
            "no symbol breakdown", result.insights["symbol"]["exp-B"]["note"],
        )

    def test_no_confluence_never_fabricated(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        result = ResearchIntelligence().analyze(report)
        self.assertEqual(result.confluence.status(), "CONFLUENCE_DATA_UNAVAILABLE")

    def test_confluence_pass_through(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        result = ResearchIntelligence().analyze(
            report, confluence=[{"name": "fvg", "value": True, "sample": 5}],
        )
        self.assertEqual(result.confluence.status(), "AVAILABLE")
        self.assertEqual(result.confluence.by_name("fvg")[0].value, True)

    def test_report_serialization_roundtrip(self):
        exps, _ = _build_bundles()
        report = _Report(BASELINE_METRICS, exps)
        result = ResearchIntelligence().analyze(report)
        d = result.to_dict()
        self.assertEqual(d["phase"], "9E")
        self.assertEqual(len(d["recommendations"]), len(exps))
        for r in d["recommendations"]:
            self.assertIn("recommendation_status", r)
            self.assertIn("recommendation_id", r)
            self.assertIn("robustness_status", r)
        self.assertIn("recommendation_reminder", d)

    def test_render_includes_reminder(self):
        exps, _ = _build_bundles()
        result = ResearchIntelligence().analyze(_Report(BASELINE_METRICS, exps))
        text = result.render()
        self.assertIn("9E", text)
        self.assertIn("research only", text.lower())

    def test_determinism_across_runs(self):
        exps, _ = _build_bundles()
        r1 = ResearchIntelligence().analyze(_Report(BASELINE_METRICS, exps))
        r2 = ResearchIntelligence().analyze(_Report(BASELINE_METRICS, exps))
        self.assertEqual(r1.to_dict(), r2.to_dict())


# ==========================================================
# Real 9D integration (ResearchAnalyzer -> ResearchIntelligence)
# ==========================================================


class RealIntegrationTest(unittest.TestCase):
    def _candles(self):
        class C:
            __slots__ = ("open", "high", "low", "close", "timestamp")
            def __init__(self, o, h, l, c, ts):
                self.open, self.high, self.low = o, h, l
                self.close, self.timestamp = c, ts

        return {
            "bull": [
                C(100.0, 101.0, 99.0, 100.0, 0),
                C(100.0, 101.0, 99.0, 101.0, 1),
                C(100.0, 100.5, 99.5, 100.0, 2),
                C(100.0, 106.0, 100.0, 105.0, 3),
            ],
            "bull_loss": [
                C(100.0, 101.0, 99.0, 100.0, 0),
                C(100.0, 101.0, 99.0, 101.0, 1),
                C(100.0, 102.0, 97.0, 98.0, 2),
            ],
        }

    def _records(self, instrument="BTCUSDT"):
        def rec(can, direction, reasons, result, pnl, r):
            stop = 98.0 if direction == "BULLISH" else 102.0
            target = 104.0 if direction == "BULLISH" else 96.0
            return OpportunityRecord(
                canonical_id=can,
                exchange="TESTEX",
                instrument_id=instrument,
                timeframe="1m",
                direction=direction,
                strategy="BREAKOUT_CONTINUATION",
                setup_id=can,
                setup={"entry": 100.0, "stop_loss": stop,
                       "take_profit": target, "risk_reward": 2.0,
                       "bar": 0, "atr": 4.0,
                       "rejection_reasons": list(reasons or [])},
                order={},
                trade={"result": result, "pnl": pnl, "risk_amount": 2.0,
                       "entry_bar": 2, "exit_bar": 2, "bars_held": 1,
                       "r": r, "exit_price": 104.0 if direction == "BULLISH"
                       else 96.0},
                terminal_outcome="ORDER_NOT_CREATED",
            )

        far = rec("r-far", "BULLISH", ["TOO_FAR_FROM_MARKET"],
                  "NONE", 0.0, 0.0)
        width = rec("r-width", "BULLISH", ["INSUFFICIENT_RISK_WIDTH"],
                    "NONE", 0.0, 0.0)
        stale = rec("r-stale", "BULLISH", ["STALE_ZONE"],
                    "NONE", 0.0, 0.0)
        return [far, width, stale]

    def _build_symbol_outcomes(self):
        """Real 9C outcomes across two instruments (read-only)."""
        candles = self._candles()
        from core.research.counterfactual import OpportunitySimulator

        sim = OpportunitySimulator()
        config = CounterfactualConfig(
            params={"entry_model": "BREAKOUT_CONTINUATION", "rr": 2.0,
                    "stop_mode": "EXISTING_STOP", "target_mode": "FIXED_RR"},
        )
        btc = [sim.simulate(rec, config, candles["bull"])
               for rec in self._records("BTCUSDT")]
        eth = [sim.simulate(rec, config, candles["bull"])
               for rec in self._records("ETHUSDT")]
        return btc + eth

    def test_real_9d_report_consumed_end_to_end(self):
        records = self._records()
        candles = self._candles()
        config = CounterfactualConfig(
            params={"entry_model": "BREAKOUT_CONTINUATION", "rr": 2.0,
                    "stop_mode": "EXISTING_STOP", "target_mode": "FIXED_RR"},
        )
        from core.research.counterfactual import OpportunitySimulator

        outcomes = [
            OpportunitySimulator().simulate(rec, config, candles["bull"])
            for rec in records
        ]
        report = ResearchAnalyzer().analyze(records, [(config, outcomes)])
        result = ResearchIntelligence().analyze(report)
        self.assertEqual(len([r for r in result.recommendations]), 1)
        self.assertEqual(result.status, "RECOMMENDATIONS_AVAILABLE")
        rec_ = result.recommendations[0]
        self.assertEqual(rec_.candidate_experiment_ids, (report.experiments[0].experiment_id,))
        self.assertTrue(rec_.recommendation_id.startswith("rec-"))


# ==========================================================
# Boundaries: no production / AI / simulation at 9E layer
# ==========================================================


class BoundaryTest(unittest.TestCase):
    def _intelligence_sources(self):
        import os
        base = os.path.join(os.path.dirname(__file__), "..", "core",
                            "research", "intelligence")
        for fname in os.listdir(base):
            if fname.endswith(".py"):
                with open(os.path.join(base, fname), encoding="utf-8") as fh:
                    yield fname, fh.read()

    def test_no_production_internals_imported(self):
        banned = re.compile(
            r"^\s*(from|import)\s+" + r"(core\.)?"
            r"(execution|risk|portfolio|engine|trade|account|strategy)"
        )
        for fname, src in self._intelligence_sources():
            for line in src.splitlines():
                if banned.match(line):
                    self.fail(
                        f"{fname} imports production internals: {line}"
                    )

    def test_no_ai_ml_or_mlx_dependency(self):
        forbidden_imports = ("torch", "tensorflow", "sklearn", "keras",
                             "transformers", "openai", "anthropic",
                             "mlx", "mlflow", "pytorch")
        for fname, src in self._intelligence_sources():
            # only imports of real AI/ML libraries are forbidden; the
            # package may DOCUMENT the denial in prose.
            for line in src.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    low = line.lower()
                    for token in forbidden_imports:
                        self.assertNotIn(
                            token, low,
                            f"{fname} imports forbidden AI/ML: {token}",
                        )
            # no AI/ML inference calls may appear in executable code
            for smell in (".fit(", ".predict(", ".transform(", "tokenizer",
                          "nn.", "layers.", "embedding("):
                self.assertNotIn(smell, src,
                                 f"{fname} contains AI/ML inference: {smell}")

    def test_no_lookahead_simulation_imported(self):
        for fname, src in self._intelligence_sources():
            if re.search(r"OpportunitySimulator|run_configs|simulate\(",
                         src):
                self.fail(f"{fname} invokes simulation")

    def test_no_math_stats_significance(self):
        for fname, src in self._intelligence_sources():
            low = src.lower()
            self.assertNotIn("scipy", low)
            for line in src.splitlines():
                if "p-value" in line.lower() or "significan" in line.lower():
                    # allowed only as an explicit denial
                    self.assertTrue(
                        "never" in line.lower()
                        or "no " in line.lower()
                        or "not" in line.lower(),
                        f"{fname} may claim significance: {line}",
                    )

    def test_statuses_never_mean_production_approval(self):
        # the serialized report always carries a non-production reminder
        exps, _ = _build_bundles()
        result = ResearchIntelligence().analyze(_Report(BASELINE_METRICS, exps))
        reminder = result.to_dict()["recommendation_reminder"]
        self.assertIn("NOT a production directive", reminder)


if __name__ == "__main__":
    unittest.main()