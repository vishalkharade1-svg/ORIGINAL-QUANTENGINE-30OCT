"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N) -- engine

The deterministic 9N review conductor.

9N is a READBACK layer: it consumes the frozen research reports already
produced by 9M (OosReport with its HypothesisOosResult list) and, when
supplied, the frozen 9L (ConditionalMlReport) and 9K (RegimeReport)
reports, then emits for every consumed discovery a RecommendationFinding
whose recommendation_status is one of the closed 9N vocabulary and whose
directive is ALWAYS INVESTIGATE_FURTHER.

It never simulates, never optimizes, never modifies parameters, never
promotes. Every period verdict and every limitation is retained in the
evidence chain. A finding touching the frozen 7E directional NO-GO is
7E_BLOCKED and never reviewed further.
====================================================================
"""

from core.research.recommendation import constants as _c
from core.research.recommendation.evidence import (
    build_finding,
    to_recommendation,
)
from core.research.recommendation.report import build_report
from core.research.recommendation.types import ReviewOverview


class RecommendationEngine:
    """Deterministic 9N review over consumed frozen research reports."""

    def __init__(self, gates=None):
        self.gates = dict(_DEFAULT_GATES)
        if gates:
            unknown = sorted(set(gates) - set(_DEFAULT_GATES))
            if unknown:
                raise ValueError(
                    "unknown gate keys %s; supported=%s"
                    % (unknown, sorted(_DEFAULT_GATES))
                )
            for key, value in gates.items():
                self.gates[key] = int(value)

    # -------------------------------------------------------------

    def run(self, oos_report, ml_report=None, regime_report=None,
            hypothesis_ids=None):
        """Read back the frozen 9M OosReport (+ optional 9L/9K reads).

        Params
        ------
        oos_report:
            the frozen 9M OosReport (or a dict-equivalent / object with
            .results). Its HypothesisOosResult list drives the review.
        ml_report:
            optional frozen 9L ConditionalMlReport (or dict/to_dict
            object) for the ancillary recovery / entry / calibration
            readback.
        regime_report:
            optional frozen 9K RegimeReport (or dict/to_dict object) for
            the regime finding / walk-forward readback.
        hypothesis_ids:
            optional filter -- read back only these hypothesis ids. When
            None (default) every result in the Oos report is reviewed.
        """
        results = _extract_results(oos_report)
        if hypothesis_ids is not None:
            idset = set(hypothesis_ids)
            results = [r for r in results
                       if _hid(r) in idset]

        (ml, regime_findings, walk_forward_map, oos_id) = _prepare_inputs(
            oos_report, ml_report, regime_report)

        findings = tuple(
            build_finding(
                r,
                oos_report_id=oos_id,
                ml_report=ml,
                regime_findings=regime_findings,
                walk_forward_map=walk_forward_map,
            )
            for r in results
        )

        # 1:1 -- every finding maps to exactly one flattened
        # recommendation; nothing is dropped or collapsed.
        recommendations = tuple(to_recommendation(f) for f in findings)
        assert len(recommendations) == len(findings)

        return build_report(
            recommendations=recommendations,
            findings=findings,
        )


def _extract_results(oos_report):
    if oos_report is None:
        return []
    if isinstance(oos_report, dict):
        results = oos_report.get("results", ()) or ()
        return list(results)
    if hasattr(oos_report, "results"):
        return list(oos_report.results or ())
    return []


def _hid(r):
    if isinstance(r, dict):
        return r.get("hypothesis_id") or ""
    if hasattr(r, "hypothesis_id"):
        return r.hypothesis_id or ""
    if hasattr(r, "to_dict"):
        return (r.to_dict() or {}).get("hypothesis_id") or ""
    return ""


def _get(report, key, default=()):
    if hasattr(report, key):
        value = getattr(report, key)
        if value is None:
            return default
        return value
    if isinstance(report, dict):
        return report.get(key, default)
    if hasattr(report, "to_dict"):
        d = report.to_dict() or {}
        return d.get(key, default)
    return default


def _prepare_inputs(oos_report, ml_report, regime_report):
    oos_id = ""
    if isinstance(oos_report, dict):
        oos_id = oos_report.get("report_id") or ""
    elif hasattr(oos_report, "report_id"):
        oos_id = oos_report.report_id or ""

    ml = None
    if ml_report is not None:
        ml = ml_report
    if isinstance(ml, dict) or (hasattr(ml, "to_dict")):
        ml = dict(ml.to_dict()) if hasattr(ml, "to_dict") else dict(ml)

    regime_findings = _get(regime_report, "findings", ()) or ()
    walk_map = _walk_forward_map(regime_report)
    if isinstance(regime_findings, tuple):
        regime_findings = list(regime_findings)

    return ml, regime_findings, walk_map, oos_id


def _walk_forward_map(regime_report):
    wf = _get(regime_report, "walk_forward", {}) or {}
    if isinstance(wf, dict):
        out = {}
        for key, val in wf.items():
            survived = False
            if isinstance(val, dict):
                survived = bool(val.get("survived"))
            elif hasattr(val, "survived"):
                survived = bool(val.survived)
            out[str(key)] = survived
        return out
    return {}


def _overview(findings):
    by = {s: 0 for s in _c.RECOMMENDATION_STATUSES}
    for f in findings:
        by[f.recommendation_status] += 1
    return ReviewOverview(
        n_findings=len(findings),
        by_status=dict(by),
        n_blocked=by[_c.RECOMMENDATION_STATUSES[0]],
        n_rejected=by[_c.RECOMMENDATION_STATUSES[3]],
        n_inconclusive_no_evidence=(
            by[_c.RECOMMENDATION_STATUSES[1]]
            + by[_c.RECOMMENDATION_STATUSES[2]]
        ),
        n_requires_more=by[_c.RECOMMENDATION_STATUSES[4]],
        n_conditional=by[_c.RECOMMENDATION_STATUSES[5]],
        n_promising=by[_c.RECOMMENDATION_STATUSES[6]],
        n_robust=by[_c.RECOMMENDATION_STATUSES[7]],
    )


_DEFAULT_GATES = {
    "min_reviewed_periods": _c.MIN_REVIEWED_PERIODS,
}
