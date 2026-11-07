"""
====================================================

QuantEngine

Research Intelligence -- orchestrator (Phase 9E)

`ResearchIntelligence` consumes a 9D ResearchReport (already
produced, never resimulated) and produces a deterministic, immutable
`IntelligenceReport` of evidence-backed research recommendations.

It NEVER:
   * modifies strategy, execution, risk, portfolio or live/paper
     behaviour, or the ResearchReport it consumed (immutable);
   * promotes or optimises automatically (recommendation status is a
     research label, not an approval);
   * imports or calls any AI/LLM/ML model; it only packages evidence
     for a future interpreter;
   * fabricates confluence, directional or symbol evidence when the
     underlying 9D data is absent (reports *_UNAVAILABLE instead);
   * reinterprets Phase 7E's NO-GO as a production directive: the
     directional layer remains research-only and never emits a
     directional production rule.

Recommendation status (in priority order):
   BLOCKED            -- evidence insufficient to compare at all
                          (no usable experiment bundles)
   OBSERVATION        -- candidate == baseline band, or negligible
                          advantage, no material recovery
   HYPOTHESIS         -- candidate beats baseline with limited data
                          or recovery-only wins (small sample)
   PROMISING          -- candidate beats baseline + material
                          recovery + no loss-expansion + robust
                          (still research-only; OOS still required)
   INCONCLUSIVE       -- no comparison available (no deviations)
   REQUIRES_OOS       -- in-sample advantage that must be validated
                          OOS before any further consideration
   REJECTED           -- candidate LOSES to baseline on filled /
                          R / expectancy / win-rate / PF

A single LEAD recommendation is chosen deterministically as the first
of: PROMISING, then REQUIRES_OOS, then HYPOTHESIS; otherwise None.
====================================================
"""

from dataclasses import dataclass, field

from core.research.intelligence.recommendation import (
    Recommendation,
    recommendation_id_for,
)
from core.research.intelligence.recommendation_types import (
    OBSERVATION,
    HYPOTHESIS,
    PROMISING,
    INCONCLUSIVE,
    REJECTED,
    REQUIRES_OOS,
    BLOCKED,
    NON_ROBUST,
    OOS_REQUIRED,
    EVIDENCE_SMALL_SAMPLE,
    EVIDENCE_LIMITED,
)
from core.research.intelligence.evidence import (
    EvidencePackage,
    evidence_strength_for,
)
from core.research.intelligence.opportunity_recovery import (
    opportunity_recovery_insight,
)
from core.research.intelligence.parameter_insights import parameter_insights
from core.research.intelligence.directional_analysis import (
    directional_breakdown,
    symbol_breakdown,
)
from core.research.intelligence.confluence_analysis import (
    ConfluenceAnalysis,
    confluence_from_features,
)
from core.research.intelligence.robustness_gate import robustness_status_for
from core.research.intelligence.hypothesis import generate_hypotheses


def _symbol_metrics_for(exp_id, outcomes):
    """Per-symbol metrics from read-only 9C outcomes (never simulated).

    Returns {instrument_id: metrics}; empty when no outcomes supplied
    (reported as 'no symbol breakdown available', never fabricated).
    """
    if not outcomes:
        return {}
    from core.research.analyzer.experiment_metrics import group_metrics

    grouped = group_metrics(outcomes, ["instrument_id"]).get("instrument_id", {})
    return dict(grouped)


def _baseline_from_report(report):
    return getattr(report, "baseline_metrics", None) or {}


def _report_rejected(report):
    return dict(getattr(report, "rejected", None) or {})


def _blend(report, bundles, outcomes_by_experiment=None):
    """The core recommendation engine over a 9D report's experiments.

    Determines a status + reasoned metrics for each candidate.
    Returns (recommendations, insights_collection, evidence_list).

    `outcomes_by_experiment` optionally maps experiment_id to the
    already-produced 9C outcomes so symbol / directional insights can
    be computed from read-only evidence (NEVER resimulated). When
    absent the corresponding insight reports insufficient data rather
    than fabricating.
    """
    outcomes_by_experiment = outcomes_by_experiment or {}
    baseline = _baseline_from_report(report)
    bas_filled = baseline.get("filled", 0) or 1
    bas_wr = baseline.get("win_rate", 0.0)
    bas_pf = baseline.get("profit_factor", 0.0)
    bas_ex = baseline.get("expectancy", 0.0)
    bas_mae = baseline.get("avg_MAE", 0.0)
    bas_mfe = baseline.get("avg_MFE", 0.0)

    insights_package = {
        "recovery": [],
        "parameter": [],
        "directional": {},
        "symbol": {},
    }
    evidence_list = []
    recommendations = []

    for exp_id, exp in bundles:
        cfg = exp.config
        exp_params = dict(getattr(cfg, "params", None) or {})
        cand_metrics = getattr(exp, "metrics", None) or {}
        cand_mae = cand_metrics.get("avg_MAE", 0.0)
        cand_mfe = cand_metrics.get("avg_MFE", 0.0)
        comparison = getattr(exp, "comparison", None)
        comp = comparison.to_dict() if comparison else {}
        recov = getattr(exp, "recovery", None)
        recov_dict = recov.to_dict() if recov else {}
        robustness = getattr(exp, "robustness", None)
        robs = list(robustness) if robustness else []
        robs = list(dict.fromkeys(robs))

        rec_recovered = recov_dict.get("recovered", 0)
        rec_unsettled = recov_dict.get("recovered_unsettled", 0) or 0
        rec_incremental_R = recov_dict.get("incremental_R", 0.0) or 0.0
        rec_incremental_pnl = recov_dict.get("incremental_pnl", 0.0) or 0.0
        cand_filled = cand_metrics.get("filled", 0) or 0
        cand_wins = cand_metrics.get("wins", 0) or 0
        cand_losses = cand_metrics.get("losses", 0) or 0
        cand_ex = cand_metrics.get("expectancy", 0.0) or 0.0
        cand_r = cand_metrics.get("total_R", 0.0) or 0.0
        cand_wr = cand_metrics.get("win_rate", 0.0) or 0.0
        cand_pf = cand_metrics.get("profit_factor", 0.0) or 0.0
        cand_resent = cand_metrics.get("settled", 0) or 0

        # evidence package
        evidence = EvidencePackage(
            experiment_id=exp_id,
            config=_present_cfg(exp),
            baseline_metrics=baseline,
            candidate_metrics=cand_metrics,
            comparison=comp,
            recovery=recov_dict,
            robustness=robs,
            sample_size=cand_resent,
        )
        evidence_list.append(evidence)

        # recovery insight
        try:
            rec_insight = opportunity_recovery_insight(exp)
        except Exception:
            rec_insight = None
        if rec_insight is not None:
            insights_package["recovery"].append(rec_insight.to_dict())

        # directional / symbol (read-only evidence; never resimulated)
        directional_evidence = getattr(exp, "directional", None) or {}
        insights_package["directional"] = directional_breakdown(
            [(exp_id, directional_evidence, robs)]
        )
        symbol_metric_map = _symbol_metrics_for(
            exp_id, outcomes_by_experiment.get(exp_id),
        )
        insights_package["symbol"][exp_id] = symbol_breakdown(
            exp_id, symbol_metric_map, cand_metrics,
        )

        # -------- recommendation grading against baseline --------
        delta_filled = cand_filled - bas_filled
        delta_ex = cand_ex - bas_ex
        delta_wr = cand_wr - bas_wr
        delta_pf = cand_pf - bas_pf
        delta_r = (cand_r - (bas_filled * bas_ex)) / bas_filled \
            if bas_filled else 0.0
        delta_mae = cand_mae - bas_mae
        delta_mfe = cand_mfe - bas_mfe

        has_advantage = (
            delta_r > 0.0
            and cand_ex >= 0
            and delta_wr >= 0.0
            and delta_pf >= 0.0
        )

        strength = evidence.evidence_strength
        rob_status = robustness_status_for(
            strength, cand_resent, robs,
            incremental_wins=recov_dict.get("recovered_wins", 0),
            incremental_losses=recov_dict.get("recovered_losses", 0),
            has_advantage=has_advantage,
        )

        # category determination
        category = _category_for(exp_params)
        affected = _affected_categories(recov_dict)

        # public status
        status = INCONCLUSIVE
        if not bundles:
            status = BLOCKED
        elif delta_filled == 0 and delta_ex == 0.0 and delta_wr == 0.0 and \
                delta_pf == 0.0:
            status = OBSERVATION
        elif has_advantage:
            if strength == EVIDENCE_SMALL_SAMPLE or rob_status == NON_ROBUST:
                status = HYPOTHESIS
            elif strength == EVIDENCE_LIMITED and rob_status == OOS_REQUIRED:
                status = REQUIRES_OOS
            else:
                status = PROMISING
        else:
            status = REJECTED

        rec = Recommendation(
            recommendation_id=recommendation_id_for(
                category, [exp_id], exp_params
            ),
            category=category,
            status=status,
            title=_title(category, exp_params),
            hypothesis=_hypothesis_text(
                has_advantage, affected, recov_dict, exp_params
            ),
            evidence_strength=strength,
            affected_opportunity_categories=tuple(sorted(affected)),
            affected_directions=tuple(
                sorted(insights_package["directional"].get(exp_id, {})
                       .get("directions", {}).keys())
            ),
            affected_symbols=tuple(
                r["symbol"] for r in
                insights_package["symbol"][exp_id].get("positive_symbols", [])
            ),
            baseline_experiment_id="baseline",
            candidate_experiment_ids=(exp_id,),
            parameters_changed=dict(exp_params),
            baseline_metrics=baseline,
            candidate_metrics=cand_metrics,
            incremental_fills=rec_recovered,
            recovered_opportunities=recov_dict.get("recovered", 0),
            recovered_wins=recov_dict.get("recovered_wins", 0),
            recovered_losses=recov_dict.get("recovered_losses", 0),
            recovered_unsettled=rec_unsettled,
            recovered_R=rec_incremental_R,
            recovered_pnl=rec_incremental_pnl,
            incremental_R=delta_r,
            expectancy_delta=delta_ex,
            win_rate_delta=delta_wr,
            profit_factor_delta=delta_pf,
            mae_delta=delta_mae,
            mfe_delta=delta_mfe,
            robustness_status=rob_status,
            sample_size=cand_resent,
            warnings=tuple(robs),
            recommendation_status=status,
        )
        recommendations.append(rec)

    recommendations.sort(key=lambda r: r.recommendation_id)
    return recommendations, insights_package, evidence_list


def _present_cfg(exp):
    cfg = getattr(exp, "config", None)
    if cfg is None:
        return {}
    params = dict(getattr(cfg, "params", None) or {})
    if hasattr(cfg, "baseline"):
        params["baseline"] = cfg.baseline
    if hasattr(cfg, "outcome_bars"):
        params["outcome_bars"] = cfg.outcome_bars
    if hasattr(cfg, "recovery_bars"):
        params["recovery_bars"] = cfg.recovery_bars
    return params


def _category_for(params):
    if "rr" in params and len(params) == 1:
        return "RR_ANALYSIS"
    if "expiry" in params and len(params) == 1:
        return "EXPIRY_ANALYSIS"
    if "entry_offset" in params or "entry_offset_atr" in params:
        return "ENTRY_OFFSET_ANALYSIS"
    if "entry_window" in params:
        return "MISSED_CONTINUATION"
    if "entry_model" in params:
        return "ENTRY_RECOVERY"
    if "stop_mode" in params or "target_mode" in params:
        return "STOP_TARGET_ANALYSIS"
    return "GENERAL"


def _affected_categories(recov_dict):
    transitions = recov_dict.get("transitions", {})
    affected = set(
        t.split("->", 1)[0].strip()
        for t in transitions if "->" in t
    )
    return {c for c in affected if c in ("REJECTED", "ENTRY_NOT_REACHED",
                                         "MISSED_CONTINUATION", "INVALIDATED")}


def _title(category, params):
    return f"{category} insight (params: {_short_params(params)})"


def _hypothesis_text(has_advantage, affected, recov_dict, params):
    rec_wins = recov_dict.get("recovered_wins", 0)
    rec_losses = recov_dict.get("recovered_losses", 0)
    if has_advantage:
        return (f"candidate {_short_params(params)} improves the "
                f"baseline (expectancy, total-R, win-rate) "
                f"and recovers {len(affected)} opportunity "
                f"categories ({rec_wins} wins / {rec_losses} losses).")
    return (f"candidate {_short_params(params)} did NOT beat the "
            f"baseline on filled / R / expectancy metrics.")


def _short_params(params):
    return ", ".join(f"{k}={v}" for k, v in sorted(params.items()))


class ResearchIntelligence:
    """Deterministic, evidence-based research intelligence layer."""

    def __init__(self, horizon="9E"):
        self.horizon = horizon

    def analyze(self, report, confluence=None, outcomes_by_experiment=None):
        """Produce an IntelligenceReport from a 9D ResearchReport.

        report: a 9D ResearchReport (with .experiments of
                ExperimentAnalysis). Confluence is optional and is
                never fabricated. outcomes_by_experiment optionally
                maps experiment_id to already-produced 9C outcomes so
                symbol / directional evidence is derived from read-only
                facts (NEVER resimulated).
        """
        experiments = list(getattr(report, "experiments", None) or [])
        bundles = [
            (e.experiment_id, e) for e in experiments
            if getattr(e, "config", None) is not None
            and getattr(e, "experiment_id", None)
        ]

        recommendations = []
        insights = {}
        evidence_list = []
        if bundles:
            recommendations, insights, evidence_list = _blend(
                report, bundles, outcomes_by_experiment,
            )
        else:
            insights = {
                "recovery": [], "parameter": [],
                "directional": {}, "symbol": {},
            }

        # parameter insights (multi-experiment, moved only if they vary)
        p_ins = []
        if bundles:
            p_ins = parameter_insights([
                (e.config, (getattr(e, "metrics", None) or {}),
                 e.experiment_id)
                for _id, e in bundles
            ])
        insights["parameter"] = [pi.to_dict() for pi in p_ins]

        # confluence: NEVER fabricated
        ca = confluence_from_features(confluence) if confluence else (
            ConfluenceAnalysis()
        )

        # hypotheses over recommendations + insights
        hypotheses = generate_hypotheses(
            recommendations,
            parameter_insights=p_ins,
            directional_by_id=insights.get("directional"),
        )

        lead = _pick_lead(recommendations)
        status = _orchestrator_status(recommendations, bundles, experiments)

        return IntelligenceReport(
            phase="9E",
            status=status,
            lead=lead,
            recommendations=tuple(recommendations),
            evidence=tuple(evidence_list),
            confluence=ca,
            insights=insights,
            baseline=_baseline_from_report(report),
            hypotheses=tuple(hypotheses),
            rejected=frozenset(_report_rejected(report).keys()),
            horizon=self.horizon,
        )


def _pick_lead(recommendations):
    for rank in (PROMISING, REQUIRES_OOS, HYPOTHESIS):
        for rec in recommendations:
            if rec.status == rank:
                return rec
    return None


def _orchestrator_status(recommendations, bundles, experiments):
    recs = list(recommendations)
    if not recs:
        return BLOCKED
    has_promising = any(r.status == PROMISING for r in recs)
    has_others = any(r.status in (REQUIRES_OOS, HYPOTHESIS, OBSERVATION,
                                  REJECTED, INCONCLUSIVE) for r in recs)
    if has_promising or has_others:
        return "RECOMMENDATIONS_AVAILABLE"
    return BLOCKED


@dataclass(frozen=True)
class IntelligenceReport:
    """Immutable, deterministic output of the 9E intelligence layer."""

    phase: str
    status: str
    lead: Recommendation
    recommendations: tuple
    evidence: tuple
    confluence: ConfluenceAnalysis
    insights: dict
    baseline: dict
    hypotheses: tuple
    rejected: frozenset
    horizon: str

    # -------------------------------------------------

    def to_dict(self):
        return {
            "phase": "9E",
            "horizon": self.horizon,
            "status": self.status,
            "lead": _lead_to_dict(self.lead),
            "recommendations": [r.to_dict() for r in self.recommendations],
            "evidence": [e.to_dict() for e in self.evidence],
            "confluence": self.confluence.to_dict(),
            "insights": self.insights,
            "baseline": self.baseline,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "rejected": sorted(self.rejected),
            "recommendation_reminder": (
                "Deterministic research evidence only. NOT a production "
                "directive. No configuration is promoted automatically. "
                "No statistical significance is claimed. OOS validation "
                "is required before any production consideration."
            ),
        }

    def render(self):
        """Deterministic, human-readable text rendering."""
        lines = [
            "=" * 60,
            f"PHASE 9E RESEARCH INTELLIGENCE ({self.horizon})",
            "=" * 60,
            f"status: {self.status}",
            "",
        ]
        if self.lead is not None:
            lines.append(
                f"LEAD: [{self.lead.status}] {self.lead.category}\n"
                f"    {self.lead.title}\n"
                f"    hypothesis: {self.lead.hypothesis}\n"
                f"    evidence: {self.lead.evidence_strength} "
                f"({self.lead.sample_size} settled)\n"
                f"    robustness: {self.lead.robustness_status}",
            )
        if self.recommendations:
            lines.append("RECOMMENDATIONS:")
            for rec in self.recommendations:
                delta = (" +" if rec.expectancy_delta >= 0 else " ")
                lines.append(
                    f"  [{rec.status}] {rec.category} "
                    f"expectancy_delta={delta}{rec.expectancy_delta:.2f} "
                    f"recovered={rec.recovered_wins}W/{rec.recovered_losses}L"
                )
        else:
            lines.append("RECOMMENDATIONS: (none — insufficient evidence)")

        lines.append(
            "\nConfluence: "
            + self.confluence.status()
            + " — never fabricated, never a lookahead source."
        )
        lines.append(
            "\nReminder: research only. No production changes in this phase."
        )
        return "\n".join(lines)


def _lead_to_dict(lead):
    return lead.to_dict() if lead is not None else None