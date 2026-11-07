"""
====================================================================

QuantEngine

Multi-Period Out-of-Sample Validation (Phase 9M) -- validator

Independent re-evaluation of ONE consumed hypothesis on an unseen OOS
population.

The candidate configuration is ALWAYS replayed through the frozen 9C
counterfactual machinery (CounterfactualRunner) against the FROZEN
production baseline (BREAKOUT_CONTINUATION) -- never against the
observations that generated the discovery. The comparison therefore
respects the hard TRUTH-DISCOVERY / OOS distinction:

   discover(A) -> validate(B) with B strictly AFTER the decision
   boundary. discover(A+B) -> validate(A+B) is never called OOS.

Gates (locked defaults in constants / engine):
   * an insufficient sample is INCONCLUSIVE, never silently discarded;
   * genuine loss expansion or worsened economics is REJECTION
     evidence;
   * an MAE increase is a REPORTABLE trade-off (PROMISING), not
     automatic rejection.
====================================================================
"""

from core.research.counterfactual.counterfactual_config import (
    CounterfactualConfig,
)
from core.research.counterfactual.counterfactual_runner import (
    CounterfactualRunner,
)
from core.research.oos import constants as _c
from core.research.oos.oos_types import OosPeriodEvidence


def _settled(outcome):
    return (outcome.result or "").upper() in ("WIN", "LOSS")


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def evaluate_pool(records, candles, base_config, hypothesis, outcome_bars,
                  gates, runner=None):
    """Re-evaluate candidate vs frozen baseline over one record pool.

    Returns a plain dict of deterministic metrics + a settled status.
    Candidate params that cannot be materialized into a frozen 9C
    config FAIL LOUDLY (ValueError) -- unknown axes are never silently
    invented.
    """
    params = dict(hypothesis.params)
    if not params.get("entry_model"):
        raise ValueError(
            "hypothesis candidate must declare an entry_model; "
            "supported=%s" % (_c.CANDIDATE_ALTERNATIVES,)
        )

    base_params = dict(base_config)
    base_params.setdefault("entry_model", "BREAKOUT_CONTINUATION")

    cand_cfg = CounterfactualConfig(
        params=params, outcome_bars=outcome_bars, baseline_id="baseline")
    base_cfg = CounterfactualConfig(
        params=base_params, outcome_bars=outcome_bars, baseline_id="baseline")

    runner = runner or CounterfactualRunner(
        candles, baseline_id="baseline")
    cand = runner.run_config(records, cand_cfg)
    base = runner.run_config(records, base_cfg)

    c_settled = [o for o in cand if _settled(o)]
    b_settled = [o for o in base if _settled(o)]
    n = len(records)
    n_filled = sum(1 for o in cand if o.filled)
    n_trades = len(c_settled)
    wins = sum(1 for o in c_settled if (o.result or "").upper() == "WIN")
    losses = n_trades - wins
    base_trades = len(b_settled)
    base_wins = sum(1 for o in b_settled
                    if (o.result or "").upper() == "WIN")
    base_losses = base_trades - base_wins

    win_rate = wins / n_trades if n_trades else None
    base_win_rate = base_wins / base_trades if base_trades else None
    expectancy = _mean([o.r for o in c_settled])
    baseline_expectancy = _mean([o.r for o in b_settled])
    expectancy_delta = (
        expectancy - baseline_expectancy
        if expectancy is not None and baseline_expectancy is not None
        else None
    )
    cand_loss_rate = losses / n_trades if n_trades else None
    base_loss_rate = base_losses / base_trades if base_trades else None
    loss_rate_delta = (
        cand_loss_rate - base_loss_rate
        if cand_loss_rate is not None and base_loss_rate is not None
        else None
    )
    cand_mae = _mean([o.mae for o in c_settled])
    base_mae = _mean([o.mae for o in b_settled])
    mae_delta = (
        cand_mae - base_mae
        if cand_mae is not None and base_mae is not None else None
    )

    # recovery / capture: opportunities the frozen baseline missed or
    # left unsettled but the candidate captured as a WIN.
    recovered_ids = set()
    rec_rs = []
    for idx, bo in enumerate(base):
        if _settled(bo):
            continue
        if idx >= len(cand):
            continue
        co = cand[idx]
        if co.filled and (co.result or "").upper() == "WIN":
            recovered_ids.add(co.opportunity_id)
            if co.r is not None:
                rec_rs.append(co.r)
    n_baseline_missed = sum(1 for o in base if not _settled(o))
    n_recovered = len(recovered_ids)
    capture_gain = (
        n_recovered / n_baseline_missed if n_baseline_missed else None
    )
    recovery_gain = _mean(rec_rs)

    mae_tradeoff = bool(mae_delta is not None and mae_delta > 1e-9)
    min_opp = int(gates["min_oos_opportunities_per_period"])
    min_trades = int(gates["min_oos_trades_per_period"])
    loss_expansion_gate = float(
        gates.get("loss_rate_expansion", _c.LOSS_RATE_EXPANSION)
    )
    loss_expansion = bool(
        loss_rate_delta is not None
        and loss_rate_delta > loss_expansion_gate
    )
    expect_ok = bool(expectancy_delta is not None and expectancy_delta >= -1e-9)
    capture_ok = bool(capture_gain is None or capture_gain >= -1e-9)

    reasons = []
    sample_sufficient = bool(n >= min_opp and n_trades >= min_trades)
    if n == 0:
        return {
            "n_opportunities": 0, "n_trades": 0, "n_wins": 0,
            "n_losses": 0, "n_candidate_filled": 0,
            "n_baseline_settled": 0, "n_baseline_missed": 0,
            "n_recovered": 0, "win_rate": None, "expectancy": None,
            "baseline_expectancy": None, "expectancy_delta": None,
            "capture_gain": None, "loss_rate_delta": None,
            "max_drawdown_delta": None, "recovery_gain": None,
            "mae_tradeoff": False, "loss_expansion": False,
            "economic_acceptable": False, "sample_sufficient": False,
            "status": _c.PERIOD_STATUSES[-1],
            "reasons": ["no eligible opportunities in this period"],
        }

    if not sample_sufficient:
        if n < min_opp:
            reasons.append(
                "opportunities %d below the %d per-period gate"
                % (n, min_opp))
        if n_trades < min_trades:
            reasons.append(
                "trades %d below the %d per-period gate" % (n_trades, min_trades))
        return {
            "n_opportunities": n, "n_trades": n_trades, "n_wins": wins,
            "n_losses": losses, "n_candidate_filled": n_filled,
            "n_baseline_settled": len(b_settled),
            "n_baseline_missed": n_baseline_missed,
            "n_recovered": n_recovered, "win_rate": win_rate,
            "expectancy": expectancy,
            "baseline_expectancy": baseline_expectancy,
            "expectancy_delta": expectancy_delta,
            "capture_gain": capture_gain, "loss_rate_delta": loss_rate_delta,
            "max_drawdown_delta": mae_delta, "recovery_gain": recovery_gain,
            "mae_tradeoff": mae_tradeoff, "loss_expansion": loss_expansion,
            "economic_acceptable": False, "sample_sufficient": False,
            "status": _c.PERIOD_STATUSES[2],
            "reasons": tuple(reasons),
        }

    if baseline_expectancy is None or expectancy is None \
            or expectancy_delta is None:
        reasons.append(
            "no settled baseline expectancy to compare against "
            "(baseline settled=%d)" % len(b_settled))
        return {
            "n_opportunities": n, "n_trades": n_trades, "n_wins": wins,
            "n_losses": losses, "n_candidate_filled": n_filled,
            "n_baseline_settled": len(b_settled),
            "n_baseline_missed": n_baseline_missed,
            "n_recovered": n_recovered, "win_rate": win_rate,
            "expectancy": expectancy,
            "baseline_expectancy": baseline_expectancy,
            "expectancy_delta": expectancy_delta,
            "capture_gain": capture_gain, "loss_rate_delta": loss_rate_delta,
            "max_drawdown_delta": mae_delta, "recovery_gain": recovery_gain,
            "mae_tradeoff": mae_tradeoff, "loss_expansion": loss_expansion,
            "economic_acceptable": False, "sample_sufficient": True,
            "status": _c.PERIOD_STATUSES[2],
            "reasons": tuple(reasons),
        }

    if loss_expansion:
        reasons.append(
            "genuine loss-rate expansion: %.3f" % (loss_rate_delta or 0.0))
    if not expect_ok:
        reasons.append(
            "candidate expectancy %.3f below baseline %.3f"
            % (expectancy, baseline_expectancy))
    if not capture_ok:
        reasons.append("no capture/recovery gain vs missed baselines")
    if mae_tradeoff:
        reasons.append(
            "reportable MAE trade-off: +%.3f points avg adverse "
            "excursion" % (mae_delta or 0.0))
    economic_acceptable = not loss_expansion and expect_ok and capture_ok
    if not economic_acceptable:
        status = _c.PERIOD_STATUSES[3]
    elif mae_tradeoff:
        status = _c.PERIOD_STATUSES[1]
    else:
        status = _c.PERIOD_STATUSES[0]

    return {
        "n_opportunities": n, "n_trades": n_trades, "n_wins": wins,
        "n_losses": losses, "n_candidate_filled": n_filled,
        "n_baseline_settled": len(b_settled),
        "n_baseline_missed": n_baseline_missed,
        "n_recovered": n_recovered, "win_rate": win_rate,
        "expectancy": expectancy,
        "baseline_expectancy": baseline_expectancy,
        "expectancy_delta": expectancy_delta,
        "capture_gain": capture_gain, "loss_rate_delta": loss_rate_delta,
        "max_drawdown_delta": mae_delta, "recovery_gain": recovery_gain,
        "mae_tradeoff": mae_tradeoff, "loss_expansion": loss_expansion,
        "economic_acceptable": economic_acceptable,
        "sample_sufficient": True,
        "status": status,
        "reasons": tuple(reasons),
    }


def evaluate_period(period_label, records, candles, base_config, hypothesis,
                    outcome_bars, gates, runner=None):
    """OosPeriodEvidence for one OOS period (frozen container)."""
    m = evaluate_pool(records, candles, base_config, hypothesis,
                      outcome_bars, gates, runner=runner)
    return OosPeriodEvidence(
        period=period_label,
        n_opportunities=m["n_opportunities"],
        n_baseline_settled=m["n_baseline_settled"],
        n_baseline_missed=m["n_baseline_missed"],
        n_candidate_filled=m.get("n_candidate_filled"),
        n_trades=m["n_trades"],
        n_wins=m["n_wins"],
        n_losses=m["n_losses"],
        n_recovered=m["n_recovered"],
        win_rate=m["win_rate"],
        expectancy=m["expectancy"],
        baseline_expectancy=m["baseline_expectancy"],
        expectancy_delta=m["expectancy_delta"],
        capture_gain=m["capture_gain"],
        loss_rate_delta=m["loss_rate_delta"],
        max_drawdown_delta=m["max_drawdown_delta"],
        recovery_gain=m["recovery_gain"],
        mae_tradeoff=m["mae_tradeoff"],
        loss_expansion=m["loss_expansion"],
        economic_acceptable=m["economic_acceptable"],
        sample_sufficient=m["sample_sufficient"],
        status=m["status"],
        reasons=m["reasons"],
    )