"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- gates

Deterministic anti-overfitting gates for the 9L discovery surfaces.
9L deliberately does NOT search 100k combinations and pick the best:
it evaluates a fixed, bounded grid and then applies every gate --
minimum sample size, temporal OOS validation, economic significance,
confidence/calibration and a GLOBAL multiple-testing correction that
is stricter than any per-surface guard.

   * required_min_n      -- sample requirement that grows with the
                            total number of hypotheses tested,
   * familywise_alpha    -- Sidak familywise control across the TOTAL
                            enumerated hypothesis family,
   * holm_survives       -- Holm-Bonferroni survival flags over the
                            same global family (strictest per-finding
                            threshold),
   * z_prop_p            -- deterministic two-proportion z-test
                            p-value (pure math, no scipy).

All correction machinery is conservative and clearly labeled as a
research gate, never a significance oracle.
====================================================
"""

import math

# pure-math erf (deterministic, no scipy/numpy dependency)
_erf = math.erf


def required_min_n(min_n, n_hypotheses):
    """Sample requirement grows logarithmically with hypotheses."""
    if n_hypotheses <= 0:
        return int(min_n)
    return int(min_n) + int(math.ceil(math.log2(1.0 + n_hypotheses)))


def familywise_alpha(alpha=0.05, n_hypotheses=1):
    """Sidak familywise alpha across the total hypothesis family."""
    if n_hypotheses <= 0:
        return alpha
    return 1.0 - (1.0 - alpha) ** (1.0 / n_hypotheses)


def holm_survives(p_values, alpha=0.05):
    """Holm-Bonferroni survival flags over a p-value family.

    Deterministic: ties sort by the supplied index order. Returns
    (survives_list, n_family). The found p-values are already the
    family ENUMERATED by the fixed grid (never cherry-picked).
    """
    n = len(p_values)
    flags = [False] * n
    if n == 0:
        return flags, 0
    order = sorted(range(n), key=lambda i: (p_values[i] if p_values[i] is not None else 1.0, i))
    for rank, idx in enumerate(order):
        p = p_values[idx]
        if p is None:
            continue
        thresh = alpha / (n - rank)
        if p <= thresh:
            flags[idx] = True
        else:
            # Holm is step-down: once a null fails, the remaining fail.
            break
    return flags, n


def z_prop_win(known_a, wins_a, known_b, wins_b):
    """Two-proportion z-test p-value (two-sided, normal approx).

    Pure math via math.erf -- deterministic, no scipy. Degenerate
    (zero denominators) returns None.
    """
    if known_a <= 0 or known_b <= 0:
        return None
    pa = wins_a / known_a
    pb = wins_b / known_b
    p_pool = (wins_a + wins_b) / (known_a + known_b)
    if p_pool <= 0.0 or p_pool >= 1.0:
        return None
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / known_a + 1.0 / known_b))
    if se <= 0.0:
        return None
    z = abs(pa - pb) / se
    # two-sided tail probability P(|Z| > z)
    return float(1.0 - _erf(z / math.sqrt(2.0)))


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    if len(xs) < 2:
        return None
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def z_mean_diff(group_a, group_b):
    """Two-sample mean test p-value (two-sided, normal approx, Welch).

    Deterministic pure math; returns None when degenerate.
    """
    a = [x for x in group_a if x is not None]
    b = [x for x in group_b if x is not None]
    if not a or not b:
        return None
    ma = _mean(a)
    mb = _mean(b)
    sa = _std(a)
    sb = _std(b)
    if sa is None or sb is None:
        return None
    se = math.sqrt(sa ** 2 / len(a) + sb ** 2 / len(b))
    if se <= 0.0:
        return None
    z = abs(ma - mb) / se
    # two-sided tail probability P(|Z| > z)
    return float(1.0 - _erf(z / math.sqrt(2.0)))