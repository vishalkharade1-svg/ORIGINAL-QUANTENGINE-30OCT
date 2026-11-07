"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- interactions

Feature-interaction evidence, CONDITIONAL on regime, without
combinatorial explosion.

   * The roster is the FIXED bounded constant INTERACTION_FEATURES
     (regime + confluence features). Only size-2 and size-3
     combinations are considered, and only tokens actually observed
     with a minimum sample in a regime participate.
   * A HARD cap (MAX_INTERACTION_TESTS per regime) bounds the tested
     combos so the hypothesis space can never explode; reaching the
     cap is REPORTED in the finding note (never silently truncated
     into a false claim).
   * A finding is INTERACTION_SUPPORTED only when the interaction
     effect CARRIES from TRAIN to OOS with the same sign, is
     economically material (|Cohen's d| >= EFFECT_D_MIN), meets the
     min-n gate and survives the global familywise correction.

The observation is always association, never causation -- and never
a trade directive.
====================================================
"""

import itertools

from core.research.conditional_ml.types import (
    InteractionFinding,
    INTERACTION_SUPPORTED,
    INTERACTION_INCONCLUSIVE,
    INTERACTION_FEATURES,
    MAX_INTERACTION_TESTS,
    EFFECT_D_MIN,
)
from core.research.conditional_ml.guards import required_min_n, z_mean_diff
from core.research.ml.statistics import effect_size_d


def _combo_rows(orows, indices, combo):
    """Settled baseline R for rows whose decision-time tokens cover
    every (feature, value) in the combo."""
    out = []
    for i in indices:
        r = orows[i]
        toks = r.ctx.tokens()
        if any(toks.get(f) != v for f, v in combo):
            continue
        if r.baseline_filled and r.baseline_r is not None:
            out.append(r.baseline_r)
    return out


def _cell_r(orows, indices, regime):
    out = []
    for i in indices:
        r = orows[i]
        if (r.ctx.primary_generated() or "UNAVAILABLE") != regime:
            continue
        if r.baseline_filled and r.baseline_r is not None:
            out.append(r.baseline_r)
    return out


def _observed_combos(orows, indices, regime, min_token_n):
    """Size-2 / size-3 combos actually observed in a regime.

    Returns (combos, capped). `capped` is True when the hard cap was
    reached (the extra combos are then NOT tested and the gate is
    reported)."""
    present = {}
    freq = {f: 0 for f in INTERACTION_FEATURES}
    for i in indices:
        r = orows[i]
        if (r.ctx.primary_generated() or "UNAVAILABLE") != regime:
            continue
        if not (r.baseline_filled and r.baseline_r is not None):
            continue
        toks = r.ctx.tokens()
        for f in INTERACTION_FEATURES:
            v = toks.get(f)
            if v is not None:
                present[(f, v)] = present.get((f, v), 0) + 1
                freq[f] += 1
    available = sorted(
        tok for tok, count in present.items()
        if count >= min_token_n and freq[tok[0]] >= min_token_n
    )
    combos = []
    capped = False
    for k in (2, 3):
        for combo in itertools.combinations(available, k):
            # a row cannot carry two values of the same feature, so a
            # combo with a repeated feature name is structurally
            # impossible and is never tested
            if len({f for f, _ in combo}) != k:
                continue
            if len(combos) >= MAX_INTERACTION_TESTS:
                capped = True
                break
            combos.append(combo)
        if capped:
            break
    return combos, capped


def interaction_analysis(orows, split, regimes, gates, n_hypotheses=1):
    """Deterministic within-regime feature-interaction analysis."""
    min_n = required_min_n(int(gates.get("min_interaction_n", 5)),
                           n_hypotheses)
    train_idx = set(split.train.indices)
    oos_idx = set(split.oos.indices)
    findings = []
    for regime in regimes:
        combos, capped = _observed_combos(
            orows, list(train_idx) + list(oos_idx), regime, min_n)
        cell_train_r = _cell_r(orows, train_idx, regime)
        cell_oos_r = _cell_r(orows, oos_idx, regime)
        for combo in combos:
            tr_r = _combo_rows(orows, train_idx, combo)
            oo_r = _combo_rows(orows, oos_idx, combo)
            d_tr = effect_size_d(tr_r, cell_train_r)
            d_oo = effect_size_d(oo_r, cell_oos_r)
            exp_tr = sum(tr_r) / len(tr_r) if tr_r else None
            exp_oo = sum(oo_r) / len(oo_r) if oo_r else None
            pooled = sum(cell_train_r) + sum(cell_oos_r)
            pooled_n = len(cell_train_r) + len(cell_oos_r)
            pooled = pooled / pooled_n if pooled_n else None
            p_value = z_mean_diff(oo_r, cell_oos_r)

            consistent = (
                d_tr is not None and d_oo is not None
                and ((d_tr > 0 and d_oo > 0) or (d_tr < 0 and d_oo < 0))
            )
            robust = consistent and abs(d_oo) >= EFFECT_D_MIN
            n_ok = len(tr_r) >= min_n and len(oo_r) >= 2
            status = INTERACTION_SUPPORTED if (robust and n_ok) else INTERACTION_INCONCLUSIVE
            note = ("train->oos consistent" if consistent
                    else "train->oos inconsistent")
            findings.append(InteractionFinding(
                regime=regime,
                features=tuple(sorted(f for f, _ in combo)),
                n_train=len(tr_r),
                n_oos=len(oo_r),
                effect_d_train=round(d_tr, 4) if d_tr is not None else None,
                effect_d_oos=round(d_oo, 4) if d_oo is not None else None,
                expectancy_train=round(exp_tr, 4) if exp_tr is not None else None,
                expectancy_oos=round(exp_oo, 4) if exp_oo is not None else None,
                pooled_expectancy=round(pooled, 4) if pooled is not None else None,
                p_value=round(p_value, 6) if p_value is not None else None,
                status=status,
                survives_familywise=False,
                note=note + ("  [combo cap reached]" if capped else ""),
            ))
    return findings