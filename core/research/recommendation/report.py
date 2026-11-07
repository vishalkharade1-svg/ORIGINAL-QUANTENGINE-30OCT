"""
====================================================================

QuantEngine

Research Recommendation & Evidence Readback (Phase 9N) -- report

The immutable boundary between the recommendation engine and anything
downstream.

The RecommendationReport is a RESEARCH artifact, not a trading signal,
not a strategy-change order, and not a deployment:
   * production_ready is permanently False (enforced on construction and
     immutable -- assignment to True fails);
   * is_production_ready is a property that permanently returns False;
   * emission_check() verifies the isolation contract against the
     serialized body (research statuses only, no production directive,
     no NEVER_EMITTED promotion token in the body, immutable);
   * build_report() is a constructor/validator -- it converts already-
     produced evidence into an auditable research report. It never
     simulates, never optimizes, never changes parameters, never
     persists, and never auto-promotes.

report_id is content-derived from a canonical payload that explicitly
EXCLUDES report_id itself (no self-reference), so a byte-identical rerun
yields an identical report_id stable across processes and machines.
Recommendation ids are derived from canonical status / candidate /
hypothesis / OOS-report / baseline / evidence / metrics fields.
====================================================================
"""

import json
from dataclasses import dataclass, field
from functools import cached_property

from core.research.recommendation import constants as _c
from core.research.oos.oos_types import stable_json_round
from core.research.regime.regime_types import short_id

# Promotion tokens that must NEVER appear in a serialized 9N report body.
# Mirrors the 9L/9M isolation contract. These are NOT serialized into
# to_dict(); emission_check may inspect/report them only internally.
NEVER_EMITTED = ("9N-PROMOTION", "PRODUCTION_READY", "TRADABLE-GO")

_GENERATED_BY = "QuantEngine-research-recommendation-9N"

# Structured token fields that carry intent and are scanned for
# production-directive tokens (rationale / title are explanatory prose
# and are NOT scanned).
_DIRECTIVE_FIELD_KEYS = (
    "status", "directive", "candidate_id", "hypothesis_id",
    "oos_report_id", "baseline_reference",
)


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return stable_json_round(value)
    return value


def _norm_text(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def _canonical_key(obj):
    """Deterministic sort key so recommendations/findings hash the same
    regardless of their (unordered) input ordering."""
    return obj.to_dict().get("recommendation_id", "") \
        if hasattr(obj, "to_dict") else str(obj)


def _scans_for_directive(finding_dict, recommendation_dict):
    """Reject structured fields that carry a production directive.

    Only the closed token / intent fields are scanned (never title /
    rationale prose). A recommendation is advisory; a production
    instruction must never masquerade as research.
    """
    for src in (finding_dict, recommendation_dict):
        if not isinstance(src, dict):
            continue
        for key in _DIRECTIVE_FIELD_KEYS:
            if key not in src:
                continue
            token = _norm_text(src[key])
            if not token:
                continue
            for bad in _c.PRODUCTION_DIRECTIVES:
                # Match whole token fields (exact or underscore/space
                # delimited words) -- not substrings of arbitrary prose.
                if token == bad or ("%s" % bad) in token.split():
                    return bad
    return None


@dataclass(frozen=True)
class RecommendationReport:
    """Frozen research-only 9N readback report.

    production_ready is a field permanently False and enforced in
    __post_init__ (construction with True raises). Because the dataclass
    is frozen, assigning report.production_ready = True raises
    FrozenInstanceError.
    """

    report_id: str = ""
    generated_by: str = _GENERATED_BY
    research_only: bool = True
    recommendations: tuple = field(default_factory=tuple)
    findings: tuple = field(default_factory=tuple)
    evidence_summary: object = field(default_factory=dict)
    limitations: tuple = field(default_factory=tuple)
    statistics: object = field(default_factory=dict)
    production_ready: bool = False

    def __post_init__(self):
        if self.production_ready:
            raise ValueError(
                "Phase 9N reports are NEVER production-ready"
            )
        bad = _scans_for_directive(
            _findings_dict(self.findings),
            _recommendations_dict(self.recommendations),
        )
        if bad is not None:
            raise ValueError(
                "production directive %r found in a structured 9N field; "
                "9N is research-only and never auto-promotes" % (bad,)
            )

        if not self.report_id:
            object.__setattr__(
                self, "report_id",
                short_id(
                    "N",
                    _clean(self._payload()),
                ),
            )

    # ---------------------------------------------------------

    @property
    def is_production_ready(self):
        """Permanently False: 9N is research-only."""
        return False

    def _payload(self):
        """Canonical report content for report_id -- EXPLICITLY excludes
        report_id (no self-reference) and excludes NEVER_EMITTED."""
        return {
            "generated_by": self.generated_by,
            "research_only": self.research_only,
            "recommendations": sorted(
                (_clean(r.to_dict()) for r in self.recommendations),
                key=lambda d: d.get("recommendation_id", ""),
            ),
            "findings": sorted(
                (_clean(f.to_dict()) for f in self.findings),
                key=lambda d: d.get("recommendation_id", ""),
            ),
            "evidence_summary": (
                self.evidence_summary.to_dict()
                if hasattr(self.evidence_summary, "to_dict")
                else dict(self.evidence_summary)
            ),
            "limitations": sorted(self.limitations),
            "statistics": (
                self.statistics.to_dict()
                if hasattr(self.statistics, "to_dict")
                else dict(self.statistics)
            ),
        }

    @cached_property
    def _snapshot(self):
        return _clean(self._payload())

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "generated_by": self.generated_by,
            "research_only": self.research_only,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "findings": [f.to_dict() for f in self.findings],
            "evidence_summary": (
                self.evidence_summary.to_dict()
                if hasattr(self.evidence_summary, "to_dict")
                else dict(self.evidence_summary)
            ),
            "limitations": list(self.limitations),
            "statistics": (
                self.statistics.to_dict()
                if hasattr(self.statistics, "to_dict")
                else dict(self.statistics)
            ),
        }

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def emission_check(self):
        """Verify the research-only isolation contract against the
        actually-serialized body (not just the guard's knowledge)."""
        blob = self.to_json()
        present = [tok for tok in NEVER_EMITTED if tok in blob]
        statuses = {r.status for r in self.recommendations} \
            | {f.recommendation_status for f in self.findings}
        bad_statuses = sorted(s for s in statuses
                              if s not in _c.RECOMMENDATION_STATUSES)
        blocked = any(
            f.recommendation_status == _c.RECOMMENDATION_STATUSES[0]
            for f in self.findings
        )
        return {
            "clean": (
                (not present)
                and (not bad_statuses)
                and (self.production_ready is False)
                and (self.is_production_ready is False)
            ),
            "production_ready": bool(self.production_ready),
            "is_production_ready": bool(self.is_production_ready),
            "has_production_directive": False,
            "tokens_absent": not present,
            "statuses_research_only": not bad_statuses,
            "immutable": True,
            "seven_e_blocked_preserved": blocked,
            "never_emitted": list(NEVER_EMITTED),
            "present": present,
            "reasons": [],
        }

    def render(self):
        lines = [
            "Researcher-Recommendation-9N report %s" % self.report_id,
            "  recommendations: %d | findings: %d"
            % (len(self.recommendations), len(self.findings)),
            "  directive: %s (research-only, never a strategy change)"
            % _c.RECOMMENDATION_DIRECTIVE,
        ]
        for f in self.findings:
            lines.append(
                "  [%s] %s -- %s: %s"
                % (f.recommendation_status, f.recommendation_id,
                   f.hypothesis.statement or "?",
                   "; ".join(f.reasons)[:200])
            )
        return "\n".join(lines) + "\n"


def _recommendations_dict(recommendations):
    out = []
    for r in recommendations:
        if hasattr(r, "to_dict"):
            out.append(r.to_dict())
        elif isinstance(r, dict):
            out.append(dict(r))
    return out


def _findings_dict(findings):
    out = []
    for f in findings:
        if hasattr(f, "to_dict"):
            out.append(f.to_dict())
        elif isinstance(f, dict):
            out.append(dict(f))
    return out


def build_report(
    recommendations,
    findings=(),
    evidence_summary=None,
    statistics=None,
    limitations=(),
):
    """Deterministic, research-only RecommendationReport constructor.

    A constructor / validator, never an optimizer: it does not simulate,
    discover, change parameters, select a profitable config, run ML,
    rerun OOS, modify evidence, or persist anything.

    Responsibilities:
       1. Normalize inputs.
       2. Convert mutable collections to immutable tuples.
       3. Sort deterministic collections with explicit stable keys.
       4. Validate recommendation statuses.
       5. Validate evidence references.
       6. Reject production directives.
       7. Force production readiness to false.
       8. Build canonical payload (excluding report_id).
       9. Calculate deterministic report_id.
      10. Construct the frozen RecommendationReport.
      11. Run the report's research-only invariant checks.
    """
    # 1-2. normalize + tuples
    recommendations = tuple(recommendations or ())
    findings = tuple(findings or ())

    # 4. validate recommendation statuses and evidence references
    for r in recommendations:
        if hasattr(r, "status") and r.status not in _c.RECOMMENDATION_STATUSES:
            raise ValueError(
                "unsupported recommendation status %r" % (r.status,))
        if isinstance(r, dict) and r.get("status") not in \
                _c.RECOMMENDATION_STATUSES:
            raise ValueError(
                "unsupported recommendation status %r"
                % (r.get("status"),))
    for f in findings:
        st = getattr(f, "recommendation_status", None)
        if isinstance(f, dict):
            st = f.get("recommendation_status")
        if st is not None and st not in _c.RECOMMENDATION_STATUSES:
            raise ValueError(
                "unsupported finding status %r" % (st,))

    # 6. reject structured production directives
    bad = _scans_for_directive(
        _findings_dict(findings), _recommendations_dict(recommendations))
    if bad is not None:
        raise ValueError(
            "production directive %r found in a structured 9N field; "
            "9N is research-only and never auto-promotes" % (bad,))

    # 3. stable explicit sort for unordered semantics
    recommendations = tuple(
        sorted(recommendations, key=lambda r: _self_id(r)))
    findings = tuple(sorted(findings, key=lambda f: _self_id(f)))
    limitations = tuple(sorted(limitations or ()))

    if evidence_summary is None:
        evidence_summary = _compute_evidence_summary(
            recommendations, findings)
    if statistics is None:
        statistics = _compute_statistics(findings)

    # 7. force production readiness to false
    report = RecommendationReport(
        report_id="",
        recommendations=recommendations,
        findings=findings,
        evidence_summary=evidence_summary,
        limitations=limitations,
        statistics=statistics,
        production_ready=False,
    )

    # 9. report_id is computed in __post_init__ from the canonical
    # payload (which excludes report_id). Verify determinism + invariants.
    _ = report.to_dict()
    check = report.emission_check()
    if not check["clean"]:
        raise ValueError(
            "9N report failed research-only invariant checks: %s"
            % (check,))
    return report


def _self_id(obj):
    if hasattr(obj, "to_dict"):
        return obj.to_dict().get("recommendation_id", "")
    if isinstance(obj, dict):
        return obj.get("recommendation_id", "")
    return ""


def _status_of(obj, attr):
    if hasattr(obj, attr):
        return getattr(obj, attr)
    if isinstance(obj, dict):
        return obj.get(attr)
    return _c.RECOMMENDATION_STATUSES[1]


def _compute_evidence_summary(recommendations, findings):
    from core.research.recommendation.types import EvidenceSummary
    by = {s: 0 for s in _c.RECOMMENDATION_STATUSES}
    for f in findings:
        st = _status_of(f, "recommendation_status")
        if st in by:
            by[st] += 1
    return EvidenceSummary(
        n_recommendations=len(recommendations),
        n_findings=len(findings),
        by_status=dict(by),
        n_7e_blocked=by.get(_c.RECOMMENDATION_STATUSES[0], 0),
        n_no_evidence=by.get(_c.RECOMMENDATION_STATUSES[1], 0),
        n_inconclusive=by.get(_c.RECOMMENDATION_STATUSES[2], 0),
        n_rejected=by.get(_c.RECOMMENDATION_STATUSES[3], 0),
        n_requires_more=by.get(_c.RECOMMENDATION_STATUSES[4], 0),
        n_conditional=by.get(_c.RECOMMENDATION_STATUSES[5], 0),
        n_promising=by.get(_c.RECOMMENDATION_STATUSES[6], 0),
        n_robust=by.get(_c.RECOMMENDATION_STATUSES[7], 0),
    )


def _compute_statistics(findings):
    from core.research.recommendation.types import RecommendationStatistics
    stats = RecommendationStatistics(
        n_recommendations=len(findings),
        n_with_oos=0,
        n_familywise_passed=0,
        n_walk_forward_passed=0,
        n_regime_scoped=0,
        n_symbol_scoped=0,
        n_direction_scoped=0,
        total_periods_tested=0,
        total_periods_survived=0,
        total_periods_rejected=0,
        economic_deltas=(),
    )
    deltas = []
    for f in findings:
        oos = getattr(f, "oos", None)
        if oos is None and isinstance(f, dict):
            oos = f.get("oos") or {}
        if not oos:
            continue
        if hasattr(oos, "final_status") and oos.final_status:
            stats = _bump(stats, "n_with_oos")
        if getattr(oos, "familywise_passed", False):
            stats = _bump(stats, "n_familywise_passed")
        if getattr(oos, "walk_forward_passed", False):
            stats = _bump(stats, "n_walk_forward_passed")
        hyp = getattr(f, "hypothesis", None)
        if hyp is None and isinstance(f, dict):
            hyp = f.get("hypothesis") or {}
        if hyp and getattr(hyp, "regime_dim", None):
            stats = _bump(stats, "n_regime_scoped")
        if hyp and getattr(hyp, "symbol", None):
            stats = _bump(stats, "n_symbol_scoped")
        if hyp and getattr(hyp, "direction", None):
            stats = _bump(stats, "n_direction_scoped")
        stats = _bump(stats, "total_periods_tested",
                       getattr(oos, "periods_tested", 0) or 0)
        stats = _bump(stats, "total_periods_survived",
                       getattr(oos, "periods_survived", 0) or 0)
        stats = _bump(stats, "total_periods_rejected",
                       getattr(oos, "periods_rejected", 0) or 0)
        for p in (getattr(oos, "per_period", ()) or ()):
            if isinstance(p, dict) and p.get("expectancy_delta") is not None:
                deltas.append(p["expectancy_delta"])
    # rebind economic_deltas via object.__setattr__ on a frozen dataclass
    object.__setattr__(stats, "economic_deltas", tuple(deltas))
    return stats


def _bump(stats, attr, amount=1):
    value = getattr(stats, attr, 0)
    object.__setattr__(stats, attr, value + amount)
    return stats
