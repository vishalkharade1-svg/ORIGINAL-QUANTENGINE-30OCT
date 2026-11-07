"""
====================================================

QuantEngine

Research Analyzer -- opportunity dataset analysis (Phase 9D)

Population-level analysis of the baseline OpportunityRecords:
category distribution (reusing the existing 9C categories -- no
invented vocabulary), rejection-reason distribution (verbatim
reasons only), and missed-continuation classification.

Read-only: records are never mutated; malformed records are
counted / warned, not fatal.
====================================================
"""

from core.research.counterfactual.opportunity_categories import (
    classify_opportunity,
)


def category_distribution(records):
    """{category: count} over the records -- deterministic, reuses
    the existing 9C classification exclusively."""
    counts = {}
    for rec in records:
        counts[classify_opportunity(rec)] = (
            counts.get(classify_opportunity(rec), 0) + 1
        )
    return counts


def rejected_by_reason(records):
    """Verbatim rejection-reason distribution.

    A record with several reasons contributes to each of its reasons
    (deterministic). `records_rejected` is the count of distinct
    records classified REJECTED.
    """
    counts = {}
    rejected_records = 0
    seen = set()
    for rec in records:
        category = classify_opportunity(rec)
        if category != "REJECTED":
            continue
        rejected_records += 1
        setup = getattr(rec, "setup", None) or {}
        reasons = setup.get("rejection_reasons") or []
        for raw in reasons:
            reason = str(raw).strip()
            if not reason:
                continue
            key = (getattr(rec, "canonical_id", ""), reason)
            if key in seen:
                continue
            seen.add(key)
            counts[reason] = counts.get(reason, 0) + 1
    return {
        "records_rejected": rejected_records,
        "by_reason": counts,
    }


def missed_continuation_counts(records):
    """Count of records the 9C classification marks MISSED_CONTINUATION."""
    total = 0
    for rec in records:
        if classify_opportunity(rec) == "MISSED_CONTINUATION":
            total += 1
    return {"missed_continuation": total}