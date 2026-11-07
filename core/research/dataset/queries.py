"""
====================================================

QuantEngine

Unified Research Dataset -- query / knowledge layer (Phase 9I)

Deterministic, read-only queries over the unified ResearchDataset
that turn normalized 9A-9H rows into the evidence tables and answer
the knowledge questions an autonomous researcher (or a human) raises:

   * entry_pipeline_breakdown -- "We had N structurally valid setups;
     why were only M entered?" (fills / entry-reached / settled / win
     rates split by opportunity category and by rejection reason).
   * recovery_candidates      -- "Of the missed/rejected/entry-not-
     reached opportunities, which could have been profitable if entry
     model / offset / expiry / RR / confirmation had changed?"
     (joins JOURNAL or COUNTERFACTUAL observation-rows against the
     counterfactual rows that recovered them, and reports captured-vs-
     missed economics).
   * unify_by_observation     -- cross-source join for one opportunity.
   * aggregate                -- generic group-by / measure aggregation.

Every query is pure: it never mutates the dataset, never imports
production internals, never orders, never looks ahead, and returns
plain dicts / tuples that carry a research-only disclaimer. Nothing
here promotes a configuration to production.
====================================================
"""

from collections import OrderedDict

from core.research.dataset.row import (
    DatasetSource as S,
    SOURCES,
)
from core.research.counterfactual import (
    FILLED,
    REJECTED,
    MISSED_CONTINUATION,
    INVALIDATED,
    ENTRY_NOT_REACHED,
    NON_EVALUABLE,
)

_DISCLAIMER = (
    "Research-only Knowledge/Data Intelligence. These tables are "
    "ASSOCIATION evidence for experimentation planning; they are not "
    "a trade directive and never promote a configuration to production."
)


# ==================================================================
# Entry pipeline breakdown
# ==================================================================
def entry_pipeline_breakdown(dataset):
    """Answer: how many structurally valid setups, and why only some
    were entered?

    Split counts by opportunity category and by rejection reason over
    the JOURNAL rows (observed facts)."""
    journal = dataset.rows(S.JOURNAL)
    category_counts = OrderedDict()
    for c in (FILLED, REJECTED, MISSED_CONTINUATION, INVALIDATED,
              ENTRY_NOT_REACHED, NON_EVALUABLE):
        category_counts[c] = 0
    entered = 0
    settled = 0
    wins = 0
    losses = 0
    rejected_by_reason = OrderedDict()
    valid_setups = len(journal)

    for r in journal:
        cat = r.category or NON_EVALUABLE
        if cat in category_counts:
            category_counts[cat] += 1
        else:
            category_counts[cat] = 1
        if cat == FILLED:
            entered += 1
        res = r.result or ""
        if res in (FILLED, "WIN", "LOSS"):
            if res in ("WIN", "LOSS"):
                settled += 1
            if res == "WIN":
                wins += 1
            elif res == "LOSS":
                losses += 1
        for reason in (r.kv.get("rejection_reasons") or []):
            if reason is not None:
                rejected_by_reason[str(reason)] = \
                    rejected_by_reason.get(str(reason), 0) + 1

    non_entered = valid_setups - entered
    return {
        "structurally_valid_setups": valid_setups,
        "entered": entered,
        "not_entered": max(0, non_entered),
        "entry_rate": (entered / valid_setups) if valid_setups else None,
        "settled": settled,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / settled) if settled else None,
        "by_category": dict(category_counts),
        "rejected_by_reason": dict(sorted(
            rejected_by_reason.items(), key=lambda kv: (-kv[1], kv[0]),
        )),
        "research_only": _DISCLAIMER,
    }


# ==================================================================
# Recovery candidates
# ==================================================================
def recovery_candidates(dataset):
    """Answer: of the non-entered / rejected opportunities, which ones
    could have been profitable if the entry model / offset / expiry /
    RR / confirmation had changed?

    Joins each JOURNAL observation that did NOT reach a profitable
    conclusion against the COUNTERFACTUAL rows (from the frozen 9C
    experiments) sharing the same observation_id, and reports the
    recovered economics. When no JOURNAL row exists, the counterfactual
    rows themselves carry the recovery evidence.

    Returns a deterministic report: candidate list, captured vs missed
    wins, and the net R that a recovery would have added."""
    journal = {r.observation_id: r for r in dataset.rows(S.JOURNAL)
               if r.observation_id}
    cf_rows = list(dataset.rows(S.COUNTERFACTUAL))
    cf_by_obs = OrderedDict()
    for r in cf_rows:
        cf_by_obs.setdefault(r.observation_id, []).append(r)

    # Observed profitable fills (baseline captured wins).
    captured_ids = set()
    captured_wins = 0
    captured_losses = 0
    for r in journal.values():
        if r.category == FILLED:
            captured_ids.add(r.observation_id)
            if r.result == "WIN":
                captured_wins += 1
            elif r.result == "LOSS":
                captured_losses += 1

    candidates = []
    recoverable_ids = set()
    expected_captured_R = 0.0
    for cf in cf_rows:
        obs_id = cf.observation_id
        if obs_id in captured_ids:
            continue
        # A counterfactual WIN under an alternative config on a
        # non-captured opportunity = a potentially recoverable win.
        if cf.result == "WIN":
            recoverable_ids.add(obs_id)
    # aggregate per opportunity: pick best alternative config evidence
    by_obs_order = sorted(
        ({c.observation_id for c in cf_rows if c.observation_id})
    )
    for obs_id in by_obs_order:
        if obs_id in captured_ids or obs_id not in recoverable_ids:
            continue
        cf_for = cf_by_obs.get(obs_id, [])
        recovered_any = any(c.result == "WIN" for c in cf_for)
        if not recovered_any:
            continue
        best = max(
            (c for c in cf_for if c.result == "WIN"),
            key=lambda c: c.measured.get("r", 0.0),
        )
        jr = journal.get(obs_id)
        params = {k: v for k, v in best.kv.items()
                  if k in (
                      "entry_model", "entry_offset", "entry_offset_atr",
                      "expiry", "rr", "stop_mode", "target_mode",
                      "confirmation_distance", "breakout_buffer",
                      "outcome_bars",
                  )}
        candidates.append(OrderedDict([
            ("observation_id", obs_id),
            ("instrument_id", jr.instrument_id if jr else best.instrument_id),
            ("direction", jr.direction if jr else best.direction),
            ("category", jr.category if jr else best.category),
            ("baseline_result", jr.result if jr else ""),
            ("recovered_r", best.measured.get("r", 0.0)),
            ("recovered_pnl", best.measured.get("pnl", 0.0)),
            ("recovered_mfe", best.measured.get("mfe", 0.0)),
            ("recovered_mae", best.measured.get("mae", 0.0)),
            ("alternative_config", params),
            ("evidence_experiment_id", best.source_id),
        ]))

    resolved = [c for c in candidates
                if c["recovered_r"] is not None]
    for c in resolved:
        expected_captured_R += float(c["recovered_r"] or 0.0)

    return {
        "total_observations": len(journal),
        "captured_opportunity_count": len(captured_ids),
        "captured_wins": captured_wins,
        "captured_losses": captured_losses,
        "potentially_recoverable_count": len(recoverable_ids),
        "missed_wins_before_recovery": len(recoverable_ids),
        "recovery_candidates": candidates,
        "recovery_candidate_count": len(candidates),
        "expected_captured_R_from_recovery": expected_captured_R,
        "net_captured_opportunities": len(captured_ids) + len(candidates),
        "research_only": _DISCLAIMER,
    }


# ==================================================================
# Cross-source unify
# ==================================================================
def unify_by_observation(dataset, observation_id):
    """Return every ResearchRow (across all sources) keyed to a single
    opportunity/observation id, so the full evidence chain for one
    setup can be inspected."""
    matched = []
    for src in SOURCES:
        for r in dataset.rows(src):
            if r.observation_id == observation_id:
                matched.append(r)
    return tuple(
        sorted(matched, key=lambda r: (r.source, r.row_id))
    )


# ==================================================================
# Generic aggregation
# ==================================================================
def aggregate(rows, group_by=(), measures=(), filters=None):
    """Group ResearchRow by a tuple of kv/identity keys and compute
    aggregate measures, in insertion order (deterministic).

    group_by: tuple of row attribute / kv keys, e.g. ("category",).
    measures: tuple of ("key", "agg") where key selects a performed
              measured/kv value and agg is one of count / sum / mean /
              win_rate (fraction of WIN over WIN+LOSS).
    filters: optional callable(row)->bool (e.g.
             lambda r: r.source == 'COUNTERFACTUAL')."""
    groups = OrderedDict()
    order = []
    for r in rows:
        if filters is not None and not filters(r):
            continue
        key = tuple(_resolve(r, k) for k in group_by)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    result = []
    for key in order:
        members = groups[key]
        rec = {}
        for k, name in zip(group_by, key):
            rec[k] = name
        for mkey, agg in measures:
            values = [_resolve(r, mkey) for r in members]
            numeric = [v for v in values
                       if isinstance(v, (int, float)) and v is not None]
            if agg == "count":
                rec[f"{mkey}_count"] = sum(
                    1 for v in values if v is not None
                )
            elif agg == "sum":
                rec[f"{mkey}_sum"] = _safe_sum(numeric)
            elif agg == "mean":
                rec[f"{mkey}_mean"] = (
                    _safe_sum(numeric) / len(numeric)
                    if numeric else None
                )
            elif agg == "win_rate":
                wins = sum(1 for v in values if v == "WIN")
                settled = sum(
                    1 for v in values if v in ("WIN", "LOSS")
                )
                rec[f"{mkey}_win_rate"] = (
                    (wins / settled) if settled else None
                )
        rec["n"] = len(members)
        result.append(rec)
    return result


def _resolve(row, key):
    attrs = ("category", "result", "direction", "instrument_id",
             "strategy", "timeframe", "source")
    if key in attrs:
        return getattr(row, key)
    if key in ("measure",):
        return row
    if key in row.kv:
        return row.kv[key]
    if key in row.measured:
        return row.measured[key]
    return None


def _safe_sum(values):
    total = 0.0
    for v in values:
        try:
            total += float(v)
        except (TypeError, ValueError):
            pass
    return total


# ==================================================================
# Compact evidence context for 9H
# ==================================================================
def answer_context(dataset):
    """A compact, deterministic evidence dictionary that an autonomous
    researcher can consume directly as question context.

    Combines the entry-pipeline breakdown and the recovery-candidate
    head into a single read-only block."""
    breakdown = entry_pipeline_breakdown(dataset)
    recovery = recovery_candidates(dataset)
    return {
        "phase": "9I",
        "structurally_valid_setups": breakdown["structurally_valid_setups"],
        "entered": breakdown["entered"],
        "not_entered": breakdown["not_entered"],
        "entry_rate": breakdown["entry_rate"],
        "by_category": breakdown["by_category"],
        "rejected_by_reason": breakdown["rejected_by_reason"],
        "potentially_recoverable_count": recovery["potentially_recoverable_count"],
        "missed_wins_before_recovery": recovery["missed_wins_before_recovery"],
        "recovery_candidate_count": recovery["recovery_candidate_count"],
        "expected_captured_R_from_recovery": recovery[
            "expected_captured_R_from_recovery"
        ],
        "research_only": _DISCLAIMER,
    }
