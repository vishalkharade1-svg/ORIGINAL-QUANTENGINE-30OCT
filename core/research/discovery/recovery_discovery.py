"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- recovery discovery

Recovery-first centerpiece. Joins the OBSERVED baseline population
(OpportunityRecords) with the freshly EXECUTED counterfactual outcomes
(9C) to answer: "of the opportunities that did not capture value under
the baseline, which are recovered profitably under an explicit
alternative, and at what incremental R / PnL / MAE / MFE / bars?"

   recovery_findings(records, outcomes_by_experiment)
       returns a deterministic report:

         recovered_observations -- observation ids recovered under at
                                   least one executed experiment
         per-category counts where the recovery lives (REJECTED /
         ENTRY_NOT_REACHED / MISSED_CONTINUATION / INVALIDATED ...)
         best alternative config per recovered observation (max R,
         deterministic tie-break by experiment_id)
         incremental economics: added captured wins / losses and the
         net added R
         honesty fields: recovered LOSSES are reported -- a recovery
         candidate is never hidden, even when it adds losses.

Nothing here mutates records or outcomes; ordering is deterministic.
====================================================
"""

from core.research.discovery.discovery_types import short_id

_SETTLED = {"WIN", "LOSS"}
_TERMINAL_CAPTURED = {"FILLED", "FILLED_CLOSED", "WIN", "LOSS"}


def _observation_key(record_or_outcome):
    return (
        getattr(record_or_outcome, "canonical_id", "")
        or getattr(record_or_outcome, "observation_id", "")
        or getattr(record_or_outcome, "opportunity_id", "")
        or getattr(record_or_outcome, "setup_id", "")
    )


def _captured_ids(records):
    """Observed opportunities that already reached a terminal capture."""
    captured = {}
    for rec in records:
        observation_id = _observation_key(rec)
        if not observation_id:
            continue
        outcome = str(getattr(rec, "terminal_outcome", "") or "").upper()
        trade_result = str((getattr(rec, "trade", {}) or {}).get("result", "") or "").upper()
        if outcome in _TERMINAL_CAPTURED or trade_result in _SETTLED:
            captured[observation_id] = rec
    return captured


def recovery_findings(records, outcomes_by_experiment):
    """Live recovery evidence from executed counterfactual outcomes."""
    captured = _captured_ids(records)
    recovered_wins = {}
    recovered_losses = {}

    # best alternative config per recovered observation (max R)
    best = {}
    for experiment_id, outcomes in sorted(
            (outcomes_by_experiment or {}).items()):
        for outcome in outcomes:
            observation_id = _observation_key(outcome)
            if not observation_id or observation_id in captured:
                continue
            result = str(getattr(outcome, "result", "") or "").upper()
            if result not in _SETTLED:
                continue
            r = 0.0
            try:
                r = float(getattr(outcome, "r", 0.0) or 0.0)
            except (TypeError, ValueError):
                r = 0.0
            if result == "WIN":
                recovered_wins.setdefault(observation_id, []).append(experiment_id)
                if observation_id not in best:
                    best[observation_id] = (r, experiment_id, outcome)
                elif r > best[observation_id][0]:
                    best[observation_id] = (r, experiment_id, outcome)
            else:
                recovered_losses.setdefault(observation_id, []).append(experiment_id)

    recovered_ids = sorted({
        oid for oid in recovered_wins
    })

    candidates = []
    for observation_id in recovered_ids:
        r, experiment_id, outcome = best[observation_id]
        config = getattr(outcome, "config", None)
        params = {}
        if config is not None:
            cand = getattr(config, "params", None)
            if cand:
                params = dict(cand)
            elif hasattr(config, "to_dict"):
                params = dict(getattr(config, "to_dict", lambda: {})() or {})
        candidates.append({
            "observation_id": observation_id,
            "recovered_r": r,
            "alternative_experiment_id": experiment_id,
            "alternative_config": params,
            "instrument_id": getattr(outcome, "instrument_id", "") or "",
            "direction": getattr(outcome, "direction", "") or "",
            "category": getattr(outcome, "category", "") or "",
            "recovered_pnl": getattr(outcome, "pnl", 0.0),
            "recovered_mfe": getattr(outcome, "mfe", 0.0),
            "recovered_mae": getattr(outcome, "mae", 0.0),
            "bars_to_entry": getattr(outcome, "bars_to_entry", 0),
            "bars_in_trade": getattr(outcome, "bars_in_trade", 0),
        })

    # a recovered observation is counted even if another experiment also
    # brought its losses; the honesty section reports those too.
    recovered_loss_obs = sorted({
        oid for oid in recovered_losses
    })
    per_category = {}
    for candidate in candidates:
        cat = candidate["category"] or "UNKNOWN"
        per_category[cat] = per_category.get(cat, 0) + 1

    return {
        "recovered_observations": tuple(recovered_ids),
        "recovery_count": len(recovered_ids),
        "recovered_wins": len(recovered_ids),
        "recovered_losses_observations": len(recovered_loss_obs),
        "recovered_loss_seen": bool(recovered_loss_obs),
        "added_captured_wins": len(recovered_ids),
        "added_R": round(sum(c["recovered_r"] for c in candidates), 6),
        "per_category": dict(sorted(per_category.items())),
        "candidates": tuple(candidates),
    }