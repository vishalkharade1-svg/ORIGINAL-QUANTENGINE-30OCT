"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- transitions

Regime transition between SETUP GENERATION and FILL.

A setup may be generated in one market regime and actually FILLED in
another -- a potentially important distinction the layer tracks
explicitly. For every opportunity whose 9C baseline factually filled,
this reports:

   generated_regime -> filled_regime

   * n, win rate, average R of the filled baseline trades,
   * expectancy delta vs the STABLE reference (generated == filled),
   * status CHANGED when the sample meets the gate and the delta is
     economically material; STABLE otherwise; INCONCLUSIVE when the
     transition has too few filled observations.

The (generated -> filled) buckets are retained for every observed
transition -- never hidden.
====================================================
"""

from core.research.conditional_ml.types import (
    TransitionFinding,
    TRANSITION_STABLE,
    TRANSITION_CHANGED,
    TRANSITION_INCONCLUSIVE,
    UNAVAILABLE,
)


def _fits(orows):
    out = []
    for i, r in enumerate(orows):
        if not r.ctx.baseline_filled:
            continue
        g = r.ctx.primary_generated() or UNAVAILABLE
        f = r.ctx.primary_filled()
        if f is None:
            continue
        out.append((i, g, f))
    return out


def transitions(orows, min_n=3, delta_r=0.5):
    """Deterministic (generated, filled) transition table."""
    rows = _fits(orows)
    if not rows:
        return []

    buckets = {}
    for i, g, f in rows:
        buckets.setdefault((g, f), []).append(orows[i])

    stable = [r for r in rows
              if r[1] == r[2]]
    stable_r = [orows[i].baseline_r for i, _, _ in stable
                if orows[i].baseline_r is not None]
    stable_exp = (sum(stable_r) / len(stable_r)) if stable_r else None

    out = []
    for (g, f) in sorted(buckets.keys(), key=lambda x: (str(x[0]), str(x[1]))):
        cell = buckets[(g, f)]
        n = len(cell)
        rs = [r.baseline_r for r in cell if r.baseline_r is not None]
        wins = [r for r in cell
                if r.baseline_r is not None and r.baseline_r > 0]
        avg_r = (sum(rs) / len(rs)) if rs else None
        win_rate = (len(wins) / len(rs)) if rs else None
        delta = None
        if avg_r is not None and stable_exp is not None:
            delta = avg_r - stable_exp

        if n < min_n:
            status = TRANSITION_INCONCLUSIVE
        elif g == f:
            status = TRANSITION_STABLE
        else:
            material = delta is not None and abs(delta) >= delta_r
            status = TRANSITION_CHANGED if material else TRANSITION_STABLE

        out.append(TransitionFinding(
            generated_regime=g,
            filled_regime=f,
            n=n,
            win_rate=round(win_rate, 4) if win_rate is not None else None,
            avg_r=round(avg_r, 4) if avg_r is not None else None,
            expectancy_delta_vs_stable=round(delta, 4) if delta is not None else None,
            status=status,
            note="transition" if g != f else "stable",
        ))
    return out