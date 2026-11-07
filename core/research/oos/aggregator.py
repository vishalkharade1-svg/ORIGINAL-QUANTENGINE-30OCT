"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- aggregator

Cross-period aggregation, consistency metrics, the familywise
multiple-testing accounting, and the closed OOS status ladder.

Every settled period is retained and counted: survival ratio is never
reduced to a single profitability number, and

   OOS periods 6 / survived 5 / rejected 1
   vs
   OOS periods 2 / survived 2

remain distinguishable even when both share a survival-ratio ceiling.

The multiple-testing family is the TOTAL number of hypotheses
re-validated together; the corrected (Sidak) alpha is reported WITH
the raw alpha and the family size -- the denominator is never hidden.
9M never silently resets the protection the 9L layer already applied.
====================================================================
"""

import math

from core.research.conditional_ml.guards import familywise_alpha
from core.research.oos import constants as _c
from core.research.oos.oos_types import (
    economic_statistics,
    survival_ratio,
)

_SETTLED = (_c.PERIOD_STATUSES[0], _c.PERIOD_STATUSES[1],
            _c.PERIOD_STATUSES[3])
_SURVIVED = (_c.PERIOD_STATUSES[0], _c.PERIOD_STATUSES[1])


def summarize_periods(period_evs, gates):
    """Counts + consistency metrics over one hypothesis' periods."""
    tested = [p for p in period_evs if p.status != _c.PERIOD_STATUSES[-1]]
    available = [p for p in period_evs if p.status in _SETTLED]
    survived = [p for p in available if p.status in _SURVIVED]
    rejected = [p for p in available if p.status == _c.PERIOD_STATUSES[3]]
    inconclusive = [p for p in period_evs
                    if p.status == _c.PERIOD_STATUSES[2]]
    unavailable = [p for p in period_evs
                   if p.status == _c.PERIOD_STATUSES[-1]]

    avail = len(available)
    surv = len(survived)
    reject = len(rejected)
    sign_consistent = sum(
        1 for p in available
        if p.expectancy_delta is not None and p.expectancy_delta >= -1e-9
    )
    economic_consistent = (
        avail > 0 and surv >= gates["min_surviving_periods"]
        and sign_consistent >= gates["required_sign_consistent_periods"]
        and reject <= 1
    )
    return {
        "periods_tested": len(tested),
        "periods_available": avail,
        "periods_survived": surv,
        "periods_rejected": reject,
        "periods_inconclusive": len(inconclusive),
        "periods_unavailable": len(unavailable),
        "survival_ratio": survival_ratio(surv, avail),
        "sign_consistent_periods": sign_consistent,
        "economic_consistent": economic_consistent,
        "economic_statistics": economic_statistics(
            [p.expectancy_delta for p in available]
        ),
    }


def final_status(hypothesis, period_evs, gates, robustness_level=None,
                 precedent=None):
    """Closed ladder verdict for one hypothesis (Section 17).

    Every non-top transition carries a reason. No status may skip
    mandatory OOS evidence.
    """
    s = summarize_periods(period_evs, gates)
    avail = s["periods_available"]
    surv = s["periods_survived"]
    reject = s["periods_rejected"]
    min_surv = gates["min_surviving_periods"]
    req_sign = gates["required_sign_consistent_periods"]
    min_total = gates["min_total_oos_trades"]
    total_trades = sum(p.n_trades for p in period_evs)

    reasons = []
    if hypothesis.seven_e_no_go:
        return _c.OOS_STATUSES[0], ("7E NO-GO surface preserved: a "
                                    "directional breakout semantic can "
                                    "never be promoted out of NO-GO",)

    tested = s["periods_tested"]
    if tested == 0:
        return _c.OOS_STATUSES[1], (
            "no supplied OOS evidence could be evaluated",)

    if reject == 0 and s["economic_statistics"]["n"] == 0:
        return _c.OOS_STATUSES[2], (
            "no settled OOS evidence (no period met the sample gates "
            "with a comparable baseline)",)

    if avail < min_surv:
        reason = (
            "only %d settled period(s); %d required for confirmation"
            % (avail, min_surv)
        )
        if surv == 0 or surv < math.ceil(2.0 * avail / 3.0):
            return _c.OOS_STATUSES[3], (
                reason +
                ("; no majority of settled periods is economically "
                 "positive" if surv == 0 else
                 "; fewer than 2/3 of settled periods positive"),)
        return _c.OOS_STATUSES[4], (reason + "; positive but partial "
                                    "temporal breadth",)

    if reject > 1:
        return _c.OOS_STATUSES[3], (
            "%d rejected OOS period(s); repeated adverse evidence"
            % reject,)

    if (s["periods_inconclusive"] > 0
            and gates.get("conclusive_only", False)
            and reject == 0):
        return _c.OOS_STATUSES[2], (
            "conclusive-only protocol: inconclusive periods keep "
            "the finding from confirmation",)

    if surv < min_surv:
        if surv >= min_surv - 1 and reject <= 1:
            return _c.OOS_STATUSES[5], (
                "%d/%d survived; %d rejected - strong but not meeting "
                "the 5/6 robust requirement"
                % (surv, avail, reject),)
        return _c.OOS_STATUSES[3], (
            "only %d/%d settled periods economically positive"
            % (surv, avail),)

    if s["sign_consistent_periods"] < req_sign:
        return _c.OOS_STATUSES[3], (
            "%d sign-consistent periods below the required %d"
            % (s["sign_consistent_periods"], req_sign),)

    if total_trades < min_total:
        return _c.OOS_STATUSES[2], (
            "total OOS trades %d below the %d minimum - insufficient "
            "evidence for a robustness claim" % (total_trades, min_total),)

    # Candidate reached the robust tier: confirm provenance gates.
    blocked_by = []
    if not hypothesis.walk_forward_passed:
        blocked_by.append("declared 9K walk-forward evidence missing")
    if robustness_level == "LOW":
        blocked_by.append("robustness classification LOW")
    if precedent is not None:
        for tag, ok in precedent.items():
            if not ok:
                blocked_by.append("consistency gate %s failed" % tag)

    if not blocked_by:
        return _c.OOS_STATUSES[-1], (
            "repeated independent multi-period OOS confirmation: "
            "%d settled periods, %d survived, %d rejected, walk-forward "
            "declared passed"
            % (avail, surv, reject),)
    return _c.OOS_STATUSES[6], (
        "%d/%d survived with consistency, but research conveyor gate "
        "not fully cleared: %s" % (surv, avail, "; ".join(blocked_by)),)


def multiple_testing(family_size, alpha=0.05):
    """Familywise accounting: Sidak correction over the re-validated
    family. The raw alpha, family size and corrected alpha are always
    reported -- never the denominator hidden."""
    corrected = familywise_alpha(float(alpha), int(family_size))
    return {
        "n_hypotheses": int(family_size),
        "family_size": int(family_size),
        "method": "Sidak-familywise",
        "raw_alpha": float(alpha),
        "corrected_alpha": corrected,
        "note": "protection applied across the 9M re-validated family; "
                "the 9L correction family is never reset",
        "survives_correction": int(family_size),
    }


def per_period_summary(results, n_periods):
    """Cross-hypothesis summary per OOS period (no top-N filtering)."""
    out = []
    for i in range(n_periods):
        label = "OOS-%d" % (i + 1)
        evs = [r for r in results if any(
            p.period == label and p.status in _SETTLED
            and p.sample_sufficient
            for p in getattr(r, "per_period", ())
        )]
        survived = [r for r in results if any(
            p.period == label and p.status in _SURVIVED
            for p in getattr(r, "per_period", ())
        )]
        out.append({
            "period": label,
            "n_hypotheses_evaluated": len(evs),
            "n_hypotheses_survived": len(survived),
        })
    return {
        "n_periods": n_periods,
        "per_period": tuple(out),
    }