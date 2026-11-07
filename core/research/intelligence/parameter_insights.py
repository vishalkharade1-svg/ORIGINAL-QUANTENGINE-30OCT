"""
====================================================

QuantEngine

Research Intelligence -- parameter insights (Phase 9E)

Deterministic comparison of experiments that differ along ONE
experiment parameter (rr / expiry / entry_offset / entry_offset_atr /
entry_model / stop_mode / target_mode / outcome_bars). For each
parameter it reports how filled / wins / losses / expectancy /
total_R / MAE / MFE move with each distinct value, using ONLY the
already-computed 9D experiment metrics.

Evidence is reported as MOVES ("higher expectancy", "lower MAE"),
never as "best" / "optimal". Value ordering is deterministic
(numeric ascending first, then string ascending).

Bundles: list of (CounterfactualConfig, metrics_dict, experiment_id).
The bundle's own metrics are compared along the parameter(s) present
in its config; if an explicit `params` list is given, only those are
reported.
====================================================
"""

def _sort_key(value):
    """Deterministic, cross-type sort key (numeric before string)."""
    if isinstance(value, bool):
        return (0, 1, float(value))
    if isinstance(value, (int, float)):
        return (0, 0, float(value))
    return (1, 1, str(value))


def _metric_row(value, metrics, ids):
    m = metrics or {}
    return {
        "value": value,
        "filled": m.get("filled", 0),
        "wins": m.get("wins", 0),
        "losses": m.get("losses", 0),
        "unsettled": m.get("unsettled", 0),
        "expectancy": m.get("expectancy", 0.0),
        "total_R": m.get("total_R", 0.0),
        "net_pnl": m.get("net_pnl", 0.0),
        "avg_MAE": m.get("avg_MAE", 0.0),
        "median_MAE": m.get("median_MAE", 0.0),
        "avg_MFE": m.get("avg_MFE", 0.0),
        "median_MFE": m.get("median_MFE", 0.0),
        "win_rate": m.get("win_rate", 0.0),
        "profit_factor": m.get("profit_factor", 0.0),
        "sample_size": m.get("settled", 0),
        "experiment_ids": sorted(ids),
    }


class ParameterInsight:
    """Deterministic per-parameter comparison across experiments."""

    def __init__(self, param, rows):
        self.param = param
        self.rows = rows

    def to_dict(self):
        return {
            "parameter": self.param,
            "values": [r["value"] for r in self.rows],
            "rows": self.rows,
        }


def _bundle_params(config):
    params = getattr(config, "params", None) or {}
    return {k: v for k, v in params.items() if k != "__order__"}


def parameter_insights(bundles, params=None):
    """Deterministic ParameterInsight per parameter across bundles.

    bundles: list of (CounterfactualConfig, metrics_dict, experiment_id).
    params:  optional explicit parameter list; defaults to the union
             of the experiments' config params. Only params with >1
             distinct value across the bundles are reported as insights.
    """
    if params is None:
        keys = set()
        for config, _m, _id in bundles:
            keys.update(_bundle_params(config).keys())
        keys = sorted(keys)
    else:
        keys = sorted(params)

    insights = []
    for param in keys:
        by_value = {}
        ids_by_value = {}
        for config, metrics, exp_id in bundles:
            params_map = _bundle_params(config)
            if param not in params_map:
                continue
            value = params_map[param]
            if value not in by_value:
                by_value[value] = metrics or {}
            ids_by_value.setdefault(value, []).append(exp_id)
        # only report params that actually VARY across the bundles
        if len(by_value) < 2:
            continue
        values = sorted(by_value.keys(), key=_sort_key)
        rows = [
            _metric_row(v, by_value[v], ids_by_value.get(v, []))
            for v in values
        ]
        insights.append(ParameterInsight(param, rows))
    return insights