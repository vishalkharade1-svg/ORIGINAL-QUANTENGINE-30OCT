"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- walk-forward validation

Chronological, expanding-window validation of a conditional finding:
train/discover on EARLIER observations, validate on LATER unseen
observations, across multiple temporal windows. NO random shuffling,
NO temporal leakage (an observation never appears in a training cell
that precedes its own decision bar).

A conditional finding survives when, in a majority (2/3) of windows
with a sufficient within-cell validation sample reachable, the
candidate's validating expectancy is positive AND exceeds the frozen
baseline inside the same validating cell.
====================================================
"""

import math

from core.research.counterfactual.counterfactual_runner import (
    CounterfactualRunner,
)
from core.research.regime.regime_types import (
    WalkForwardWindow,
    WalkForwardSummary,
)
from core.research.regime.conditional import (
    build_config,
    _expectancy,
)


def _time_key(obs):
    bar = obs.decision_bar
    if isinstance(bar, (int, float)):
        return (0, float(bar), obs.observation_id)
    return (2, 0.0, obs.observation_id)


def temporal_windows(observations, n_windows=3):
    """Expanding-train, trailing-test chronological windows. Returns an
    empty tuple when the population cannot support a real fold."""
    ordered = sorted(observations, key=_time_key)
    n = len(ordered)
    if n < 2 * n_windows:
        return ()
    size = int(math.ceil(n / n_windows))
    windows = []
    for j in range(n_windows - 1):
        train = ordered[:(j + 1) * size]
        test = ordered[(j + 1) * size:(j + 2) * size]
        if not train or not test:
            continue
        windows.append({"window_index": j, "train": train,
                        "validate": test})
    return tuple(windows)


def _cell_records(records, cell_observations):
    ids = {o.observation_id for o in cell_observations}
    return tuple(
        r for r in records
        if getattr(r, "canonical_id", "") in ids
    )


def validate_conditional(finding, observations, records, candles,
                         base_config, n_windows=3, min_validation_n=3):
    """Walk-forward validation of one conditional finding."""
    runner = CounterfactualRunner(
        candles,
        baseline_id=getattr(base_config, "baseline_id", "baseline"),
    )
    cfg = build_config(base_config, dict(finding.config_params))
    cfg_id = cfg.experiment_id()
    windows = temporal_windows(observations, n_windows)
    if not windows:
        return WalkForwardSummary(
            survived=False,
            windows=(WalkForwardWindow(
                window_index=0, dimension=finding.dimension,
                label=finding.label, config_id=cfg_id,
                train_n=0, train_expectancy=None,
                validation_n=0, validation_expectancy=None,
                validation_delta=None, survived=False,
                note="population too small to build a chronological "
                     "walk-forward fold",
            ),),
        )
    wrows = []
    for w in windows:
        train_cell = [o for o in w["train"]
                      if o.in_regime(finding.dimension, finding.label)]
        val_cell = [o for o in w["validate"]
                    if o.in_regime(finding.dimension, finding.label)]
        train_recs = _cell_records(records, train_cell)
        val_recs = _cell_records(records, val_cell)
        tr_exp = _expectancy(
            runner.run_config(train_recs, cfg)) if train_recs else None
        va_exp = _expectancy(
            runner.run_config(val_recs, cfg)) if val_recs else None
        bva_exp = _expectancy(
            runner.run_config(val_recs, base_config)) if val_recs else None
        val_delta = (
            va_exp - bva_exp
            if va_exp is not None and bva_exp is not None else None
        )
        val_n = len(val_recs)
        if val_n < min_validation_n:
            survived = False
            note = (
                "within-cell validation sample %d below %d; OOS trail "
                "too thin to claim survival" % (val_n, min_validation_n)
            )
        elif va_exp is None or val_delta is None:
            survived = False
            note = "no settled validating expectancy available"
        elif va_exp > 0 and val_delta > 0:
            survived = True
            note = "validating expectancy positive and above baseline"
        else:
            survived = False
            note = (
                "validating expectancy not positive above baseline "
                "(%.3f vs baseline %.3f)" % (
                    va_exp if va_exp is not None else 0.0,
                    bva_exp if bva_exp is not None else 0.0,
                )
            )
        wrows.append(WalkForwardWindow(
            window_index=w["window_index"],
            dimension=finding.dimension,
            label=finding.label,
            config_id=cfg_id,
            train_n=len(train_recs),
            train_expectancy=tr_exp,
            validation_n=val_n,
            validation_expectancy=va_exp,
            validation_delta=val_delta,
            survived=survived,
            note=note,
        ))
    adequate = [w for w in wrows if w.validation_n >= min_validation_n]
    survived = False
    if adequate:
        ok = sum(1 for w in adequate if w.survived)
        survived = ok >= math.ceil(2.0 * len(adequate) / 3.0)
    return WalkForwardSummary(survived=survived, windows=tuple(wrows))