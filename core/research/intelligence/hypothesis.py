"""
====================================================

QuantEngine

Research Intelligence -- hypothesis generation (Phase 9E)

Deterministic, traceable research hypotheses derived from observed
9D evidence. Every hypothesis names its experiment id(s), describes
the candidate change in a testable form, and carries the baseline /
candidate ids. Hypotheses are NOT production proposals -- they are
candidates for a later validation (9F / OOS) layer.

Generated from real metrics only; never fabricates a claim.
====================================================
"""

from dataclasses import dataclass, field
import hashlib
import json


def _stable(key, hyp_text, exp_ids):
    payload = json.dumps(
        {"category": key, "hypothesis": hyp_text, "ids": sorted(exp_ids)},
        sort_keys=True,
        default=list,
    ).encode("utf-8")
    return "hyp-" + hashlib.sha1(payload).hexdigest()[:12]


@dataclass(frozen=True)
class Hypothesis:
    """One deterministic research hypothesis."""

    hypothesis_id: str = ""
    text: str = ""
    source_experiment_ids: tuple = field(default_factory=tuple)
    category: str = ""

    def to_dict(self):
        return {
            "hypothesis_id": self.hypothesis_id,
            "text": self.text,
            "source_experiment_ids": list(self.source_experiment_ids),
            "category": self.category,
        }


def _hyp(text, src_ids, category):
    return Hypothesis(
        hypothesis_id=_stable(category, text, src_ids),
        text=text,
        source_experiment_ids=tuple(sorted(src_ids)),
        category=category,
    )


def generate_hypotheses(recommendations, parameter_insights=None,
                        directional_by_id=None):
    """Deterministic hypothesis set from recommendations + insights.

    Publishes one hypothesis per recommendation (entry-category
    recovery / parameter move) plus directional caveats for any
    experiment flagged directional-imbalanced. Returns a list of
    Hypothesis (sorted by id for determinism).
    """
    hyps = []
    for rec in (recommendations or []):
        src = [
            rec.baseline_experiment_id,
            *rec.candidate_experiment_ids,
        ]
        src = [e for e in src if e]
        if rec.category == "ENTRY_RECOVERY":
            hyps.append(_hyp(
                f"BREAKOUT/alternative entry may recover "
                f"{rec.affected_opportunity_categories} opportunities; "
                f"recovered {rec.recovered_wins} wins / "
                f"{rec.recovered_losses} losses "
                f"(experiment {rec.candidate_experiment_ids}).",
                src, rec.category,
            ))
        elif rec.category == "ENTRY_NOT_REACHED":
            hyps.append(_hyp(
                f"extending expiry / adjusting entry offset may recover "
                f"ENTRY_NOT_REACHED opportunities (recovered "
                f"{rec.recovered_wins} wins).",
                src, rec.category,
            ))
        elif rec.category == "MISSED_CONTINUATION":
            hyps.append(_hyp(
                f"widening the entry window may recover "
                f"MISSED_CONTINUATION opportunities.",
                src, rec.category,
            ))
        elif rec.category == "RR_ANALYSIS":
            hyps.append(_hyp(
                f"RR {rec.parameters_changed.get('rr')} produced "
                f"delta_expectancy {rec.expectancy_delta:.2f} in the "
                f"evaluated population; OOS validation required.",
                src, rec.category,
            ))
        elif rec.category == "EXPIRY_ANALYSIS":
            hyps.append(_hyp(
                f"expiry {rec.parameters_changed.get('expiry')} "
                f"recovered {rec.recovered_opportunities} "
                f"opportunities (wins {rec.recovered_wins}).",
                src, rec.category,
            ))
        else:
            hyps.append(_hyp(
                f"{rec.category}: {rec.title}",
                src, rec.category,
            ))

    for exp_id, info in (directional_by_id or {}).items():
        if info.get("directional_imbalance_flag"):
            hyps.append(_hyp(
                f"experiment {exp_id} is directionally imbalanced; "
                "any apparent improvement is direction-specific, "
                "research-only, and requires directional OOS validation.",
                [exp_id], "DIRECTIONAL_ANALYSIS",
            ))

    for p_ins in (parameter_insights or []):
        for row in p_ins.rows:
            hyps.append(_hyp(
                f"parameter {p_ins.param}={row['value']}: "
                f"expectancy {row['expectancy']:.2f}, "
                f"total_R {row['total_R']:.2f}, "
                f"sample {row['sample_size']}.",
                row.get("experiment_ids", []), "PARAMETER_INSIGHT",
            ))

    hyps.sort(key=lambda h: h.hypothesis_id)
    return hyps