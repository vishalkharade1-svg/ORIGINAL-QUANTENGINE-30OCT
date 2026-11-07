"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- discovery report

The deterministic, immutable report of one discovery run:

   * full provenance (dataset shape, vocabulary, gaps, hypotheses,
     skipped items, every experiment INCLUDING rejected/inconclusive/
     blocked ones);
   * recovery + confluence evidence;
   * a deterministic ranking (score desc, then expectancy delta desc,
     then settled desc, then id) whose SCORING COMPONENTS are exposed
     on every experiment (score / status / delta_expectancy / settled
     / population note) -- never hidden;
   * explicit limitations + next-research suggestions + the 7E NO-GO
     preservation block;
   * research_only disclaimer; is_production_ready is permanently
     False; no promotion token is ever emitted.

report_id is a deterministic sha1 over the run content (experiments,
findings, gaps, recovery head), so repeated runs are byte-identical.
====================================================
"""

from dataclasses import dataclass, field

from core.research.discovery.constants import (
    RESEARCH_ONLY_DISCLAIMER,
    NEVER_EMITTED,
    gate_score,
)
from core.research.discovery.discovery_types import (
    stable_json,
    sha1_digest,
)


def _rank_experiments(experiments):
    """Deterministic ranking: status score, expectancy delta, settled."""
    ranked = []
    for e in experiments:
        ranked.append({
            "experiment_id": e.experiment_id,
            "hypothesis_id": e.hypothesis_id,
            "status": e.status,
            "score": gate_score(e.status),
            "delta_expectancy": float(
                (e.comparison or {}).get("delta_expectancy") or 0.0
            ),
            "settled": int((e.metrics or {}).get("settled", 0)),
            "population_note": e.population_note,
        })
    ranked.sort(key=lambda r: (
        -r["score"],
        -r["delta_expectancy"],
        -r["settled"],
        r["experiment_id"],
    ))
    return tuple(ranked)


@dataclass(frozen=True)
class DiscoveryReport:
    """One deterministic discovery run report (research-only)."""

    report_id: str
    symbol: str
    phase: str = "9J"
    dataset_shape: dict = field(default_factory=dict)
    vocabulary: dict = field(default_factory=dict)
    gaps: tuple = field(default_factory=tuple)
    hypotheses: tuple = field(default_factory=tuple)
    skipped: tuple = field(default_factory=tuple)
    experiments: tuple = field(default_factory=tuple)
    findings: tuple = field(default_factory=tuple)
    recovery: dict = field(default_factory=dict)
    confluence: dict = field(default_factory=dict)
    ranking: tuple = field(default_factory=tuple)
    limitations: tuple = field(default_factory=tuple)
    next_research: tuple = field(default_factory=tuple)
    seven_e: dict = field(default_factory=dict)
    research_only: str = RESEARCH_ONLY_DISCLAIMER
    is_production_ready: bool = False

    def __post_init__(self):
        if self.is_production_ready:
            raise ValueError(
                "a DiscoveryReport is NEVER production ready"
            )

    # -------------------------------------------------

    @classmethod
    def build(cls, *, symbol, dataset_shape, vocabulary, gaps,
              hypotheses, skipped, experiments, findings, recovery,
              confluence, limitations, next_research, seven_e):
        report_id = cls._report_id(
            experiments, findings, gaps, recovery, confluence
        )
        return cls(
            report_id=report_id,
            symbol=symbol,
            dataset_shape=dict(dataset_shape or {}),
            vocabulary=dict(vocabulary or {}),
            gaps=tuple(sorted(gaps, key=lambda g: g.gap_id))
                if gaps else (),
            hypotheses=tuple(sorted(
                hypotheses, key=lambda h: h.hypothesis_id
            )) if hypotheses else (),
            skipped=tuple(sorted(
                skipped,
                key=lambda s: (s[0].hypothesis_id, s[1]),
            )) if skipped else (),
            experiments=tuple(sorted(
                experiments, key=lambda e: e.experiment_id
            )) if experiments else (),
            findings=tuple(sorted(
                findings, key=lambda f: f.finding_id
            )) if findings else (),
            recovery=dict(recovery or {}),
            confluence=dict(confluence or {}),
            ranking=_rank_experiments(experiments) if experiments else (),
            limitations=tuple(limitations or ()),
            next_research=tuple(next_research or ()),
            seven_e=dict(seven_e or {}),
        )

    @staticmethod
    def _report_id(experiments, findings, gaps, recovery, confluence):
        payload = {
            "experiments": [e.to_dict() for e in experiments],
            "findings": [f.to_dict() for f in findings],
            "gaps": [g.to_dict() for g in gaps],
            "recovery": {
                "recovered_observations": (recovery or {}).get(
                    "recovered_observations", ()
                ),
                "recovery_count": (recovery or {}).get("recovery_count", 0),
            },
            "confluence": {
                "feature_availability": (confluence or {}).get(
                    "feature_availability", []
                ),
                "associations": (confluence or {}).get("associations", ()),
            },
        }
        return "J-%s" % sha1_digest(payload)[:10]

    # -------------------------------------------------

    @property
    def emission_check(self):
        """True when no promotion token ever appears in the report."""
        blob = stable_json(self.to_dict())
        return all(token not in blob for token in NEVER_EMITTED)

    def to_dict(self):
        return {
            "phase": self.phase,
            "report_id": self.report_id,
            "symbol": self.symbol,
            "dataset_shape": dict(self.dataset_shape),
            "vocabulary": dict(self.vocabulary),
            "gaps": [g.to_dict() for g in self.gaps],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "skipped": [
                {"hypothesis_id": h.hypothesis_id, "reason": reason}
                for h, reason in self.skipped
            ],
            "experiments": [e.to_dict() for e in self.experiments],
            "findings": [f.to_dict() for f in self.findings],
            "recovery": dict(self.recovery),
            "confluence": dict(self.confluence),
            "ranking": list(self.ranking),
            "limitations": list(self.limitations),
            "next_research": list(self.next_research),
            "seven_e": dict(self.seven_e),
            "research_only": self.research_only,
            "is_production_ready": self.is_production_ready,
        }

    # -------------------------------------------------

    def render(self):
        lines = []
        lines.append(f"Phase {self.phase} Strategy Discovery -- "
                     f"symbol={self.symbol} (research-only)")
        lines.append(f"report_id={self.report_id}")
        lines.append("")
        lines.append("dataset_shape: %s" % str(self.dataset_shape))
        lines.append("gaps (%d): %s"
                     % (len(self.gaps), ", ".join(
                         f"{g.category}={g.count}" for g in self.gaps
                     )))
        lines.append("hypotheses (%d)" % len(self.hypotheses))
        lines.append("skipped (%d)" % len(self.skipped))
        lines.append("experiments (%d, ALL retained)"
                     % len(self.experiments))
        lines.append("")
        lines.append("ranking:")
        for r in self.ranking:
            lines.append(
                f"  {r['experiment_id']} {r['status']} "
                f"score={r['score']:.1f} "
                f"delta_expectancy={r['delta_expectancy']:.4f} "
                f"settled={r['settled']}"
            )
        lines.append("")
        repro = self.recovery or {}
        lines.append(f"recovery: {repro.get('recovery_count', 0)} "
                     f"recovered, added_R={repro.get('added_R', 0.0)}")
        conf = self.confluence or {}
        lines.append("confluence: %s"
                     % conf.get("status", "OBSERVED_ASSOCIATIONS_ONLY"))
        lines.append("")
        lines.append("limitations:")
        for note in self.limitations:
            lines.append(f"  - {note}")
        lines.append("")
        lines.append("next_research:")
        for note in self.next_research:
            lines.append(f"  - {note}")
        lines.append("")
        lines.append("seven_e: %s" % str(self.seven_e))
        lines.append("is_production_ready: %s" % self.is_production_ready)
        return "\n".join(lines)