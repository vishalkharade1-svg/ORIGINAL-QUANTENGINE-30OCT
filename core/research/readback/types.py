"""
====================================================================

QuantEngine

Research UX -- Recommendation Readback (Phase 9O) -- types

Frozen, deterministic containers for explaining a frozen 9N
RecommendationReport to a human (or a future interpreter).

Every recommendation in the consumed 9N report maps 1:1 to a
ReadbackEntry that carries:

    * the research verdict (a closed RESEARCH_VERDICTS member; the
      maximum is VALIDATED_RESEARCH_FINDING -- never TRADABLE),
    * per-aspect evidence explanations (OOS / regime / discovery /
      counterfactual / baseline / supporting metrics),
    * negative evidence and limitations (what failed -- nothing hidden),
    * the closed uncertainty roster,
    * a deterministic rationale in prose for "why this exists",
    * the production status RESEARCH_ONLY.

The whole ReadbackReport is frozen and research-only. Its
production_status is always RESEARCH_ONLY, and it cannot ever claim a
TRADABLE_STRATEGY verdict (the vocabulary has no such member).
====================================================================
"""

import json
from dataclasses import dataclass, field
from functools import cached_property

from core.research.readback import constants as _c
from core.research.oos.oos_types import stable_json_round
from core.research.regime.regime_types import short_id


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


def _story(aspects):
    """Deterministic, canonical ordered list of (aspect, entries) rows
    used for stable derivation; entries are flattened to scalars."""
    out = []
    for aspect in _c.EXPLANATION_ASPECTS:
        items = aspects.get(aspect)
        if not items:
            continue
        for it in items:
            if isinstance(it, dict):
                out.append((aspect, str(it.get("key", "")),
                            str(it.get("label", ""))))
            else:
                out.append((aspect, str(it), ""))
    return out


@dataclass(frozen=True)
class ReadbackEntry:
    """One 9O explanation for exactly one 9N recommendation."""

    recommendation_id: str = ""
    research_verdict: str = _c.RESEARCH_VERDICTS[0]
    evidence_status: str = ""
    title: str = ""
    claim: str = ""
    rationale: str = ""
    aspects: dict = field(default_factory=dict)
    uncertainty: tuple = field(default_factory=tuple)
    production_status: str = _c.PRODUCTION_STATUS

    def __post_init__(self):
        if self.research_verdict not in _c.RESEARCH_VERDICTS:
            raise ValueError(
                "unsupported research verdict %r; supported=%s"
                % (self.research_verdict, _c.RESEARCH_VERDICTS)
            )
        for u in self.uncertainty:
            if u not in _c.UNCERTAINTY_ROSTER:
                raise ValueError(
                    "unknown uncertainty tag %r; supported=%s"
                    % (u, _c.UNCERTAINTY_ROSTER)
                )
        if self.production_status != _c.PRODUCTION_STATUS:
            raise ValueError(
                "9O readback production status must be %r"
                % (_c.PRODUCTION_STATUS,)
            )
        if not self.recommendation_id:
            object.__setattr__(
                self, "recommendation_id",
                short_id(
                    "O",
                    self.research_verdict,
                    self.evidence_status,
                    sorted(_story(self.aspects)),
                    sorted(self.uncertainty),
                ),
            )

    @property
    def is_tradable(self):
        """Permanently False: no 9O readback is ever tradable."""
        return False

    def to_dict(self):
        return {
            "recommendation_id": self.recommendation_id,
            "research_verdict": self.research_verdict,
            "evidence_status": self.evidence_status,
            "title": self.title,
            "claim": self.claim,
            "rationale": self.rationale,
            "aspects": dict(self.aspects),
            "uncertainty": list(self.uncertainty),
            "production_status": self.production_status,
        }


@dataclass(frozen=True)
class ReadbackReport:
    """Frozen research-only 9O explanation over a frozen 9N report.

    production_status is always RESEARCH_ONLY and enforced in
    __post_init__; the frozen dataclass makes assignment fail.
    is_tradable is a property permanently returning False.
    """

    report_id: str = ""
    generated_by: str = "QuantEngine-research-readback-9O"
    production_status: str = _c.PRODUCTION_STATUS
    research_verdicts: tuple = field(default_factory=tuple)
    entries: tuple = field(default_factory=tuple)
    uncertainty_summary: tuple = field(default_factory=tuple)
    source_report_id: str = ""

    def __post_init__(self):
        if self.production_status != _c.PRODUCTION_STATUS:
            raise ValueError(
                "9O readback reports are NEVER production-ready"
            )
        for e in self.entries:
            if not hasattr(e, "recommendation_id"):
                raise ValueError(
                    "9O entries must be ReadbackEntry instances"
                )
        if not self.report_id:
            object.__setattr__(
                self, "report_id",
                short_id("O", _clean(self._payload())),
            )

    @property
    def is_tradable(self):
        """Permanently False: 9O readback is research-only."""
        return False

    def _payload(self):
        """Canonical report content for report_id -- EXCLUDES report_id
        (no self-reference) and never includes a tradable token."""
        return {
            "generated_by": self.generated_by,
            "production_status": self.production_status,
            "research_verdicts": sorted(self.research_verdicts),
            "entries": sorted(
                (_clean(e.to_dict()) for e in self.entries),
                key=lambda d: d.get("recommendation_id", ""),
            ),
            "uncertainty_summary": sorted(self.uncertainty_summary),
            "source_report_id": self.source_report_id,
        }

    @cached_property
    def _snapshot(self):
        return _clean(self._payload())

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "generated_by": self.generated_by,
            "production_status": self.production_status,
            "research_verdicts": list(self.research_verdicts),
            "entries": [e.to_dict() for e in self.entries],
            "uncertainty_summary": list(self.uncertainty_summary),
            "source_report_id": self.source_report_id,
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
        actually-serialized body."""
        blob = self.to_json()
        present = [tok for tok in _c.NEVER_EMITTED if tok in blob]
        tradable = any(getattr(e, "is_tradable", False) for e in self.entries)
        verdicts = set(self.research_verdicts)
        bad = sorted(v for v in verdicts
                     if v not in _c.RESEARCH_VERDICTS)
        return {
            "clean": (
                (not present)
                and (not tradable)
                and (not bad)
                and (self.production_status == _c.PRODUCTION_STATUS)
                and (self.is_tradable is False)
            ),
            "tradable_requested": tradable,
            "production_status": self.production_status,
            "is_tradable": bool(self.is_tradable),
            "tokens_absent": not present,
            "verdicts_research_only": not bad,
            "immutable": True,
            "never_emitted": list(_c.NEVER_EMITTED),
            "present": present,
            "reasons": [],
        }

    def render(self):
        lines = [
            "Researcher-Readback-9O report %s"
            % self.report_id,
            "  source: 9N report %s" % self.source_report_id,
            "  production_status: %s"
            % self.production_status,
            "  verdicts: %s" % ", ".join(sorted(self.research_verdicts)),
            "  tradable: NO (impossible at this boundary)",
        ]
        for e in self.entries:
            lines.append("")
            lines.append("  [%s] %s" % (e.research_verdict, e.title))
            lines.append("    claim: %s" % e.claim)
            lines.append("    why: %s" % e.rationale)
            if e.aspects:
                for aspect in _c.EXPLANATION_ASPECTS:
                    items = e.aspects.get(aspect)
                    if items:
                        labels = "; ".join(
                            (it.get("label", str(it)) if isinstance(it, dict)
                             else str(it)) for it in items)
                        lines.append("    %s: %s" % (aspect, labels))
            if e.uncertainty:
                lines.append("    uncertainty: %s"
                             % ", ".join(e.uncertainty))
            lines.append("    production: %s" % e.production_status)
        return "\n".join(lines) + "\n"
