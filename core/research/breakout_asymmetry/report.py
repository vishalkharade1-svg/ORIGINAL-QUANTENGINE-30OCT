"""
====================================================

QuantEngine

Phase 7 -- Asymmetry Report assembly

Combines 7A (feature decomposition), 7B (outcome
decomposition), 7C (origin decomposition) and 7D
(counterfactual) into a single printable, offline evidence
document. The report is a RESEARCH ARTIFACT -- it proposes
nothing, changes no threshold, and is never consulted by any
engine.

load_dataset() accepts either:
  * a list of CausalValidationState objects (the native form),
  * a list of plain dicts with the same keys, or
  * the path to a results file written by dump().

build_report() runs every phase and returns an
AsymmetryReport whose .summary() renders the key findings and
.verify() confirms the origin-decomposition totals reconcile
with the outcome decomposition (no double counting).

Because 7E (strategy change) is explicitly gated behind the
evidence, this report outputs a HYPOTHESIS (not a change):
if the origin decomposition shows a directional geometry or
setup-selection asymmetry, the hypothesis is "a directional
BREAKOUT_CONTINUATION policy (BULLISH / BEARISH branch)"; the
isolated research path would develop and unit-test it BEFORE
any production integration.
====================================================
"""

import json

from core.research.breakout_asymmetry.features import extract_features
from core.research.breakout_asymmetry.outcomes import (
    OutcomeClassifier,
    compare_directions,
)
from core.research.breakout_asymmetry.origins import decompose_origins
from core.research.breakout_asymmetry.counterfactual import (
    counterfactual_study,
)


class AsymmetryReport:

    def __init__(
        self,
        states,
        features,
        profiles,
        origins,
        counterfactual,
    ):

        self.states = states
        self.features = features
        self.profiles = profiles
        self.origins = origins
        self.counterfactual = counterfactual

    # --------------------------------------------------

    def verify(self):
        """Reconcile 7B and 7C: every triggered setup appears
        exactly once in the outcome buckets, and the origin
        triggered totals match. Returns (bool, message).

        The causal semantics distinguish a TRIGGER (Rule 2, a
        breakout fired at a candle close) from a TRADE (Rule 3,
        only when there is an executable NEXT_BAR_OPEN entry).
        `origins.total_triggered` counts every TRIGGER -- including
        the small set that fired on the last in-window bar and never
        converted to an entry (NO_ENTRY). Because the Outcome
        profiles also carry those states (they are part of the
        population), the reconciliation is across the FULL classified
        population; the trigger->entry shortfall is surfaced
        separately as `never_entered` (see origin D's conversion
        rate)."""

        classifier = OutcomeClassifier()

        outcomes = classifier.classify_all(self.states)

        never_entered = len(
            [o for o in outcomes if o.outcome == "NO_ENTRY"]
        )

        total_bucketed = sum(
            p.count for p in (
                self.profiles["BULLISH"],
                self.profiles["BEARISH"],
            )
        )

        ok = (
            self.origins.total_triggered == len(outcomes)
            and total_bucketed == len(outcomes)
        )

        return ok, (
            "origins.total_triggered == outcomes == bucketed "
            f"({self.origins.total_triggered}); outcomes "
            f"{len(outcomes)}; bucketed {total_bucketed}; "
            f"never_entered {never_entered}"
        )

    # --------------------------------------------------

    def hypothesis(self):
        """The evidence-led hypothesis for 7E. Never a change."""

        dominant = self.origins.dominant()

        bull = self.profiles["BULLISH"]
        bear = self.profiles["BEARISH"]

        diff = bull.win_rate() - bear.win_rate()

        geometry = "BULLISH_GEOMETRY_STRONGER"
        if abs(bull.avg_mfe_atr - bear.avg_mfe_atr) < 1e-9 and \
           abs(bull.avg_mae_atr - bear.avg_mae_atr) < 1e-9:
            geometry = "GEOMETRY_SYMMETRIC"

        return {
            "dominant_origin": (
                dominant.code if dominant else None
            ),
            "win_rate_gap_pp": round(diff, 6),
            "geometry_read": geometry,
            "candidate_change": (
                "DIRECTIONAL_POLICY"
                if dominant is not None and dominant.present
                else "NONE"
            ),
            "note": (
                "7E is gated behind this evidence: a directional "
                "BREAKOUT_CONTINUATION policy is only proposed if "
                "the origin decomposition shows a genuine directional "
                "asymmetry; it would be developed and unit-tested in "
                "the isolated research path before any production "
                "integration."
            ),
        }

    # --------------------------------------------------

    def as_dict(self):

        return {
            "total_setups": len(self.states),
            "triggered": self.origins.total_triggered,
            "profiles": {
                d: {
                    "count": p.count,
                    "wins": p.wins,
                    "losses": p.losses,
                    "unsettled": p.unsettled,
                    "excluded": p.excluded,
                    "never_entered": p.never_entered,
                    "win_rate_pct": round(p.win_rate(), 6),
                    "profit_factor": round(p.profit_factor(), 6),
                    "expectancy_R": round(p.expectancy(), 6),
                    "avg_win_R": round(p.avg_win_r, 6),
                    "avg_loss_R": round(p.avg_loss_r, 6),
                    "payoff": round(p.payoff(), 6),
                    "avg_mae_atr": round(p.avg_mae_atr, 6),
                    "avg_mfe_atr": round(p.avg_mfe_atr, 6),
                    "avg_rr": round(p.avg_rr, 6),
                }
                for d, p in self.profiles.items()
            },
            "origins": self.origins.as_dict(),
            "counterfactual": {
                "execution_asymmetry": (
                    self.counterfactual.execution_asymmetry()
                ),
                "bull_native_win": round(
                    self.counterfactual.bull_native.win_rate(), 6
                ),
                "bear_native_win": round(
                    self.counterfactual.bear_native.win_rate(), 6
                ),
            },
            "hypothesis": self.hypothesis(),
        }

    # --------------------------------------------------

    def dump(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.as_dict(), fh, indent=2)

    # --------------------------------------------------

    def summary(self):
        """Human-readable multi-line evidence summary."""

        ok, message = self.verify()

        bull = self.profiles["BULLISH"]
        bear = self.profiles["BEARISH"]

        lines = [
            "BREAKOUT ASYMMETRY RESEARCH (PHASE 7)",
            "===================================",
            f"datasets : {len(self.states)}",
            f"triggered: {self.origins.total_triggered}",
            f"verify   : {message} -> {'OK' if ok else 'FAIL'}",
            "",
            "OUTCOME (7B)  BULLISH vs BEARISH",
            "--------------------------------",
            f"count     : {bull.count:>4} vs {bear.count:>4}",
            f"win rate  : {bull.win_rate():6.1f}% vs {bear.win_rate():6.1f}%",
            f"profit fx : {bull.profit_factor():6.2f} vs {bear.profit_factor():6.2f}",
            f"expectancy: {bull.expectancy():+6.3f}R vs {bear.expectancy():+6.3f}R",
            f"MAE (ATR) : {bull.avg_mae_atr:6.2f} vs {bear.avg_mae_atr:6.2f}",
            f"MFE (ATR) : {bull.avg_mfe_atr:6.2f} vs {bear.avg_mfe_atr:6.2f}",
            f"payoff    : {bull.payoff():6.2f} vs {bear.payoff():6.2f}",
        ]

        lines.append("")
        lines.append("ORIGIN (7C)")
        lines.append("------------")
        for origin in self.origins.origins:
            lines.append(
                f"  [{origin.code}] {origin.name:24} "
                f"{origin.metric_name}: "
                f"bull={origin.bullish_value:6.3f} "
                f"bear={origin.bearish_value:6.3f} "
                f"asym={origin.asymmetry:6.3f}"
                f"{'' if origin.present else ' (held constant)'}"
            )

        cf = self.counterfactual.execution_asymmetry()
        lines.append("")
        lines.append("COUNTERFACTUAL (7D)")
        lines.append("-------------------")
        lines.append(
            f"  execution verification: {cf['verdict']} "
            f"(bull shift {cf['bull_shift_pp']}pp, "
            f"bear shift {cf['bear_shift_pp']}pp)"
        )

        hypothesis = self.hypothesis()
        lines.append("")
        lines.append("HYPOTHESIS (7E, not a change)")
        lines.append("------------------------------")
        lines.append(
            f"  dominant origin: {hypothesis['dominant_origin']}"
        )
        lines.append(
            f"  candidate change: {hypothesis['candidate_change']}"
        )
        lines.append(f"  {hypothesis['note']}")

        return "\n".join(lines)


def _coerce_states(states):
    """Coerce lists of dicts into CausalValidationState objects so
    load_dataset is tolerant of both native and serialized forms."""

    from core.setup.causal_validation import CausalValidationState

    coerced = []

    for item in states:

        if isinstance(item, dict):

            coerced.append(
                CausalValidationState(**{
                    k: v
                    for k, v in item.items()
                    if k in CausalValidationState.__dataclass_fields__
                })
            )

        else:

            coerced.append(item)

    return coerced


def load_dataset(source):
    """Load a causal dataset from: a list of states, a list of
    dicts, or a path to a JSON file dumped by dump()."""

    if isinstance(source, str):

        with open(source, encoding="utf-8") as fh:

            source = json.load(fh)

    return _coerce_states(source)


def build_report(states, metadata=None):
    """Run every phase over a causal dataset and return an
    AsymmetryReport. `metadata` routes to the feature extractor."""

    states = _coerce_states(states)

    features = extract_features(states, metadata=metadata)

    profiles = compare_directions(states)

    origins = decompose_origins(states, profiles=profiles)

    counterfactual = counterfactual_study(states)

    return AsymmetryReport(
        states=states,
        features=features,
        profiles=profiles,
        origins=origins,
        counterfactual=counterfactual,
    )