"""
====================================================

QuantEngine

Feature Evidence -- feature analyzer / orchestrator (Phase 9F)

`FeatureAnalyzer` records a deterministic, decision-time FeatureSnapshot
per opportunity (keyed by opportunity/decision bar), derives the
confluence feature map, feeds it into the FROZEN 9E ConfluenceAnalysis
surface (via ConfluenceFeature rows) and joins it to the read-only
9C/9D outcome evidence into DependencyAnalysis tables.

It is STRICTLY research-only:
   * NEVER simulates (production / 9C simulation is untouched),
   * NEVER mutates the 9A OpportunityRecord / 9C outcome / candles,
   * NEVER reads a bar at or after the decision bar (no lookahead),
   * NEVER fabricates an unavailable feature value,
   * produces a ConfluenceAnalysis that correctly reports
     CONFLUENCE_DATA_UNAVAILABLE when zero features could be
     computed -- it never claims confluence that does not exist.

The unique vantage of this phase: the exact feature values that were
observed AT each decision point, preserved immutably, so later 9G
datasets and the eventual AI research layer can study what was true
when each opportunity was (or was not) acted on.
====================================================
"""

from dataclasses import dataclass, field

from core.research.intelligence.confluence_analysis import (
    ConfluenceAnalysis,
    ConfluenceFeature,
)
from core.research.features.causal_window import extract_causal_window
from core.research.features.confluence_features import ALL_PRODUCERS
from core.research.features.feature_snapshot import FeatureSnapshot
from core.research.features.dependency_analysis import (
    DependencyAnalysis,
    build_dependency,
)


def _setup_value(record, key, default=None):
    return (record.setup or {}).get(key, default) if record is not None \
        else default


class FeatureAnalyzer:
    """Records decision-time feature evidence for opportunities."""

    def __init__(self, lookback=20):
        self.lookback = lookback

    # -------------------------------------------------

    def snapshot(self, record, candles):
        """Build a FeatureSnapshot for one OpportunityRecord at its
        decision bar (causal window, decision-time only)."""
        decision_bar = int(_setup_value(record, "bar", 0) or 0)
        direction = (record.direction or "").upper()
        instrument = record.instrument_id or ""
        setup = record.setup or {}
        entry = setup.get("entry")
        stop = setup.get("stop_loss")
        target = setup.get("take_profit")
        atr = setup.get("atr")

        window = extract_causal_window(
            candles, decision_bar, self.lookback,
            direction=direction, instrument_id=instrument,
        )

        features = self._compute_features(window, setup, direction)

        return FeatureSnapshot(
            opportunity_id=record.canonical_id,
            instrument_id=instrument,
            direction=direction,
            timeframe=record.timeframe or "",
            decision_bar=decision_bar,
            window_size=window.size,
            entry=entry,
            stop=stop,
            target=target,
            atr=atr,
            features=features,
        )

    # -------------------------------------------------

    def _compute_features(self, window, setup, direction):
        features = {}
        entry = setup.get("entry")
        stop = setup.get("stop_loss")
        atr = setup.get("atr")

        features["wyckoff_phase"] = _produce("wyckoff_phase", window)
        features["market_structure"] = _produce("market_structure", window)
        features["atr_regime"] = _produce("atr_regime", window, atr)
        features["bollinger_position"] = _produce("bollinger_position", window)
        features["sma_slope"] = _produce("sma_slope", window)
        features["obv_trend"] = _produce("obv_trend", window)
        features["liquidity_sweep"] = _produce(
            "liquidity_sweep", window, stop, direction)
        features["fvg_present"] = _produce("fvg_present", window, direction)
        features["displacement_strength"] = _produce(
            "displacement_strength", window, direction)
        features["order_block"] = _produce("order_block", window)
        features["fibonacci_zone"] = _produce(
            "fibonacci_zone", window, entry, direction)
        # order-flow / volume-profile evidence is UNAVAILABLE here
        # because the OHLCV-only stream cannot support it.
        features["volume_profile"] = _produce("volume_profile", window)
        features["footprint_flow"] = _produce("footprint_flow", window)
        return features

    # -------------------------------------------------

    def analyze(self, records, candles, outcomes=None,
                recoveries=None, feature_names=None):
        """Deterministic FeatureEvidenceReport over the given records.

        records:    iterable of 9A OpportunityRecord.
        candles:    the decision-time candle series.
        outcomes:   optional {opportunity_id: 9C outcome} for
                    dependency evidence.
        recoveries: optional {opportunity_id: recovered_bool}.
        feature_names: optional whitelist.
        """
        records = list(records)
        snapshots = []
        for rec in records:
            try:
                snap = self.snapshot(rec, candles)
            except Exception:
                continue
            snapshots.append(snap)

        dependency = build_dependency(
            snapshots,
            outcomes or {},
            feature_names=feature_names,
            recoveries_by_opportunity=recoveries or {},
        )

        confluence = self._to_confluence(snapshots, records, outcomes or {})

        return FeatureEvidenceReport(
            phase="9F",
            snapshots=tuple(snapshots),
            confluence=confluence,
            dependency=dependency,
            evidence_method="decision_time_causal_features",
        )

    # -------------------------------------------------

    def _to_confluence(self, snapshots, records, outcomes):
        """Aggregate feature-value -> outcome evidence into the FROZEN
        9E ConfluenceFeature rows (one row per feature-value bucket)."""
        feature_rows = {}
        for snap in snapshots:
            for name, value in snap.features.items():
                if value is None:
                    continue  # never fabricate an unavailable feature
                key = (name, value)
                row = feature_rows.setdefault(key, {
                    "sample": 0, "outcomes": {"wins": 0, "losses": 0},
                    "unsettled": 0, "experiment_id": "",
                })
                row["sample"] += 1
                outcome = outcomes.get(snap.opportunity_id)
                result = ""
                if isinstance(outcome, dict):
                    result = outcome.get("result", "") or ""
                elif outcome is not None:
                    result = getattr(outcome, "result", "") or ""
                if result == "WIN":
                    row["outcomes"]["wins"] += 1
                elif result == "LOSS":
                    row["outcomes"]["losses"] += 1
                else:
                    row["unsettled"] += 1

        features = [
            ConfluenceFeature(
                name=name,
                value=value,
                sample=row["sample"],
                outcomes={
                    "wins": row["outcomes"]["wins"],
                    "losses": row["outcomes"]["losses"],
                    "unsettled": row["unsettled"],
                },
                experiment_id=row["experiment_id"],
            )
            for (name, value), row in sorted(
                feature_rows.items(),
                key=lambda kv: (kv[0][0], str(kv[0][1])),
            )
        ]
        return ConfluenceAnalysis(features)


# ------------------------------------------------------------------


def _produce(name, window, *args):
    """Deterministically call a named producer; returns UNAVAILABLE on
    any error (never fabricates)."""
    for fn in ALL_PRODUCERS:
        if fn.__name__ == name:
            try:
                return fn(window, *args)
            except Exception:
                return None
    return None


@dataclass(frozen=True)
class FeatureEvidenceReport:
    """Immutable, deterministic output of the 9F feature layer."""

    phase: str
    snapshots: tuple
    confluence: ConfluenceAnalysis
    dependency: DependencyAnalysis
    evidence_method: str

    def to_dict(self):
        return {
            "phase": "9F",
            "evidence_method": self.evidence_method,
            "confluence": self.confluence.to_dict(),
            "dependency": self.dependency.to_dict(),
            "snapshots": [s.to_dict() for s in self.snapshots],
        }

    def render(self):
        lines = [
            "=" * 60,
            "PHASE 9F FEATURE EVIDENCE",
            "=" * 60,
            f"opportunities: {len(self.snapshots)}",
            f"confluence: {self.confluence.status()}",
            f"evidence method: {self.evidence_method}",
        ]
        for snap in self.snapshots[:5]:
            lines.append(
                f"  {snap.opportunity_id} @bar{snap.decision_bar} "
                f"({snap.available_feature_count()} features)"
            )
        if len(self.snapshots) > 5:
            lines.append(f"  ... {len(self.snapshots) - 5} more")
        lines.append(
            "Reminder: decision-time causal features only; never a "
            "lookahead source; research-only; no production changes."
        )
        return "\n".join(lines)