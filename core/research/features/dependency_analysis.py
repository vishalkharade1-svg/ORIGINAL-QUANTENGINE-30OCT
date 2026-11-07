"""
====================================================

QuantEngine

Feature Evidence -- dependency analysis (Phase 9F)

READ-ONLY, deterministic evidence tables that join each
opportunity's FeatureSnapshot to its already-labelled outcome (from
9D / 9C facts) and report, per feature value, how the outcome varies:

   * entry_reached rate
   * recovered rate (rejected / unfilled opportunity that a
     candidate experiment then filled) -- where recovery evidence is
     supplied
   * missed-continuation share
   * WIN / LOSS / unsettled rates
   * average R, average MAE, average MFE
   * segmented by direction and by symbol

This is CORRELATION OF EVIDENCE, never causation, never ML, and it
never fabricates an outcome when no outcome evidence exists for an
opportunity. Feature buckets with zero known outcomes are omitted.
====================================================
"""

UNAVAILABLE = None


# ------------------------------------------------------------------
# Outcome accessors (tolerate full objects or dicts; read-only).
# ------------------------------------------------------------------


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _label_outcome(outcome):
    """Deterministic outcome label for a 9C CounterfactualOutcome."""
    if outcome is None:
        return None, None
    result = _field(outcome, "result", "") or ""
    entry_reached = bool(_field(outcome, "entry_reached", False))
    category = (_field(outcome, "category", "") or "").upper()
    if result in ("WIN", "LOSS"):
        return result, entry_reached
    if category and result not in ("WIN", "LOSS"):
        # a filled-but-unresolved or categorical outcome
        return result or None, entry_reached
    return None, entry_reached


# ------------------------------------------------------------------
# One feature's dependency table.
# ------------------------------------------------------------------


class FeatureDependency:
    """Deterministic per-feature, per-value outcome table."""

    def __init__(self, name, rows):
        self.name = name
        self.rows = rows  # list of dicts, value -> metrics

    def by_value(self, value):
        for row in self.rows:
            if row["value"] == value:
                return row
        return None

    def to_dict(self):
        return {
            "feature": self.name,
            "rows": self.rows,
        }


class DependencyAnalysis:
    """Container of per-feature tables + an overall coverage header."""

    def __init__(self, features, opportunity_count, evidence_method,
                 segmented):
        self.features = features
        self.opportunity_count = opportunity_count
        self.evidence_method = evidence_method
        self.segmented = segmented

    def for_feature(self, name):
        for f in self.features:
            if f.name == name:
                return f
        return None

    def to_dict(self):
        return {
            "opportunity_count": self.opportunity_count,
            "evidence_method": self.evidence_method,
            "segmented": self.segmented,
            "features": [f.to_dict() for f in self.features],
        }


# ------------------------------------------------------------------
# Builders
# ------------------------------------------------------------------


def _bucket_summary(values):
    n = len(values)
    if n == 0:
        return {}
    wins = sum(1 for v in values if v == "WIN")
    losses = sum(1 for v in values if v == "LOSS")
    unsettled = n - wins - losses
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "unsettled": unsettled,
        "win_rate": (wins / n) if n else 0.0,
    }


def build_dependency(
    snapshots,
    outcomes_by_opportunity,
    feature_names=None,
    recoveries_by_opportunity=None,
):
    """Deterministic DependencyAnalysis.

    snapshots:              iterable of FeatureSnapshot.
    outcomes_by_opportunity: {opportunity_id: outcome} (9C / dict).
    feature_names:          optional whitelist of feature names.
    recoveries_by_opportunity: {opportunity_id: recovered_bool} --
        marks whether a rejected / unfilled opportunity was recovered
        by a candidate experiment (protocol-recovery evidence).
    """
    snapshots = list(snapshots)
    feature_order = {}
    if feature_names:
        feature_order = {name: k for k, name in enumerate(feature_names)}

    # collate buckets: feature -> (value -> [label, entry_reached,
    # r, mae, mfe, direction, instrument, recovered])
    tables = {}
    for snap in snapshots:
        oid = snap.opportunity_id
        outcome = outcomes_by_opportunity.get(oid)
        label, entry_reached = _label_outcome(outcome)
        r = _num(_field(outcome, "r"))
        mae = _num(_field(outcome, "mae"))
        mfe = _num(_field(outcome, "mfe"))
        category = (_field(outcome, "category", "") or "").upper()
        recovered = bool(
            (recoveries_by_opportunity or {}).get(oid, False)
        ) or bool(_field(outcome, "recovered", False))

        for name, value in snap.features.items():
            if feature_names and name not in feature_order:
                continue
            bucket = tables.setdefault(name, {})
            row = bucket.setdefault(value, {
                "n": 0, "labels": [],
                "entry_reached_count": 0, "entry_reached_known": 0,
                "recovered_count": 0, "recovered_known": 0,
                "r": [], "mae": [], "mfe": [],
                "directions": {}, "instruments": {},
                "missed_continuation_count": 0,
            })
            row["n"] += 1
            if entry_reached is not None:
                row["entry_reached_known"] += 1
                if entry_reached:
                    row["entry_reached_count"] += 1
            if recovered is not None:
                row["recovered_known"] += 1
                if recovered:
                    row["recovered_count"] += 1
            if label:
                row["labels"].append(label)
            if r is not None:
                row["r"].append(r)
            if mae is not None:
                row["mae"].append(mae)
            if mfe is not None:
                row["mfe"].append(mfe)
            direction = (snap.direction or "").upper()
            if direction:
                row["directions"][direction] = row["directions"].get(direction, 0) + 1
            instrument = snap.instrument_id or ""
            if instrument:
                row["instruments"][instrument] = row["instruments"].get(instrument, 0) + 1
            if category.startswith("MISSED_CONTINUATION") or category == "EXPIRED":
                row["missed_continuation_count"] += 1

    # build deterministic per-feature tables
    feature_list = []
    for name in sorted(tables.keys(), key=lambda n: (
        feature_order.get(n, 1e9), n,
    )):
        bucket = tables[name]
        rows = []
        for value in sorted(bucket.keys(), key=_value_sort):
            row = bucket[value]
            labels = row["labels"]
            summary = _bucket_summary(labels)
            rows.append({
                "value": value,
                "n": row["n"],
                "win_rate": summary.get("win_rate", 0.0),
                "wins": summary.get("wins", 0),
                "losses": summary.get("losses", 0),
                "unsettled": summary.get("unsettled", 0),
                "entry_reached_rate": (
                    row["entry_reached_count"] / row["entry_reached_known"]
                    if row["entry_reached_known"] else None
                ),
                "recovered_rate": (
                    row["recovered_count"] / row["recovered_known"]
                    if row["recovered_known"] else None
                ),
                "missed_continuation_count": row["missed_continuation_count"],
                "avg_R": _avg(row["r"]),
                "avg_MAE": _avg(row["mae"]),
                "avg_MFE": _avg(row["mfe"]),
                "directions": dict(row["directions"]),
                "instruments": dict(row["instruments"]),
            })
        feature_list.append(FeatureDependency(name, rows))

    return DependencyAnalysis(
        features=feature_list,
        opportunity_count=len(snapshots),
        evidence_method="read_only_evidence_correlation",
        segmented=True,
    )


# ------------------------------------------------------------------


def _value_sort(value):
    if isinstance(value, bool):
        return (0, 0, int(value))
    if isinstance(value, (int, float)):
        return (1, 0, float(value))
    return (2, 1, str(value))


def _avg(seq):
    if not seq:
        return None
    return round(sum(seq) / len(seq), 6)