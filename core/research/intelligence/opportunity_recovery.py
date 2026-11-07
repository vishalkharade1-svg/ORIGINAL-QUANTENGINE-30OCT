"""
====================================================

QuantEngine

Research Intelligence -- opportunity recovery insight (Phase 9E)

For every baseline failure / rejection category the engine already
tracks (REJECTED, ENTRY_NOT_REACHED, MISSED_CONTINUATION, INVALIDATED,
FILLED, NON_EVALUABLE) this deterministically summarises, per
experiment, whether the counterfactual recovered the opportunity and
whether that recovery was a WIN, a LOSS or UNSETTLED.

It deliberately distinguishes:
   * recovered WIN    (a successful recovery)
   * recovered LOSS     (a recovery that costs R -- never counted as
                         a success)
   * recovered UNSETTLED
   * still rejected / still not reached / still missed (no fill)

Recovery facts come ONLY from 9D experiments (never resimulated).
====================================================
"""

from core.research.intelligence.recommendation_types import (
    RECOVERABLE_BASELINE_CATEGORIES,
)


def _transition_parts(transition):
    """Return (baseline_category, state) from a composed transition
    string such as 'REJECTED -> WIN'. Deterministic; tolerant."""
    if "->" not in transition:
        return "", transition
    cat, state = transition.split("->", 1)
    return cat.strip(), state.strip()


class OpportunityRecoveryInsight:
    """Per-experiment recovery summary keyed by baseline category."""

    def __init__(self, experiment_id, comparative_recovered=0,
                 comparative_wins=0, comparative_losses=0,
                 baseline_filled=0, previously_unfilled=0):
        self.experiment_id = experiment_id
        self.comparative_recovered = comparative_recovered
        self.comparative_wins = comparative_wins
        self.comparative_losses = comparative_losses
        # category-level recovery (from composed transitions)
        self.recoverable = {}
        self.recovered_win = {}
        self.recovered_loss = {}
        self.still = {}

    def add_transition(self, transition):
        cat, state = _transition_parts(transition)
        if not cat:
            return
        if cat in RECOVERABLE_BASELINE_CATEGORIES:
            self.recoverable[cat] = self.recoverable.get(cat, 0) + 1
            if state == "WIN":
                self.recovered_win[cat] = self.recovered_win.get(cat, 0) + 1
            elif state == "LOSS":
                self.recovered_loss[cat] = self.recovered_loss.get(cat, 0) + 1
            elif state.startswith("STILL_"):
                self.still[cat] = self.still.get(cat, 0) + 1

    def recovery_rate(self, category=None):
        if category is None:
            denom = sum(self.recoverable.values())
            num = sum(self.recovered_win.values()) + sum(self.recovered_loss.values())
        else:
            denom = self.recoverable.get(category, 0)
            num = (self.recovered_win.get(category, 0)
                   + self.recovered_loss.get(category, 0))
        return (num / denom) if denom else 0.0

    def successful_recovery_rate(self, category=None):
        if category is None:
            num = sum(self.recovered_win.values())
            denom = sum(self.recovered_win.values()) + sum(self.recovered_loss.values())
        else:
            num = self.recovered_win.get(category, 0)
            denom = (self.recovered_win.get(category, 0)
                     + self.recovered_loss.get(category, 0))
        return (num / denom) if denom else 0.0

    def to_dict(self):
        return {
            "experiment_id": self.experiment_id,
            "comparative_recovered": self.comparative_recovered,
            "comparative_wins": self.comparative_wins,
            "comparative_losses": self.comparative_losses,
            "category_recoverable": dict(self.recoverable),
            "category_recovered_win": dict(self.recovered_win),
            "category_recovered_loss": dict(self.recovered_loss),
            "category_still": dict(self.still),
        }


def opportunity_recovery_insight(experiment_analysis):
    """Deterministic OpportunityRecoveryInsight from a 9D
    ExperimentAnalysis (uses its RecoveryReport transitions + the
    comparative incremental facts)."""
    exp_id = experiment_analysis.experiment_id
    recovery = getattr(experiment_analysis, "recovery", None)
    recovery_dict = recovery.to_dict() if recovery else {}

    transitions = recovery_dict.get("transitions", {})

    insight = OpportunityRecoveryInsight(
        experiment_id=exp_id,
        comparative_recovered=recovery_dict.get("recovered", 0),
        comparative_wins=recovery_dict.get("recovered_wins", 0),
        comparative_losses=recovery_dict.get("recovered_losses", 0),
        baseline_filled=recovery_dict.get("baseline_filled", 0),
        previously_unfilled=recovery_dict.get("previously_unfilled", 0),
    )
    for transition, count in transitions.items():
        for _ in range(int(count or 1)):
            insight.add_transition(transition)
    return insight