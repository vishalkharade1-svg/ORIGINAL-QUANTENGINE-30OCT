"""
====================================================

QuantEngine

Autonomous AI Researcher -- orchestrator (Phase 9H)

The autonomous research-scientist loop, wired to the frozen 9A-9G
deterministic machinery. Given a population of OpportunityRecords
(9A), a candle series and a base configuration, it completes the
full evidence chain:

   QUESTION -> HYPOTHESIS -> WHY -> DATASET -> FEATURES -> EXPERIMENT
   -> BASELINE -> COUNTERFACTUAL RESULTS -> STATISTICAL RESULTS ->
   OOS RESULTS -> ROBUSTNESS -> CONCLUSION -> RECOMMENDATION

and records everything in Research Memory (dedup, next-suggestion).

Invariants maintained here:
   * provider-neutral: NullProvider always available; external
     providers are optional interpreters (numeric truth stays in
     9B-9G)
   * research-only: no production import, no order placement, no
     ledger / portfolio / account writes, no auto-promotion
   * no OOS bypass: VALIDATED requires the chronological OOS gate
   * INSUFFICIENT_EVIDENCE is returned, never guessed
   * failed experiments are retained, never pruned
   * deterministic ids throughout
====================================================
"""

from core.research.counterfactual import (
    CounterfactualConfig,
    classify_opportunity,
)
from core.research.researcher.types import (
    OBSERVATION,
    HYPOTHESIS,
    VALIDATED,
    REJECTED,
    INSUFFICIENT_EVIDENCE,
    BLOCKED,
    EvidenceContext,
    InvestigationReport,
    ResearchRecommendation,
    STANDING_LIMITATION,
)
from core.research.researcher.providers import (
    NullProvider,
    available_providers,
)
from core.research.researcher.memory import ResearchMemory
from core.research.researcher.planner import ResearchPlanner
from core.research.researcher.experiments import ExperimentExecutor
from core.research.researcher.evaluate import EvidenceEvaluator, _num

DEFAULT_BASE_CONFIG = CounterfactualConfig(
    params={
        "entry_model": "BREAKOUT_CONTINUATION",
        "rr": 2.0,
        "stop_mode": "EXISTING_STOP",
        "target_mode": "FIXED_RR",
    }
)


def build_context(records):
    """Deterministic EvidenceContext from a population of 9A records."""
    records = list(records or [])
    population = {}
    rejected_by_reason = {}
    rs = []
    for rec in records:
        cat = classify_opportunity(rec)
        population[cat] = population.get(cat, 0) + 1
        setup = getattr(rec, "setup", None) or {}
        reasons = setup.get("rejection_reasons") or []
        for reason in reasons:
            key = str(reason) or "UNKNOWN"
            rejected_by_reason[key] = rejected_by_reason.get(key, 0) + 1
        trade = getattr(rec, "trade", None) or {}
        r = trade.get("r")
        if r is not None:
            try:
                rs.append(float(r))
            except (TypeError, ValueError):
                pass

    filled = len(rs)
    expectancy = (sum(rs) / filled) if filled else None
    wins = sum(1 for v in rs if v > 0)
    win_rate = (100.0 * wins / filled) if filled else None

    notes = []
    if not records:
        notes.append("no opportunities supplied -- reasoning would be a guess")
    if filled == 0 and records:
        notes.append("no settled population evidence -- counterfactual "
                     "results would be vacuous")

    return EvidenceContext(
        records=len(records),
        filled=filled,
        population=population,
        rejected_by_reason=rejected_by_reason,
        expectancy=expectancy,
        avg_R=expectancy,
        win_rate=win_rate,
        notes=tuple(notes),
    )


class AutonomousResearcher:
    """Provider-neutral autonomous research scientist (research-only)."""

    def __init__(self, provider=None, memory=None, base_config=None,
                 candles=None, baseline_id="baseline", oos_fraction=0.2):
        self.provider = provider or NullProvider()
        self.memory = memory or ResearchMemory()
        self.base_config = base_config or DEFAULT_BASE_CONFIG
        self.candles = candles
        self.baseline_id = baseline_id
        self.oos_fraction = oos_fraction
        self.planner = ResearchPlanner(self.memory)
        self.evaluator = EvidenceEvaluator()

    # -------------------------------------------------

    def investigate(self, records, candles=None, base_config=None,
                    symbol="UNKNOWN"):
        """Run one autonomous investigation. Returns InvestigationReport
        (never mutates records, never writes a ledger)."""
        records = list(records or [])
        candles = candles if candles is not None else self.candles
        base_config = base_config if base_config is not None else self.base_config

        if candles is None:
            raise ValueError(
                "a candle series is required to run counterfactual "
                "experiments (no lookahead: only the supplied bars are "
                "ever read)"
            )

        context = build_context(records)

        provider = self.provider
        provider_available = provider.available()
        if not provider_available:
            provider = NullProvider()

        hypotheses, notes = self.planner.plan(
            context, provider, base_config=base_config,
        )
        planner_notes = list(notes)

        executor = ExperimentExecutor(
            candles,
            baseline_id=self.baseline_id,
            oos_fraction=self.oos_fraction,
        )

        runs = []
        experiment_ids = []
        recommendations = []
        oos_statuses = []
        for hypothesis in hypotheses:
            run = executor.execute(records, base_config, hypothesis)
            runs.append(run)
            for result in run.results:
                experiment_ids.append(result.experiment_id)
            recommendation = self.evaluator.conclude(
                run, context.expectancy, context
            )
            recommendations.append(recommendation)
            oos_statuses.append(_oos_mark(recommendation))

        if not recommendations:
            if context.vacuous:
                recommendations.append(_observation(
                    hypothesis_id="",
                    status=INSUFFICIENT_EVIDENCE,
                    question="Why reason without a population?",
                    statement="No opportunity population was supplied; any "
                              "hypothesis would be a guess, so none is "
                              "proposed.",
                    why="; ".join(context.notes) or "vacuous dataset",
                    score=0.5,
                    evidence=(_vacuous_evidence(context),),
                    next_step="supply a settled opportunity population",
                ))
            elif not hypotheses:
                recommendations.append(_observation(
                    hypothesis_id="",
                    status=OBSERVATION,
                    question="What does the supplied population show?",
                    statement="All planner hypothesis drafts were blocked "
                              "or none were applicable; the observed "
                              "population is recorded as-is.",
                    why="; ".join(planner_notes) or "no triggered rules",
                    score=1.0,
                    evidence=(_observation_evidence(context),),
                    next_step="resolve the blocked drafts or supply richer "
                              "opportunity evidence",
                ))

        report_status = _aggregate_status(recommendations)

        headline_question = (
            hypotheses[0].question if hypotheses
            else (recommendations[0].question if recommendations else "")
        )
        memory_nudge = ""
        if headline_question:
            memory_nudge = self.memory.next_suggestion(headline_question)

        investigation_id = self.memory.investigation_id_for(
            symbol, headline_question,
            [h.hypothesis_id for h in hypotheses],
        )

        if hypotheses:
            self.memory.record(
                investigation_id=investigation_id,
                question=headline_question,
                hypotheses=hypotheses,
                experiment_ids=experiment_ids,
                recommendation_statuses=[r.status for r in recommendations],
                oos_statuses=oos_statuses,
                report_status=report_status,
            )

        ranked = sorted(
            recommendations,
            key=lambda r: (r.score, r.recommendation_id),
            reverse=True,
        )

        return InvestigationReport(
            phase="9H",
            investigation_id=investigation_id,
            symbol=symbol,
            baseline=(_baseline_summary(context) or {}),
            context=context,
            hypotheses=tuple(hypotheses),
            recommendations=tuple(ranked),
            memory_nudge=memory_nudge,
            provider=(self.provider.name if self.provider.available()
                      else NullProvider().name),
            provider_available=True,
            status=report_status,
            production_ready=False,
            standing_limitations=(STANDING_LIMITATION,),
        )

    # -------------------------------------------------

    @staticmethod
    def availability():  # pragma: no cover - trivial passthrough
        return [
            {"name": p.name, "available": p.available(),
             "note": p.unavailable_note() if not p.available() else ""}
            for p in available_providers()
        ]


def _observation(hypothesis_id, status, question, statement, why,
                 score, evidence, next_step):
    import hashlib
    rec_id = "R" + hashlib.sha1(
        ("observation|%s|%s" % (question, status)).encode("utf-8")
    ).hexdigest()[:10]
    return ResearchRecommendation(
        recommendation_id=rec_id,
        hypothesis_id=hypothesis_id,
        kind="GENERAL",
        score=score,
        status=status,
        question=question,
        statement=statement,
        why=why,
        evidence=tuple(evidence),
        next_step=next_step,
        is_production_directive=False,
    )


def _vacuous_evidence(context):
    return {
        "records": context.records,
        "filled": context.filled,
        "population": dict(context.population),
        "note": "insufficient evidence; no claim issued",
    }


def _observation_evidence(context):
    return {
        "records": context.records,
        "filled": context.filled,
        "population": dict(context.population),
        "rejected_by_reason": dict(context.rejected_by_reason),
        "expectancy": context.expectancy,
    }


def _baseline_summary(context):
    return {
        "records": context.records,
        "filled": context.filled,
        "expectancy": _num(context.expectancy),
        "win_rate": _num(context.win_rate),
        "population": dict(context.population),
        "rejected_by_reason": dict(context.rejected_by_reason),
    }


def _oos_mark(recommendation):
    marks = []
    for package in recommendation.evidence:
        oos = (package or {}).get("oos") or {}
        marks.append(
            "oos_settled=%s" % oos.get("oos_settled", "na")
        )
    return "|".join(marks) or "none"


def _aggregate_status(recommendations):
    present = {r.status for r in recommendations}
    for status in (VALIDATED, HYPOTHESIS, OBSERVATION, REJECTED, BLOCKED):
        if status in present:
            return status
    return INSUFFICIENT_EVIDENCE