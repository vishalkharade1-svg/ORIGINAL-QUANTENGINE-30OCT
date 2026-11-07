"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- report

Deterministic research-only report surface.

The OOS report is a RESEARCH artifact, not a trading signal:
   * is_production_ready always raises (the contract never yields a
     tradable "go" from research OOS data),
   * emission_check always returns (False, reason),
   * the NEVER_EMITTED token is embedded so any production import scan
     can refuse the surface.

report_id is content-derived (stable under identical inputs), so a
byte-identical rerun yields an identical report_id -- determinism is
part of the 9M contract.
====================================================================
"""

import json
from dataclasses import dataclass, field
from functools import cached_property

from core.research.oos import constants as _c
from core.research.oos.aggregator import per_period_summary
from core.research.oos.oos_types import (
    stable_json,
    stable_json_round,
)
from core.research.regime.regime_types import short_id

# Promotion tokens that must NEVER appear in a 9M research report body.
# Mirrors the 9L isolation contract: the report is research-only and any
# production import scan that finds these refuses the surface.
NEVER_EMITTED = ("9M-PROMOTION", "PRODUCTION_READY", "TRADABLE-GO")

_GENERATED_BY = "QuantEngine-research-oos-9M"


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


@dataclass(frozen=True)
class OosReport:
    """Frozen research-only 9M report."""

    report_id: str = ""
    generated_by: str = _GENERATED_BY
    data: dict = field(default_factory=dict)
    derived: dict = field(default_factory=dict)
    partition: dict = field(default_factory=dict)
    familywise: dict = field(default_factory=dict)
    aggregate: dict = field(default_factory=dict)
    results: tuple = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)

    # ---------------------------------------------------------

    @cached_property
    def _snapshot(self):
        results = [
            _clean(r.to_dict()) for r in self.results
        ]
        return (
            "oos9m",
            _clean(self.partition),
            _clean(self.familywise),
            _clean(self.aggregate),
            results,
        )

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "generated_by": self.generated_by,
            "data": dict(self.data),
            "derived": dict(self.derived),
            "partition": dict(self.partition),
            "familywise": dict(self.familywise),
            "aggregate": dict(self.aggregate),
            "results": [r.to_dict() for r in self.results],
            "metadata": dict(self.metadata),
        }

    def to_json(self):
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def is_production_ready(self):
        raise ValueError(
            "Phase 9M OOS reports are RESEARCH-ONLY; "
            "is_production_ready must never return True "
            "(promotion tokens %s are never set)."
            % (NEVER_EMITTED,)
        )

    def emission_check(self):
        return False, (
            "OOS research reports are never emitted as tradable or "
            "automated signals; promotion tokens %s are irreducible "
            "and absent from every report body." % (NEVER_EMITTED,)
        )

    def render(self):
        lines = [
            "Researcher-OOS-9M report %s" % self.report_id,
            "  protocol: 6 chronological OOS periods over the trailing "
            "50% (no shuffle, split-protocol frozen)",
            "  hypotheses tested: %d | blocked: %d | "
            "rejected: %d | partial/promising: %d | robust: %d | "
            "validated_research_only: %d"
            % (
                int(self.aggregate.get("n_hypotheses", 0)),
                int(self.aggregate.get("n_blocked", 0)),
                int(self.aggregate.get("n_rejected", 0)),
                int(self.aggregate.get("n_partial_promising", 0)),
                int(self.aggregate.get("n_robust", 0)),
                int(self.aggregate.get("n_validated_research_only", 0)),
            ),
            "  familywise: family %s, raw alpha %s, corrected alpha %s, "
            "n_survive %s (Sidak)"
            % (
                self.familywise.get("family_size"),
                self.familywise.get("raw_alpha"),
                self.familywise.get("corrected_alpha"),
                self.familywise.get("survives_correction"),
            ),
        ]
        for r in self.results:
            lines.append(
                "  [%s] %s (%s) -- %s: %s"
                % (r.status, r.hypothesis_id, r.origin, r.statement or "?",
                   "; ".join(r.reasons)[:200])
            )
        return "\n".join(lines) + "\n"


def build_report(hypotheses, partition, familywise, aggregate,
                 results, metadata=None):
    """Deterministic OosReport built from the engine's raw outputs."""
    if partition is None:
        partition_dict = {
            "n_total": 0, "n_discovery": 0, "n_oos": 0,
            "n_oos_periods": 0, "chronological": True,
            "no_shuffle": True, "discovery_fraction": 0,
            "purge_bars": 0, "embargo_bars": 0,
            "leak_guard": {"status": "NONE"},
            "boundaries": [],
        }
        n_periods = 0
    else:
        partition_dict = dict(partition.to_dict())
        n_periods = partition.n_periods()

    if familywise is None:
        familywise = {
            "n_hypotheses": 0, "family_size": 0,
            "method": "Sidak-familywise",
            "raw_alpha": float(_c.ALPHA),
            "corrected_alpha": None,
            "note": "no hypotheses re-validated in this report",
            "survives_correction": 0,
        }
    else:
        familywise = dict(familywise)

    if aggregate is None:
        aggregate = {
            "n_hypotheses": 0, "n_blocked": 0,
            "n_unavailable_inconclusive": 0, "n_rejected": 0,
            "n_partial_promising": 0, "n_robust": 0,
            "n_validated_research_only": 0,
            "n_research_only_confirmed": 0, "n_periods": n_periods,
        }
    else:
        aggregate = dict(aggregate)

    derived_summary = {}
    if results:
        derived_summary = per_period_summary(
            tuple(results), n_periods)

    data = {
        "generated_by": _GENERATED_BY,
        "protocol_version": "9M-1",
        "protocol": {
            "chronological_only": True,
            "no_shuffle": True,
            "split_protocol_frozen": bool(
                _c.SPLIT_PROTOCOL_FROZEN),
            "note": _c.SPLIT_PROTOCOL_NOTE,
        },
        "research_only": True,
        "emission_guard": "is_production_ready always raises",
    }

    report = OosReport(
        report_id="PENDING",
        data=data,
        derived=dict(derived_summary),
        partition=partition_dict,
        familywise=familywise,
        aggregate=aggregate,
        results=tuple(results),
        metadata=dict(metadata or {}),
    )
    report_id = short_id("M", report._snapshot)
    object.__setattr__(report, "report_id", report_id)
    return report