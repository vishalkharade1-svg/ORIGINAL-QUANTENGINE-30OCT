"""
====================================================

QuantEngine

Research Intelligence -- directional / symbol analysis (Phase 9E)

Deterministic per-direction (BULLISH / BEARISH) and per-symbol
decomposition of an experiment's evidence, using ONLY the grouped
metrics already produced by 9D (`group_metrics`) -- never
resimulated, never invented.

Because Phase 7E rejected the bullish-weak / bearish-strong
hypothesis on real OOS BTCUSDT data, this layer NEVER emits a
directional PRODUCTION rule. It only reports whether an apparent
improvement is broad, direction-specific or symbol-specific, and
flags directional imbalance as a warning (via 9D robustness) so the
reader can weigh it as research evidence only.
====================================================
"""

from core.research.intelligence.parameter_insights import parameter_insights

DIRECTIONS = ("BULLISH", "BEARISH")

_MIN_CELL = 5


def _bucketed(metrics, key):
    """Return a flat {label: metrics} map from a 9D grouped dict."""
    if not metrics:
        return {}
    return metrics.get(key, {})


def directional_breakdown(bundles):
    """Per-experiment directional metrics + insight flags.

    bundles: list of (experiment_id, directional {'ALL':.., 'BULLISH':
    .., 'BEARISH':..}, robustness_warnings).
    Returns a dict keyed by experiment_id.
    """
    out = {}
    for exp_id, directional, robustness in bundles:
        entries = {}
        for direction in DIRECTIONS:
            sub = directional.get(direction)
            if sub is None:
                continue
            sample = sub.get("settled", 0)
            entries[direction] = {
                "sample_size": sample,
                "filled": sub.get("filled", 0),
                "wins": sub.get("wins", 0),
                "losses": sub.get("losses", 0),
                "expectancy": sub.get("expectancy", 0.0),
                "total_R": sub.get("total_R", 0.0),
                "win_rate": sub.get("win_rate", 0.0),
                "avg_MAE": sub.get("avg_MAE", 0.0),
                "avg_MFE": sub.get("avg_MFE", 0.0),
                "insufficient_sample": sample < _MIN_CELL,
            }
        out[exp_id] = {
            "directions": entries,
            "directional_imbalance_flag": any(
                "directional imbalance" in w.lower() for w in robustness
            ),
        }
    return out


def symbol_breakdown(experiment_id, symbol_metrics, experiment_metrics):
    """Flag whether an experiment's advantage is broad or
    symbol-specific.

    symbol_metrics:  9D grouped metrics by instrument_id.
    experiment_metrics: the experiment's ALL metrics.
    Returns a deterministic dict naming symbols with a positive
    expectancy and the fraction of population they cover.
    """
    if not symbol_metrics:
        return {
            "experiment_id": experiment_id,
            "symbol_count": 0,
            "positive_symbols": [],
            "broad": False,
            "note": "no symbol breakdown available",
        }
    total_filled = experiment_metrics.get("filled", 0) or 1
    positive = []
    broad = True
    for sym, m in symbol_metrics.items():
        filled = m.get("filled", 0)
        if filled == 0:
            broad = False
            continue
        positive.append({
            "symbol": sym,
            "filled": filled,
            "expectancy": m.get("expectancy", 0.0),
            "total_R": m.get("total_R", 0.0),
            "share": filled / total_filled,
        })
    positive.sort(key=lambda r: (r["symbol"],))
    total_positive_share = sum(r["share"] for r in positive)
    broad = total_positive_share >= 0.8 and all(
        r["expectancy"] >= 0 for r in positive
    )
    return {
        "experiment_id": experiment_id,
        "symbol_count": len(symbol_metrics),
        "positive_symbols": positive,
        "positive_filled_share": total_positive_share,
        "broad": broad,
        "note": "" if broad else "advantage may be symbol-specific",
    }


def direction_insight_row(experiment_id, directional_breakdown_by_id):
    """A stable research note per direction for a given experiment."""
    exp = directional_breakdown_by_id.get(experiment_id, {})
    rows = []
    for direction in DIRECTIONS:
        entry = exp.get("directions", {}).get(direction)
        if entry is None:
            rows.append({
                "experiment_id": experiment_id,
                "direction": direction,
                "available": False,
            })
            continue
        rows.append({
            "experiment_id": experiment_id,
            "direction": direction,
            "available": True,
            "sample_size": entry["sample_size"],
            "filled": entry["filled"],
            "wins": entry["wins"],
            "losses": entry["losses"],
            "expectancy": entry["expectancy"],
            "total_R": entry["total_R"],
            "win_rate": entry["win_rate"],
            "insufficient_sample": entry["insufficient_sample"],
        })
    return rows