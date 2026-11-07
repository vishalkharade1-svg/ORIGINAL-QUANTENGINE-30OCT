"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- robustness filter /
discovery gates

The deterministic judge that turns one experiment's evidence into a
DISCOVERY status under an explicit, documented ladder:

   1. not runnable / 7E NO-GO surface  -> BLOCKED
   2. settled population too small     -> INCONCLUSIVE (retained)
   3. no advantage vs baseline         -> REJECTED (retained)
   4. loss expansion detected          -> REJECTED (retained)
   5. directional contradiction        -> REJECTED (never promoted;
                                            7E NO-GO stays intact)
   6. economic trade-off flagged       -> PROMISING (never promoted)
   7. OOS fold missing / too small     -> REQUIRES_OOS (OOS never
                                          bypassed)
   8. OOS fold does not confirm        -> REJECTED
   9. settled below confirmation       -> PROMISING (research finding,
      threshold (never validated          never promoted; retained)
      on a small population)
  10. otherwise                        -> VALIDATED (research-only)

The gate deliberately runs its OWN advantage / economic / directional /
chronological-OOS / sample checks and does NOT inherit the 9E
recommendation's robustness status: 9E grades a different (total_R
based) advantage metric, so its label would contradict a clean 9J
recovery finding for reasons that are unit-sensitive, not economic.
The sample/strength notion that matters for a conclusion is carried by
the settled-confirmation threshold (step 9) instead.

VALIDATED is a RESEARCH finding; it is never a production directive.

direction_evidence() derives the observed direction facts (dominant
direction, sign agreement) from the executed outcomes so the gate can
flag sign disagreement deterministically.
====================================================
"""

from core.research.discovery.constants import (
    REJECTED,
    INCONCLUSIVE,
    PROMISING,
    REQUIRES_OOS,
    VALIDATED,
    BLOCKED,
    MIN_SETTLED_FOR_CONCLUSION,
    MIN_OOS_SETTLED,
    MIN_SETTLED_FOR_PROMISING,
    gate_score,
)

_MISSING = ""

DIRECTIONAL_MIN_SAMPLE = 5


def _num(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def direction_evidence(hypothesis, outcomes):
    """Observed direction facts for the directional-safety gate.

    Only filled/settled outcomes contribute; no lookahead is involved
    (outcomes are already decision-bar-ordered research facts).
    """
    expected = str(hypothesis.direction or "").strip().upper()
    if not expected or not outcomes:
        return {}
    buckets = {}
    for outcome in outcomes:
        d = str(getattr(outcome, "direction", "") or "").strip().upper()
        result = str(getattr(outcome, "result", "") or "").upper()
        if result not in ("WIN", "LOSS"):
            continue
        bucket = buckets.setdefault(d, {"settled": 0, "r": 0.0})
        bucket["settled"] += 1
        bucket["r"] += _num(getattr(outcome, "r", 0.0))
    if not buckets:
        return {}
    expectancy = {
        d: bucket["r"] / bucket["settled"]
        for d, bucket in buckets.items()
        if bucket["settled"]
    }
    if not expectancy:
        return {}
    dominant = max(
        expectancy,
        key=lambda d: (expectancy[d], d),
    )
    return {
        "expected": expected,
        "dominant_direction": dominant,
        "expectancy_by_direction": {
            d: round(v, 6) for d, v in sorted(expectancy.items())
        },
        "settled_by_direction": {
            d: buckets[d]["settled"] for d in sorted(buckets)
        },
        "sign_agreement": bool(
            dominant == expected and expectancy.get(dominant, 0.0) > 0.0
        ),
        "agreed_settled": buckets.get(expected, {}).get("settled", 0),
    }


class DiscoveryGates:
    """Deterministic classification ladder (see module docstring)."""

    def __init__(self, min_settled=MIN_SETTLED_FOR_CONCLUSION,
                 min_oos=MIN_OOS_SETTLED,
                 min_promising=MIN_SETTLED_FOR_PROMISING):
        self.min_settled = min_settled
        self.min_oos = min_oos
        self.min_promising = min_promising

    # -------------------------------------------------

    def evaluate(self, hypothesis, *, metrics, comparison, robustness,
                 economic, oos, dir_evidence=None,
                 research_evidence=None, blocked_reason=""):
        """Returns (status, reasons). All evidence is retained."""
        reasons = []

        # -- 1 blocked -----------------------------------------------
        if blocked_reason:
            reasons.append(str(blocked_reason))
            return BLOCKED, tuple(reasons)
        if hypothesis.seven_e_no_go:
            reasons.append(
                "7E NO-GO surface preserved: the directional-breakout "
                "semantic can never be promoted out of NO-GO"
            )
            return BLOCKED, tuple(reasons)

        # -- 2 sample sufficiency ------------------------------------
        settled = _num(metrics.get("settled"))
        if settled < self.min_promising:
            reasons.append(
                "insufficient settled population to conclude "
                f"({int(settled)} < {self.min_promising}); the run is "
                "retained, not discarded"
            )
            return INCONCLUSIVE, tuple(reasons)

        # -- 3 advantage vs baseline ---------------------------------
        candidate_exp = _num(metrics.get("expectancy"), None)
        delta_exp = _num(comparison.get("delta_expectancy"), None)
        has_advantage = bool(
            delta_exp is not None
            and delta_exp > 0
            and candidate_exp is not None
            and candidate_exp > 0
        )
        if not has_advantage:
            reasons.append(
                "no advantage vs baseline: candidate does not beat the "
                "like-for-like baseline on expectancy (negative result "
                "retained, not hidden)"
            )
            return REJECTED, tuple(reasons)

        # -- 4 loss expansion ----------------------------------------
        economic = economic or {}
        if economic.get("loss_expansion"):
            reasons.append(str(economic.get("verdict") or
                               "loss expansion detected"))
            return REJECTED, tuple(reasons)

        # -- 5 directional safety ------------------------------------
        if hypothesis.direction:
            dir_check = self._direction_check(
                hypothesis, dir_evidence or {}
            )
            if dir_check:
                reasons.append(dir_check)
                return REJECTED, tuple(reasons)

        # -- 6 economic capture gate ----------------------------------
        if not economic.get("acceptable", False):
            reasons.append(
                "economic trade-off flagged: " +
                str(economic.get("verdict") or "not acceptable")
            )
            return PROMISING, tuple(reasons)

        # -- 7 OOS gate (cannot be bypassed) --------------------------
        oos_settled = _num(oos.get("oos_settled"), None)
        oos_exp = _num(oos.get("oos_expectancy"), None)
        if oos_settled is None or oos_settled < self.min_oos:
            reasons.append(
                "in-sample evidence is clear but the chronological OOS "
                f"fold is insufficient (settled {oos_settled}, min "
                f"{self.min_oos}) -- never validated without OOS"
            )
            return REQUIRES_OOS, tuple(reasons)

        # -- 8 OOS confirm ---------------------------------------------
        if oos_exp is None or oos_exp <= 0:
            reasons.append(
                f"OOS evidence did not confirm (OOS expectancy "
                f"{oos_exp}); the in-sample advantage is rejected, "
                "retained"
            )
            return REJECTED, tuple(reasons)

        # -- 9 confirmation threshold --------------------------------
        # a small settled population is NEVER validated, whatever the
        # OOS fold says (the candidate stands, not promoted).
        if settled < self.min_settled:
            reasons.append(
                "settled population below the validation confirmation "
                f"threshold ({int(settled)} < {self.min_settled}); "
                "candidate stands, never validated on a small sample"
            )
            return PROMISING, tuple(reasons)

        # -- 10 validated (research-only) ------------------------------
        reasons.append(
            "in-sample advantage clear, robustness gate clear, "
            "chronological OOS confirms -- VALIDATED as an autonomous "
            "research finding (never production-ready)"
        )
        return VALIDATED, tuple(reasons)

    # -------------------------------------------------

    @staticmethod
    def _direction_check(hypothesis, dir_evidence):
        expected = str(hypothesis.direction or "").upper()
        if not expected:
            return ""
        if not dir_evidence:
            return (
                "directional hypothesis without observable direction "
                "evidence (retained, not promoted)"
            )
        dominant = str(dir_evidence.get("dominant_direction") or "").upper()
        agreement = bool(dir_evidence.get("sign_agreement"))
        if not agreement:
            return (
                f"directional contradiction: hypothesis {expected}, "
                f"observed dominant {dominant or 'NONE'} -- sign "
                "disagreement; never promoted"
            )
        agreed_settled = _num(dir_evidence.get("agreed_settled"), 0)
        if agreed_settled < DIRECTIONAL_MIN_SAMPLE:
            return (
                f"directional evidence too thin ({int(agreed_settled)} < "
                f"{DIRECTIONAL_MIN_SAMPLE} settled) for a directional "
                "conclusion"
            )
        return ""


def classify_score(status):
    """Deterministic rank score for one experiment's status."""
    return gate_score(status)