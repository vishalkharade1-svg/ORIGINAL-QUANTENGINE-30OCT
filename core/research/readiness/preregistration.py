"""Frozen preregistration for the preregistered OOS execution phase.

Research-only, deterministic, offline. This module creates the
immutable preregistration record that must exist BEFORE any frozen
OOS execution:

    DISCOVERY -> PREREGISTRATION -> READINESS GATES -> FROZEN EXECUTION

Reuse (no duplicate systems):

* hypothesis identity ... ``core.research.oos.oos_types.HypothesisRecord``
  (frozen dataclass; ``hypothesis_id`` / short_id provenance);
* deterministic identity  ``research.phase11g.provenance.model.content_hash``
  (the same stable-hash authority the evidence gates reuse);
* protocol numbers ...... ``core.research.oos.constants`` (6 periods,
  10 trades/period, 60 total -- caller-supplied here, never invented);
* 7E boundary ........... ``core.research.oos.constants.SEVEN_E_NO_GO``.

Rules:

* A preregistration is immutable after creation (frozen dataclass).
  Any altered copy carries a different deterministic identity, so
  ``verify_identity()`` rejects it -- the OOS phase must refuse to
  execute from a non-verifying preregistration.
* A hypothesis with ``seven_e_no_go`` can never be preregistered.
* Parameters, thresholds, symbols, direction, regime conditions and
  boundaries are frozen at creation; changing any of them invalidates
  the preregistration and requires a new research phase.
* ``is_production_ready`` is hard-wired False and can never be True.
* No UUID, no random, no wall-clock, no ``hash()`` in any identity.
"""

from __future__ import annotations

import dataclasses

from core.research.oos import constants as _protocol
from core.research.oos import oos_types as _types
from research.phase11g.provenance.model import content_hash


SCHEMA_VERSION = "1"
ARTIFACT_TYPE = "FROZEN_OOS_PREREGISTRATION"
IDENTITY_ALGORITHM = (
    "content_hash:research.phase11g.provenance.model:"
    "sha256-canonical-json"
)


class PreregistrationError(ValueError):
    """A preregistration is malformed or fails verification."""


def _req_str(value, field):
    if not isinstance(value, str) or not value:
        raise PreregistrationError(
            "%s must be a non-empty str" % field)
    return value


def _req_int(value, field, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int):
        raise PreregistrationError(
            "%s must be int, got %s" % (field, type(value).__name__))
    if value < minimum:
        raise PreregistrationError(
            "%s must be >= %d" % (field, minimum))
    return value


def _req_bool(value, field):
    if not isinstance(value, bool):
        raise PreregistrationError(
            "%s must be bool, got %s" % (field, type(value).__name__))
    return value


def _str_tuple(value, field):
    if not isinstance(value, (tuple, list)):
        raise PreregistrationError(
            "%s must be a tuple/list" % field)
    items = tuple(value)
    for item in items:
        if not isinstance(item, str):
            raise PreregistrationError(
                "%s items must be str" % field)
    return items


@dataclasses.dataclass(frozen=True)
class FrozenPreregistration:
    """Immutable preregistered frozen-OOS experiment definition."""

    schema_version: str
    artifact_type: str
    preregistration_id: str
    identity_algorithm: str
    hypothesis_ids: tuple
    hypotheses: tuple
    dataset_identity: str
    discovery_boundary: int
    oos_boundary: int
    required_period_count: int
    minimum_trades_per_period: int
    minimum_total_trades: int
    minimum_contiguous_bars: int
    minimum_fresh_bars: int
    economics_requirements: tuple
    multiple_testing_family: str
    regime_constraints: tuple
    symbol_constraints: tuple
    directional_constraints: tuple
    frozen_execution_semantics: str
    limitations: tuple
    is_production_ready: bool = False

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise PreregistrationError("schema_version must be %r"
                                       % SCHEMA_VERSION)
        if self.artifact_type != ARTIFACT_TYPE:
            raise PreregistrationError("artifact_type must be %r"
                                       % ARTIFACT_TYPE)
        if self.identity_algorithm != IDENTITY_ALGORITHM:
            raise PreregistrationError("identity_algorithm must be %r"
                                       % IDENTITY_ALGORITHM)
        hypotheses = self.hypotheses
        if not isinstance(hypotheses, (tuple, list)):
            raise PreregistrationError("hypotheses must be a tuple/list")
        hypotheses = tuple(hypotheses)
        object.__setattr__(self, "hypotheses", hypotheses)
        for item in hypotheses:
            if not isinstance(item, _types.HypothesisRecord):
                raise PreregistrationError(
                    "hypotheses must be HypothesisRecord, got %s"
                    % type(item).__name__)
            if item.seven_e_no_go:
                raise PreregistrationError(
                    "seven_e_no_go hypothesis %r can never be "
                    "preregistered" % (item.hypothesis_id or "?"))
        object.__setattr__(self, "hypothesis_ids",
                           _str_tuple(self.hypothesis_ids,
                                      "hypothesis_ids"))
        declared = [h.hypothesis_id for h in hypotheses]
        if any(not hid for hid in declared):
            raise PreregistrationError(
                "every hypothesis must carry a hypothesis_id")
        if len(set(declared)) != len(declared):
            raise PreregistrationError("hypothesis_ids must be unique")
        if tuple(declared) != tuple(self.hypothesis_ids):
            raise PreregistrationError(
                "hypothesis_ids must list the frozen hypotheses "
                "in order")
        _req_str(self.dataset_identity, "dataset_identity")
        object.__setattr__(self, "discovery_boundary",
                           _req_int(self.discovery_boundary,
                                    "discovery_boundary", minimum=0))
        object.__setattr__(self, "oos_boundary",
                           _req_int(self.oos_boundary,
                                    "oos_boundary", minimum=0))
        if self.oos_boundary <= self.discovery_boundary:
            raise PreregistrationError(
                "oos_boundary must be strictly after discovery_boundary")
        object.__setattr__(self, "required_period_count",
                           _req_int(self.required_period_count,
                                    "required_period_count"))
        object.__setattr__(self, "minimum_trades_per_period",
                           _req_int(self.minimum_trades_per_period,
                                    "minimum_trades_per_period"))
        object.__setattr__(self, "minimum_total_trades",
                           _req_int(self.minimum_total_trades,
                                    "minimum_total_trades"))
        object.__setattr__(self, "minimum_contiguous_bars",
                           _req_int(self.minimum_contiguous_bars,
                                    "minimum_contiguous_bars"))
        object.__setattr__(self, "minimum_fresh_bars",
                           _req_int(self.minimum_fresh_bars,
                                    "minimum_fresh_bars"))
        object.__setattr__(self, "economics_requirements",
                           _str_tuple(self.economics_requirements,
                                      "economics_requirements"))
        _req_str(self.multiple_testing_family, "multiple_testing_family")
        object.__setattr__(self, "regime_constraints",
                           _str_tuple(self.regime_constraints,
                                      "regime_constraints"))
        object.__setattr__(self, "symbol_constraints",
                           _str_tuple(self.symbol_constraints,
                                      "symbol_constraints"))
        object.__setattr__(self, "directional_constraints",
                           _str_tuple(self.directional_constraints,
                                      "directional_constraints"))
        _req_str(self.frozen_execution_semantics,
                 "frozen_execution_semantics")
        object.__setattr__(self, "limitations",
                           _str_tuple(self.limitations, "limitations"))
        if self.is_production_ready is not False:
            raise PreregistrationError(
                "is_production_ready must be False")
        expected = content_hash(self._identity_payload())
        if self.preregistration_id != expected:
            raise PreregistrationError(
                "preregistration_id mismatch (expected %s)" % expected)

    # -------------------------------------------------
    # Deterministic identity (single sanctioned path)
    # -------------------------------------------------

    @staticmethod
    def _identity_payload_for(*, hypothesis_ids, hypotheses,
                              dataset_identity, discovery_boundary,
                              oos_boundary, required_period_count,
                              minimum_trades_per_period,
                              minimum_total_trades,
                              minimum_contiguous_bars,
                              minimum_fresh_bars,
                              economics_requirements,
                              multiple_testing_family,
                              regime_constraints, symbol_constraints,
                              directional_constraints,
                              frozen_execution_semantics, limitations):
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": ARTIFACT_TYPE,
            "hypothesis_ids": list(hypothesis_ids),
            "hypotheses": [h.to_dict() for h in tuple(hypotheses)],
            "dataset_identity": dataset_identity,
            "discovery_boundary": discovery_boundary,
            "oos_boundary": oos_boundary,
            "required_period_count": required_period_count,
            "minimum_trades_per_period": minimum_trades_per_period,
            "minimum_total_trades": minimum_total_trades,
            "minimum_contiguous_bars": minimum_contiguous_bars,
            "minimum_fresh_bars": minimum_fresh_bars,
            "economics_requirements": list(economics_requirements),
            "multiple_testing_family": multiple_testing_family,
            "regime_constraints": list(regime_constraints),
            "symbol_constraints": list(symbol_constraints),
            "directional_constraints": list(directional_constraints),
            "frozen_execution_semantics": frozen_execution_semantics,
            "limitations": list(limitations),
        }

    def _identity_payload(self):
        return self._identity_payload_for(
            hypothesis_ids=self.hypothesis_ids,
            hypotheses=self.hypotheses,
            dataset_identity=self.dataset_identity,
            discovery_boundary=self.discovery_boundary,
            oos_boundary=self.oos_boundary,
            required_period_count=self.required_period_count,
            minimum_trades_per_period=self.minimum_trades_per_period,
            minimum_total_trades=self.minimum_total_trades,
            minimum_contiguous_bars=self.minimum_contiguous_bars,
            minimum_fresh_bars=self.minimum_fresh_bars,
            economics_requirements=self.economics_requirements,
            multiple_testing_family=self.multiple_testing_family,
            regime_constraints=self.regime_constraints,
            symbol_constraints=self.symbol_constraints,
            directional_constraints=self.directional_constraints,
            frozen_execution_semantics=self.frozen_execution_semantics,
            limitations=self.limitations)

    @classmethod
    def create(cls, *, hypotheses, dataset_identity,
               discovery_boundary, oos_boundary,
               required_period_count=_protocol.OOS_PERIODS,
               minimum_trades_per_period=(
                   _protocol.MIN_OOS_TRADES_PER_PERIOD),
               minimum_total_trades=_protocol.MIN_TOTAL_OOS_TRADES,
               minimum_contiguous_bars, minimum_fresh_bars,
               economics_requirements, multiple_testing_family,
               regime_constraints=(), symbol_constraints=(),
               directional_constraints=(),
               frozen_execution_semantics, limitations=()):
        """Build a preregistration, deriving its deterministic id."""
        hypotheses = tuple(hypotheses)
        hypothesis_ids = tuple(h.hypothesis_id for h in hypotheses)
        preregistration_id = content_hash(
            cls._identity_payload_for(
                hypothesis_ids=hypothesis_ids,
                hypotheses=hypotheses,
                dataset_identity=dataset_identity,
                discovery_boundary=discovery_boundary,
                oos_boundary=oos_boundary,
                required_period_count=required_period_count,
                minimum_trades_per_period=minimum_trades_per_period,
                minimum_total_trades=minimum_total_trades,
                minimum_contiguous_bars=minimum_contiguous_bars,
                minimum_fresh_bars=minimum_fresh_bars,
                economics_requirements=economics_requirements,
                multiple_testing_family=multiple_testing_family,
                regime_constraints=regime_constraints,
                symbol_constraints=symbol_constraints,
                directional_constraints=directional_constraints,
                frozen_execution_semantics=frozen_execution_semantics,
                limitations=limitations))
        return cls(
            schema_version=SCHEMA_VERSION,
            artifact_type=ARTIFACT_TYPE,
            preregistration_id=preregistration_id,
            identity_algorithm=IDENTITY_ALGORITHM,
            hypothesis_ids=hypothesis_ids,
            hypotheses=hypotheses,
            dataset_identity=dataset_identity,
            discovery_boundary=discovery_boundary,
            oos_boundary=oos_boundary,
            required_period_count=required_period_count,
            minimum_trades_per_period=minimum_trades_per_period,
            minimum_total_trades=minimum_total_trades,
            minimum_contiguous_bars=minimum_contiguous_bars,
            minimum_fresh_bars=minimum_fresh_bars,
            economics_requirements=tuple(economics_requirements),
            multiple_testing_family=multiple_testing_family,
            regime_constraints=tuple(regime_constraints),
            symbol_constraints=tuple(symbol_constraints),
            directional_constraints=tuple(directional_constraints),
            frozen_execution_semantics=frozen_execution_semantics,
            limitations=tuple(limitations),
            is_production_ready=False)

    @classmethod
    def from_dict(cls, payload):
        """Rehydrate one persisted preregistration and verify its identity.

        This is the single sanctioned reload path for frozen-OOS
        preregistration artifacts. It never repairs, defaults, or mutates
        persisted content: malformed or tampered artifacts fail closed.
        """
        if not isinstance(payload, dict):
            raise PreregistrationError("payload must be a dict")
        required = (
            "schema_version", "artifact_type", "preregistration_id",
            "identity_algorithm", "hypothesis_ids", "hypotheses",
            "dataset_identity", "discovery_boundary", "oos_boundary",
            "required_period_count", "minimum_trades_per_period",
            "minimum_total_trades", "minimum_contiguous_bars",
            "minimum_fresh_bars", "economics_requirements",
            "multiple_testing_family", "regime_constraints",
            "symbol_constraints", "directional_constraints",
            "frozen_execution_semantics", "limitations",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise PreregistrationError(
                "missing persisted fields: %s" % ", ".join(missing))
        hypotheses_raw = payload["hypotheses"]
        if not isinstance(hypotheses_raw, (tuple, list)):
            raise PreregistrationError("hypotheses must be a tuple/list")
        hypotheses = []
        for item in hypotheses_raw:
            if not isinstance(item, dict):
                raise PreregistrationError("hypothesis items must be dict")
            try:
                hypotheses.append(_types.HypothesisRecord(
                    hypothesis_id=item.get("hypothesis_id", ""),
                    origin=item.get("origin", "9L"),
                    statement=item.get("statement", ""),
                    symbol=item.get("symbol", ""),
                    direction=item.get("direction", ""),
                    regime_dim=item.get("regime_dim"),
                    regime_label=item.get("regime_label"),
                    params=dict(item.get("params", {})),
                    seven_e_no_go=bool(item.get("seven_e_no_go", False)),
                    walk_forward_passed=bool(
                        item.get("walk_forward_passed", False)),
                    walk_forward_note=item.get("walk_forward_note", ""),
                    expected_outcome=item.get("expected_outcome", ""),
                    evidence=tuple(item.get("evidence", ())),
                ))
            except (TypeError, ValueError) as exc:
                raise PreregistrationError(
                    "invalid persisted hypothesis: %s" % exc) from exc
        stored_ready = payload.get("is_production_ready", False)
        if stored_ready is not False:
            raise PreregistrationError(
                "is_production_ready must be False in persisted artifact")
        return cls(
            schema_version=payload["schema_version"],
            artifact_type=payload["artifact_type"],
            preregistration_id=payload["preregistration_id"],
            identity_algorithm=payload["identity_algorithm"],
            hypothesis_ids=tuple(payload["hypothesis_ids"]),
            hypotheses=tuple(hypotheses),
            dataset_identity=payload["dataset_identity"],
            discovery_boundary=payload["discovery_boundary"],
            oos_boundary=payload["oos_boundary"],
            required_period_count=payload["required_period_count"],
            minimum_trades_per_period=payload["minimum_trades_per_period"],
            minimum_total_trades=payload["minimum_total_trades"],
            minimum_contiguous_bars=payload["minimum_contiguous_bars"],
            minimum_fresh_bars=payload["minimum_fresh_bars"],
            economics_requirements=tuple(payload["economics_requirements"]),
            multiple_testing_family=payload["multiple_testing_family"],
            regime_constraints=tuple(payload["regime_constraints"]),
            symbol_constraints=tuple(payload["symbol_constraints"]),
            directional_constraints=tuple(payload["directional_constraints"]),
            frozen_execution_semantics=payload["frozen_execution_semantics"],
            limitations=tuple(payload["limitations"]),
            is_production_ready=False,
        )

    def verify_identity(self):
        """True only when the frozen content still matches its id."""
        try:
            return content_hash(
                self._identity_payload()) == self.preregistration_id
        except Exception:  # noqa: BLE001 (any failure is non-verifying)
            return False

    def to_dict(self):
        body = self._identity_payload()
        ordered = {
            "schema_version": self.schema_version,
            "artifact_type": self.artifact_type,
            "preregistration_id": self.preregistration_id,
            "identity_algorithm": self.identity_algorithm,
        }
        ordered.update(body)
        ordered["is_production_ready"] = False
        return ordered
