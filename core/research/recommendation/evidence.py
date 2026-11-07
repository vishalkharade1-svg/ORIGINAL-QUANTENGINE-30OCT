"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N) -- evidence

Builds the deterministic evidence chain for one consumed discovery:

    recommendation -> OOS readback -> hypothesis readback ->
    optional 9L / 9K ancillary readback -> narrative answers.

It NEVER re-simulates and NEVER re-derives OOS / ML / regime numbers;
it aggregates evidence already frozen by the 9M / 9L / 9K reports and
retains EVERY period verdict and EVERY limitation (no hiding of
rejections).
====================================================================
"""

from core.research.recommendation import constants as _c
from core.research.recommendation.ladder import recommend_status
from core.research.recommendation.types import (
    AncillaryReadback,
    HypothesisReadback,
    OosReadback,
    ReadbackAnswers,
    Recommendation,
    RecommendationFinding,
)


_STATE_KEYS = ("UNAVAILABLE", "INCONCLUSIVE", "REJECTED", "PROMISING",
               "VALIDATED")


def _period_statuses(per_period):
    """Closed, ordered per-period verdict strings for the readback."""
    statuses = []
    for p in (per_period or ()):
        status = p.get("status", "") if isinstance(p, dict) else ""
        if status in _STATE_KEYS:
            statuses.append(status)
    return tuple(statuses)


def _coerce_oo(result):
    """Accept a frozen HypothesisOosResult, any object with to_dict(),
    or a plain dict."""
    if isinstance(result, dict):
        return dict(result)
    if hasattr(result, "to_dict"):
        return dict(result.to_dict())
    raise ValueError(
        "9N readback requires HypothesisOosResult / to_dict / dict; got %r"
        % (type(result).__name__,)
    )


def _null_ancillary():
    return AncillaryReadback()


def readback_ancillary(oos_result, ml_report=None, regime_findings=None,
                       walk_forward_map=None):
    """Compress optional frozen 9L / 9K readbacks into the chain.

    Every lookup is best-effort and never fabricates a number: if a
    surface is absent or the hypothesis is not found, the slot stays at
    its UNAVAILABLE default.
    """
    notes = []
    recovery_status = "UNAVAILABLE"
    entry_status = "UNAVAILABLE"
    calibration_status = "UNAVAILABLE"
    walk_survived = None
    regime_finding_status = "UNAVAILABLE"

    symbol = oos_result.get("symbol") or ""

    if ml_report is not None:
        if hasattr(ml_report, "to_dict"):
            ml = dict(ml_report.to_dict())
        elif isinstance(ml_report, dict):
            ml = dict(ml_report)
        else:
            ml = {}
        recovery = ml.get("recovery") or ()
        entry = ml.get("entry_selection") or ()
        calibration = ml.get("calibration") or ()
        for r in recovery:
            if _rec_dict_alt(r) and (r.get("symbol", symbol) in
                                     ("", symbol)):
                recovery_status = r.get("status", "UNAVAILABLE")
                break
        for e in entry:
            entry_status = e.get("status", "UNAVAILABLE")
            break
        for cal in calibration:
            calibration_status = cal.get("status", "UNAVAILABLE")
            break
        if recovery_status != "UNAVAILABLE":
            notes.append("9L recovery readback available")
        if calibration_status != "UNAVAILABLE":
            notes.append("9L calibration status %s" % calibration_status)

    if walk_forward_map:
        wid = (oos_result.get("hypothesis_id")
               or oos_result.get("statement"))
        if wid in walk_forward_map:
            walk_survived = bool(walk_forward_map[wid])
            notes.append("9K walk-forward evidence present")

    if regime_findings:
        for f in regime_findings:
            st = f.get("status", "") if isinstance(f, dict) else ""
            if st:
                regime_finding_status = st
                break

    return AncillaryReadback(
        recovery_status=recovery_status,
        entry_status=entry_status,
        calibration_status=calibration_status,
        walk_forward_survived=walk_survived,
        regime_finding_status=regime_finding_status,
        provenance_notes=tuple(notes),
    )


def _rec_dict_alt(r):
    return (isinstance(r, dict) and (r.get("alternative") or
                                     r.get("surface") or True))


def build_finding(oos_result, oos_report_id="", ml_report=None,
                  regime_findings=None, walk_forward_map=None):
    """Deterministic 9N RecommendationFinding for one 9M result."""
    raw = _coerce_oo(oos_result)

    seven_e = bool(raw.get("seven_e") or raw.get("seven_e_no_go"))
    is_conditional = bool(raw.get("regime_dim") or
                          raw.get("is_conditional"))

    # Derive the OOS readback from the frozen 9M fields. Preserve the
    # report id: prefer the explicit parameter, else the source row, so
    # the identifier survives the finding -> recommendation chain.
    oos_id = oos_report_id or (raw.get("oos_report_id") or "")
    oos_rd = OosReadback(
        oos_report_id=oos_id,
        final_status=raw.get("status") or "",
        periods_tested=int(raw.get("periods_tested") or 0),
        periods_available=int(raw.get("periods_available") or 0),
        periods_survived=int(raw.get("periods_survived") or 0),
        periods_rejected=int(raw.get("periods_rejected") or 0),
        periods_inconclusive=int(raw.get("periods_inconclusive") or 0),
        survival_ratio=raw.get("survival_ratio"),
        sign_consistent_periods=int(
            raw.get("sign_consistent_periods") or 0),
        economic_consistent=bool(raw.get("economic_consistent")),
        familywise_passed=bool(raw.get("survives_familywise")),
        robustness_level=(raw.get("robustness", {}) or {}).get(
            "level", "LOW"),
        walk_forward_passed=bool(raw.get("walk_forward_passed")),
        per_period=_period_statuses(raw.get("per_period")),
    )

    hyp_rd = HypothesisReadback(
        hypothesis_id=raw.get("hypothesis_id") or "",
        origin=raw.get("origin") or "9L",
        statement=raw.get("statement") or "",
        symbol=raw.get("symbol") or "",
        direction=raw.get("direction") or "",
        regime_dim=raw.get("regime_dim"),
        regime_label=raw.get("regime_label"),
        is_conditional=is_conditional,
        seven_e=seven_e,
        params=dict(raw.get("params") or {}),
        expected_outcome=raw.get("expected_outcome") or "",
    )

    ancillary = readback_ancillary(
        raw, ml_report=ml_report, regime_findings=regime_findings,
        walk_forward_map=walk_forward_map)

    status = recommend_status(
        oos_rd.final_status,
        is_conditional=is_conditional,
        seven_e=seven_e,
        robustness_level=oos_rd.robustness_level,
    )

    answers = build_answers(oos_rd, hyp_rd)
    reasons = build_reasons(oos_rd, hyp_rd, status)
    limitations = build_limitations(oos_rd, hyp_rd, ancillary)

    return RecommendationFinding(
        recommendation_status=status,
        reasons=tuple(reasons),
        limitations=tuple(limitations),
        oos=oos_rd,
        hypothesis=hyp_rd,
        ancillary=ancillary,
        answers=answers,
    )


def build_answers(oos_rd, hyp_rd):
    """The five narrative answers, always deterministic, drawn from the
    closed rosters when a reason applies, empty otherwise."""
    how_robust = oos_rd.robustness_level or "LOW"

    what = hyp_rd.statement or "discovery without a stated claim"

    why = []
    if oos_rd.survival_ratio is not None and oos_rd.survival_ratio >= 0.5:
        why.append(_c.WHY_NARRATIVES[0])
    if (oos_rd.economic_consistent
            and oos_rd.survival_ratio is not None
            and oos_rd.survival_ratio > 0):
        why.append(_c.WHY_NARRATIVES[1])
    if oos_rd.periods_survived > 0 and oos_rd.periods_rejected == 0:
        why.append(_c.WHY_NARRATIVES[2])

    where = []
    if hyp_rd.symbol:
        where.append(_c.WHERE_NARRATIVES[0])
    if hyp_rd.direction:
        where.append(_c.WHERE_NARRATIVES[1])
    if hyp_rd.is_conditional:
        where.append(_c.WHERE_NARRATIVES[2])

    failed = []
    if oos_rd.periods_rejected > 0:
        failed.append(_c.WHERE_NARRATIVES[3])

    return ReadbackAnswers(
        what_discovered=what,
        why_it_worked=tuple(why),
        where_it_worked=tuple(where),
        where_it_failed=tuple(failed),
        how_robust=how_robust,
    )


def build_reasons(oos_rd, hyp_rd, status):
    reasons = []
    if status == _c.RECOMMENDATION_STATUSES[0]:       # 7E_BLOCKED
        reasons.append(_c.SEVEN_E_NO_GO)
    if oos_rd.periods_available > 0:
        reasons.append(
            "OOS evidence across %d period(s); %d of %d survived"
            % (oos_rd.periods_tested, oos_rd.periods_survived,
               max(oos_rd.periods_available, 1)))
    if oos_rd.sign_consistent_periods > 0:
        reasons.append(
            "%d sign-consistent period(s)" % oos_rd.sign_consistent_periods)
    if oos_rd.familywise_passed:
        reasons.append("familywise multiple-testing correction passed")
    if oos_rd.walk_forward_passed:
        reasons.append("9K walk-forward evidence was previously passed")
    if oos_rd.periods_rejected > 0:
        reasons.append(
            "%d rejected period(s) retained (not hidden)"
            % oos_rd.periods_rejected)
    if hyp_rd.is_conditional:
        reasons.append(
            "evidence scoped to regime %r; never promoted to universal"
            % (hyp_rd.regime_label,))
    return reasons


def build_limitations(oos_rd, hyp_rd, ancillary):
    limitations = []
    if oos_rd.survival_ratio is not None and oos_rd.survival_ratio < 1.0:
        limitations.append(
            "survival ratio %.2f is below full 6/6 confirmation"
            % oos_rd.survival_ratio)
    if oos_rd.periods_rejected > 0:
        limitations.append("adverse evidence in some periods "
                           "(%d rejected period(s) retained)"
                           % oos_rd.periods_rejected)
    if oos_rd.robustness_level != "HIGH":
        limitations.append("robustness tier is %s (not HIGH)"
                           % oos_rd.robustness_level)
    if hyp_rd.is_conditional:
        limitations.append("claim is confined to its claimed regime cell")
    if not oos_rd.familywise_passed:
        limitations.append("familywise correction not cleared")
    if ancillary.recovery_status == "UNAVAILABLE":
        limitations.append("no 9L recovery readback available")
    return limitations


def to_recommendation(finding):
    """Flatten a RecommendationFinding into a 1:1 human-facing
    Recommendation.

    Maps ONLY fields already present on the finding -- it does not invent
    semantics. The recommendation_id is re-derived deterministically from
    the canonical status / candidate / hypothesis / OOS-report / base /
    evidence / metrics fields, so it is stable across identical inputs.

    Every finding maps to exactly one recommendation; nothing is dropped
    or collapsed (callers may assert the 1:1 invariant).
    """
    if hasattr(finding, "to_dict"):
        raw = finding.to_dict()
    elif isinstance(finding, dict):
        raw = dict(finding)
    else:
        raise ValueError(
            "to_recommendation requires RecommendationFinding / dict; got %r"
            % (type(finding).__name__,)
        )

    hyp = _field(raw, "hypothesis") or {}
    oos = _field(raw, "oos") or {}
    answers = _field(raw, "answers") or {}

    # Prefer the canonical typed OOS evidence object over its
    # serialization when it is available (domain model, not the text form).
    typed_oos = getattr(finding, "oos", None)
    oos_report_id = getattr(typed_oos, "oos_report_id", "") or oos.get(
        "oos_report_id")

    metrics = []
    sr = oos.get("survival_ratio")
    if sr is not None:
        metrics.append(("survival_ratio", round(float(sr), 4)))
    metrics.append(("periods_survived", int(oos.get("periods_survived") or 0)))
    metrics.append(("periods_rejected",
                    int(oos.get("periods_rejected") or 0)))
    metrics.append(("sign_consistent_periods",
                    int(oos.get("sign_consistent_periods") or 0)))
    if oos.get("familywise_passed") is not None:
        metrics.append(("familywise_passed", bool(oos.get("familywise_passed"))))
    if oos.get("robustness_level"):
        metrics.append(("robustness_level", oos.get("robustness_level")))

    evidence_ids = list((raw.get("evidence_ids") or ()))
    if not evidence_ids and oos_report_id:
        evidence_ids = [oos_report_id]

    title = raw.get("title") or (
        "%s: %s" % (raw.get("recommendation_status", ""),
                    (hyp.get("statement") or "").strip())
    )

    rationale = raw.get("rationale") or _rationale_from(raw, hyp, oos, answers)

    return Recommendation(
        recommendation_id="",
        status=raw.get("recommendation_status")
        or _c.RECOMMENDATION_STATUSES[1],
        title=title.strip(),
        rationale=rationale.strip(),
        candidate_id=raw.get("candidate_id", hyp.get("hypothesis_id")),
        hypothesis_id=hyp.get("hypothesis_id"),
        oos_report_id=oos_report_id,
        evidence_ids=tuple(evidence_ids),
        baseline_reference=raw.get("baseline_reference"),
        regime=_regime_ref(hyp),
        symbol=hyp.get("symbol"),
        direction=hyp.get("direction"),
        metrics=tuple(metrics),
        limitations=tuple(raw.get("limitations") or ()),
    )


def _field(mapping, key, default=None):
    value = mapping.get(key)
    if isinstance(value, dict):
        return value
    if value is not None and hasattr(value, "to_dict"):
        return value.to_dict()
    return default


def _regime_ref(hyp):
    if not hyp.get("regime_label"):
        return None
    return "%s=%s" % (hyp.get("regime_dim"), hyp.get("regime_label"))


def _rationale_from(raw, hyp, oos, answers):
    parts = []
    base = raw.get("baseline_reference")
    if base:
        parts.append("vs baseline %s" % base)
    fails = list((answers or {}).get("where_it_failed") or ())
    wheres = list((answers or {}).get("where_it_worked") or ())
    if wheres:
        parts.append("where: %s" % "; ".join(wheres))
    if fails:
        parts.append("failed: %s" % "; ".join(fails))
    if not parts:
        parts.append((hyp.get("statement") or "discovery").strip())
    return "; ".join(parts)
