"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- gap detection &
hypothesis generation

Deterministic, evidence-gated discovery: the engine NEVER guesses.
Every hypothesis is derived from OBSERVED evidence in the 9I unified
dataset (queries.entry_pipeline_breakdown / recovery_candidates).

   detect_gaps(dataset)
       turns the 9I entry-pipeline and recovery-candidate evidence into
       OpportunityGap objects (which categories / reasons / recovery
       potential were missed).

   generate_hypotheses(dataset, base_config, symbol)
       maps each gap to the SMALLEST defensible parameter change
       (recovery-first: entry offset / entry model / expiry / RR /
       stop gear) expressed ONLY in the supported 9B/9C vocabulary.
       Unsupported params never appear; evidence is carried on each
       hypothesis.

Every hypothesis is executable (non-empty overrides) and carries its
evidence row ids. Ordering is deterministic (kind, question, id).
This module NEVER invents a feature or a simulation parameter.
====================================================
"""

from core.research.dataset import (
    DatasetSource as S,
    entry_pipeline_breakdown,
    recovery_candidates,
)
from core.research.discovery.candidate_space import SUPPORTED_ENTRY_MODELS
from core.research.discovery.discovery_types import (
    OpportunityGap,
    DiscoveryHypothesis,
    short_id,
)
from core.research.counterfactual import (
    FILLED,
    REJECTED,
    MISSED_CONTINUATION,
    INVALIDATED,
    ENTRY_NOT_REACHED,
)

# categories we investigate for missed economic value (NON_EVALUABLE is
# deliberately excluded: there is no opportunity evidence there).
_GAP_CATEGORIES = (
    ENTRY_NOT_REACHED,
    MISSED_CONTINUATION,
    REJECTED,
    INVALIDATED,
    FILLED,
)

_KIND_ORDER = (
    "RECOVERY_ENTRY_OFFSET",
    "RECOVERY_ENTRY_MODEL",
    "RECOVERY_EXPIRY",
    "RECOVERY_CONFIRMATION",
    "RECOVERY_RR",
    "RECOVERY_STOP",
)


# ==================================================================
# gap detection
# ==================================================================
def _rows_for_category(dataset, category):
    return [
        r for r in dataset.rows(S.JOURNAL)
        if r.category == category
    ]


def _category_gap(dataset, category):
    """Align a JOURNAL category with an OpportunityGap (or None)."""
    rows = _rows_for_category(dataset, category)
    if not rows:
        return None
    observation_ids = tuple(sorted({
        r.observation_id for r in rows if r.observation_id
    }))
    instruments = tuple(sorted({
        r.instrument_id for r in rows if r.instrument_id
    }))
    directions = tuple(sorted({
        r.direction for r in rows if r.direction
    }))
    reasons = tuple(sorted({
        str(x)
        for r in rows
        for x in (r.kv.get("rejection_reasons") or [])
        if x
    }))
    return OpportunityGap(
        category=category,
        count=len(rows),
        observation_ids=observation_ids,
        instruments=instruments,
        directions=directions,
        reasons=reasons,
        evidence=tuple(sorted({r.row_id for r in rows})),
    )


def _recovery_potential_gap(dataset, recovery):
    candidates = recovery.get("recovery_candidates") or []
    if not candidates:
        return None
    observation_ids = tuple(sorted({
        str(c.get("observation_id")) for c in candidates
        if c.get("observation_id")
    }))
    instruments = tuple(sorted({
        str(c.get("instrument_id")) for c in candidates
        if c.get("instrument_id")
    }))
    directions = tuple(sorted({
        str(c.get("direction")) for c in candidates
        if c.get("direction")
    }))
    return OpportunityGap(
        category="RECOVERY_POTENTIAL",
        count=len(candidates),
        observation_ids=observation_ids,
        instruments=instruments,
        directions=directions,
        expected_R=float(recovery.get(
            "expected_captured_R_from_recovery", 0.0
        ) or 0.0),
        evidence=tuple(sorted({c["observation_id"] for c in candidates})),
    )


def detect_gaps(dataset):
    """Deterministic opportunity gaps from the 9I evidence tables."""
    recovery = recovery_candidates(dataset)
    gaps = []
    for category in _GAP_CATEGORIES:
        gap = _category_gap(dataset, category)
        if gap is not None:
            gaps.append(gap)
    recovered = _recovery_potential_gap(dataset, recovery)
    if recovered is not None:
        gaps.append(recovered)

    # deterministic order: category, then count desc, then id
    gaps.sort(key=lambda g: (g.category, -g.count, g.gap_id))
    return tuple(gaps)


# ==================================================================
# hypothesis templates (recovery-first, incremental, supported-only)
# ==================================================================
def _single_direction(directions):
    """Return the shared direction when evidence is single-sided."""
    non_empty = {d for d in directions if d}
    if len(non_empty) == 1:
        return sorted(non_empty)[0].upper()
    return ""


def _offset_hypothesis(gap, base_config, symbol):
    question = (
        f"can a closer alternative entry offset capture previously "
        f"{gap.category.lower()} {symbol} opportunities without worse "
        "economics?"
    )
    return DiscoveryHypothesis(
        kind="RECOVERY_ENTRY_OFFSET",
        question=question,
        statement=(
            f"For {gap.category} opportunities ({gap.count}) the baseline "
            "entry did not capture value; test incremental entry-offset "
            "relaxations (entry_offset_atr) as the smallest defensible "
            "recovery change."
        ),
        why=(
            f"gap {gap.gap_id}: {gap.count} opportunities in category "
            f"{gap.category}; recovery potential "
            f"{gap.expected_R:.2f} R retained."
        ),
        expected_outcome=(
            "more fills on the missed opportunities while preserving "
            "baseline expectancy and not expanding loss/risk."
        ),
        overrides={"entry_offset_atr": [0.25, 0.5]},
        direction=_single_direction(gap.directions),
        symbol=symbol,
        evidence=gap.evidence,
    )


def _base_entry_model(base_config):
    params = getattr(base_config, "params", None)
    if isinstance(params, dict) and params.get("entry_model"):
        return str(params["entry_model"])
    value = getattr(base_config, "entry_model", "BREAKOUT_CONTINUATION")
    return str(value or "BREAKOUT_CONTINUATION")


def _model_hypothesis(gap, base_config, symbol):
    base_model = _base_entry_model(base_config)
    alternates = [
        m for m in SUPPORTED_ENTRY_MODELS
        if m != base_model
    ]
    if not alternates:
        return None
    question = (
        f"which alternative supported entry model reaches previously "
        f"{gap.category.lower()} {symbol} opportunities?"
    )
    return DiscoveryHypothesis(
        kind="RECOVERY_ENTRY_MODEL",
        question=question,
        statement=(
            f"For {gap.category} opportunities ({gap.count}) test the "
            f"other supported entry models ({alternates}) as explicit "
            "recovery candidates."
        ),
        why=(
            f"gap {gap.gap_id}: {gap.count} opportunities did not reach "
            "entry under the baseline entry semantics."
        ),
        expected_outcome=(
            "entry reaches on previously unreached opportunities without "
            "worse per-trade economics."
        ),
        overrides={"entry_model": alternates},
        direction=_single_direction(gap.directions),
        symbol=symbol,
        evidence=gap.evidence,
    )


def _expiry_hypothesis(gap, symbol):
    question = (
        f"does a longer entry expiry capture late continuations on "
        f"{gap.category.lower()} {symbol} opportunities?"
    )
    return DiscoveryHypothesis(
        kind="RECOVERY_EXPIRY",
        question=question,
        statement=(
            f"For {gap.category} opportunities ({gap.count}) test longer "
            "entry expiry windows; late continuations may be the "
            "un-captured value."
        ),
        why=(
            f"gap {gap.gap_id}: {gap.count} opportunities; expiry "
            "bounded the entry window against continuation."
        ),
        expected_outcome=(
            "later entries capture continuation value that a shorter "
            "window dismissed."
        ),
        overrides={"expiry": [3, 5]},
        direction=_single_direction(gap.directions),
        symbol=symbol,
        evidence=gap.evidence,
    )


def _confirmation_hypothesis(gap, symbol):
    question = (
        f"does confirmation-distance filtering surface continuation "
        f"quality on {gap.category.lower()} {symbol} opportunities?"
    )
    return DiscoveryHypothesis(
        kind="RECOVERY_CONFIRMATION",
        question=question,
        statement=(
            f"For {gap.category} opportunities ({gap.count}) test "
            "confirmation-distance admission as an explicit alias for "
            "continuation quality."
        ),
        why=(
            f"gap {gap.gap_id}: {gap.count} opportunities that missed "
            "the continuation."
        ),
        expected_outcome=(
            "confirmation admission captures continuations while "
            "excluding late re-entries."
        ),
        overrides={"confirmation_distance": [0.25, 0.5]},
        direction=_single_direction(gap.directions),
        symbol=symbol,
        evidence=gap.evidence,
    )


def _rr_hypothesis(gap, symbol):
    question = (
        f"does raising the risk-reward target capture more value on "
        f"{gap.category.lower()} {symbol} opportunities?"
    )
    return DiscoveryHypothesis(
        kind="RECOVERY_RR",
        question=question,
        statement=(
            f"For {gap.category} opportunities ({gap.count}) test higher "
            "FIXED_RR targets as the smallest defensible value-capture "
            "change."
        ),
        why=(
            f"gap {gap.gap_id}: {gap.count} opportunities; captured "
            "trades may have left value on the table under a low RR."
        ),
        expected_outcome=(
            "higher average R on the captured population without "
            "razing win rate."
        ),
        overrides={"rr": [3.0, 4.0]},
        direction=_single_direction(gap.directions),
        symbol=symbol,
        evidence=gap.evidence,
    )


def _stop_hypothesis(gap, symbol):
    question = (
        f"does an ATR-based stop bound losses on {gap.category.lower()} "
        f"{symbol} opportunities?"
    )
    return DiscoveryHypothesis(
        kind="RECOVERY_STOP",
        question=question,
        statement=(
            f"For {gap.category} opportunities ({gap.count}) test ATR "
            "stops as the smallest defensible risk change on the "
            "captured population."
        ),
        why=(
            f"gap {gap.gap_id}: {gap.count} opportunities; captured "
            "losses weigh on expectancy."
        ),
        expected_outcome=(
            "lower average MAE and loss rate on the captured population "
            "without cutting capture."
        ),
        overrides={"stop_mode": ["ATR"]},
        direction=_single_direction(gap.directions),
        symbol=symbol,
        evidence=gap.evidence,
    )


def generate_hypotheses(dataset, base_config, symbol="UNKNOWN"):
    """Deterministic evidence-gated executable hypotheses per gap."""
    hypotheses = []
    for gap in detect_gaps(dataset):
        if gap.category == ENTRY_NOT_REACHED:
            h = _offset_hypothesis(gap, base_config, symbol)
            hypotheses.append(h)
            m = _model_hypothesis(gap, base_config, symbol)
            if m is not None:
                hypotheses.append(m)
        elif gap.category in (MISSED_CONTINUATION, INVALIDATED):
            hypotheses.append(_expiry_hypothesis(gap, symbol))
            if gap.category == MISSED_CONTINUATION:
                hypotheses.append(_confirmation_hypothesis(gap, symbol))
        elif gap.category == REJECTED:
            hypotheses.append(_offset_hypothesis(gap, base_config, symbol))
            hypotheses.append(_expiry_hypothesis(gap, symbol))
        elif gap.category == FILLED:
            hypotheses.append(_rr_hypothesis(gap, symbol))
            hypotheses.append(_stop_hypothesis(gap, symbol))
        elif gap.category == "RECOVERY_POTENTIAL":
            hypotheses.append(_offset_hypothesis(gap, base_config, symbol))
            hypotheses.append(_expiry_hypothesis(gap, symbol))

    # deterministic ordering
    hypotheses.sort(key=lambda h: (
        _KIND_ORDER.index(h.kind) if h.kind in _KIND_ORDER else 99,
        h.question,
        h.hypothesis_id,
    ))
    return tuple(hypotheses)


def dedup_hypotheses(hypotheses):
    """Drop exact-duplicate hypotheses (same id), keeping first order."""
    seen = set()
    result = []
    for h in sorted(hypotheses, key=lambda h: (h.injected, h.hypothesis_id)):
        if h.hypothesis_id in seen:
            continue
        seen.add(h.hypothesis_id)
        result.append(h)
    return tuple(result)