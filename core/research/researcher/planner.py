"""
====================================================

QuantEngine

Autonomous AI Researcher -- planner (Phase 9H)

Deterministic, evidence-gated experiment design. The planner takes
provider hypothesis drafts (NullProvider by default) and turns them
into concrete Hypotheses with a STRICT contract:

   * experiment semantics are only ever drawn from the already
     supported 9B/9C vocabulary (ExperimentConfig fields + the
     canonical supported entry models). Unknown parameters or entry
     models FAIL LOUDLY (BLOCKED with a reason) -- behaviour is never
     invented.
   * hypotheses are gated on observed evidence; a vacuous population
     produces NO hypothesis (never a guess).
   * dedup against research memory prevents rediscovery of an
     identical idea.
   * ids are deterministic sha1 fingerprints of the intrinsic
     content.
====================================================
"""

import hashlib
import math

from core.research.researcher.types import EvidenceContext, Hypothesis
from core.research.researcher.memory import params_fingerprint
from core.research.counterfactual import SUPPORTED_ENTRY_MODELS
from core.research.lab.experiment_config import ExperimentConfig

SUPPORTED_GRID_KEYS = frozenset(ExperimentConfig.__dataclass_fields__)

_NUMERIC_FIELDS = {
    "entry_offset",
    "entry_offset_atr",
    "entry_model",
    "confirmation_distance",
    "breakout_buffer",
    "retest_tolerance",
    "max_entry_distance",
    "rr",
    "custom_stop_ratio",
    "custom_target_ratio",
    "expiry",
}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ResearchPlanner:
    """Turns provider drafts into validated, memory-deduped Hypotheses."""
    def __init__(self, memory=None):
        self.memory = memory

    # -------------------------------------------------

    def validate_override(self, field_name, values):
        """Raise ValueError on unsupported experiment semantics."""
        if field_name not in SUPPORTED_GRID_KEYS:
            raise ValueError(
                f"unsupported experiment parameter {field_name!r}: "
                f"supported={sorted(SUPPORTED_GRID_KEYS)}"
            )
        if field_name == "entry_model":
            for v in values:
                if v not in SUPPORTED_ENTRY_MODELS:
                    raise ValueError(
                        f"unsupported entry model {v!r}: "
                        f"supported={list(SUPPORTED_ENTRY_MODELS)}"
                    )
            return
        if field_name == "expiry":
            for v in values:
                if v is not None:
                    n = _num(v)
                    if n is None or n <= 0 or not float(n).is_integer():
                        raise ValueError(
                            f"expiry grid value {v!r} must be a positive "
                            "int or None"
                        )
            return
        for v in values:
            n = _num(v)
            if n is None or not math.isfinite(n) or n < 0:
                raise ValueError(
                    f"grid value {v!r} for {field_name!r} must be a "
                    "non-negative finite number"
                )

    # -------------------------------------------------

    def plan(self, context, provider, memory=None, base_config=None):
        """Produce validated Hypotheses + planner notes.

        base_config is unused by the pure planner (the executor merges
        the grid on top of it) but is accepted for API symmetry.
        """
        if not isinstance(context, EvidenceContext):
            raise TypeError("context must be an EvidenceContext")
        memory = memory or self.memory

        drafts = list(provider.propose_hypotheses(context))
        hypotheses = []
        notes = []

        for draft in drafts:
            overrides = dict(draft.get("overrides") or {})
            try:
                for field_name, values in sorted(overrides.items()):
                    self.validate_override(field_name, list(values))
            except ValueError as exc:
                notes.append(
                    f"blocked hypothesis ({draft.get('kind', '')}): {exc}"
                )
                continue

            if memory is not None:
                fp = params_fingerprint(overrides)
                q = draft.get("question", "")
                if self._seen(memory, q, fp):
                    notes.append(
                        f"skipped duplicate hypothesis "
                        f"({draft.get('kind', '')}): already studied "
                        "in research memory"
                    )
                    continue

            hypothesis_id = _hypothesis_id(draft.get("kind", ""), overrides)
            hypotheses.append(Hypothesis(
                hypothesis_id=hypothesis_id,
                kind=draft.get("kind", "GENERAL"),
                question=draft.get("question", ""),
                statement=draft.get("statement", ""),
                why=draft.get("why", ""),
                dataset=_dataset_for(context),
                features=tuple(draft.get("features") or ()),
                overrides=overrides,
                outcome_bars=draft.get("outcome_bars"),
                baseline_id="baseline",
            ))

        hypotheses.sort(key=lambda h: (h.kind, h.hypothesis_id))
        return hypotheses, notes

    # -------------------------------------------------

    @staticmethod
    def _seen(memory, question, fp):
        for prior in memory.recall(question):
            for h in prior.get("hypotheses") or []:
                if h.get("fingerprint") == fp:
                    return True
        return False


def _hypothesis_id(kind, overrides):
    payload = "hypothesis|%s|%s" % (
        kind,
        params_fingerprint(overrides),
    )
    return "H" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _dataset_for(context):
    return (
        f"population records={context.records} fills={context.filled} "
        f"population={context.population}"
    )