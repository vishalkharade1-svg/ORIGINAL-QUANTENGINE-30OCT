"""
====================================================

QuantEngine

Strategy Discovery / Experiment Engine (Phase 9J) -- confluence discovery

Association-only confluence evidence built from OBSERVED decision-time
feature snapshots (9F, collected into the 9I FEATURE rows) crossed with
the observed recovery candidates (9J recovery_discovery).

Guarantees:
   * evidence comes ONLY from FeatureSnapshot rows that actually exist
     in the dataset -- if a feature is unavailable it is reported as
     unavailable, NEVER synthesized;
   * no fabricated simulation parameters, no invented price/volume
     profile, no order-flow assumptions;
   * deterministic bucketing (sorted feature names, deterministic
     value labels) and explicit sample counts on every association.

   confluence_findings(dataset, recovered_ids)
       returns a deterministic report dict:
         feature_availability   -- the feature keys actually present
         associations           -- (feature, value) -> n / recovered /
                                    recovery_rate (research-only)
         interactions           -- deterministic co-occurrence pairs
         status                 -- OBSERVED_ASSOCIATIONS_ONLY
====================================================
"""

from core.research.dataset import DatasetSource as S
from core.research.discovery.discovery_types import stable_json


def feature_availability(dataset):
    """The decision-time feature keys actually present (never guessed)."""
    return tuple(sorted({
        key
        for row in dataset.rows(S.FEATURE)
        for key in (row.kv or {})
    }))


def _value_label(value):
    if value is None:
        return "NONE"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, str)):
        return str(value)
    return stable_json(value)


def _rows_by_observation(dataset):
    by_obs = {}
    for row in dataset.rows(S.FEATURE):
        if row.observation_id:
            by_obs.setdefault(row.observation_id, []).append(row)
    return by_obs


def confluence_findings(dataset, recovered_ids=()):
    """Association tables: observed feature values vs recovery status."""
    recovered = set(recovered_ids or ())
    rows_by_obs = _rows_by_observation(dataset)
    features = feature_availability(dataset)

    # bucket rows by (feature, value)
    buckets = {}
    order = []
    row_refs = {}
    for observation_id, rows in sorted(rows_by_obs.items()):
        for row in rows:
            for key, value in sorted((row.kv or {}).items()):
                label = _value_label(value)
                bucket = (key, label)
                if bucket not in buckets:
                    buckets[bucket] = []
                    order.append(bucket)
                buckets[bucket].append(row)
                row_refs.setdefault(bucket, set()).add(row.row_id)

    associations = []
    for bucket in order:
        key, label = bucket
        members = buckets[bucket]
        obs_ids = {r.observation_id for r in members}
        recovered_count = len(obs_ids & recovered)
        n = len(members)
        rate = (recovered_count / n) if n else 0.0
        strong = n >= 3 and rate >= 0.6
        associations.append({
            "feature": key,
            "value": label,
            "n": n,
            "recovered": recovered_count,
            "recovery_rate": round(rate, 6),
            "evidence": tuple(sorted(row_refs[bucket])),
            "research_note": (
                "association evidence only, never a trade directive"
            ),
        })
    # deterministic ranking: recovered-first, then n, then feature/value
    associations.sort(key=lambda a: (
        -a["recovered"], -a["n"], a["feature"], a["value"],
    ))

    interactions = _interactions(rows_by_obs, recovered, features)

    notes = []
    if not features:
        notes.append(
            "no decision-time FeatureSnapshot evidence available; "
            "confluence associations were NOT fabricated"
        )
    else:
        notes.append(
            "confluence associations derive only from observed "
            "FeatureSnapshot rows (9F); unavailable features stay "
            "unavailable"
        )

    return {
        "feature_availability": list(features),
        "associations": tuple(associations),
        "interactions": tuple(interactions),
        "status": "OBSERVED_ASSOCIATIONS_ONLY",
        "status_reason": (
            "association evidence only; validation requires a later "
            "OOS/research milestone"
        ),
        "notes": tuple(notes),
    }


def _interactions(rows_by_obs, recovered, features):
    """Deterministic observed (feature,value) co-occurrence pairs."""
    obs_rows = [
        (obs_id, sorted((r.kv or {}).items()))
        for obs_id, rows in sorted(rows_by_obs.items())
        for r in rows
    ]
    pairs = {}
    order = []
    for obs_id, kv in obs_rows:
        # only observations with >= 2 features form a pairing evidence
        if len(kv) < 2 or not features:
            continue
        for i, (f1, v1) in enumerate(kv):
            for f2, v2 in kv[i + 1:]:
                pair = (
                    (f1, _value_label(v1)),
                    (f2, _value_label(v2)),
                )
                if pair not in pairs:
                    pairs[pair] = []
                    order.append(pair)
                pairs[pair].append(obs_id)
    interactions = []
    for pair in order:
        obs_ids = pairs[pair]
        recovered_count = len(set(obs_ids) & set(recovered))
        if len(obs_ids) < 2:
            continue
        interactions.append({
            "feature_a": pair[0][0],
            "value_a": pair[0][1],
            "feature_b": pair[1][0],
            "value_b": pair[1][1],
            "n": len(obs_ids),
            "recovered": recovered_count,
            "recovery_rate": round(
                recovered_count / len(obs_ids), 6
            ),
            "evidence": tuple(sorted(set(obs_ids))),
        })
    interactions.sort(key=lambda i: (
        -i["recovered"], -i["n"],
        i["feature_a"], i["value_a"],
        i["feature_b"], i["value_b"],
    ))
    return interactions