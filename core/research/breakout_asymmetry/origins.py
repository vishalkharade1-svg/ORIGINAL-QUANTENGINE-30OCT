"""
====================================================

QuantEngine

Phase 7C -- Where Does the Asymmetry Originate?

Distinguishes among seven causal origin classes so we never
conclude "the market is bearish" merely from aggregate
statistics:

    A  MARKET                the raw trigger/win rates differ
                             purely from where price spent time.
    B  STRUCTURE-GENERATION  the eligible OB generation differs
                             per direction (count / width / age).
    C  SETUP-SELECTION       the trade-eligible population
                             differs (entry_distance_atr, RR,
                             freshness, FVG presence).
    D  BREAKOUT-TRIGGER      the trigger-to-fill conversion
                             differs (breakout_entered /
                             causally_executable / trigger rate).
    E  STOP-TARGET GEOMETRY  the reward/risk geometry is biased
                             per direction (avg_risk, avg_reward,
                             avg_rr, MAE/MFE in ATR).
    F  EXECUTION             the fill path differs per direction.
                             In the causal dataset this is held
                             CONSTANT (both run NEXT_BAR_OPEN),
                             so F is expected to be zero and 7D
                             verifies it.
    G  DATA-SAMPLE IMBALANCE raw counts differ, so every ratio
                             must be read against the population
                             size (never a fixed aggregate).

decompose_origins() returns one AsymmetryOrigin per class with
a direction-neutral SIGNAL recorded for both directions plus an
`asymmetry` magnitude computed as the normalized per-direction
gap, so the report can rank which origin dominates.

Every signal reads ONLY the frozen causal record fields --
no re-walk, no threshold change. This is a description of
evidence, not a strategy modification.
====================================================
"""

from dataclasses import dataclass, field

from core.research.breakout_asymmetry.features import _safe_div
from core.research.breakout_asymmetry.outcomes import (
    NEVER_ENTERED,
    TARGET_HIT,
    STOP_HIT,
    UNRESOLVED,
    EXCLUDED,
    OutcomeClassifier,
)


@dataclass
class AsymmetryOrigin:
    """Evidence for ONE asymmetry-origin class."""

    code: str = ""
    name: str = ""
    metric_name: str = ""
    bullish_value: float = 0.0
    bearish_value: float = 0.0
    asymmetry: float = 0.0
    note: str = ""
    present: bool = False

    def ratio(self):
        """Direction ratio (bullish / bearish); 1.0 = symmetric."""

        return _safe_div(self.bullish_value, self.bearish_value)


@dataclass
class OriginDecomposition:
    """The full 7C result."""

    total_setups: int = 0
    total_triggered: int = 0
    origins: list = field(default_factory=list)

    def by_code(self, code):

        for origin in self.origins:

            if origin.code == code:

                return origin

        return None

    def dominant(self):
        """Return the Origin with the largest |asymmetry| where
        the class is present. None if no origin shows asymmetry."""

        ranked = [
            o for o in self.origins if o.present and o.asymmetry != 0
        ]

        if not ranked:

            return None

        return max(
            ranked,
            key=lambda o: abs(o.asymmetry),
        )

    def as_dict(self):

        return {
            o.code: {
                "name": o.name,
                "metric": o.metric_name,
                "bullish": o.bullish_value,
                "bearish": o.bearish_value,
                "asymmetry": o.asymmetry,
                "present": o.present,
                "note": o.note,
            }
            for o in self.origins
        }


def _gap(bull, bear, scale=1.0):
    """Normalized per-direction gap on [0, 1]; 0 = symmetric."""

    denom = max(abs(bull), abs(bear), 1e-9)
    num = abs(bull - bear)
    return _safe_div(num, denom)


def decompose_origins(states, profiles=None, metadata=None):
    """Decompose per-direction asymmetry across the seven origin
    classes. `profiles` (optional) is the OutcomeProfile dict from
    compare_directions; if omitted it is recomputed here.
    Returns an OriginDecomposition.

    Reads only frozen causal fields. No thresholds are changed.
    """

    classifier = OutcomeClassifier()

    outcomes = classifier.classify_all(states)

    bull_out = [o for o in outcomes if (o.direction or "").upper() == "BULLISH"]
    bear_out = [o for o in outcomes if (o.direction or "").upper() == "BEARISH"]

    total_setups = len(states)

    n_bull = len(bull_out)
    n_bear = len(bear_out)

    total_triggered = n_bull + n_bear

    # ---------- reusable per-direction helpers ----------

    def share(lst, predicate):
        if not lst:
            return 0.0
        return _safe_div(
            sum(1 for o in lst if predicate(o)),
            len(lst),
        ) * 100.0

    def mean(lst, attr):
        vals = [float(getattr(o, attr, 0.0) or 0.0) for o in lst]
        if not vals:
            return 0.0
        return sum(vals) / len(vals)

    def settled_win_rate(lst):
        w = sum(1 for o in lst if (o.conservative or "") == "WIN")
        l = sum(1 for o in lst if (o.conservative or "") == "LOSS")
        return _safe_div(w, w + l) * 100.0

    origins = []

    def add(code, name, metric, bv, av, note, present=True):
        origins.append(
            AsymmetryOrigin(
                code=code,
                name=name,
                metric_name=metric,
                bullish_value=round(bv or 0.0, 6),
                bearish_value=round(av or 0.0, 6),
                asymmetry=round(_gap(bv, av), 6),
                note=note,
                present=present,
            )
        )

    # ---- G: data-sample imbalance first (framing) ----

    add(
        "G",
        "DATA-SAMPLE IMBALANCE",
        "triggered count (% of dataset)",
        _safe_div(n_bull, total_setups) * 100.0 if total_setups else 0.0,
        _safe_div(n_bear, total_setups) * 100.0 if total_setups else 0.0,
        (
            f"{n_bull} bullish vs {n_bear} bearish triggered; "
            "read every ratio as a rate, never as a count."
        ),
    )

    # ---- A: market ----
    # The most basic trigger outcome asymmetry: settled win rate and
    # the raw stopped/targeted split. Where the price went, per dir.

    add(
        "A",
        "MARKET",
        "settled win rate (%)",
        settled_win_rate(bull_out),
        settled_win_rate(bear_out),
        "settled win rate across the triggered population.",
    )

    # ---- B: structure generation ----
    # Count of triggered setups per direction (how much structure
    # each side generated through the eligible population).

    add(
        "B",
        "STRUCTURE-GENERATION",
        "triggered setups (%), population share",
        _safe_div(n_bull, total_setups) * 100.0 if total_setups else 0.0,
        _safe_div(n_bear, total_setups) * 100.0 if total_setups else 0.0,
        "how much of the eligible population each side generated.",
    )

    # ---- C: setup-selection ----
    # Entry distance ATR (distance-from-market) and average RR of the
    # selected setups per direction -- selection bias in scope.

    add(
        "C",
        "SETUP-SELECTION",
        "avg entry distance (ATR)",
        mean(
            [s for s in states if (getattr(s, 'direction', '') or '').upper() == "BULLISH"],
            "entry_distance_atr",
        ),
        mean(
            [s for s in states if (getattr(s, 'direction', '') or '').upper() == "BEARISH"],
            "entry_distance_atr",
        ),
        "average distance-from-market of the selected setups.",
    )

    # ---- D: breakout-trigger conversion ----
    # Trigger -> executable-entry conversion per direction.

    def executable_share(lst):
        return share(
            lst,
            lambda o: o.bucket != NEVER_ENTERED and o.outcome != "NO_ENTRY",
        )

    add(
        "D",
        "BREAKOUT-TRIGGER",
        "causally-executable entry rate (%)",
        executable_share(bull_out),
        executable_share(bear_out),
        "fraction of triggered setups that convert to an executable entry.",
    )

    # ---- E: stop/target geometry ----
    # ATR-normalized MAE/MFE and reward/risk geometry per direction.

    add(
        "E",
        "STOP-TARGET GEOMETRY",
        "avg MFE (ATR)",
        mean(bull_out, "mfe_atr"),
        mean(bear_out, "mfe_atr"),
        "max favorable excursion (ATR) of the triggered population.",
    )

    add(
        "E",
        "STOP-TARGET GEOMETRY",
        "avg MAE (ATR)",
        mean(bull_out, "mae_atr"),
        mean(bear_out, "mae_atr"),
        "max adverse excursion (ATR) of the triggered population.",
    )

    add(
        "E",
        "STOP-TARGET GEOMETRY",
        "avg reward : risk",
        mean(bull_out, "rr"),
        mean(bear_out, "rr"),
        "reward : risk geometry of the triggered population.",
    )

    # ---- F: execution ----
    # In the causal dataset execution is IDENTICAL for both
    # directions (NEXT_BAR_OPEN), so no fill-path divergence is
    # expected here. Present=False flags that this is held constant;
    # 7D verifies it explicitly with the mirror study.

    add(
        "F",
        "EXECUTION",
        "fill-path divergence (counterfactual-held-constant)",
        0.0,
        0.0,
        (
            "execution is held IDENTICAL across directions in the "
            "causal dataset (NEXT_BAR_OPEN); any residual difference "
            "is setup-origin, not fill-path. 7D verifies via mirror."
        ),
        present=False,
    )

    return OriginDecomposition(
        total_setups=total_setups,
        total_triggered=total_triggered,
        origins=origins,
    )