"""
====================================================

QuantEngine

ML / Statistical Research -- feature-interaction analysis (Phase 9G)

9G.3 -- deterministic ASSOCIATION tables over combinations of feature
values (e.g. Wyckoff=SPRING + FVG=PRESENT + OB=PRESENT + Fibonacci=
0.618 + volatility=NORMAL + liquidity_sweep=TRUE) joined to the
already-labelled 9F FeatureSnapshot / 9C outcomes.

Each combination is reported as a bundle with:
   ENTRY_REACHED rate, WIN rate, avg R, avg MAE, avg MFE, sample.

The engine is EXPLICIT and strict about vocabulary: this is
ASSOCIATION, NOT causation, and never a trade decision. Combinations
with a tiny / zero labelled sample are reported honestly (rate=None,
not fabricated).

To keep the analysis tractable and honest, only combinations that
actually OCCUR in the supplied snapshots (with the given features
present) are reported -- absent combinations are simply not listed.
====================================================
"""


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _result(row):
    if isinstance(row, dict):
        return (row.get("result") or "").upper()
    return (getattr(row, "result", "") or "").upper()


def interaction_analysis(snapshots, outcomes, features, min_sample=1):
    """Deterministic association table over feature-value combos.

    snapshots: iterable of 9F FeatureSnapshot (features dict + id).
    outcomes:  {opportunity_id: 9C outcome} labelled evidence.
    features:  ordered feature names to combine (subset of snapshot
               features). Combinations are built from the values
               present in each snapshot.
    min_sample: combos with fewer labelled rows are still listed with
               honest None rates (never fabricated), but a
               'sufficient_sample' flag marks >= min_sample.

    Returns a deterministic list of bundle dicts sorted by (combo
    key); each row:
       {key, combo, n, entry_reached_rate, win_rate, avg_R, avg_MAE,
        avg_MFE, sufficient_sample}
    """
    snapshots = list(snapshots)
    features = list(features)
    bundles = {}
    for snap in snapshots:
        feats = snap.features if isinstance(snap.features, dict) else {}
        oid = snap.opportunity_id
        outcome = outcomes.get(oid)
        result = _result(outcome) if outcome is not None else ""
        r = _num(_field(outcome, "r")) if outcome is not None else None
        mae = _num(_field(outcome, "mae")) if outcome is not None else None
        mfe = _num(_field(outcome, "mfe")) if outcome is not None else None
        er = (_field(outcome, "entry_reached")
              if outcome is not None else None)

        # build the combo from the requested features that are present
        combo = []
        complete = True
        for name in features:
            if name in feats and feats[name] is not None:
                combo.append((name, feats[name]))
            else:
                complete = False
        if not complete or not combo:
            # partial/absent combos are not reported (honest)
            continue
        key = " + ".join(f"{n}={v}" for n, v in combo)

        b = bundles.setdefault(key, {
            "combo": combo, "n": 0,
            "entry_reached_count": 0, "entry_reached_known": 0,
            "wins": 0, "known": 0, "r": [], "mae": [], "mfe": [],
        })
        b["n"] += 1
        if er is not None:
            b["entry_reached_known"] += 1
            if bool(er):
                b["entry_reached_count"] += 1
        if result == "WIN":
            b["wins"] += 1
            b["known"] += 1
        elif result == "LOSS":
            b["known"] += 1
        if r is not None and result in ("WIN", "LOSS"):
            b["r"].append(r)
        if mae is not None:
            b["mae"].append(mae)
        if mfe is not None:
            b["mfe"].append(mfe)

    rows = []
    for key in sorted(bundles.keys()):
        b = bundles[key]
        win_rate = (b["wins"] / b["known"] if b["known"] else None)
        entry_rate = (b["entry_reached_count"] / b["entry_reached_known"]
                      if b["entry_reached_known"] else None)
        rows.append({
            "key": key,
            "combo": {n: v for n, v in b["combo"]},
            "n": b["n"],
            "sufficient_sample": b["n"] >= min_sample,
            "entry_reached_rate": entry_rate,
            "win_rate": win_rate,
            "avg_R": (_mean(b["r"]) if b["r"] else None),
            "avg_MAE": (_mean(b["mae"]) if b["mae"] else None),
            "avg_MFE": (_mean(b["mfe"]) if b["mfe"] else None),
        })
    return rows


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def interaction_to_table(rows):
    """Render the association table lines (deterministic)."""
    lines = []
    for r in rows:
        lines.append(
            f"  {r['key']}: n={r['n']} ENTRY_REACHED="
            f"{_pct(r['entry_reached_rate'])} WIN={_pct(r['win_rate'])} "
            f"R={_fmt(r['avg_R'])}" + ("*" if not r["sufficient_sample"] else "")
        )
    return lines


def _pct(x):
    if x is None:
        return "n/a"
    return f"{100.0 * x:.0f}%"


def _fmt(x):
    if x is None:
        return "n/a"
    return f"{x:+.2f}"