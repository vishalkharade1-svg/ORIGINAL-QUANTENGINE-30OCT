"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- calibration

Confidence / calibration over OUT-OF-SAMPLE observations only.

The 9L contract: a model that says 80% must actually perform near
80% over appropriate OOS observations. Every probability surface of
the layer is therefore paired with a CalibrationSummary:

   * bins:   equal-width confidence bins with expected vs observed
             rates (all retained -- a gap is reported, never hidden),
   * ECE:    expected calibration error (mean |expected-observed|
             weighted by bin mass),
   * Brier:  mean squared probability error,
   * slope:  linear slope of observed outcome on the model's logit
             (calibration slope; None when degenerate).

status == CALIBRATED only when the OOS sample meets the minimum and
the ECE stays within the closed bound (ECE_MAX_CALIBRATED).
====================================================
"""

from core.research.conditional_ml.types import (
    CalibrationBin,
    CalibrationSummary,
    CALIBRATED,
    CALIBRATION_GAP,
    ECE_MAX_CALIBRATED,
)


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def calibration_summary(pairs, surface="", min_n_gate=10, n_bins=10):
    """pairs: iterable of (predicted_prob, actual_label). Deterministic.

    Returns a CalibrationSummary. Empty / degenerate inputs produce a
    CALIBRATION_GAP summary with empty bins (never fabricated).
    """
    pairs = [(_num(p), _num(y)) for p, y in pairs]
    pairs = [p for p in pairs if p[0] is not None and p[1] is not None]
    oos_n = len(pairs)
    if oos_n == 0:
        return CalibrationSummary(
            surface=surface,
            oos_n=0,
            ece=None,
            brier=None,
            slope=None,
            status=CALIBRATION_GAP,
            min_n_gate=min_n_gate,
            bins=(),
        )

    brier = sum((p - y) ** 2 for p, y in pairs) / oos_n

    # equal-width bins over [0, 1]
    bins = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        rows = [(p, y) for p, y in pairs if lo <= p < hi or (i == n_bins - 1 and p == 1.0)]
        if not rows:
            bins.append(CalibrationBin(
                bin_index=i,
                midpoint=(lo + hi) / 2.0,
                n=0,
                expected_rate=None,
                observed_rate=None,
                abs_error=None,
            ))
            continue
        n = len(rows)
        expected = _mean([p for p, _ in rows])
        observed = _mean([y for _, y in rows])
        bins.append(CalibrationBin(
            bin_index=i,
            midpoint=(lo + hi) / 2.0,
            n=n,
            expected_rate=round(expected, 4),
            observed_rate=round(observed, 4),
            abs_error=round(abs(expected - observed), 4),
        ))

    populated = [b for b in bins if b.n > 0]
    total_populated = sum(b.n for b in populated)
    ece = None
    if total_populated:
        ece = sum(
            (b.n / total_populated) * abs(b.expected_rate - b.observed_rate)
            for b in populated
        )

    _logit = []
    for p, y in pairs:
        p = max(1e-4, min(1.0 - 1e-4, p))
        _logit.append((math_logit(p), y))
    slope = None
    if len(_logit) >= 3:
        xs = [x for x, _ in _logit]
        ys = [y for _, y in _logit]
        mx = _mean(xs)
        my = _mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            slope = num / den

    ece = round(ece, 4) if ece is not None else None
    slope = round(slope, 6) if slope is not None else None
    status = CALIBRATED if (
        oos_n >= min_n_gate and ece is not None and ece <= ECE_MAX_CALIBRATED
    ) else CALIBRATION_GAP

    return CalibrationSummary(
        surface=surface,
        oos_n=oos_n,
        ece=ece,
        brier=round(brier, 4),
        slope=slope,
        status=status,
        min_n_gate=min_n_gate,
        bins=tuple(bins),
    )


def math_logit(p):
    import math

    return math.log(p / (1.0 - p))