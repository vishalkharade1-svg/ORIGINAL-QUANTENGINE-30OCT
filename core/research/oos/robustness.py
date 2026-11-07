"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- robustness

Deterministic robustness classification across the 9M dimensions:

   * time-period consistency (5/6 survival threshold)
   * economic consistency (sign-consistent majority)
   * sample-size sufficiency (per-period + total gates)
   * regime consistency (target conditioned separately; no universal
     generalization)
   * symbol consistency (per-symbol evidence, INCONCLUSIVE != REJECTED
     != UNAVAILABLE)
   * directional consistency (LONG / SHORT evaluated separately; no
     automatic inference LONG good -> SHORT good or the reverse)

A finding that only works in one tiny slice never earns HIGH.
====================================================================
"""

from core.research.oos import constants as _c


def classify(hypothesis, summary, regime=None, symbols=None,
             directions=None, gates=None):
    """LOW / MEDIUM / HIGH with an explicit pass/fail report per
    dimension."""
    gates = gates or {}
    min_surv = int(gates.get("min_surviving_periods", 5))
    req_sign = int(gates.get("required_sign_consistent_periods", 5))
    min_total = int(gates.get("min_total_oos_trades", 60))

    avail = summary["periods_available"]
    surv = summary["periods_survived"]
    reject = summary["periods_rejected"]
    sign = summary["sign_consistent_periods"]
    total_trades = summary.get("total_oos_trades", 0)

    time_ok = surv >= min_surv and avail >= min_surv and reject <= 1
    economic_ok = sign >= req_sign and summary["economic_consistent"]
    sample_ok = avail >= min_surv and total_trades >= min_total

    regime_ok = True
    regime_note = "not conditioned"
    if hypothesis.is_conditional():
        if regime is None:
            regime_ok = False
            regime_note = "no regime evidence evaluated"
        else:
            target = regime.get("target")
            non = regime.get("non_target")
            regime_ok = bool(
                target is not None
                and (target.get("n_settled") or 0) > 0
                and (target.get("expectancy_delta") or 0) >= 0
            )
            regime_note = (
                "conditional evidence retained; target evaluated "
                "separately from non-target"
                if non is not None else regime_note
            )

    symbol_ok = True
    if symbols and len(symbols) > 1:
        # a symbol with settled evidence that is adversarially negative
        # blocks a HIGH classification on this dimension.
        negatives = [
            s for s in symbols.values()
            if (s.get("n_settled") or 0) > 0
            and (s.get("expectancy_delta") or 0) < 0
        ]
        symbol_ok = not negatives
    elif hypothesis.symbol and symbols:
        symbol_ok = bool(
            symbols.get(hypothesis.symbol, {}).get("n_settled", 0) > 0
        )

    direction_ok = True
    if directions and hypothesis.direction:
        research_dir = {
            "LONG": "BULLISH", "SHORT": "BEARISH",
        }.get(hypothesis.direction, hypothesis.direction)
        mine = directions.get(research_dir)
        if not mine:
            direction_ok = False
        elif (mine.get("n_settled") or 0) > 0 \
                and (mine.get("expectancy_delta") or 0) < 0:
            direction_ok = False
        # an OPPOSITE direction is surfaced as asymmetry, never merged.

    core = sum(bool(x) for x in (time_ok, economic_ok, sample_ok))
    if core >= 3 and regime_ok and symbol_ok and direction_ok:
        level = _c.ROBUSTNESS_LEVELS[2]
    elif core >= 2:
        level = _c.ROBUSTNESS_LEVELS[1]
    else:
        level = _c.ROBUSTNESS_LEVELS[0]

    return {
        "level": level,
        "passed": {
            "time_period": time_ok,
            "economic": economic_ok,
            "sample_size": sample_ok,
            "regime": regime_ok,
            "symbol": symbol_ok,
            "directional": direction_ok,
        },
        "reasons": {
            "time_period": (
                "%d/%d settled periods survived, %d rejected"
                % (surv, avail, reject) if avail else "no settled periods"),
            "economic": (
                "%d sign-consistent periods of %d required"
                % (sign, req_sign)),
            "sample_size": (
                "total OOS trades %d of %d required"
                % (total_trades, min_total)),
            "regime": regime_note,
            "symbol": "per-symbol evidence separated",
            "directional": "LONG/SHORT evidence never merged",
        },
    }