"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- scheduler

Deterministic ordering of the candidate hypotheses into an explicit
experiment schedule, under an explicit budget. Responsibilities:

   * deterministic ordering (kind, question, id) -- the schedule is
     reproducible byte for byte;
   * explicit experiment budget -- no unbounded combinatorial sweep;
     the budget applies to GENERATED hypotheses only, so a
     deliberately-requested experiment is never suppressed;
   * research-memory dedup -- hypotheses identical to a previously
     studied experiment are skipped and EXPLICITLY reported as
     skipped, never silently dropped;
   * fail-loud validation -- every scheduled hypothesis passes
     candidate_space.validate_overrides before it is returned.

The scheduler never decides "good/bad"; it only orders, budgets,
dedups and validates. Execution is the runner's concern.
====================================================
"""

from core.research.discovery.candidate_space import validate_overrides


def _sort_key(h):
    return (h.kind, h.question, h.hypothesis_id)


def schedule(hypotheses, memory=None, budget=None):
    """Return (scheduled, skipped).

    scheduled: tuple of DiscoveryHypothesis to execute (validated).
    skipped:   tuple of (DiscoveryHypothesis, reason) kept for honesty.
    """
    ordered = sorted(hypotheses, key=_sort_key)

    scheduled = []
    skipped = []

    # Deliberately-requested (injected) experiments are NEVER suppressed
    # by memory dedup or by the generated budget.
    for h in ordered:
        if not h.injected:
            continue
        try:
            validate_overrides(h.overrides)
        except ValueError as exc:
            skipped.append((h, f"invalid candidate: {exc}"))
            continue
        scheduled.append(h)

    generated_budget = budget
    for h in ordered:
        if h.injected:
            continue
        if not h.overrides:
            skipped.append((h, "evidence-only hypothesis (no executable "
                                "parameter change)"))
            continue
        try:
            validate_overrides(h.overrides)
        except ValueError as exc:
            skipped.append((h, f"invalid candidate: {exc}"))
            continue
        if memory is not None:
            if memory.heard_of_hypothesis(h.question, h):
                skipped.append((
                    h,
                    "previously studied in research memory",
                ))
                continue
        if generated_budget is not None:
            if generated_budget <= 0:
                skipped.append((h, "experiment budget reached"))
                continue
            generated_budget -= 1
        scheduled.append(h)

    # deterministic final order
    scheduled.sort(key=_sort_key)
    skipped.sort(key=lambda t: _sort_key(t[0]))
    return tuple(scheduled), tuple(skipped)