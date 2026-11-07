"""
====================================================

QuantEngine

ML / Statistical Research -- orchestrator (Phase 9G)

`MlAnalyzer` is the driver of the 9G ML / statistical research layer.
It consumes the 9F FeatureEvidenceReport (decision-time FeatureSnapshots
+ outcomes + dependency tables) and produces an immutable
`MlResearchReport` containing:

   * a chronological dataset split (TRAIN | VALIDATION | OOS, no
     temporal leakage) and an expanding-window walk-forward
   * 9G.1 statistical baselines (win rate, expectancy, avg R, avg
     MAE / MFE, R distribution, effect sizes, conditional
     probabilities)
   * 9G.2 simple-ML baselines (numpy logistic / decision tree -- and
     sklearn when installed) fit CHRONOLOGICALLY on TRAIN and scored
     on VALIDATION / OOS by AUC; target encoders ENTRY_REACHED / WIN /
     POSITIVE_R / EXPECTED_R / RECOVERY_SUCCESS
   * 9G.3 feature-interaction association tables
   * FIRST-CLASS OPPORTUNITY RECOVERY RESEARCH: rejected /
     not-reached opportunities -> feature snapshot -> alternative
     entry / RR / expiry / model -> recovery probability + expected
     R / MAE / MFE
   * a standing reminder that everything here is ASSOCIATION, never
     causation, never a production trade directive.

Dependency isolation: the report is computable with sklearn ABSENT
(numpy-backend); every sklearn call is guarded and degrades to
ML_BACKEND_UNAVAILABLE gracefully -- the production / paper engine is
never coupled to an ML dependency.
====================================================
"""

from dataclasses import dataclass, field

from core.research.ml.split import (
    temporal_split,
    walk_forward,
)
from core.research.ml.statistics import (
    StatisticalBaseline,
    conditional_statistics,
    effect_size_d,
    effect_size_h,
)
from core.research.ml.models import (
    encode_target,
    SimpleModel,
    auc,
    ml_backend_status,
    ML_BACKEND_UNAVAILABLE,
)
from core.research.ml.interaction import (
    interaction_analysis,
)


TARGETS = ("ENTRY_REACHED", "WIN", "POSITIVE_R", "EXPECTED_R",
           "RECOVERY_SUCCESS")


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _result(row):
    if isinstance(row, dict):
        return (row.get("result") or "").upper()
    return (getattr(row, "result", "") or "").upper()


def _label_rows(outcomes):
    """Normalise 9C outcome-like rows into dicts for stats models."""
    rows = []
    for o in outcomes:
        if isinstance(o, dict):
            rows.append(dict(o))
        elif o is not None:
            rows.append({
                "result": getattr(o, "result", ""),
                "r": getattr(o, "r", None),
                "mae": getattr(o, "mae", None),
                "mfe": getattr(o, "mfe", None),
                "entry_reached": getattr(o, "entry_reached", None),
                "recovered": getattr(o, "recovered", False),
            })
    return rows


class MlAnalyzer:
    """Deterministic MNL/statistical research driver."""

    def __init__(self, backend="auto", model_kind="LOGISTIC"):
        # 'auto' -> sklearn when present else numpy; explicit backend
        # can force 'numpy' for determinism / isolation tests.
        self.backend = backend
        self.model_kind = model_kind

    def _resolve_backend(self):
        if self.backend == "auto":
            from core.research.ml.models import _HAS_SKLEARN
            return "sklearn" if _HAS_SKLEARN else "numpy"
        return self.backend

    # -------------------------------------------------

    def analyze(self, report, outcomes=None, features=None,
                recovery_rows=None, min_combo_sample=1,
                recovery_alt=None):
        """Produce an MlResearchReport over a 9F FeatureEvidenceReport.

        report:       a 9F report exposing .snapshots (tuple of
                      FeatureSnapshot with .opportunity_id, .direction,
                      .instrument_id, .features, .decision_bar) and
                      optionally .dependency / .confluence.
        outcomes:     optional {opportunity_id: outcome} to OVERRIDE
                      (defaults to the rows built from snapshots; if
                      the report carries no outcomes, callers supply).
        features:     ordered feature names for interaction analysis.
        recovery_rows: optional iterable of recovered-outcome rows for
                      RECOVERY_SUCCESS modelling.
        recovery_alt: optional {opportunity_id: alt_strategy_dict}
                      recording WHAT alternative was proposed for a
                      recovery candidate (entry/RR/expiry/model).
        """
        snapshots = list(report.snapshots)
        if outcomes is None:
            outcomes = {}
        # chronological split over snapshots by decision_bar
        split = temporal_split(snapshots, validation_fraction=0.2,
                               oos_fraction=0.2)
        wf = walk_forward(snapshots, train_size=0.5, step=0.25)

        # ---- 9G.1 statistical baseline over all settled outcomes ----
        all_outcomes = [outcomes.get(s.opportunity_id) for s in snapshots
                        if outcomes.get(s.opportunity_id) is not None]
        baseline = StatisticalBaseline(
            name="ALL", rows=_label_rows(all_outcomes),
            category="ALL",
        )

        # ---- 9G.1 conditional probabilities per feature ----
        cond = {}
        feats = features or _feature_names(snapshots)
        for name in feats:
            cond[name] = conditional_statistics(
                all_outcomes,
                feature_accessor=lambda row, _n=name: _feature_for(
                    snapshots, outcomes, row, _n),
                label_accessor=lambda row: _result(row),
                target="WIN",
            )

        # ---- 9G.2 simple-ML baselines (chronological) ----
        ml_results = self._run_models(snapshots, outcomes, split, recovery_rows)

        # ---- 9G.3 interaction association tables ----
        interaction = interaction_analysis(
            snapshots, outcomes, feats, min_sample=min_combo_sample)

        # ---- opportunity recovery research (first-class) ----
        recovery = self._recovery_research(
            snapshots, outcomes, recovery_rows, recovery_alt)

        return MlResearchReport(
            snapshots=tuple(snapshots),
            split=split,
            walk_forward=wf,
            baseline=baseline,
            conditional=cond,
            ml_results=ml_results,
            interaction=interaction,
            recovery=recovery,
            backend=self._resolve_backend(),
            features=tuple(feats),
        )

    # -------------------------------------------------

    def _run_models(self, snapshots, outcomes, split, recovery_rows):
        backend = self._resolve_backend()
        if (backend == "sklearn"
                and not _sklearn_available()):
            backend = "numpy"

        resolved = {}
        # per-target feature matrix from snapshot features (the values
        # that are numeric; nominal are one-hot'd with a fixed index).
        rows_by_id = {s.opportunity_id: s for s in snapshots}
        order_ids = [s.opportunity_id for s in snapshots]
        order_map = {oid: i for i, oid in enumerate(order_ids)}
        feature_names = _feature_names(snapshots)

        train_idx = list(split.train.indices)
        val_idx = list(split.validation.indices)
        oos_idx = list(split.oos.indices)
        # Phase-8 leakage correction: the matrix encoding is fit on
        # training snapshots only; validation/OOS rows (including any
        # unseen nominal values) transform into the fixed train
        # encoding and can never alter it.
        train_encoding = _fit_encoding(
            [snapshots[i] for i in train_idx], feature_names)
        X_full = _transform_matrix(snapshots, train_encoding)

        for target in TARGETS:
            labels, mask = encode_target(
                [outcomes.get(o) for o in order_ids], target)
            # restrict to masked (labelled) rows
            if sum(mask) < 4:
                resolved[target] = {
                    "target": target,
                    "backend": backend,
                    "status": "INSUFFICIENT_LABELS",
                    "auc_validation": None,
                    "auc_oos": None,
                }
                continue
            if not train_idx or not (val_idx or oos_idx):
                resolved[target] = {
                    "target": target,
                    "backend": backend,
                    "status": "INSUFFICIENT_SPLIT",
                    "auc_validation": None,
                    "auc_oos": None,
                }
                continue
            model = SimpleModel(kind=self.model_kind, backend=backend,
                                target=target)
            model.fit(
                [X_full[i] for i in train_idx],
                [labels[i] for i in train_idx],
            )
            if not model.trained:
                resolved[target] = {
                    "target": target,
                    "backend": backend,
                    "status": ML_BACKEND_UNAVAILABLE,
                    "auc_validation": None,
                    "auc_oos": None,
                }
                continue
            auc_val = None
            if val_idx:
                pv = model.predict_proba([X_full[i] for i in val_idx])
                if pv is not None:
                    auc_val = auc(
                        [labels[i] for i in val_idx],
                        [float(p) for p in pv],
                    )
            auc_os = None
            if oos_idx:
                po = model.predict_proba([X_full[i] for i in oos_idx])
                if po is not None:
                    auc_os = auc(
                        [labels[i] for i in oos_idx],
                        [float(p) for p in po],
                    )
            resolved[target] = {
                "target": target,
                "backend": backend,
                "status": "TRAINED",
                "auc_validation": auc_val,
                "auc_oos": auc_os,
                "kind": self.model_kind,
            }
        return resolved

    # -------------------------------------------------

    def _recovery_research(self, snapshots, outcomes, recovery_rows,
                           recovery_alt):
        """First-class Opportunity Recovery Prediction research.

        For rejected / not-reached opportunities carrying a feature
        snapshot, join to any recovery evidence:
           recovery probability (share recovered),
           expected R / expected MAE / expected MFE over recovered
           outcomes,
           the alternative entry / RR / expiry / model that was
           proposed (when supplied).
        Emits honest None when no recovery evidence exists for a
        candidate. This is ASSOCIATION of evidence -- not a
        recommendation to trade.
        """
        recovery_alt = recovery_alt or {}
        alt_map = {k: dict(v) for k, v in recovery_alt.items()}
        candidates = []
        for s in snapshots:
            oid = s.opportunity_id
            out = outcomes.get(oid)
            result = _result(out) if out is not None else ""
            category = (_field(out, "category", "") if out is not None
                         else "") or ""
            is_reject = category in (
                "REJECTED", "ENTRY_NOT_REACHED", "MISSED_CONTINUATION",
            ) or result in ("REJECTED", "EXPIRED")
            if not is_reject:
                continue
            candidates.append({
                "opportunity_id": oid,
                "direction": s.direction,
                "instrument_id": s.instrument_id,
                "category": category or "REJECTED",
                "recovered": (bool(_field(out, "recovered", False))
                              if out is not None else False),
                "r": (_field(out, "r") if out is not None else None),
                "mae": (_field(out, "mae") if out is not None else None),
                "mfe": (_field(out, "mfe") if out is not None else None),
                "alternative": alt_map.get(oid),
                "features": dict(s.features),
            })
        if not candidates:
            return []
        recovered = [c for c in candidates if c["recovered"]]
        all_r = [_num(c["r"]) for c in candidates]
        all_r = [x for x in all_r if x is not None]
        return {
            "candidates": candidates,
            "candidate_count": len(candidates),
            "recovered_count": len(recovered),
            "recovery_rate": (len(recovered) / len(candidates)
                              if candidates else None),
            "expected_R": (_mean(all_r) if all_r else None),
            "expected_MAE": (_mean([x for x in
                                   [_num(c["mae"]) for c in candidates]
                                   if x is not None]) or None),
            "expected_MFE": (_mean([x for x in
                                   [_num(c["mfe"]) for c in candidates]
                                   if x is not None]) or None),
            "association_only": True,
            "not_a_trade_directive": True,
        }


# ------------------------------------------------------------------


def _feature_names(snapshots):
    names = []
    for s in snapshots:
        for k in s.features.keys():
            if k not in names:
                names.append(k)
    return names


def _feature_for(snapshots, outcomes, row, name):
    """Find the snapshot for a given outcome row and pull feature."""
    oid = (_field(row, "opportunity_id", "") if isinstance(row, dict)
           else getattr(row, "opportunity_id", ""))
    if not oid:
        # try matching by position not possible; search by id
        return None
    for s in snapshots:
        if s.opportunity_id == oid:
            return s.features.get(name)
    return None


def _fit_encoding(snapshots, feature_names):
    """Fit the matrix encoding on the given snapshots ONLY.

    Phase-8 leakage correction: callers must fit on training
    snapshots, then transform every split with the fitted encoding.
    Future (validation/OOS) rows never alter the encoding; unseen
    nominal values transform to zeros. Returns
    ``(numeric, nominal_values)`` consumed by ``_transform_matrix``.
    """
    numeric = {}
    nominal_values = {}
    for name in feature_names:
        first = None
        for s in snapshots:
            v = s.features.get(name)
            if v is not None:
                first = v
                break
        if isinstance(first, bool) or isinstance(first, (int, float)):
            numeric[name] = True
        else:
            numeric[name] = False
            values = []
            for s in snapshots:
                v = s.features.get(name)
                if v is not None and v not in values:
                    values.append(v)
            nominal_values[name] = values
    return numeric, nominal_values


def _transform_matrix(snapshots, encoding):
    """Transform snapshots with a fitted encoding (fixed columns).

    Rows for unseen nominal values contribute zeros in that
    feature's one-hot block; numeric values pass through as-is
    (NaN/None -> 0.0). Deterministic.
    """
    numeric, nominal_values = encoding
    rows = []
    for s in snapshots:
        vec = []
        feats = s.features
        for name in numeric:
            if numeric[name]:
                v = feats.get(name)
                if isinstance(v, bool):
                    vec.append(1.0 if v else 0.0)
                elif isinstance(v, (int, float)):
                    vec.append(float(v))
                else:
                    vec.append(0.0)
            else:
                for val in nominal_values[name]:
                    vec.append(1.0 if feats.get(name) == val else 0.0)
        rows.append(vec)
    return rows


def _build_matrix(snapshots, order_map, feature_names):
    """Fixed deterministic numeric matrix from snapshot features.

    Legacy joint behavior preserved exactly (fit + transform over the
    supplied snapshots). Model paths must prefer fit-on-train plus
    ``_transform_matrix``; see ``_fit_encoding``.
    """
    return _transform_matrix(snapshots, _fit_encoding(snapshots, feature_names))


def _sklearn_available():
    from core.research.ml import models
    return models._HAS_SKLEARN


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MlResearchReport:
    """Immutable, deterministic output of the 9G ML/statistical layer."""

    snapshots: tuple
    split: object
    walk_forward: object
    baseline: StatisticalBaseline
    conditional: dict
    ml_results: dict
    interaction: list
    recovery: object
    backend: str
    features: tuple

    def to_dict(self):
        return {
            "phase": "9G",
            "backend": self.backend,
            "split": self.split.to_dict(),
            "walk_forward": self.walk_forward.to_dict(),
            "baseline": self.baseline.to_dict(),
            "conditional": {k: v for k, v in self.conditional.items()},
            "ml_results": dict(self.ml_results),
            "interaction": list(self.interaction),
            "recovery": (dict(self.recovery)
                         if isinstance(self.recovery, dict) else None),
            "association_not_causation": True,
            "no_trade_directive": True,
        }

    def render(self):
        lines = [
            "=" * 60,
            "PHASE 9G ML / STATISTICAL RESEARCH (ASSOCIATION ONLY)",
            "=" * 60,
            f"backend: {self.backend}",
            f"opportunities: {len(self.snapshots)}",
            f"split: {self.split.to_dict()}",
            f"baseline: n={self.baseline.n()} win_rate="
            f"{_fmt(self.baseline.win_rate())} avg_R="
            f"{_fmt(self.baseline.avg_R())}",
        ]
        for target, r in self.ml_results.items():
            lines.append(
                f"  ML[{target}]: status={r['status']} "
                f"auc_val={_fmt(r['auc_validation'])} "
                f"auc_oos={_fmt(r['auc_oos'])}"
            )
        if self.interaction:
            lines.append("interaction (association, not causation):")
            for r in self.interaction:
                lines.append(
                    f"  {r['key']}: n={r['n']} WIN={_pct(r['win_rate'])} "
                    f"R={_fmt(r['avg_R'])}"
                )
        if isinstance(self.recovery, dict):
            lines.append(
                f"recovery: n={self.recovery['candidate_count']} "
                f"rate={_fmt(self.recovery['recovery_rate'])}"
            )
        lines.append(
            "Reminder: statistical association ONLY -- never causation, "
            "never a production trade directive."
        )
        return "\n".join(lines)


def _pct(x):
    if x is None:
        return "n/a"
    return f"{100.0 * x:.0f}%"


def _fmt(x):
    if x is None:
        return "n/a"
    return f"{x:+.3f}"