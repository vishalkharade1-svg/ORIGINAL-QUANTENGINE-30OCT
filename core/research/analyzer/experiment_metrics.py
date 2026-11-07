"""
====================================================

QuantEngine

Research Analyzer -- deterministic metrics (Phase 9D)

The metric bundle the 9D report/analyzer surface. It reuses the
frozen 9B lab.metrics formulas (WIN := pnl>=0, profit factor :=
gross profit / gross loss, expectancy := avg pnl, drawdown over an
ordered equity curve) -- never duplicating them -- and augments with
the deterministic fields the research questions need:

   total / average / median R, gross Profit-R / gross Loss-R,
   average / median MAE and MFE, average / median bars-to-entry.

The same `metrics_for` is applied to BASELINE views and EXPERIMENT
outcomes so baseline vs counterfactual compare like-for-like.

Deterministic contract:
   * zero denominators yield 0.0
   * PF with gross_loss==0 mirrors 9B (inf when gross_profit > 0,
     else 0.0) -- never NaN
   * MAE / MFE of None are excluded, never invented
   * inputs are treated as read-only
====================================================
"""

from statistics import median

from core.research.lab.metrics import metrics as _lab_metrics

_SETTLED = ("WIN", "LOSS")


def _avg(values):
    return (sum(values) / len(values)) if values else 0.0


def _med(values):
    return median(values) if values else 0.0


def metrics_for(items):
    """Deterministic metric bundle over baseline views OR experiment
    outcomes (any object exposing the outcome surface)."""
    items = list(items)
    base = _lab_metrics(items)

    n = len(items)
    filled = sum(1 for it in items if getattr(it, "filled", False))
    settled = base["settled"]

    rs = [it.r for it in items if getattr(it, "result", "") in _SETTLED]
    gross_profit_r = sum(r for r in rs if r >= 0)
    gross_loss_r = abs(sum(r for r in rs if r < 0))

    maes = [
        it.mae
        for it in items
        if getattr(it, "result", "") in _SETTLED and getattr(it, "mae", None) is not None
    ]
    mfes = [
        it.mfe
        for it in items
        if getattr(it, "result", "") in _SETTLED and getattr(it, "mfe", None) is not None
    ]
    entry_bars = [
        it.bars_to_entry
        for it in items
        if getattr(it, "filled", False)
        and getattr(it, "bars_to_entry", None) is not None
    ]

    return {
        # population
        "opportunities": n,
        "evaluated": n,
        "filled": filled,
        "unfilled": n - filled,
        "settled": settled,
        "wins": base["wins"],
        "losses": base["losses"],
        "unsettled": base["unsettled"],
        # PnL / R fundamentals (formula parity with 9B / production)
        "win_rate": base["win_rate"],
        "profit_factor": base["profit_factor"],
        "expectancy": base["expectancy"],
        "net_pnl": base["net_pnl"],
        "gross_profit": base["gross_profit"],
        "gross_loss": base["gross_loss"],
        "total_R": base["total_R"],
        "avg_R": base["avg_R"],
        "median_R": base["median_R"],
        "gross_profit_R": gross_profit_r,
        "gross_loss_R": gross_loss_r,
        # adverse / favourable excursion (excludes None facts)
        "avg_MAE": _avg(maes),
        "median_MAE": _med(maes),
        "avg_MFE": _avg(mfes),
        "median_MFE": _med(mfes),
        # timing
        "avg_bars_to_entry": _avg(entry_bars),
        "median_bars_to_entry": _med(entry_bars),
        "avg_holding_bars": base["avg_holding_bars"],
        "max_drawdown": base["max_drawdown"],
    }


def _group_value(item, key):
    """Deterministic group-key value for an outcome / baseline view."""
    if key == "experiment_id":
        val = getattr(item, "experiment_id", "") or ""
        return val or "BASELINE"
    if key == "entry_model":
        cfg = getattr(item, "config", None)
        if cfg is not None:
            return getattr(cfg, "entry_model", "") or "UNKNOWN"
        val = getattr(item, "entry_model", "") or ""
        return val or "BASELINE"
    if key in ("direction", "exchange", "instrument_id", "timeframe",
               "strategy", "category"):
        val = getattr(item, key, "") or ""
        if key == "direction":
            val = val.upper()
        return val or "UNKNOWN"
    raise KeyError(f"Unsupported group dimension: {key!r}")


def group_sizes(items, key):
    """Deterministic {group_value: count} for a dimension."""
    counts = {}
    for it in items:
        try:
            g = _group_value(it, key)
        except KeyError:
            g = "UNKNOWN"
        counts[g] = counts.get(g, 0) + 1
    return {k: counts[k] for k in sorted(counts)}


def group_metrics(items, keys):
    """Nested {dimension: {group_value: metrics}} for one or many
    dimensions. Group order is sorted for determinism; reads only."""
    if isinstance(keys, str):
        keys = [keys]
    result = {}
    for key in keys:
        buckets = {}
        for it in items:
            try:
                g = _group_value(it, key)
            except KeyError:
                g = "UNKNOWN"
            buckets.setdefault(g, []).append(it)
        result[key] = {
            g: metrics_for(group) for g, group in sorted(buckets.items())
        }
    return result