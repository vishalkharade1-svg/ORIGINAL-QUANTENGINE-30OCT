"""
====================================================

QuantEngine

Phase 7B -- Outcome Decomposition

Compare distributions, not just aggregate profit factor.
For each direction the triggered population is classified
into mutually-exclusive outcome buckets and the EXCURSION
distributions (immediate favorable / max favorable / max
adverse) are compared bucket-by-bucket.

Every bucket is computed from the frozen causal record's OWN
fields (breakout_resolved/conservative, breakout_mae,_mfe,
_tp_hit, _sl_hit, breakout_r_multiple) -- this module never
re-walks a candle and never changes a threshold. It structures
evidence already captured by the Phase 4H causal validator.

Outcome bucket (per triggered setup):

    STOP_HIT     stop touched => LOSS (breakout_sl_hit)
    TARGET_HIT   target won  => WIN  (breakout_tp_hit)
    UNRESOLVED   neither stop nor target inside the window
    EXCLUDED     ambiguous bar excluded from W/L under
                 CONSERVATIVE intrabar policy
    NEVER_ENTERED  triggered but no executable next bar
                 (breakout_causally_executable False) -- counted
                 separately because it is an execution artifact,
                 not an outcome.

Aggregate profile per bucket (a Win/Loss, or the Direction
Profile) carries, in addition to counts:

    win_rate, profit_factor, expectancy_R (R multiples),
    avg_win_R, avg_loss_R, payoff, avg_mae_atr,
    avg_mfe_atr, avg_bars_held.
====================================================
"""

from dataclasses import dataclass

from core.research.breakout_asymmetry.features import _safe_div


STOP_HIT = "STOP_HIT"
TARGET_HIT = "TARGET_HIT"
UNRESOLVED = "UNRESOLVED"
EXCLUDED = "EXCLUDED"
NEVER_ENTERED = "NEVER_ENTERED"

OUTCOME_BUCKETS = (
    STOP_HIT,
    TARGET_HIT,
    UNRESOLVED,
    EXCLUDED,
    NEVER_ENTERED,
)


@dataclass
class OutcomeProfile:
    """Aggregate profile of one outcome bucket (or one
    direction). Distributions, not a single number."""

    name: str = ""
    count: int = 0
    wins: int = 0
    losses: int = 0
    unsettled: int = 0
    excluded: int = 0
    never_entered: int = 0

    # R-multiple aggregate
    total_r: float = 0.0
    sum_win_r: float = 0.0
    sum_loss_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0

    # Excursion distributions (ATR-normalized, mean)
    avg_mae_atr: float = 0.0
    avg_mfe_atr: float = 0.0

    # Geometry
    avg_reward: float = 0.0
    avg_risk: float = 0.0
    avg_rr: float = 0.0

    # Statistics derived on demand
    def win_rate(self):
        decided = self.wins + self.losses
        return _safe_div(self.wins, decided) * 100.0

    def profit_factor(self):
        return _safe_div(self.sum_win_r, abs(self.sum_loss_r))

    def expectancy(self):
        decided = self.wins + self.losses
        if decided == 0:
            return 0.0
        return _safe_div(self.total_r, decided)

    def payoff(self):
        return _safe_div(self.avg_win_r, abs(self.avg_loss_r))

    def edge_success(self):
        """Break-even win rate required at the realized payoff."""

        payoff = self.payoff()

        if payoff <= 0:
            return 100.0

        return _safe_div(1.0, 1.0 + payoff) * 100.0


@dataclass
class Outcome:
    """One triggered setup's outcome classification (7B)."""

    setup_id: str = ""
    direction: str = ""
    bucket: str = ""
    outcome: str = ""          # WIN / LOSS / UNRESOLVED / EXCLUDED / NO_ENTRY
    conservative: str = ""     # WIN / LOSS / UNRESOLVED / EXCLUDED
    r_multiple: float = 0.0
    mae_atr: float = 0.0
    mfe_atr: float = 0.0
    reward: float = 0.0
    risk: float = 0.0
    rr: float = 0.0
    ambiguous: bool = False

    @property
    def decided(self):
        return self.outcome in ("WIN", "LOSS")


class OutcomeClassifier:

    def __init__(self):
        pass

    def classify(self, state):
        """Classify ONE triggered causal setup into an Outcome.
        Never re-walks; reads only the frozen causal fields."""

        entry = float(getattr(state, "entry", 0.0) or 0.0)
        stop = float(getattr(state, "stop_loss", 0.0) or 0.0)
        target = float(getattr(state, "take_profit", 0.0) or 0.0)

        risk = abs(entry - stop)
        reward = abs(target - entry)

        r_mult = float(getattr(state, "breakout_r_multiple", 0.0) or 0.0)

        mae = float(getattr(state, "breakout_mae_atr", 0.0) or 0.0)
        mfe = float(getattr(state, "breakout_mfe_atr", 0.0) or 0.0)

        settled = (getattr(state, "breakout_resolved", "") or "").upper()
        conservative = (
            getattr(state, "breakout_conservative", "") or ""
        ).upper()
        entered = bool(getattr(state, "breakout_entered", False))
        executable = bool(
            getattr(state, "breakout_causally_executable", False)
        )
        sl_hit = bool(getattr(state, "breakout_sl_hit", False))
        tp_hit = bool(getattr(state, "breakout_tp_hit", False))
        ambiguous = bool(getattr(state, "breakout_ambiguous", False))

        # Execution artifact: triggered but no executable next bar.
        if not entered or not executable:

            bucket = NEVER_ENTERED
            outcome = "NO_ENTRY"
            conservative = conservative or "NO_ENTRY"

            return Outcome(
                setup_id=getattr(state, "setup_id", "") or "",
                direction=(getattr(state, "direction", "") or "").upper(),
                bucket=bucket,
                outcome=outcome,
                conservative=(
                    "EXCLUDED" if ambiguous else conservative
                ),
                r_multiple=0.0,
                mae_atr=mae,
                mfe_atr=mfe,
                reward=reward,
                risk=risk,
                rr=_safe_div(reward, risk),
                ambiguous=ambiguous,
            )

        # Deterministic CONSERVATIVE resolution for decided buckets.
        if ambiguous and conservative in ("WIN", "LOSS"):

            outcome = conservative
            bucket = TARGET_HIT if outcome == "WIN" else STOP_HIT

        elif sl_hit and not tp_hit:

            bucket = STOP_HIT
            outcome = "LOSS"
            conservative = conservative or "LOSS"

        elif tp_hit and not sl_hit:

            bucket = TARGET_HIT
            outcome = "WIN"
            conservative = conservative or "WIN"

        elif sl_hit and tp_hit:

            # Ambiguous intrabar: CONSERVATIVE (stop-first) wins.
            bucket = STOP_HIT if conservative == "LOSS" else TARGET_HIT
            outcome = conservative or settled
            conservative = conservative or outcome

        else:

            bucket = UNRESOLVED
            outcome = "UNRESOLVED"
            conservative = conservative or "UNRESOLVED"

        return Outcome(
            setup_id=getattr(state, "setup_id", "") or "",
            direction=(getattr(state, "direction", "") or "").upper(),
            bucket=bucket,
            outcome=outcome,
            conservative=conservative,
            r_multiple=r_mult,
            mae_atr=mae,
            mfe_atr=mfe,
            reward=reward,
            risk=risk,
            rr=_safe_div(reward, risk),
            ambiguous=ambiguous,
        )

    def classify_all(self, states):
        return [self.classify(state) for state in states]


def _is_win(conservative):
    return conservative == "WIN"


def _is_loss(conservative):
    return conservative == "LOSS"


def _decided(conservative):
    return conservative in ("WIN", "LOSS")


def build_profile(name, outcomes):
    """Aggregate a list of Outcomes into an OutcomeProfile with
    the full distribution/statistics."""

    profile = OutcomeProfile(name=name)

    total = len(outcomes)

    profile.count = total

    resolved_wins = 0
    resolved_losses = 0
    win_r = 0.0
    loss_r = 0.0
    n_win_r = 0
    n_loss_r = 0

    sum_mae = 0.0
    n_mae = 0
    sum_mfe = 0.0
    n_mfe = 0

    sum_reward = 0.0
    sum_risk = 0.0
    n_geom = 0

    for out in outcomes:

        conservative = out.conservative

        if _is_win(conservative):

            resolved_wins += 1
            win_r += out.r_multiple
            n_win_r += 1
            profile.wins += 1

        elif _is_loss(conservative):

            resolved_losses += 1
            loss_r += out.r_multiple
            n_loss_r += 1
            profile.losses += 1

        elif out.bucket == UNRESOLVED:

            profile.unsettled += 1

        elif out.bucket == EXCLUDED:

            profile.excluded += 1

        elif out.bucket == NEVER_ENTERED:

            profile.never_entered += 1

        if out.mae_atr:

            sum_mae += out.mae_atr
            n_mae += 1

        if out.mfe_atr:

            sum_mfe += out.mfe_atr
            n_mfe += 1

        if out.risk or out.reward:

            sum_reward += out.reward
            sum_risk += out.risk
            n_geom += 1

    profile.total_r = win_r + loss_r
    profile.sum_win_r = win_r
    profile.sum_loss_r = loss_r
    profile.avg_win_r = _safe_div(win_r, n_win_r)
    profile.avg_loss_r = _safe_div(loss_r, n_loss_r)
    profile.avg_mae_atr = _safe_div(sum_mae, n_mae)
    profile.avg_mfe_atr = _safe_div(sum_mfe, n_mfe)
    profile.avg_reward = _safe_div(sum_reward, n_geom)
    profile.avg_risk = _safe_div(sum_risk, n_geom)
    profile.avg_rr = _safe_div(
        profile.avg_reward, profile.avg_risk
    )

    return profile


def profile_direction(state_list, direction, classifier=None):
    """Classify + aggregate one direction's triggered outcomes.

    NOTE: the causal dataset is per SETUP (every trade-eligible
    canonical setup), so profile_direction aggregates over the
    TRIGGERED subset of that population. `direction` filters the
    population AND the classifier; the profile is labeled by the
    direction."""

    classifier = classifier or OutcomeClassifier()

    outcomes = [
        o
        for o in classifier.classify_all(state_list)
        if (o.direction or "").upper() == (direction or "").upper()
    ]

    return build_profile(direction, outcomes)


def classify_outcomes(states, direction=None):
    """Classify the whole causal dataset (optionally one
    direction). Returns a list of Outcom."""

    classifier = OutcomeClassifier()

    outcomes = classifier.classify_all(states)

    if direction is not None:

        d = (direction or "").upper()

        outcomes = [
            o for o in outcomes if (o.direction or "").upper() == d
        ]

    return outcomes


def compare_directions(states):
    """Per-direction profile for the bullish and bearish triggered
    populations. Returns {'BULLISH': OutcomeProfile,
    'BEARISH': OutcomeProfile}."""

    return {
        "BULLISH": profile_direction(states, "BULLISH"),
        "BEARISH": profile_direction(states, "BEARISH"),
    }