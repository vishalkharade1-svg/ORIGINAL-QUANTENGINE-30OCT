"""
====================================================

QuantEngine

Research Analyzer -- recovery analysis (Phase 9D)

The heart of the "what could have happened / why was it missed"
questions. For EVERY opportunity it builds a deterministic
transition between:

    BASELINE category (the actual production outcome, reusing the
    existing 9C `classify_opportunity` -- no invented vocabulary)
    and EXPERIMENT state (what the replay produced).

Composed transition labels use only existing tokens, e.g.:

    REJECTED -> WIN
    REJECTED -> LOSS
    REJECTED -> STILL_REJECTED
    ENTRY_NOT_REACHED -> WIN
    ENTRY_NOT_REACHED -> STILL_NOT_REACHED
    MISSED_CONTINUATION -> LOSS
    FILLED -> BETTER_RESULT  / WORSE_RESULT / SAME_RESULT
    ... -> NOT_EVALUABLE

`RecoveryReport` also answers the COST of recovery questions:

    additional trades / wins / losses, incremental R and PnL,
    recovery rate, profitable recovery rate, rejected-reason
    recovery (verbatim reasons), missed-continuation isolation.

Opportunity identity is always preserved (canonical_id). Inputs are
read-only; a malformed outcome is warned and skipped, never fatal.
====================================================
"""

from core.research.counterfactual.opportunity_categories import (
    classify_opportunity,
    FILLED,
    REJECTED,
    MISSED_CONTINUATION,
    INVALIDATED,
    ENTRY_NOT_REACHED,
    NON_EVALUABLE,
)

_FILLED_STATES = ("WIN", "LOSS", "UNSETTLED_FILL")
_RECOVERABLE_BASELINE = (REJECTED, MISSED_CONTINUATION, INVALIDATED,
                         ENTRY_NOT_REACHED)


def experiment_state(baseline_category, outcome):
    """Deterministic experiment-side state token for one outcome."""
    if getattr(outcome, "filled", False):
        result = getattr(outcome, "result", "")
        if result == "WIN":
            return "WIN"
        if result == "LOSS":
            return "LOSS"
        return "UNSETTLED_FILL"
    if outcome.category == NON_EVALUABLE or getattr(outcome, "warnings", None):
        return "NOT_EVALUABLE"
    if baseline_category == REJECTED:
        return "STILL_REJECTED"
    if baseline_category == MISSED_CONTINUATION:
        return "STILL_MISSED"
    if baseline_category == INVALIDATED:
        return "STILL_INVALIDATED"
    if baseline_category == ENTRY_NOT_REACHED:
        return "STILL_NOT_REACHED"
    return "NOT_FILLED"


def transition_for(record, outcome):
    """Deterministic composed transition `BASELINE -> STATE`."""
    baseline_category = classify_opportunity(record)
    return f"{baseline_category} -> {experiment_state(baseline_category, outcome)}"


def result_quality_for(record, outcome):
    """For a baseline-FILLED opportunity: BETTER / WORSE / SAME result
    versus the baseline R. Requires a settled baseline trade."""
    baseline_category = classify_opportunity(record)
    if baseline_category != FILLED:
        return "N/A"
    if not getattr(outcome, "filled", False):
        return "NOT_FILLED"
    if not outcome.settled:
        return "UNSETTLED"
    trade = getattr(record, "trade", None) or {}
    base_result = trade.get("result") or "UNSETTLED"
    if base_result not in ("WIN", "LOSS"):
        return "NOW_SETTLED"
    base_r = float(trade.get("r") or 0.0)
    exp_r = float(getattr(outcome, "r", 0.0) or 0.0)
    if exp_r > base_r:
        return "BETTER_RESULT"
    if exp_r < base_r:
        return "WORSE_RESULT"
    return "SAME_RESULT"


def _first_reasons(record):
    setup = getattr(record, "setup", None) or {}
    reasons = setup.get("rejection_reasons") or []
    return [str(r).strip() for r in reasons if str(r).strip()]


class RecoveryReport:
    """Aggregated recovery classification for one experiment.

    Joins outcomes to baseline records by canonical opportunity id;
    preserves the original opportunity identity throughout.
    """

    def __init__(self, records, outcomes):
        self.by_id = {
            getattr(r, "canonical_id", "") or "": r for r in records
        }
        self._outcomes = list(outcomes)
        self.transitions = {}
        self.recoveries = []
        self.quality = {}
        self.warnings = []
        self._analyze(self._outcomes)

    # -------------------------------------------------

    def _analyze(self, outcomes):
        for outcome in outcomes:
            try:
                rec = self.by_id.get(getattr(outcome, "opportunity_id", ""))
                if rec is not None:
                    baseline_cat = classify_opportunity(rec)
                    label = f"{baseline_cat} -> {experiment_state(baseline_cat, outcome)}"
                    quality = result_quality_for(rec, outcome)
                    reasons = _first_reasons(rec)
                else:
                    baseline_cat = outcome.category
                    label = f"{baseline_cat} -> {experiment_state(baseline_cat, outcome)}"
                    quality = "N/A"
                    reasons = []
                    if getattr(outcome, "baseline_rejection", ""):
                        reasons = [
                            r for r in
                            str(outcome.baseline_rejection).split(";") if r
                        ]
            except Exception as exc:  # noqa: BLE001 - isolated research path
                self.warnings.append(
                    f"recovery analysis skipped for "
                    f"{getattr(outcome, 'opportunity_id', '?')}: {exc}"
                )
                continue

            self.transitions[label] = self.transitions.get(label, 0) + 1

            state = label.split(" -> ")[1]
            if baseline_cat in _RECOVERABLE_BASELINE and state in _FILLED_STATES:
                self.recoveries.append({
                    "opportunity_id": getattr(outcome, "opportunity_id", ""),
                    "experiment_id": getattr(outcome, "experiment_id", ""),
                    "transition": label,
                    "category": baseline_cat,
                    "result": getattr(outcome, "result", "") or "UNSETTLED",
                    "r": float(getattr(outcome, "r", 0.0) or 0.0),
                    "pnl": float(getattr(outcome, "pnl", 0.0) or 0.0),
                    "reasons": reasons,
                })
            if quality != "N/A":
                self.quality[quality] = self.quality.get(quality, 0) + 1

    # -------------------------------------------------

    def _cats_used(self):
        cats = {}
        for outcome in self._outcomes:
            rec = self.by_id.get(getattr(outcome, "opportunity_id", ""))
            cat = classify_opportunity(rec) if rec is not None else \
                getattr(outcome, "category", NON_EVALUABLE)
            cats[cat] = cats.get(cat, 0) + 1
        return cats

    # -------------------------------------------------

    def rejected_reason_recovery(self):
        """Verbatim-reason recovery buckets for REJECTED baselines."""
        buckets = {}
        for item in self.recoveries:
            if "REJECTED ->" not in item["transition"]:
                continue
            for reason in (item["reasons"] or ["UNKNOWN_REASON"]):
                bucket = buckets.setdefault(
                    reason, {"recovered": 0, "wins": 0, "losses": 0}
                )
                bucket["recovered"] += 1
                if item["result"] == "WIN":
                    bucket["wins"] += 1
                elif item["result"] == "LOSS":
                    bucket["losses"] += 1
        return {k: buckets[k] for k in sorted(buckets)}

    def missed_continuation(self):
        """Isolated missed-continuation recovery counts."""
        total = 0
        recovered = 0
        wins = 0
        losses = 0
        for item in self.recoveries:
            if not item["transition"].startswith("MISSED_CONTINUATION ->"):
                continue
            total += 1
            recovered += 1
            if item["result"] == "WIN":
                wins += 1
            elif item["result"] == "LOSS":
                losses += 1
        return {
            "missed_continuation_recovered": recovered,
            "recovered_wins": wins,
            "recovered_losses": losses,
        }

    # -------------------------------------------------

    def to_dict(self):
        baseline_filled = sum(
            c for cat, c in self._cats_used().items() if cat == FILLED
        )
        previously_unfilled = sum(
            c for cat, c in self._cats_used().items() if cat != FILLED
        )
        recovered = len(self.recoveries)
        wins = sum(1 for r in self.recoveries if r["result"] == "WIN")
        losses = sum(1 for r in self.recoveries if r["result"] == "LOSS")
        unsettled = recovered - wins - losses
        incremental_r = sum(r["r"] for r in self.recoveries)
        incremental_pnl = sum(r["pnl"] for r in self.recoveries)

        return {
            "transitions": dict(self.transitions),
            "baseline_filled": baseline_filled,
            "previously_unfilled": previously_unfilled,
            "recovered": recovered,
            "recovered_wins": wins,
            "recovered_losses": losses,
            "recovered_unsettled": unsettled,
            "recovery_rate": (
                recovered / previously_unfilled if previously_unfilled else 0.0
            ),
            "profitable_recovery_rate": (
                wins / previously_unfilled if previously_unfilled else 0.0
            ),
            "recovered_win_rate": (wins / recovered) if recovered else 0.0,
            "additional_trades": recovered,
            "additional_wins": wins,
            "additional_losses": losses,
            "incremental_R": incremental_r,
            "incremental_pnl": incremental_pnl,
            "quality": dict(self.quality),
            "rejected_reason_recovery": self.rejected_reason_recovery(),
            "missed_continuation": self.missed_continuation(),
        }