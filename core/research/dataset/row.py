"""
====================================================

QuantEngine

Unified Research Dataset -- row model & sources (Phase 9I)

The row model for the Research Knowledge & Data Intelligence
layer: one normalized, deterministic "research fact" that can be
fed from ANY of the frozen 9A-9H surfaces (journal records,
counterfactual outcomes, 9D analysis, 9E intelligence, 9F feature
evidence, 9G ML/statistical research, 9H autonomous investigations).

A ResearchRow is deliberately CONTENT-NEUTRAL: it carries a stable
deterministic id, a closed source label, an observation/opportunity
join key (where one exists), a small set of typed identity fields
(instrument / direction / timeframe / strategy / decision_bar /
category / result / source_id) used for querying and grouping, and two
evidence bags:

   * kv        -- descriptive key/value facts (strings, levels,
                  parameters, reasons, features)
   * measured  -- quantitative outcomes (pnl / R / MAE / MFE / bars /
                  recovered flags).

This lets the query layer answer questions 9H itself raises with a
single, uniform surface:

   * "1,000 structurally valid setups -- why only 200 entered?"
   * "of the 800 missed/rejected, which could have been profitable
     if entry model / offset / expiry / RR / confirmation changed?"

Boundaries: pure data -- no imports of production internals, no
ordering, no ledger, no lookahead, no auto-promotion, deterministic
ids only (sha1 over the fully-serialized row, never UUID/timestamp).
====================================================
"""

from dataclasses import dataclass, field, asdict
import hashlib
import json


class DatasetSource:
    """Closed vocabulary of the unified research row sources.
    Each maps to exactly one frozen research surface."""

    JOURNAL = "JOURNAL"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    ANALYSIS = "ANALYSIS"
    INTELLIGENCE = "INTELLIGENCE"
    FEATURE = "FEATURE"
    ML = "ML"
    RESEARCH = "RESEARCH"


SOURCES = (
    DatasetSource.JOURNAL,
    DatasetSource.COUNTERFACTUAL,
    DatasetSource.ANALYSIS,
    DatasetSource.INTELLIGENCE,
    DatasetSource.FEATURE,
    DatasetSource.ML,
    DatasetSource.RESEARCH,
)


def _stable_json(value):
    """Deterministic serialization for id derivation: sort dict keys
    recursively, use a consistent default for non-JSON values."""
    def _norm(v):
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, dict):
            return {str(k): _norm(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [_norm(x) for x in v]
        return str(v)

    return json.dumps(
        _norm(value), sort_keys=True, separators=(",", ": "),
        default=str,
    )


@dataclass(frozen=True)
class ResearchRow:
    """One normalized research fact unified across 9A-9H."""

    source: str
    row_id: str = ""
    observation_id: str = ""
    instrument_id: str = ""
    direction: str = ""
    timeframe: str = ""
    strategy: str = ""
    decision_bar: object = None
    category: str = ""
    result: str = ""
    source_id: str = ""
    kv: dict = field(default_factory=dict)
    measured: dict = field(default_factory=dict)

    def _id_content(self):
        return _stable_json({
            "source": self.source,
            "observation_id": self.observation_id,
            "instrument_id": self.instrument_id,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "strategy": self.strategy,
            "decision_bar": self.decision_bar,
            "category": self.category,
            "result": self.result,
            "source_id": self.source_id,
            "kv": dict(self.kv),
            "measured": dict(self.measured),
        })

    def __post_init__(self):
        if not self.row_id:
            digest = hashlib.sha1(
                self._id_content().encode("utf-8")
            ).hexdigest()[:10]
            object.__setattr__(self, "row_id", f"I-{digest}")

    def to_dict(self):
        return {
            "source": self.source,
            "row_id": self.row_id,
            "observation_id": self.observation_id,
            "instrument_id": self.instrument_id,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "strategy": self.strategy,
            "decision_bar": self.decision_bar,
            "category": self.category,
            "result": self.result,
            "source_id": self.source_id,
            "kv": dict(self.kv),
            "measured": dict(self.measured),
        }


def row_from_dict(data):
    """Rebuild a ResearchRow from a to_dict() payload (idempotent)."""
    return ResearchRow(
        source=data.get("source", ""),
        row_id=data.get("row_id", ""),
        observation_id=data.get("observation_id", ""),
        instrument_id=data.get("instrument_id", ""),
        direction=data.get("direction", ""),
        timeframe=data.get("timeframe", ""),
        strategy=data.get("strategy", ""),
        decision_bar=data.get("decision_bar"),
        category=data.get("category", ""),
        result=data.get("result", ""),
        source_id=data.get("source_id", ""),
        kv=dict(data.get("kv", {})),
        measured=dict(data.get("measured", {})),
    )
