"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- recovery

Recovery probability for MISSED / REJECTED setups.

For every 9A opportunity where the frozen baseline NEVER filled
(entry not reached / rejected), each FIXED alternative
(LIMIT_RETEST / MARKET_CONFIRMATION / BREAKOUT_CONTINUATION) is
replayed independently by 9C. A recovery is the counterfactual fact:

   alternative filled AND settled a WIN

Only settled attempts are scored; a non-fill counts as a failed
recovery (you sat out -- honest, no fabrication). Deterministic.

Per (alternative, generated regime) cell this reports:

   * p_recovery          P(WIN | alternative attempt on a miss)
   * expected_r          average realised R of the attempts
   * expected_drawdown   average MAE (adverse move during the attempt)
   * loss_probability    P(LOSS | attempt settled)
   * adverse_excursion   MAE p50 / p90
   * regime_dependency   Cohen's h between the regime's recovery rate
                         and the alternative's overall recovery rate

status == RECOVERY_SUPPORTED only when the sample meets the raised
min-n gate, the expected R is positive, and the cell survives the
global familywise correction.
====================================================
"""

import math

from core.research.conditional_ml.types import (
    RecoveryFinding,
    RECOVERY_SUPPORTED,
    RECOVERY_INCONCLUSIVE,
    UNAVAILABLE,
)
from core.research.conditional_ml.guards import required_min_n
from core.research.ml.statistics import effect_size_h
from core.research.regime.regime_types import short_id


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _quantile(xs, q):
    if not xs:
        return None
    ordered = sorted(xs)
    idx = int(math.ceil(q * (len(ordered) - 1)))
    return ordered[idx]


def recovery_probabilities(rows, alternatives, min_n=6, n_hypotheses=0):
    """rows: model rows aligned to opportunities, each exposing
    .ctx (OpportunityContext), .recovery (dict alt->label 0/1),
    .rs (dict alt->settled R or None), .maes (dict alt->MAE or None),
    .known (bool -- opportunity was a missed/rejected baseline).

    Returns a list of RecoveryFinding (deterministic order).
    """
    pool = [r for r in rows if getattr(r, "known", False)]
    if not pool:
        return []

    min_n_gate = required_min_n(min_n, n_hypotheses)
    findings = []
    for alt in alternatives:
        overall = [r for r in pool if getattr(r, "recovery", {}).get(alt) is not None]
        if not overall:
            continue
        overall_p = sum(1 for r in overall
                        if int(getattr(r, "recovery", {}).get(alt)) == 1) / len(overall)
        regimes = {}
        for r in overall:
            regime = r.ctx.primary_generated() or UNAVAILABLE
            regimes.setdefault(regime, []).append(r)
        for regime in sorted(regimes.keys(), key=lambda x: (str(x), str(x))):
            cell = regimes[regime]
            n = len(cell)
            labels = [int(r.recovery.get(alt)) for r in cell
                      if r.recovery.get(alt) is not None]
            if not labels:
                continue
            recovered = sum(labels)
            p_recovery = recovered / n if n else None

            settled = [r for r in cell if r.rs.get(alt) is not None]
            rs = [r.rs[alt] for r in settled]
            mae = [r.maes[alt] for r in settled if r.maes.get(alt) is not None]
            losses = [r for r in settled if r.rs[alt] < 0]
            expected_r = (sum(rs) / len(rs)) if rs else None
            expected_dd = (sum(mae) / len(mae)) if mae else None
            loss_prob = (len(losses) / len(settled)) if settled else None
            adv50 = _quantile(mae, 0.5) if mae else None
            adv90 = _quantile(mae, 0.9) if mae else None
            dep_h = effect_size_h(p_recovery, overall_p) if p_recovery is not None else None

            n_gate_ok = n >= min_n_gate
            econ_ok = expected_r is not None and expected_r > 0.0
            status = RECOVERY_SUPPORTED if (n_gate_ok and econ_ok) else RECOVERY_INCONCLUSIVE

            findings.append(RecoveryFinding(
                alternative=alt,
                regime=regime,
                n=n,
                recovered=recovered,
                p_recovery=round(p_recovery, 4) if p_recovery is not None else None,
                expected_r=round(expected_r, 4) if expected_r is not None else None,
                expected_drawdown=round(expected_dd, 4) if expected_dd is not None else None,
                loss_probability=round(loss_prob, 4) if loss_prob is not None else None,
                adverse_excursion_p50=round(adv50, 4) if adv50 is not None else None,
                adverse_excursion_p90=round(adv90, 4) if adv90 is not None else None,
                regime_dependency_h=round(dep_h, 4) if dep_h is not None else None,
                min_n_gate=min_n_gate,
                status=status,
                survives_familywise=False,
                finding_id=short_id("L", alt, regime),
            ))
    return findings