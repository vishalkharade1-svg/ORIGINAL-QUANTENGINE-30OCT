"""
====================================================================

QuantEngine

Research UX -- Recommendation Readback (Phase 9O) -- explain

The ExplanationEngine converts a frozen 9N RecommendationReport into a
deterministic, human-usable readback. It consumes ONLY the frozen 9N
report (never re-running OOS / conditional ML / regime), and for each
recommendation it states:

    * the research verdict (a closed RESEARCH_VERDICTS member; the
      maximum is VALIDATED_RESEARCH_FINDING -- never TRADABLE),
    * per-aspect evidence (OOS / regime / discovery / counterfactual /
      baseline / supporting metrics),
    * negative evidence and limitations (what failed -- nothing hidden),
    * the closed uncertainty tags,
    * a deterministic prose rationale for "why this recommendation
      exists and why it is still research-only".

Every recommendation maps 1:1 to a ReadbackEntry; nothing is dropped
and nothing is collapsed. No research number is re-derived: the engine
only re-states values already frozen in the consumed report.
====================================================================
"""

from core.research.readback import constants as _c
from core.research.readback.types import ReadbackEntry, ReadbackReport
from core.research.recommendation import constants as _rec_c


# Total 1:1 mapping from the closed 9N status vocabulary to the closed
# 9O research-verdict vocabulary.
_VERDICT_FOR_STATUS = {
    "7E_BLOCKED": "SEVEN_E_BLOCKED",
    "NO_EVIDENCE": "NO_EVIDENCE",
    "INCONCLUSIVE": "INCONCLUSIVE",
    "REJECTED": "REJECTED",
    "REQUIRES_MORE_OOS": "REQUIRES_MORE_OOS",
    "CONDITIONAL": "CONDITIONAL",
    "PROMISING": "PROMISING",
    "ROBUST_RESEARCH_FINDING": "VALIDATED_RESEARCH_FINDING",
}


def verdict_for_9n_status(status):
    """Total deterministic 9N status -> 9O research verdict mapping."""
    verdict = _VERDICT_FOR_STATUS.get(status)
    if verdict is None:
        raise ValueError(
            "unsupported 9N status %r for 9O readback" % (status,))
    return verdict


def _entry(e):
    """a (key, label) row"""
    return {"key": e[0], "label": e[1]}


def _add(aspects, aspect, key, label):
    aspects.setdefault(aspect, []).append(
        {"key": key, "label": label})
    return aspects


def _oos_aspects(aspects, oos):
    _add(aspects, "oos_evidence", "report", oos.get("oos_report_id") or "")
    _add(aspects, "oos_evidence", "survived",
         "%s OF %s" % (oos.get("periods_survived") or 0,
                       oos.get("periods_tested") or 0))
    _add(aspects, "oos_evidence", "rejected",
         str(oos.get("periods_rejected") or 0))
    sr = oos.get("survival_ratio")
    if sr is not None:
        _add(aspects, "oos_evidence", "survival_ratio",
             "%.4f" % float(sr))
    _add(aspects, "oos_evidence", "familywise_passed",
         str(bool(oos.get("familywise_passed"))))
    _add(aspects, "oos_evidence", "walk_forward_passed",
         str(bool(oos.get("walk_forward_passed"))))
    _add(aspects, "oos_evidence", "robustness",
         oos.get("robustness_level") or "LOW")
    return aspects


def _regime_aspects(aspects, hyp, ancillary):
    dim = hyp.get("regime_dim")
    label = hyp.get("regime_label")
    if dim and label:
        _add(aspects, "regime_evidence", "scoped",
             "%s=%s" % (dim, label))
        _add(aspects, "regime_evidence", "conditional", "true")
    else:
        _add(aspects, "regime_evidence", "scoped", "none")
        _add(aspects, "regime_evidence", "conditional", "false")
    if ancillary:
        _add(aspects, "regime_evidence", "finding_status",
             ancillary.get("regime_finding_status") or "UNAVAILABLE")
    return aspects


def _discovery_aspects(aspects, hyp):
    _add(aspects, "discovery_evidence", "origin",
         hyp.get("origin") or "9L")
    return aspects


def _counterfactual_aspects(aspects, oos, baseline):
    _add(aspects, "counterfactual_evidence", "walk_forward",
         "passed" if oos.get("walk_forward_passed") else "not_passed")
    if baseline:
        _add(aspects, "counterfactual_evidence", "baseline", str(baseline))
    return aspects


def _baseline_aspects(aspects, oos, baseline):
    if baseline:
        _add(aspects, "baseline_comparison", "reference", str(baseline))
    _add(aspects, "baseline_comparison", "economic_consistent",
         str(bool(oos.get("economic_consistent"))))
    return aspects


def _metrics_aspects(aspects, metrics):
    for pair in (metrics or ()):
        if isinstance(pair, (tuple, list)) and len(pair) == 2:
            _add(aspects, "supporting_metrics", str(pair[0]), str(pair[1]))
        else:
            _add(aspects, "supporting_metrics", "metric", str(pair))
    return aspects


def _negative_aspects(aspects, oos, hyp, limitations, status):
    rejected = oos.get("periods_rejected") or 0
    if rejected:
        _add(aspects, "negative_evidence", "rejected_periods", str(rejected))
    if not oos.get("familywise_passed"):
        _add(aspects, "negative_evidence", "familywise",
             "not_survived")
    if hyp.get("seven_e"):
        _add(aspects, "negative_evidence", "seven_e", "NO_GO")
    if status == "7E_BLOCKED":
        _add(aspects, "negative_evidence", "verdict", "7E_BLOCKED")
    for lim in (limitations or ()):
        # Re-state any negative limitation without inventing new numbers.
        _add(aspects, "negative_evidence", "limitation", str(lim))
    return aspects


def _uncertainty(oos, hyp, status, verdict, limitations):
    """Derive a closed uncertainty tag set from the frozen evidence."""
    tags = []
    superscript = sorted(
        (t for t in (limitations or ()) if t in _c.UNCERTAINTY_ROSTER))
    tags.extend(superscript)
    if status == "7E_BLOCKED":
        tags.append("REPEATED_REJECTION")
    if (oos.get("periods_tested") or 0) > 0 \
            and (oos.get("periods_survived") or 0) == 0:
        tags.append("NO_OOS_EVIDENCE")
    if (oos.get("periods_tested") or 0) > 0 \
            and (oos.get("periods_survived") or 0) < (
                oos.get("periods_tested") or 0):
        tags.append("POSITIVE_TOO_FEW_PERIODS")
    if hyp.get("regime_dim"):
        tags.append("CONDITIONAL_SCOPE")
    if oos.get("familywise_passed") is False:
        tags.append("FAMILYWISE_NOT_SURVIVED")
    if not tags:
        tags.append("NO_UNCERTAINTY")
    return tuple(sorted(t for t in tags if t in _c.UNCERTAINTY_ROSTER))


def _rationale(rec, oos, hyp, ancillary, verdict, status, uncertainty):
    parts = []
    statement = (hyp.get("statement") or rec.get("title") or
                 (rec.get("rationale") or "").strip())
    parts.append("This is a research-only finding for %r."
                 % (statement,))
    parts.append("9N evidence status: %s; 9O research verdict: %s."
                 % (status, verdict))
    survived = oos.get("periods_survived") or 0
    tested = oos.get("periods_tested") or 0
    if tested:
        parts.append("It survived %s of %s out-of-sample periods."
                     % (survived, tested))
    if hyp.get("regime_dim"):
        parts.append("Evidence is scoped to %s=%s, so it is never "
                     "treated as universal."
                     % (hyp.get("regime_dim"), hyp.get("regime_label")))
    if uncertainty:
        parts.append("Remaining uncertainty: %s."
                     % ", ".join(uncertainty))
    parts.append("The directive remains %s and production status is %s."
                 % (_rec_c.RECOMMENDATION_DIRECTIVE, _c.PRODUCTION_STATUS))
    return " ".join(parts)


def _join_key(d):
    """Stable join key shared by a 9N Recommendation and its flattened
    RecommendationFinding. The two carry DIFFERENT recommendation_ids
    (derived from different field sets) and are independently sorted by
    build_report, so they are paired here by (hypothesis_id,
    oos_report_id) -- fields both objects carry verbatim."""
    hyp = d.get("hypothesis") or {}
    oos = d.get("oos") or {}
    h = hyp.get("hypothesis_id") or d.get("hypothesis_id") or ""
    o = oos.get("oos_report_id") or d.get("oos_report_id") or ""
    return "%s|%s" % (h, o)


def _iter_findings(report):
    """Yield (recommendation_dict, finding_dict_or_None) pairs, joined
    deterministically on the shared (hypothesis_id, oos_report_id) key."""
    recs = {}
    for r in getattr(report, "recommendations", ()):
        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        recs[_join_key(d)] = d
    findings_by_key = {}
    for f in getattr(report, "findings", ()):
        d = f.to_dict() if hasattr(f, "to_dict") else dict(f)
        findings_by_key[_join_key(d)] = d
    for key in sorted(recs):
        yield recs[key], findings_by_key.get(key)


def explain_report(report):
    """Convert a frozen 9N RecommendationReport into a 9O
    ReadbackReport. Consumes ONLY the frozen 9N report; never re-runs
    research, never re-derives a number."""
    verdicts = set()
    uncertainty_all = []
    entries = []
    for rec, finding in _iter_findings(report):
        entry = explain_entry(rec, finding)
        entries.append(entry)
        verdicts.add(entry.research_verdict)
        uncertainty_all.extend(entry.uncertainty)
    src_id = getattr(report, "report_id", "")
    return build_readback(
        source_report_id=src_id,
        entries=entries,
        research_verdicts=verdicts,
        uncertainty_summary=uncertainty_all,
    )


def explain_entry(rec, finding=None):
    """One 1:1 ReadbackEntry for one 9N recommendation (with its
    optional matching evidence-rich finding)."""
    if rec is None:
        raise ValueError("explain_entry requires a recommendation")
    rec_d = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
    f_d = None
    if finding is not None:
        f_d = finding.to_dict() if hasattr(finding, "to_dict") \
            else dict(finding)

    status = rec_d.get("status") or (f_d or {}).get("recommendation_status")
    verdict = verdict_for_9n_status(status)

    oos = (f_d or {}).get("oos") or {}
    hyp = (f_d or {}).get("hypothesis") or {}
    ancillary = (f_d or {}).get("ancillary") or {}
    answers = (f_d or {}).get("answers") or {}
    limitations = rec_d.get("limitations") or (f_d or {}).get("limitations")
    metrics = rec_d.get("metrics") or ()

    aspects = {}
    _add(aspects, "status", "verdict", verdict)
    _add(aspects, "status", "evidence", status)
    if rec_d.get("candidate_id"):
        _add(aspects, "candidate", "id", str(rec_d["candidate_id"]))
    if rec_d.get("hypothesis_id") or hyp.get("hypothesis_id"):
        _add(aspects, "hypothesis", "id",
             str(rec_d.get("hypothesis_id") or hyp.get("hypothesis_id")))
    if hyp.get("statement"):
        _add(aspects, "hypothesis", "statement", hyp["statement"])
    _oos_aspects(aspects, oos)
    _regime_aspects(aspects, hyp, ancillary)
    _discovery_aspects(aspects, hyp)
    _counterfactual_aspects(
        aspects, oos, rec_d.get("baseline_reference"))
    _baseline_aspects(
        aspects, oos, rec_d.get("baseline_reference"))
    _metrics_aspects(aspects, metrics)
    _negative_aspects(
        aspects, oos, hyp, limitations, status)

    uncertainty = _uncertainty(oos, hyp, status, verdict, limitations)

    title = rec_d.get("title") or (
        "%s: %s" % (verdict, hyp.get("statement") or "?"))
    claim = (hyp.get("statement") or rec_d.get("title") or
             rec_d.get("rationale") or "").strip()
    # A clean claim uses the discovery's own statement, never the
    # upstream title that may embed a status prefix.
    if claim.startswith("%s:" % status):
        claim = claim[len("%s:" % status):].strip()

    rationale = _rationale(
        rec_d, oos, hyp, ancillary, verdict, status, uncertainty)

    return ReadbackEntry(
        recommendation_id=rec_d.get("recommendation_id", ""),
        research_verdict=verdict,
        evidence_status=status,
        title=title,
        claim=claim,
        rationale=rationale,
        aspects=aspects,
        uncertainty=uncertainty,
        production_status=_c.PRODUCTION_STATUS,
    )


def build_readback(source_report_id="", entries=None,
                   research_verdicts=None, uncertainty_summary=None):
    """Deterministic 9O ReadbackReport constructor (validator, not an
    optimizer). Normalizes + sorts, validates verdicts, and enforces the
    research-only / non-tradable contract."""
    entries = tuple(entries or ())
    for e in entries:
        if not isinstance(e, ReadbackEntry):
            raise ValueError(
                "9O entries must be ReadbackEntry instances; got %r"
                % (type(e).__name__,))
        if e.research_verdict not in _c.RESEARCH_VERDICTS:
            raise ValueError(
                "unsupported research verdict %r" % (e.research_verdict,))
    sorted_entries = tuple(sorted(
        entries,
        key=lambda e: e.recommendation_id))
    verdicts = set(research_verdicts) if research_verdicts else \
        {e.research_verdict for e in entries}
    for v in verdicts:
        if v not in _c.RESEARCH_VERDICTS:
            raise ValueError("unsupported research verdict %r" % (v,))
    uniq = set(uncertainty_summary) if uncertainty_summary else set()
    for u in uniq:
        if u not in _c.UNCERTAINTY_ROSTER:
            raise ValueError("unknown uncertainty tag %r" % (u,))
    report = ReadbackReport(
        report_id="",
        production_status=_c.PRODUCTION_STATUS,
        research_verdicts=tuple(sorted(verdicts)),
        entries=sorted_entries,
        uncertainty_summary=tuple(sorted(uniq)),
        source_report_id=source_report_id or "",
    )
    _ = report.to_dict()
    check = report.emission_check()
    if not check["clean"]:
        raise ValueError(
            "9O report failed research-only invariant checks: %s"
            % (check,))
    return report
