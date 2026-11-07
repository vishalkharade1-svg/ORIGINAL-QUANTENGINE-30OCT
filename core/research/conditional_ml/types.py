"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- types

Closed vocabularies + frozen evidence containers for advanced
conditional machine learning over the frozen 9A-9K research stack.

The layer ANSWERS "at this decision point, in this regime + feature
context, how likely is each candidate alternative to produce an
economically useful outcome?" -- it never picks the "best profit"
automatically, never searches 100k combinations, and never emits a
trade directive.

RESEARCH ONLY: every container is frozen, research-only, and can
never be a production directive. is_production_ready is permanently
False (enforced in __post_init__).

Closed statuses:

   * selection / recovery / interaction / symbol / transition
     surfaces report a closed status vocabulary (SUPPORTED only when
     evidence + gates + familywise survival hold, else INCONCLUSIVE /
     NOT_JUSTIFIED / STABLE -- always retained, never hidden),
   * calibration reports CALIBRATED vs CALIBRATION_GAP -- a model
     that says 80% must perform near 80% on out-of-sample
     observations to be considered calibrated,
   * UNAVAILABLE means data-gated (order-flow / footprint evidence is
     never synthesised).
====================================================
"""

from dataclasses import dataclass, field

UNAVAILABLE = "UNAVAILABLE"

# ---- status vocabularies (closed) ----
ENTRY_SELECTION_SUPPORTED = "ENTRY_SELECTION_SUPPORTED"
ENTRY_SELECTION_INCONCLUSIVE = "ENTRY_SELECTION_INCONCLUSIVE"
RECOVERY_SUPPORTED = "RECOVERY_SUPPORTED"
RECOVERY_INCONCLUSIVE = "RECOVERY_INCONCLUSIVE"
INTERACTION_SUPPORTED = "INTERACTION_SUPPORTED"
INTERACTION_INCONCLUSIVE = "INTERACTION_INCONCLUSIVE"
TRANSITION_STABLE = "STABLE"
TRANSITION_CHANGED = "CHANGED"
TRANSITION_INCONCLUSIVE = "TRANSITION_INCONCLUSIVE"
SYMBOL_JUSTIFIED = "SYMBOL_JUSTIFIED"
SYMBOL_NOT_JUSTIFIED = "SYMBOL_NOT_JUSTIFIED"
CALIBRATED = "CALIBRATED"
CALIBRATION_GAP = "CALIBRATION_GAP"

# ---- entry-state labels for the opportunity context ----
ENTRY_STATE_FILLED = "FILLED"
ENTRY_STATE_NOT_FILLED = "NOT_FILLED"
ENTRY_STATE_UNKNOWN = "UNKNOWN"

# The fixed, bounded candidate alternative roster. 9L evaluates these
# EXACTLY (3 alternatives + the frozen baseline) -- this is a fixed
# research grid, never an unbounded optimizer.
CANDIDATE_ALTERNATIVES = (
    "LIMIT_RETEST",
    "MARKET_CONFIRMATION",
    "BREAKOUT_CONTINUATION",
)

# Confidence threshold under which an "expected" outcome is material
# for economic significance framing (a graded finding still retains
# every alternative row -- nothing is hidden).
ECONOMIC_R_MIN = 0.5
EFFECT_D_MIN = 0.3
ECE_MAX_CALIBRATED = 0.15

# Bounded interaction roster (2-way / 3-way combos only). The roster
# is a FIXED constant so the hypothesis space cannot explode.
INTERACTION_FEATURES = (
    "trend_vs_range",
    "direction_structure",
    "volatility_regime",
    "atr_regime",
    "displacement",
    "liquidity",
    "wyckoff",
    "fvg",
    "order_block",
)
MAX_INTERACTION_TESTS = 100


@dataclass(frozen=True)
class OpportunityContext:
    """Immutable decision-time context for ONE opportunity.

    Combines the market regime AT the decision bar, the regime AT the
    (counterfactual) fill bar when one exists, the 9F decision-time
    feature snapshot evidence, and the entry state of the frozen
    baseline. All regime/feature values are decision-time only (no
    lookahead); missing evidence is never fabricated.
    """

    opportunity_id: str = ""
    symbol: str = ""
    direction: str = ""
    decision_bar: int = 0
    fill_bar: object = None
    generated_regime: dict = field(default_factory=dict)
    filled_regime: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    entry_state: str = ENTRY_STATE_UNKNOWN
    baseline_terminal: str = ""
    baseline_rejection: str = ""
    baseline_r: object = None
    baseline_filled: bool = False

    def tokens(self):
        """Decision-time (feature, value) token map for models."""
        out = {}
        for dim, value in (self.generated_regime or {}).items():
            out["regime.%s" % dim] = value
        for name, value in (self.features or {}).items():
            if value is not None and value != UNAVAILABLE:
                out["feature.%s" % name] = value
        return out

    def primary_generated(self):
        return (self.generated_regime or {}).get("trend_vs_range", UNAVAILABLE)

    def primary_filled(self):
        return (self.filled_regime or {}).get("trend_vs_range", UNAVAILABLE)

    def to_dict(self):
        return {
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "decision_bar": self.decision_bar,
            "fill_bar": self.fill_bar,
            "generated_regime": dict(self.generated_regime),
            "filled_regime": dict(self.filled_regime),
            "features": dict(self.features),
            "entry_state": self.entry_state,
            "baseline_terminal": self.baseline_terminal,
            "baseline_rejection": self.baseline_rejection,
            "baseline_r": self.baseline_r,
            "baseline_filled": self.baseline_filled,
        }


@dataclass(frozen=True)
class RecoveryFinding:
    """Recovery probability for a missed / rejected setup.

    p_recovery, expected_r, expected_drawdown, loss_probability and
    adverse excursion are estimated deterministically from the fixed
    alternative grid; regime dependency compares recovery success
    between generated regimes.
    """

    alternative: str = ""
    regime: object = UNAVAILABLE
    n: int = 0
    recovered: int = 0
    p_recovery: object = None
    expected_r: object = None
    expected_drawdown: object = None
    loss_probability: object = None
    adverse_excursion_p50: object = None
    adverse_excursion_p90: object = None
    regime_dependency_h: object = None
    min_n_gate: int = 0
    status: str = RECOVERY_INCONCLUSIVE
    survives_familywise: bool = False
    finding_id: str = ""

    def to_dict(self):
        return {
            "alternative": self.alternative,
            "regime": self.regime,
            "n": self.n,
            "recovered": self.recovered,
            "p_recovery": self.p_recovery,
            "expected_r": self.expected_r,
            "expected_drawdown": self.expected_drawdown,
            "loss_probability": self.loss_probability,
            "adverse_excursion_p50": self.adverse_excursion_p50,
            "adverse_excursion_p90": self.adverse_excursion_p90,
            "regime_dependency_h": self.regime_dependency_h,
            "min_n_gate": self.min_n_gate,
            "status": self.status,
            "survives_familywise": self.survives_familywise,
            "finding_id": self.finding_id,
        }


@dataclass(frozen=True)
class AlternativeEvidence:
    """Per-alternative evidence row inside one entry-selection cell."""

    alternative: str = ""
    n_train: int = 0
    n_oos: int = 0
    p_win_oos: object = None
    expected_r_oos: object = None
    baseline_expectancy_oos: object = None
    delta_expectancy_oos: object = None
    p_two_sided: object = None

    def to_dict(self):
        return {
            "alternative": self.alternative,
            "n_train": self.n_train,
            "n_oos": self.n_oos,
            "p_win_oos": self.p_win_oos,
            "expected_r_oos": self.expected_r_oos,
            "baseline_expectancy_oos": self.baseline_expectancy_oos,
            "delta_expectancy_oos": self.delta_expectancy_oos,
            "p_two_sided": self.p_two_sided,
        }


@dataclass(frozen=True)
class EntrySelection:
    """Conditional entry-model selection for one cell.

    A cell is a (primary generated regime, direction) context. The
    layer picks among the FIXED supported alternatives (LIMIT_RETEST,
    MARKET_CONFIRMATION, BREAKOUT_CONTINUATION) only where the
    evidence -- sample size, OOS expectancy above the baseline by an
    economic margin, robustness and familywise survival -- supports
    it. Otherwise the selection is ENTRY_SELECTION_INCONCLUSIVE and
    every alternative row is retained (never hidden).
    """

    cell_id: str = ""
    regime: object = UNAVAILABLE
    direction: str = ""
    selected: object = None
    status: str = ENTRY_SELECTION_INCONCLUSIVE
    alternatives: tuple = ()
    min_oos_n_gate: int = 0
    economic_delta_r: object = None
    survives_familywise: bool = False

    def to_dict(self):
        return {
            "cell_id": self.cell_id,
            "regime": self.regime,
            "direction": self.direction,
            "selected": self.selected,
            "status": self.status,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "min_oos_n_gate": self.min_oos_n_gate,
            "economic_delta_r": self.economic_delta_r,
            "survives_familywise": self.survives_familywise,
        }


@dataclass(frozen=True)
class InteractionFinding:
    """Conditional feature-interaction evidence (2-way / 3-way).

    Feature interactions are tested size-2 / size-3 combinations of
    the bounded INTERACTION_FEATURES roster, separately within each
    primary regime, with a hard combinatorial cap (no explosion). A
    finding is INTERACTION_SUPPORTED only when the interaction effect
    carries from train to OOS with the same sign, is economically
    material, has a minimum sample, and survives the global
    familywise correction.
    """

    regime: object = UNAVAILABLE
    features: tuple = ()
    n_train: int = 0
    n_oos: int = 0
    effect_d_train: object = None
    effect_d_oos: object = None
    expectancy_train: object = None
    expectancy_oos: object = None
    pooled_expectancy: object = None
    p_value: object = None
    status: str = INTERACTION_INCONCLUSIVE
    survives_familywise: bool = False
    note: str = ""

    def to_dict(self):
        return {
            "regime": self.regime,
            "features": list(self.features),
            "n_train": self.n_train,
            "n_oos": self.n_oos,
            "effect_d_train": self.effect_d_train,
            "effect_d_oos": self.effect_d_oos,
            "expectancy_train": self.expectancy_train,
            "expectancy_oos": self.expectancy_oos,
            "pooled_expectancy": self.pooled_expectancy,
            "p_value": self.p_value,
            "status": self.status,
            "survives_familywise": self.survives_familywise,
            "note": self.note,
        }


@dataclass(frozen=True)
class TransitionFinding:
    """Regime transition between setup-generation and fill."""

    generated_regime: object = UNAVAILABLE
    filled_regime: object = UNAVAILABLE
    n: int = 0
    win_rate: object = None
    avg_r: object = None
    expectancy_delta_vs_stable: object = None
    status: str = TRANSITION_INCONCLUSIVE
    note: str = ""

    def to_dict(self):
        return {
            "generated_regime": self.generated_regime,
            "filled_regime": self.filled_regime,
            "n": self.n,
            "win_rate": self.win_rate,
            "avg_r": self.avg_r,
            "expectancy_delta_vs_stable": self.expectancy_delta_vs_stable,
            "status": self.status,
            "note": self.note,
        }


@dataclass(frozen=True)
class SymbolBehaviour:
    """Symbol-specific behaviour, only when the sample justifies it."""

    symbol: str = ""
    regime: object = UNAVAILABLE
    n: int = 0
    win_rate: object = None
    avg_r: object = None
    global_avg_r: object = None
    delta_expectancy: object = None
    justified: bool = False
    min_n_gate: int = 0

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "regime": self.regime,
            "n": self.n,
            "win_rate": self.win_rate,
            "avg_r": self.avg_r,
            "global_avg_r": self.global_avg_r,
            "delta_expectancy": self.delta_expectancy,
            "justified": self.justified,
            "min_n_gate": self.min_n_gate,
        }


@dataclass(frozen=True)
class CalibrationBin:
    """One confidence bin on out-of-sample predictions."""

    bin_index: int = 0
    midpoint: object = None
    n: int = 0
    expected_rate: object = None
    observed_rate: object = None
    abs_error: object = None

    def to_dict(self):
        return {
            "bin": self.bin_index,
            "midpoint": self.midpoint,
            "n": self.n,
            "expected_rate": self.expected_rate,
            "observed_rate": self.observed_rate,
            "abs_error": self.abs_error,
        }


@dataclass(frozen=True)
class CalibrationSummary:
    """Confidence / calibration over OOS observations.

    A model that says 80% must actually perform near 80% on OOS
    observations. ECE, Brier and a calibration slope are reported
    deterministically; status is CALIBRATED or CALIBRATION_GAP. The
    bins are always retained (a gap is reported, never hidden).
    """

    surface: str = ""
    oos_n: int = 0
    ece: object = None
    brier: object = None
    slope: object = None
    status: str = CALIBRATION_GAP
    min_n_gate: int = 0
    bins: tuple = ()

    def to_dict(self):
        return {
            "surface": self.surface,
            "oos_n": self.oos_n,
            "ece": self.ece,
            "brier": self.brier,
            "slope": self.slope,
            "status": self.status,
            "min_n_gate": self.min_n_gate,
            "bins": [b.to_dict() for b in self.bins],
        }