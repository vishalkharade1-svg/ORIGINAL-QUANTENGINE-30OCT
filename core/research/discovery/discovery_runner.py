"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- discovery runner

The deterministic orchestrator. It consumes the frozen 9A-9I evidence
(read-only) and executes the discovery pipeline:

   1. dataset          -- consume the 9I research dataset (JOURNAL rows
                          are normalized from the supplied records);
   2. gaps             -- hypothesis_generator.detect_gaps (9I queries);
   3. hypotheses       -- deterministic, evidence-gated recovery-first
                          candidate changes (supported 9B/9C axes only);
   4. schedule         -- deterministic order + explicit budget +
                          research-memory dedup (injected hypotheses
                          are NEVER suppressed);
   5. execute          -- 9C CounterfactualRunner.grid (frozen sim) ->
                          9D ResearchAnalyzer -> 9E ResearchIntelligence
                          -> 9G temporal_split OOS + StatisticalBaseline;
   6. gates            -- robustness_filter.DiscoveryGates (statuses,
                          7E NO-GO, directional safety, never-validate-
                          without-OOS);
   7. recovery         -- recovery_discovery.recovery_findings (live);
   8. confluence       -- confluence_discovery (9F feature rows, observed
                          values only);
   9. report           -- discovery_report.DiscoveryReport (byte-
                          deterministic, all experiments retained).

Boundaries: the runner never mutates records / candles / a caller
dataset; never touches a ledger, order, account, portfolio or
production strategy/risk state; never invents parameters; never looks
ahead (OOS is the newest chronological fold; features are decision-time
only); and never emits a promotion token.
====================================================
"""

from core.research.counterfactual import CounterfactualRunner
from core.research.analyzer import ResearchAnalyzer
from core.research.intelligence import ResearchIntelligence
from core.research.ml import StatisticalBaseline
from core.research.ml.split import temporal_split
from core.research.dataset import (
    ResearchDataset,
    collect_journal,
    DatasetSource as S,
    SOURCES,
)

from core.research.discovery.constants import (
    BLOCKED,
    PROMISING,
    INCONCLUSIVE,
)
from core.research.discovery.candidate_space import (
    validate_overrides,
    vocabulary,
)
from core.research.discovery.discovery_types import (
    DiscoveryExperiment,
    DiscoveryFinding,
    short_id,
)
from core.research.discovery.hypothesis_generator import (
    detect_gaps,
    generate_hypotheses,
    dedup_hypotheses,
)
from core.research.discovery.experiment_scheduler import schedule
from core.research.discovery.baseline_comparator import (
    compare_experiment,
    economic_assessment,
)
from core.research.discovery.recovery_discovery import recovery_findings
from core.research.discovery.confluence_discovery import confluence_findings
from core.research.discovery.robustness_filter import (
    DiscoveryGates,
    direction_evidence,
    gate_score as _gate_score,
)
from core.research.discovery.discovery_report import DiscoveryReport
from research.integrations.delta_mcp_discovery_context import (
    summarize_mcp_context, context_limitations,
)


_FINDING_STATEMENT = {
    "VALIDATED": (
        "research-validated finding: in-sample advantage, robustness "
        "clear, chronological OOS confirms -- NEVER production-ready"
    ),
    "REQUIRES_OOS": (
        "candidate requires a chronological OOS fold before any "
        "conclusion; OOS cannot be bypassed"
    ),
    "PROMISING": (
        "positive in-sample evidence but the robustness/economic gate "
        "is not yet clear; candidate stands, not promoted"
    ),
    "INCONCLUSIVE": (
        "insufficient settled population; the run is retained for "
        "later accumulation"
    ),
    "REJECTED": (
        "hypothesis not supported by the evidence; the negative result "
        "is retained, not hidden"
    ),
    "BLOCKED": (
        "experiment blocked (unrunnable or 7E NO-GO surface preserved)"
    ),
}

_NEXT_STEP = {
    "VALIDATED": "escalate to the OOS/walk-forward milestone before any production path",
    "REQUIRES_OOS": "collect later-dated opportunity outcomes and re-validate out-of-sample",
    "PROMISING": "clear the robustness/economic gate before further consideration",
    "INCONCLUSIVE": "accumulate a larger settled population",
    "REJECTED": "do not re-probe the same axis without new opportunity evidence",
    "BLOCKED": "unblock or drop the hypothesis; consult the gate reasons",
}


class DiscoveryRunner:
    """Deterministic orchestrator of one discovery run."""

    def __init__(self, candles, baseline_id="baseline", oos_fraction=0.2,
                 gates=None):
        self.candles = list(candles or ())
        self.baseline_id = baseline_id
        self.oos_fraction = oos_fraction
        self.gates = gates or DiscoveryGates()

    # -------------------------------------------------

    def run(self, records, base_config, dataset=None, symbol="UNKNOWN",
            memory=None, budget=None, extra_hypotheses=()):
        records = list(records)
        ds = dataset if dataset is not None else ResearchDataset()
        ds.add_rows(collect_journal(records))

        gaps = detect_gaps(ds)
        mcp_context = summarize_mcp_context(ds, symbol=symbol)
        generated = generate_hypotheses(ds, base_config, symbol=symbol)
        hypotheses = dedup_hypotheses(
            list(generated) + list(extra_hypotheses or ())
        )
        scheduled, skipped = schedule(hypotheses, memory=memory,
                                      budget=budget)

        runner = CounterfactualRunner(
            self.candles, baseline_id=self.baseline_id
        )
        experiments = []
        outcomes_by_exp = {}
        for hypothesis in scheduled:
            exp_list, out_map = self._execute(
                runner, records, base_config, hypothesis
            )
            experiments.extend(exp_list)
            outcomes_by_exp.update(out_map)

        recovery = recovery_findings(records, outcomes_by_exp)
        recovered_ids = set(recovery.get("recovered_observations", ()))
        confluence = confluence_findings(ds, recovered_ids)
        findings = self._findings(experiments, confluence)

        if memory is not None:
            self._record_memory(memory, hypotheses, experiments)

        return DiscoveryReport.build(
            symbol=symbol,
            dataset_shape=self._dataset_shape(ds),
            vocabulary=vocabulary(),
            gaps=gaps,
            hypotheses=hypotheses,
            skipped=skipped,
            experiments=tuple(experiments),
            findings=findings,
            recovery=recovery,
            confluence=confluence,
            limitations=(self._limitations(ds, gaps, scheduled, recovery,
                                            confluence)
                          + context_limitations(mcp_context)),
            next_research=(
                "OOS / walk-forward re-validation of PROMISING and "
                "REQUIRES_OOS candidates (9M)",
                "feature/regime segmentation of REQUIRES_OOS candidates",
                "multi-model AI review of VALIDATED findings (9L)",
            ),
            seven_e={
                "no_go_preserved": True,
                "directive": (
                    "7E directional-breakout surface remains NO-GO; "
                    "discovery emits no promotion"
                ),
            },
        )

    # -------------------------------------------------

    def _execute(self, runner, records, base_config, hypothesis):
        """Execute one hypothesis; returns (experiments, outcomes map)."""
        try:
            overrides = validate_overrides(hypothesis.overrides)
        except ValueError as exc:
            return (
                [self._blocked(hypothesis, f"invalid candidate: {exc}")],
                {},
            )

        try:
            bundles = list(runner.grid(records, base_config, **overrides))
        except Exception as exc:  # deterministic capture, never crash
            return (
                [self._blocked(hypothesis, f"experiment could not run: {exc}")],
                {},
            )

        if not bundles:
            return (
                [self._blocked(hypothesis, "empty parameter grid")],
                {},
            )

        out_map = {cfg.experiment_id(): outcomes for cfg, outcomes in bundles}

        try:
            report = ResearchAnalyzer().analyze(
                records, bundles, baseline_id=self.baseline_id
            )
        except Exception as exc:
            experiments = []
            for cfg, outcomes in bundles:
                eid = cfg.experiment_id()
                experiments.append(DiscoveryExperiment(
                    experiment_id=eid,
                    hypothesis_id=hypothesis.hypothesis_id,
                    params=self._params(cfg),
                    metrics={},
                    comparison={},
                    recovery={},
                    status=BLOCKED,
                    reasons=(f"9D analysis failed: {exc}",),
                    score=_gate_score(BLOCKED),
                    evidence=(eid,),
                ))
            return experiments, out_map

        intelligence = ResearchIntelligence().analyze(report)
        exp_by_id = {
            e.experiment_id: e for e in report.experiments
        }
        rec_by_exp = {}
        for rec in intelligence.recommendations:
            for eid in getattr(rec, "candidate_experiment_ids", ()) or ():
                rec_by_exp.setdefault(eid, rec)

        experiments = []
        for cfg, outcomes in bundles:
            eid = cfg.experiment_id()
            analysis = exp_by_id.get(eid)
            metrics = dict(analysis.metrics) if analysis else {}
            comp = compare_experiment(analysis, report.baseline_metrics)

            rec = rec_by_exp.get(eid)
            research_evidence = {
                "recommendation_status": (
                    getattr(rec, "status", "") if rec else ""
                ),
                "robustness_status": (
                    getattr(rec, "robustness_status", "") if rec else ""
                ),
                "evidence_strength": (
                    getattr(rec, "evidence_strength", "") if rec else ""
                ),
            }

            robustness = tuple(analysis.robustness) if analysis else ()
            oos = self._oos(outcomes)
            statistical = self._statistical(outcomes)
            dir_evidence = direction_evidence(hypothesis, outcomes)
            exp_recovery = recovery_findings(
                records, {eid: outcomes}
            )
            economic = economic_assessment(
                metrics,
                report.baseline_metrics,
                recovery=exp_recovery,
            )

            status, reasons = self.gates.evaluate(
                hypothesis,
                metrics=metrics,
                comparison=comp["comparison"],
                robustness=robustness,
                economic=economic.to_dict(),
                oos=oos,
                dir_evidence=dir_evidence,
                research_evidence=research_evidence,
            )

            experiments.append(DiscoveryExperiment(
                experiment_id=eid,
                hypothesis_id=hypothesis.hypothesis_id,
                params=self._params(cfg),
                metrics=metrics,
                comparison=comp["comparison"],
                recovery=exp_recovery,
                robustness=robustness,
                statistical=statistical,
                oos=oos,
                economic=economic.to_dict(),
                direction_evidence=dir_evidence,
                research_evidence=research_evidence,
                population_note=comp["population_note"],
                status=status,
                reasons=reasons,
                score=_gate_score(status),
                evidence=(eid,) + tuple(hypothesis.evidence),
            ))
        return experiments, out_map

    # -------------------------------------------------

    def _record_memory(self, memory, hypotheses, experiments):
        """Persist discovery evidence into the 9H research memory so a
        later run deterministically skips already-studied ideas. Never
        suppresses deliberately-requested (injected) experiments."""
        by_hypothesis = {}
        for e in experiments:
            by_hypothesis.setdefault(e.hypothesis_id, []).append(e)
        for hypothesis in hypotheses:
            if hypothesis.injected:
                continue
            if not hypothesis.overrides:
                continue
            matched = by_hypothesis.get(hypothesis.hypothesis_id, [])
            try:
                memory.record(
                    investigation_id=short_id(
                        "I", hypothesis.symbol, hypothesis.question
                    ),
                    question=hypothesis.question,
                    hypotheses=[hypothesis],
                    experiment_ids=[e.experiment_id for e in matched],
                    recommendation_statuses=[
                        e.status for e in matched
                    ],
                    oos_statuses=[
                        str(e.oos.get("oos_settled")) for e in matched
                    ],
                    report_status="9J_DISCOVERY_COMPLETE",
                )
            except Exception:
                # research memory is best-effort; it never crashes a run
                pass

    @staticmethod
    def _params(cfg):
        if cfg is None:
            return {}
        if hasattr(cfg, "to_dict"):
            return dict(cfg.to_dict() or {})
        params = getattr(cfg, "params", None)
        return dict(params) if isinstance(params, dict) else {}

    def _blocked(self, hypothesis, reason):
        return DiscoveryExperiment(
            experiment_id="BLOCKED-%s" % hypothesis.hypothesis_id,
            hypothesis_id=hypothesis.hypothesis_id,
            params=dict(hypothesis.overrides),
            metrics={},
            comparison={},
            recovery={},
            status=BLOCKED,
            reasons=(reason,),
            score=_gate_score(BLOCKED),
            evidence=tuple(hypothesis.evidence),
        )

    def _statistical(self, outcomes):
        try:
            return StatisticalBaseline(
                name="full", rows=outcomes
            ).to_dict()
        except Exception:
            return {"n": 0, "notes": "statistics unavailable"}

    def _oos(self, outcomes):
        try:
            split = temporal_split(outcomes, oos_fraction=self.oos_fraction)
            oos_rows = split.oos_items()
            oos_stats = StatisticalBaseline(
                name="oos", rows=oos_rows
            ).to_dict()
            return {
                "oos_filled": len(oos_rows),
                "oos_settled": (
                    oos_stats.get("wins", 0) + oos_stats.get("losses", 0)
                ),
                "oos_expectancy": oos_stats.get("expectancy"),
                "oos_win_rate": oos_stats.get("win_rate"),
                "fraction": self.oos_fraction,
                "chronological": True,
            }
        except Exception:
            return {"note": "OOS fold unavailable"}

    # -------------------------------------------------

    @staticmethod
    def _findings(experiments, confluence):
        findings = []
        for e in experiments:
            findings.append(DiscoveryFinding(
                hypothesis_id=e.hypothesis_id,
                experiment_id=e.experiment_id,
                status=e.status,
                statement=_FINDING_STATEMENT.get(
                    e.status, "research finding"
                ),
                evidence=tuple(e.evidence),
                next_step=_NEXT_STEP.get(e.status, ""),
            ))
        for assoc in (confluence or {}).get("associations", ()) or ():
            if assoc.get("recovered", 0) <= 0:
                continue
            strong = assoc["n"] >= 3 and assoc["recovery_rate"] >= 0.6
            status = PROMISING if strong else INCONCLUSIVE
            findings.append(DiscoveryFinding(
                hypothesis_id="confluence",
                experiment_id="confluence",
                status=status,
                statement=(
                    f"observed association {assoc['feature']}="
                    f"{assoc['value']} with {assoc['recovered']}/"
                    f"{assoc['n']} recovered observations (association "
                    "evidence only)"
                ),
                evidence=tuple(assoc.get("evidence", ()) or ()),
                next_step=(
                    "validate the association under a chronological OOS "
                    "fold before any conclusion"
                ),
            ))
        return tuple(sorted(findings, key=lambda f: f.finding_id))

    @staticmethod
    def _dataset_shape(ds):
        return {
            "observations": len(ds.observation_ids() or []),
            "rows_by_source": {
                src: len(ds.rows(src)) for src in SOURCES
            },
        }

    @staticmethod
    def _limitations(ds, gaps, scheduled, recovery, confluence):
        limitations = [
            "counterfactual evidence is ASSOCIATION research, not "
            "production validation",
            "recovered configurations are surfaced as candidates; "
            "promotion requires a later OOS/walk-forward milestone",
            "feature confluence exists only where decision-time "
            "FeatureSnapshot evidence is present (never fabricated)",
        ]
        if not gaps:
            limitations.append(
                "no opportunity gaps were identifiable from the supplied "
                "dataset; no hypotheses generated"
            )
        if not scheduled:
            limitations.append(
                "no executable experiments were scheduled; the report is "
                "empty by evidence, not by omission"
            )
        if not (recovery or {}).get("recovery_count", 0):
            limitations.append(
                "no recovered wins were identified among the "
                "non-captured baseline population under the executed "
                "configurations"
            )
        if not (confluence or {}).get("feature_availability"):
            limitations.append(
                "no decision-time feature evidence available; confluence "
                "associations were NOT synthesized"
            )
        return tuple(sorted(limitations))