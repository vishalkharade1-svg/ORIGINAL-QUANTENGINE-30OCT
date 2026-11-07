"""
====================================================

QuantEngine

Autonomous AI Researcher -- evidence evaluator (Phase 9H)

The deterministic judge. It converts executed counterfactual +
statistical + OOS evidence into a CONCLUSION and a RECOMMENDATION,
under an explicit, documented ladder:

   1. no experiments executed            -> INSUFFICIENT_EVIDENCE
   2. best sample below MIN_SETTLED      -> INSUFFICIENT_EVIDENCE
                                            (never guessed)
   3. no advantage vs baseline           -> REJECTED (kept evidence)
   4. robustness gate not clear (9E/9D)  -> downgrade to HYPOTHESIS
   5. OOS fold too small / negative      -> HYPOTHESIS / REJECTED
      (OOS can NEVER be bypassed)
   6. otherwise                          -> VALIDATED (research-only,
                                            never production-ready)

Every conclusion carries concrete evidence refs (experiment id,
metrics, comparison, robustness, OOS stats). Failed / insufficient
experiments are RETAINED in the run, never pruned.

Score (deterministic ranking basis):
   VALIDATED 3.0, HYPOTHESIS 2.5, OBSERVATION 1.0,
   INSUFFICIENT_EVIDENCE 0.5, REJECTED 0.0
====================================================
"""

from core.research.researcher.types import (
    OBSERVATION,
    HYPOTHESIS,
    VALIDATED,
    REJECTED,
    INSUFFICIENT_EVIDENCE,
    BLOCKED,
    ResearchRecommendation,
)

MIN_VALIDATION_SETTLED = 30
MIN_OOS_SETTLED = 5

_SCORE = {
    VALIDATED: 3.0,
    HYPOTHESIS: 2.5,
    OBSERVATION: 1.0,
    INSUFFICIENT_EVIDENCE: 0.5,
    REJECTED: 0.0,
    BLOCKED: -1.0,
}

_STATUS_ORDER = (VALIDATED, HYPOTHESIS, OBSERVATION,
                 INSUFFICIENT_EVIDENCE, REJECTED, BLOCKED)

# 9E recommendation statuses that indicate the robustness gate did
# NOT clear (the 9H gate would be bypassing 9E otherwise).
_ROBUST_BLOCKERS = (
    "OOS_REQUIRED",
    "NON_ROBUST",
    "INSUFFICIENT_SAMPLE",
    "LOSS_EXPANSION",
    "INCONCLUSIVE",
    "BLOCKED",
)

_OOS_SETTLED = "oos_settled"
_OOS_EXPECTANCY = "oos_expectancy"


def rank_status(status):
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return len(_STATUS_ORDER)


class EvidenceEvaluator:
    """Deterministic conclusion ladder over ExperimentRun evidence."""

    def __init__(self, min_settled=MIN_VALIDATION_SETTLED,
                 min_oos=MIN_OOS_SETTLED):
        self.min_settled = min_settled
        self.min_oos = min_oos

    # -------------------------------------------------

    def conclude(self, run, baseline_expectancy, context):
        """Returns a ResearchRecommendation for the run's hypothesis."""
        hypothesis = run.hypothesis
        results = list(run.results)

        if not results:
            return self._recommend(
                hypothesis, INSUFFICIENT_EVIDENCE, 0.5,
                "no experiment could be executed (empty parameter grid "
                "or no supported combos)",
                evidence=(),
                next_step="widen the supported grid or supply opportunities",
            )

        best = _best_result(results, self.min_settled)

        # -- 1/2 sample sufficiency ---------------------------------
        if best.settled < self.min_settled:
            return self._recommend(
                hypothesis, INSUFFICIENT_EVIDENCE, 0.5,
                "insufficient evidence to conclude: best experiment "
                f"settled {best.settled} of the {self.min_settled} "
                "required; the runs are retained, not discarded",
                evidence=(_evidence_package(best),),
                next_step="accumulate a larger settled population",
            )

        # -- 3 advantage vs baseline --------------------------------
        candidate_exp = best.metrics.get("expectancy")
        if candidate_exp is None:
            candidate_exp = best.statistical.get("expectancy")
        delta = _num(best.comparison.get("delta_expectancy"))
        has_advantage = (
            delta is not None and delta > 0
            and candidate_exp is not None and candidate_exp > 0
        )

        if not has_advantage:
            return self._recommend(
                hypothesis, REJECTED, 0.0,
                "no advantage vs baseline: candidate does not beat the "
                "like-for-like baseline on expectancy (negative result "
                "is retained, not hidden)",
                evidence=(_evidence_package(best),),
                next_step="do not re-probe the same axis without new "
                          "opportunity evidence",
            )

        # -- 4 robustness gate (9D warnings / 9E status) ------------
        blockers = self._robustness_blockers(best)
        if blockers:
            return self._recommend(
                hypothesis, HYPOTHESIS, 2.5,
                f"positive in-sample evidence but the robustness gate is "
                f"not clear: {'; '.join(blockers)} -- hypothesis stands, "
                "conclusion withheld",
                evidence=(_evidence_package(best),),
                next_step="clear the robustness gate before any further "
                          "consideration",
            )

        # -- 5 OOS gate (cannot be bypassed) -------------------------
        oos = best.oos or {}
        oos_settled = _num(oos.get(_OOS_SETTLED))
        oos_exp = _num(oos.get(_OOS_EXPECTANCY))

        if oos_settled is None or oos_settled < self.min_oos:
            return self._recommend(
                hypothesis, HYPOTHESIS, 2.5,
                f"positive in-sample evidence but the chronological OOS "
                f"fold is too small (settled {oos_settled}, min "
                f"{self.min_oos}) -- never validated without OOS",
                evidence=(_evidence_package(best),),
                next_step="collect later-dated opportunity outcomes and "
                          "re-validate out-of-sample",
            )

        if oos_exp is None or oos_exp <= 0:
            return self._recommend(
                hypothesis, REJECTED, 0.0,
                f"out-of-sample evidence did NOT confirm (OOS expectancy "
                f"{oos_exp}); the in-sample advantage failed the OOS "
                "gate and is rejected (retained, not hidden)",
                evidence=(_evidence_package(best),),
                next_step="do not treat the in-sample advantage as a "
                          "finding; OOS was the gate",
            )

        # -- 6 validated --------------------------------------------
        return self._recommend(
            hypothesis, VALIDATED, 3.0,
            "counterfactual evidence is positive, robustness clear, and "
            "the chronological OOS fold confirms it -- VALIDATED as an "
            "autonomous research finding (never production-ready)",
            evidence=(_evidence_package(best),),
            next_step="escalate to the next research milestone (OOS/"
                      "walk-forward gate) before any production path",
        )

    # -------------------------------------------------

    @staticmethod
    def _robustness_blockers(result):
        blockers = []
        robust_status = (result.robustness_status or "").upper()
        if robust_status in _ROBUST_BLOCKERS:
            blockers.append(f"9E robustness {robust_status}")
        status = (result.recommendation_status or "").upper()
        if status in _ROBUST_BLOCKERS:
            blockers.append(f"9E status {status}")
        strength = (result.evidence_strength or "").upper()
        if strength and "MODERATE" not in strength and "STRONG" not in strength:
            blockers.append(f"evidence strength {result.evidence_strength}")
        for warn in result.robustness:
            low = str(warn).lower()
            if "directional imbalance" in low:
                blockers.append("directional imbalance flagged by 9D")
        return sorted(set(blockers))

    # -------------------------------------------------

    @staticmethod
    def _recommend(hypothesis, status, base_score, statement,
                   evidence, next_step):
        return ResearchRecommendation(
            recommendation_id=_recommendation_id(hypothesis, status),
            hypothesis_id=hypothesis.hypothesis_id,
            kind=hypothesis.kind,
            score=base_score,
            status=status,
            question=hypothesis.question,
            statement=statement,
            why=hypothesis.why,
            evidence=tuple(evidence),
            next_step=next_step,
            is_production_directive=False,
        )


def _best_result(results, min_settled):
    """Deterministic selection of the strongest evidence package."""

    def key(r):
        exp = r.metrics.get("expectancy")
        if exp is None:
            exp = (r.statistical or {}).get("expectancy")
        exp = _num(exp)
        return (
            1 if r.settled >= min_settled else 0,
            exp if exp is not None else float("-inf"),
            r.settled,
            r.experiment_id,
        )

    return max(results, key=key)


def _evidence_package(result):
    return {
        "experiment_id": result.experiment_id,
        "filled": result.filled,
        "settled": result.settled,
        "expectancy": result.metrics.get("expectancy"),
        "delta_expectancy": result.comparison.get("delta_expectancy"),
        "recommendation_status": result.recommendation_status,
        "robustness_status": result.robustness_status,
        "evidence_strength": result.evidence_strength,
        "oos": dict(result.oos),
        "robustness": list(result.robustness),
    }


def _recommendation_id(hypothesis, status):
    import hashlib
    payload = "recommendation|%s|%s" % (hypothesis.hypothesis_id, status)
    return "R" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None