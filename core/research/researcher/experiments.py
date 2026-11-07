"""
====================================================

QuantEngine

Autonomous AI Researcher -- experiment executor (Phase 9H)

Runs a designed Hypothesis through the FROZEN deterministic research
machinery and packages per-configuration evidence:

   9C CounterfactualRunner.grid  -> (config, outcomes) bundles
   9D ResearchAnalyzer.analyze   -> ResearchReport (baseline/comparison/
                                     robustness/directional)
   9E ResearchIntelligence       -> IntelligenceReport (recommendations,
                                     evidence strength, OOS flags)
   9F FeatureAnalyzer            -> feature/outcome dependency evidence
   9G StatisticalBaseline        -> full-sample stats + a chronological
                                     OOS fold (temporal_split, no
                                     lookahead)

The executor NEVER trades, never writes a ledger, never mutates the
source records and never resimulates outside the supplied candle
set. It only reads 9A records + supplied candles with the already
supported semantics.
====================================================
"""

from dataclasses import dataclass, field

from core.research.counterfactual import CounterfactualRunner
from core.research.analyzer import ResearchAnalyzer
from core.research.intelligence import ResearchIntelligence
from core.research.researcher.types import ExperimentResult


@dataclass(frozen=True)
class ExperimentRun:
    hypothesis: object
    results: tuple = field(default_factory=tuple)
    report: object = None
    intelligence: object = None

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis.hypothesis_id,
            "kind": self.hypothesis.kind,
            "experiments": [r.to_dict() for r in self.results],
        }


class ExperimentExecutor:
    """Deterministic executor over the frozen 9B-9F machinery."""

    def __init__(self, candles, baseline_id="baseline", oos_fraction=0.2):
        self.candles = candles
        self.baseline_id = baseline_id
        self.oos_fraction = oos_fraction
        self.base_config = None

    # -------------------------------------------------

    def execute(self, records, base_config, hypothesis):
        """Run one hypothesis; returns ExperimentRun (evidence, never
        directives)."""
        records = list(records)
        self.base_config = base_config

        runner = CounterfactualRunner(
            self.candles,
            baseline_id=self.baseline_id,
        )
        bundles = runner.grid(
            records, base_config, **hypothesis.overrides
        )
        bundles = list(bundles)

        report = ResearchAnalyzer().analyze(
            records, bundles, baseline_id=self.baseline_id
        )
        intelligence = ResearchIntelligence().analyze(report)

        exp_by_id = {
            e.experiment_id: e for e in report.experiments
        }
        rec_by_exp = {}
        for rec in intelligence.recommendations:
            for eid in rec.candidate_experiment_ids:
                rec_by_exp.setdefault(eid, rec)

        results = [
            self._result(cfg, outcomes, records, exp_by_id, rec_by_exp)
            for cfg, outcomes in bundles
        ]
        return ExperimentRun(
            hypothesis=hypothesis,
            results=tuple(results),
            report=report,
            intelligence=intelligence,
        )

    # -------------------------------------------------

    def _result(self, config, outcomes, records, exp_by_id, rec_by_exp):
        exp_id = config.experiment_id()
        analysis = exp_by_id.get(exp_id)
        metrics = dict(analysis.metrics) if analysis else {}
        settled = metrics.get("settled", 0)
        filled = metrics.get("filled", 0)

        rec = rec_by_exp.get(exp_id)
        rec_status = getattr(rec, "status", "") if rec else ""
        robustness_status = getattr(rec, "robustness_status", "") if rec else ""
        evidence_strength = (
            getattr(rec, "evidence_strength", "") if rec else ""
        )

        categories = {}
        for o in outcomes:
            cat = getattr(o, "category", None) or (
                getattr(o, "category", "") or "UNKNOWN"
            )
            categories[cat] = categories.get(cat, 0) + 1

        statistical = {}
        oos = {}
        try:
            from core.research.ml.statistics import StatisticalBaseline

            def _stat(name, rows):
                try:
                    return StatisticalBaseline(name=name, rows=rows).to_dict()
                except Exception:
                    return {"n": 0, "notes": "statistics unavailable"}

            statistical = _stat(exp_id, outcomes)

            from core.research.ml.split import temporal_split
            split = temporal_split(outcomes, oos_fraction=self.oos_fraction)
            oos_rows = split.oos_items()
            oos_stats = _stat("oos", oos_rows)
            oos = {
                "oos_filled": len(oos_rows),
                "oos_settled": (
                    oos_stats.get("wins", 0) + oos_stats.get("losses", 0)
                ),
                "oos_expectancy": oos_stats.get("expectancy"),
                "oos_win_rate": oos_stats.get("win_rate"),
                "fraction": self.oos_fraction,
            }
        except Exception:
            statistical = {"n": 0, "notes": "statistics unavailable"}
            oos = {"note": "OOS fold unavailable"}

        features = {}
        try:
            from core.research.features import FeatureAnalyzer
            out_map = {getattr(o, "opportunity_id", ""): o for o in outcomes}
            frep = FeatureAnalyzer().analyze(
                records, self.candles, outcomes=out_map
            )
            dep = getattr(frep, "dependency", None)
            conf_status = getattr(
                getattr(frep, "confluence", None), "status", lambda: ""
            )()
            features = {
                "feature_snapshots": len(getattr(frep, "snapshots", ()) or ()),
                "dependency_features": len(getattr(dep, "features", []) or []),
                "confluence": conf_status,
            }
        except Exception:
            features = {"note": "feature layer unavailable"}

        return ExperimentResult(
            experiment_id=exp_id,
            config=config,
            filled=filled,
            settled=settled,
            metrics=metrics,
            comparison=(
                analysis.comparison.to_dict() if analysis else {}
            ),
            robustness=tuple(analysis.robustness) if analysis else (),
            categories=categories,
            evidence_strength=evidence_strength,
            recommendation_status=rec_status,
            robustness_status=robustness_status,
            statistical=statistical,
            oos=oos,
            features=features,
        )