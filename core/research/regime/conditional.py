"""
====================================================

QuantEngine

Regime / Opportunity Discovery (Phase 9K) -- conditional engine

Answers the 9K question: *under which market conditions does a
candidate configuration work -- and under which does it fail?*

Pipeline (per candidate over the strict 9B/9C vocabulary):

   1. validate the candidate overrides (loud fail on any axis
      outside the supported 9B set -- nothing invented);
   2. measure the candidate's GLOBAL expectancy over all records
      (frozen 9C simulation);
   3. for each regime dimension x label cell: measure the candidate
      and the frozen baseline INSIDE the cell (expectancy + recoveries
      vs baseline) -- a conditional edge exists when the within-cell
      advantage is material and the dimension splits the population;
   4. retain EVERY cell and finding (INCONCLUSIVE / NOT_SUPPORTED /
      CONDITIONAL_WEAK included) -- no hiding of negative results;
   5. separately, split the 9F feature evidence by outcome (association
      only, min-sample gated).

Boundaries: read-only over records/candles/dataset; deterministic;
no lookahead; never a trade directive.
====================================================
"""

from core.research.counterfactual.counterfactual_runner import (
    CounterfactualRunner,
)
from core.research.counterfactual.counterfactual_config import (
    CounterfactualConfig,
)
from core.research.ml import StatisticalBaseline
from core.research.ml.statistics import effect_size_h
from core.research.dataset import DatasetSource as S
from core.research.discovery.candidate_space import validate_overrides
from core.research.regime.regime_types import (
    ConditionalCell,
    ConditionalFinding,
    FeatureSplit,
    UNAVAILABLE,
)
from core.research.regime.segmenter import cell_labels
from core.research.regime.detector import (
    PRIMARY_REGIME_DIMENSIONS,
)

MIN_CELL_N_DEFAULT = 10
DELTA_THRESHOLD_DEFAULT = 0.15
SPLIT_THRESHOLD_DEFAULT = 0.30
FEATURE_MIN_N_DEFAULT = 5


def _validate_candidate(overrides):
    """Scalar candidate -> strict 9B vocabulary (lists fan out, then
    read back the scalar). Raises loudly on unsupported axes/models."""
    listed = {k: [v] for k, v in (overrides or {}).items()}
    normalized = validate_overrides(listed)
    return {k: v[0] for k, v in normalized.items()}


def build_config(base_config, overrides):
    """A frozen CounterfactualConfig = frozen base + validated scalar
    overrides (same identity scheme as 9C)."""
    params = dict(getattr(base_config, "params", {}) or {})
    params.update(overrides or {})
    return CounterfactualConfig(
        params=params,
        outcome_bars=getattr(base_config, "outcome_bars", None),
        baseline_id=getattr(base_config, "baseline_id", "baseline"),
    )


def _expectancy(outcomes):
    try:
        return StatisticalBaseline(name="cell", rows=outcomes).expectancy()
    except Exception:
        return None


def _recovered(baseline_outcomes, candidate_outcomes):
    count = 0
    for b, c in zip(baseline_outcomes or (), candidate_outcomes or ()):
        bc = (getattr(b, "result", "") or "").upper()
        cc = (getattr(c, "result", "") or "").upper()
        if cc == "WIN" and bc != "WIN":
            count += 1
    return count


def _cell_records(records, observations, dimension, label):
    ids = {
        o.observation_id for o in observations
        if o.in_regime(dimension, label)
    }
    return tuple(
        r for r in records
        if getattr(r, "canonical_id", "") in ids
    )


def _split_effect(cells, min_cell_n):
    edges = [c.delta_expectancy for c in cells
             if c.n >= min_cell_n and c.delta_expectancy is not None]
    if len(edges) < 2:
        return UNAVAILABLE
    return max(edges) - min(edges)


def _finding_status(cell, rel_edge, split_effect, delta_threshold,
                    split_threshold):
    if cell.n < cell.min_n_gate:
        return "INCONCLUSIVE"
    if cell.delta_expectancy is None or rel_edge is None:
        return "INCONCLUSIVE"
    if cell.delta_expectancy >= delta_threshold and \
            rel_edge >= delta_threshold and \
            split_effect is not UNAVAILABLE and \
            split_effect >= split_threshold:
        return "CONDITIONAL"
    if cell.delta_expectancy > 0 or rel_edge > 0:
        return "CONDITIONAL_WEAK"
    return "NOT_SUPPORTED"


def _statement(cell, status, rel_edge, global_exp):
    params = {k: v for k, v in (cell.config_params or {}).items()
              if k in ("entry_model", "rr", "stop_mode", "target_mode",
                       "entry_offset_atr", "expiry", "confirmation_distance")}
    cfg_desc = ", ".join(
        "%s=%s" % (k, v) for k, v in sorted(params.items())
    ) or "candidate"
    base = (
        "Observed conditional evidence: %s performs inside "
        "%s=%s at expectancy %s R (n=%d) vs its global %s R "
        "(relative edge %s R)" % (
            cfg_desc, cell.dimension, cell.label,
            _fmt(cell.expectancy), cell.n, _fmt(global_exp),
            _fmt(rel_edge),
        )
    )
    if status == "CONDITIONAL":
        return base + "; the dimension splits the population (regime-"
        "conditional research evidence only, NEVER a directive)"
    if status == "CONDITIONAL_WEAK":
        return base + "; edge is small -- reported honestly, not "
        "over-claimed"
    if status == "INCONCLUSIVE":
        return base + "; requires a larger within-cell population"
    return base + "; no positive within-cell edge observed"


def _fmt(x):
    return "%.3f" % x if isinstance(x, (int, float)) else str(x)


def conditional_discovery(records, candles, base_config, candidates,
                          observations, min_cell_n=MIN_CELL_N_DEFAULT,
                          delta_threshold=DELTA_THRESHOLD_DEFAULT,
                          split_threshold=SPLIT_THRESHOLD_DEFAULT,
                          dimensions=PRIMARY_REGIME_DIMENSIONS):
    """Cells + conditional findings over every candidate."""
    runner = CounterfactualRunner(
        candles,
        baseline_id=getattr(base_config, "baseline_id", "baseline"),
    )
    base = base_config
    all_cells = []
    all_findings = []
    for overrides in candidates or ():
        ov = _validate_candidate(overrides)
        cfg = build_config(base, ov)
        config_id = cfg.experiment_id()
        global_out = runner.run_config(records, cfg)
        global_exp = _expectancy(global_out)
        for dim in dimensions:
            labels = cell_labels(observations, dim)
            if not labels:
                continue
            dim_cells = []
            for label in labels:
                cell_records = _cell_records(
                    records, observations, dim, label)
                n = len(cell_records)
                out_c = runner.run_config(cell_records, cfg) \
                    if n else ()
                out_b = runner.run_config(cell_records, base) \
                    if n else ()
                within = _expectancy(out_c)
                base_within = _expectancy(out_b)
                cell = ConditionalCell(
                    dimension=dim,
                    label=label,
                    config_id=config_id,
                    config_params=dict(ov),
                    n=n,
                    wins=sum(
                        1 for o in out_c
                        if (getattr(o, "result", "") or "").upper() == "WIN"
                    ),
                    win_rate=(
                        sum(
                            1 for o in out_c
                            if (getattr(o, "result", "") or "").upper() == "WIN"
                        ) / len(out_c)
                        if out_c else None
                    ),
                    expectancy=within,
                    baseline_expectancy=base_within,
                    delta_expectancy=(
                        (within - base_within)
                        if within is not None and base_within is not None
                        else None
                    ),
                    recovered=_recovered(out_b, out_c) if n else 0,
                    min_n_gate=min_cell_n,
                )
                dim_cells.append(cell)
            split_effect = _split_effect(dim_cells, min_cell_n)
            for cell in dim_cells:
                rel_edge = (
                    (cell.expectancy - global_exp)
                    if cell.expectancy is not None and global_exp is not None
                    else None
                )
                status = _finding_status(
                    cell, rel_edge, split_effect,
                    delta_threshold, split_threshold)
                note = ""
                if cell.n < cell.min_n_gate:
                    note = (
                        "cell population %d is below the minimum-sample "
                        "gate %d; configuration is NOT asserted on this "
                        "thin evidence" % (cell.n, cell.min_n_gate)
                    )
                elif status == "NOT_SUPPORTED":
                    note = "no positive within-cell edge observed"
                else:
                    note = (
                        "minimum-sample gate %d met; in-cell evidence "
                        "only" % min_cell_n
                    )
                finding = ConditionalFinding(
                    dimension=cell.dimension,
                    label=cell.label,
                    config_id=cell.config_id,
                    config_params=dict(cell.config_params),
                    within_expectancy=cell.expectancy,
                    global_expectancy=global_exp,
                    delta=rel_edge,
                    cell_n=cell.n,
                    status=status,
                    split_breadth=split_effect,
                    min_sample_note=note,
                    statement=_statement(
                        cell, status, rel_edge, global_exp),
                    evidence=(cell.config_id, cell.dimension,
                              str(cell.label)),
                )
                all_findings.append(finding)
            all_cells.extend(dim_cells)
    return tuple(all_cells), tuple(all_findings)


def feature_splits(dataset, observations, min_n_gate=FEATURE_MIN_N_DEFAULT):
    """Association of observed 9F feature values with outcomes
    (win rate / avg R). Joins FEATURE rows to observation results by
    observation_id; only NON-UNAVAILABLE values are considered and
    only groups meeting the min-sample gate are reported."""
    if dataset is None:
        return ()
    try:
        rows = dataset.rows(S.FEATURE)
    except Exception:
        return ()
    by_id = {o.observation_id: o for o in observations}
    groups = {}
    overall_known = 0
    overall_wins = 0
    for row in rows:
        obs = by_id.get(row.observation_id)
        if obs is None:
            continue
        result = (obs.result or "").upper()
        if result == "WIN":
            overall_wins += 1
        if result in ("WIN", "LOSS"):
            overall_known += 1
        if result not in ("WIN", "LOSS"):
            continue
        for name, value in (row.kv or {}).items():
            key = "%s~%s" % (name, value)
            g = groups.setdefault(key, {
                "feature": name, "value": value, "n": 0,
                "wins": 0, "rs": [],
            })
            g["n"] += 1
            if result == "WIN":
                g["wins"] += 1
            if obs.r is not None:
                g["rs"].append(obs.r)
    overall_win = (
        overall_wins / overall_known if overall_known else None
    )
    splits = []
    for key in sorted(groups):
        g = groups[key]
        if g["n"] < min_n_gate:
            continue
        win_rate = g["wins"] / g["n"]
        avg_r = sum(g["rs"]) / len(g["rs"]) if g["rs"] else None
        splits.append(FeatureSplit(
            feature=g["feature"],
            value=g["value"],
            n=g["n"],
            win_rate=win_rate,
            avg_r=avg_r,
            overall_win_rate=overall_win,
            effect_h=effect_size_h(
                win_rate, overall_win) if overall_win is not None else None,
            min_n_gate=min_n_gate,
        ))
    return tuple(splits)