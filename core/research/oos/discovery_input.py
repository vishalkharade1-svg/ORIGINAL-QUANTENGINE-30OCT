"""Frozen 9L discovery-input contract (research-only).

Provides the sanctioned bridge from existing 9A OpportunityRecords to a
frozen 9L discovery input. It never invents opportunities, selects findings,
or executes trading logic.
"""
from dataclasses import dataclass, field
import hashlib
import json

from core.research.journal.opportunity_record import OpportunityRecord


class DiscoveryInputError(ValueError):
    pass


def _stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Discovery9LInput:
    dataset_identity: str
    provenance_identity: str
    discovery_boundary: int
    outcome_horizon: int
    symbol_scope: tuple
    opportunity_records: tuple = field(default_factory=tuple)
    input_identity: str = ""

    def __post_init__(self):
        if not self.dataset_identity:
            raise DiscoveryInputError("dataset_identity is required")
        if not self.provenance_identity:
            raise DiscoveryInputError("provenance_identity is required")
        if not isinstance(self.discovery_boundary, int) or self.discovery_boundary < 0:
            raise DiscoveryInputError("discovery_boundary must be a non-negative int")
        if not isinstance(self.outcome_horizon, int) or self.outcome_horizon < 0:
            raise DiscoveryInputError("outcome_horizon must be a non-negative int")
        symbols = tuple(self.symbol_scope)
        if not symbols or any(not isinstance(s, str) or not s for s in symbols):
            raise DiscoveryInputError("symbol_scope must contain explicit symbols")
        if tuple(sorted(set(symbols))) != symbols:
            raise DiscoveryInputError("symbol_scope must be unique and sorted")
        records = tuple(self.opportunity_records)
        if not records:
            raise DiscoveryInputError("empty discovery source is forbidden")
        if any(not isinstance(r, OpportunityRecord) for r in records):
            raise DiscoveryInputError("opportunity_records must be OpportunityRecord instances")
        for r in records:
            if r.instrument_id not in symbols:
                raise DiscoveryInputError("opportunity symbol outside symbol_scope")
            bar = _decision_bar(r)
            if bar is None:
                raise DiscoveryInputError("opportunity lacks an explicit decision bar")
            if bar >= self.discovery_boundary:
                raise DiscoveryInputError("post-boundary opportunity cannot enter discovery input")
            if self.outcome_horizon and bar + self.outcome_horizon >= self.discovery_boundary:
                raise DiscoveryInputError("outcome horizon crosses discovery boundary")
        expected = self._expected_identity()
        if self.input_identity and self.input_identity != expected:
            raise DiscoveryInputError("input_identity mismatch")
        object.__setattr__(self, "input_identity", expected)

    def _payload(self):
        return {
            "dataset_identity": self.dataset_identity,
            "provenance_identity": self.provenance_identity,
            "discovery_boundary": self.discovery_boundary,
            "outcome_horizon": self.outcome_horizon,
            "symbol_scope": list(self.symbol_scope),
            "opportunity_records": [r.to_dict() for r in self.opportunity_records],
        }

    def _expected_identity(self):
        return hashlib.sha256(_stable(self._payload()).encode()).hexdigest()

    def to_dict(self):
        return dict(self._payload(), input_identity=self.input_identity)


def _decision_bar(record):
    setup = record.setup or {}
    bar = setup.get("bar")
    if isinstance(bar, int):
        return bar
    if isinstance(record.hub_timestamp, int):
        return record.hub_timestamp
    return None


def from_opportunity_records(*, records, dataset_identity, provenance_identity,
                             discovery_boundary, outcome_horizon=0,
                             symbol_scope=None):
    """Build a frozen 9L input from existing 9A records only."""
    records = tuple(records or ())
    if not records:
        raise DiscoveryInputError("empty discovery source is forbidden")
    symbols = tuple(sorted(set(symbol_scope or [r.instrument_id for r in records])))
    if any(not s for s in symbols):
        raise DiscoveryInputError("all opportunities require explicit symbol metadata")
    seen = set()
    for r in records:
        key = (r.instrument_id, _decision_bar(r))
        if key in seen:
            raise DiscoveryInputError("duplicate opportunity decision point")
        seen.add(key)
    ordered = tuple(sorted(records, key=lambda r: (r.instrument_id, _decision_bar(r), r.canonical_id)))
    return Discovery9LInput(
        dataset_identity=dataset_identity,
        provenance_identity=provenance_identity,
        discovery_boundary=discovery_boundary,
        outcome_horizon=outcome_horizon,
        symbol_scope=symbols,
        opportunity_records=ordered,
    )
