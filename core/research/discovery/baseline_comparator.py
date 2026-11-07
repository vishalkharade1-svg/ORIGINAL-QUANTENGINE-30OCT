"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- baseline comparator
& economic capture assessment

The deterministic economic judge of DISCOVERY. Two responsibilities:

   1. compare_experiment()  -- full like-for-like metric report between
      one experiment and its baseline, with an EXPLICIT population
      difference note whenever the fill populations differ. Unlike
      populations are never compared silently.

   2. economic_assessment() -- the capture objective: capture GAIN
      (incremental fills / incremental R) without degrading expectancy,
      risk (avg MAE), loss rate, or drawdown. Loss EXPANSION
      (more fills AND strictly worse per-trade economics) is detected
      and reported. All verdicts are deterministic strings.

This module is pure arithmetic over metric dicts (frozen 9D output).
It never ranks "winners" -- it only reports the economic trade-offs.
====================================================
"""

from core.research.discovery.discovery_types import EconomicAssessment


def _num(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compare_experiment(analysis, baseline_metrics):
    """(metrics, comparison dict, population note, same-population flag)."""
    metrics = dict(getattr(analysis, "metrics", {}) or {})
    comparison = {}
    comparison_obj = getattr(analysis, "comparison", None)
    if comparison_obj is not None and hasattr(comparison_obj, "to_dict"):
        comparison = dict(comparison_obj.to_dict() or {})
    base = dict(baseline_metrics or {})

    population_note = ""
    cand_filled = _num(metrics.get("filled"), -1)
    base_filled = _num(base.get("filled"), -1)
    if cand_filled != base_filled:
        population_note = (
            "unlike populations: candidate filled "
            f"{_num(metrics.get('filled'))} vs baseline filled "
            f"{_num(base.get('filled'))}; per-settled/per-filled metrics "
            "are compared on that basis and the raw fill delta is "
            "reported separately"
        )
    elif _num(metrics.get("opportunities")) != _num(base.get("opportunities")):
        population_note = (
            "opportunity population supplied differs from the baseline "
            "population; comparisons remain like-for-like per opportunity"
        )

    return {
        "metrics": metrics,
        "comparison": comparison,
        "population_note": population_note,
        "population_same": not bool(population_note),
    }


def _loss_rate(metrics):
    settled = _num(metrics.get("settled"))
    if settled <= 0:
        return 0.0
    return _num(metrics.get("losses")) / settled


def economic_assessment(metrics, baseline_metrics, recovery=None):
    """The capture-vs-risk trade-off of an experiment vs its baseline.

    recovery: optional per-experiment recovery evidence from
    recovery_discovery (recovered_observations). When recovery is
    provided, capture_gain is the number of previously-missed
    opportunities the configuration RECOVERED (the recovery-first
    objective) and incremental_R is the R added by that recovery.
    Without recovery evidence the raw fill-delta fallback is used.

    Acceptable capture requires: no loss expansion, a non-negative
    capture gain, non-degraded expectancy, no higher loss rate and no
    higher drawdown. avg-MAE movement is REPORTED (risk_delta / verdict
    token "risk (avg MAE) rose") but does not block: a recovery-first
    earlier entry inherently touches more adverse excursion, so MAE is
    surfaced honestly instead of silently disqualifying the recovery.
    """
    cand = dict(metrics or {})
    base = dict(baseline_metrics or {})

    if recovery is not None:
        capture_gain = int(round(
            _num(recovery.get("recovery_count"))
        ))
        incremental_R = _num(recovery.get("added_R"))
    else:
        capture_gain = int(round(
            _num(cand.get("filled")) - _num(base.get("filled"))
        ))
        incremental_R = _num(cand.get("total_R")) - _num(base.get("total_R"))
    expectancy_delta = _num(cand.get("expectancy")) - _num(base.get("expectancy"))
    risk_delta = _num(cand.get("avg_MAE")) - _num(base.get("avg_MAE"))
    loss_rate_delta = _loss_rate(cand) - _loss_rate(base)
    max_drawdown_delta = (
        _num(cand.get("max_drawdown")) - _num(base.get("max_drawdown"))
    )

    # loss expansion = MORE fills AND strictly worse per-trade economics.
    cand_losses = _num(cand.get("losses"))
    base_losses = _num(base.get("losses"))
    cand_win = _num(cand.get("win_rate"))
    base_win = _num(base.get("win_rate"))
    cand_pf = _num(cand.get("profit_factor"), None)
    base_pf = _num(base.get("profit_factor"), None)
    worse_win = cand_win < base_win
    worse_pf = (base_pf == float("inf") and cand_pf != float("inf")) or \
        (cand_pf < base_pf)
    loss_expansion = bool(
        capture_gain > 0
        and cand_losses > base_losses
        and (worse_win or worse_pf)
    )

    acceptable = bool(
        not loss_expansion
        and capture_gain >= 0
        and expectancy_delta >= 0
        and loss_rate_delta <= 0
        and max_drawdown_delta <= 0
    )

    verdict = _verdict(loss_expansion, acceptable, capture_gain,
                       expectancy_delta, loss_rate_delta,
                       risk_delta=risk_delta)

    return EconomicAssessment(
        capture_gain=capture_gain,
        incremental_R=round(incremental_R, 6),
        expectancy_delta=round(expectancy_delta, 6),
        risk_delta=round(risk_delta, 6),
        loss_rate_delta=round(loss_rate_delta, 6),
        max_drawdown_delta=round(max_drawdown_delta, 6),
        loss_expansion=loss_expansion,
        acceptable=acceptable,
        verdict=verdict,
    )


def _verdict(loss_expansion, acceptable, capture_gain,
             expectancy_delta, loss_rate_delta, risk_delta=0.0):
    if loss_expansion:
        return (
            "LOSS_EXPANSION: more fills added losses with worse "
            "win-rate or profit factor -- economic capture is rejected "
            "(evidence retained)"
        )
    if acceptable:
        return (
            "RECOVERY_CAPTURES_VALUE_WITHOUT_WORSE_ECONOMICS: "
            "incremental capture with no degradation in expectancy, "
            "loss rate or drawdown"
        )
    flag = []
    if capture_gain <= 0:
        flag.append("no net capture gain")
    if expectancy_delta < 0:
        flag.append("expectancy degraded")
    if risk_delta > 0:
        flag.append("risk (avg MAE) rose")
    if loss_rate_delta > 0:
        flag.append("loss rate rose")
    if not flag:
        flag.append("no net capture gain")
    return "CAPTURE_TRADE_OFF: " + "; ".join(flag)