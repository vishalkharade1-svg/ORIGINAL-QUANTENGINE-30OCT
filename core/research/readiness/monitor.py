"""Frozen-OOS readiness monitor (research-only).

Converts the one-time readiness evaluation into a deterministic
monitoring + future-execution handoff layer:

    acquire/inspect current evidence
            -> run existing readiness evaluator (reuse, no new engine)
            -> record deterministic readiness snapshot
            -> identify remaining blockers with classes
            -> derive the handoff state
            -> STOP (never executes OOS automatically)

Reuse (no duplicate systems):

* readiness arithmetic .. ``oos_execution_readiness.evaluate`` /
  ``observe_dataset`` (the existing evaluator -- the monitor
  adds NO gate math of its own);
* preregistration ....... ``preregistration.FrozenPreregistration``;
* deterministic identity  ``research.phase11g.provenance.model.
  content_hash``;
* protocol .............. ``core.research.oos.constants``.

Rules:

* Time-bound data is a legitimate prerequisite: shortfalls are
  reported as arithmetic gaps from source-data timestamps only.
  No wall-clock, no completion-date prediction (no ``datetime``,
  no ``time`` anywhere in this module).
* ``NO_NEW_SOURCE_DATA`` (source holds nothing beyond the latest
  stored observation) is a normal condition, never an error.
* Handoff states are closed and terminal for this task:
  ``READY_FOR_OOS_EXECUTION`` means a SEPARATE explicitly
  authorized task may begin -- it never means executed,
  validated, profitable, or production-ready, and this module
  contains no execution path.
* Synthetic or unprovenanced rows can never satisfy genuineness:
  the snapshot binds the exact dataset identity and requires
  ``A-DIRECT`` acquisition provenance, else an
  ``OPERATOR_PREREQUISITE`` blocker is recorded.
* ``is_production_ready`` is hard-wired False.
"""

from __future__ import annotations

import dataclasses

from core.research.readiness import oos_execution_readiness as _eval
from research.phase11g.provenance.model import content_hash


SCHEMA_VERSION = "1"
SNAPSHOT_TYPE = "OOS_READINESS_SNAPSHOT"
IDENTITY_ALGORITHM = (
    "content_hash:research.phase11g.provenance.model:"
    "sha256-canonical-json"
)
PROTOCOL_ID = "9M-1"

BLOCKER_CLASSES = (
    "DATA_TIME_BOUND",
    "DATA_INSUFFICIENT",
    "NO_ELIGIBLE_HYPOTHESES",
    "NO_FILLS",
    "ECONOMICS_UNAVAILABLE",
    "MICROSTRUCTURE_UNAVAILABLE",
    "PREREGISTRATION_REQUIRED",
    "OPERATOR_PREREQUISITE",
    "REPOSITORY_FORENSIC_BLOCK",
)

HANDOFF_STATES = (
    "WAITING_FOR_DATA",
    "WAITING_FOR_HYPOTHESES",
    "WAITING_FOR_ECONOMICS",
    "WAITING_FOR_MICROSTRUCTURE",
    "WAITING_FOR_FILLS",
    "READY_FOR_PREREGISTRATION",
    "READY_FOR_OOS_EXECUTION",
)

SOURCE_STATES = ("CURRENT", "NO_NEW_SOURCE_DATA")

REPO_FORENSIC_STATES = ("VERIFIED", "BLOCKED")


class MonitorError(ValueError):
    """A monitor input, snapshot, or handoff is invalid."""


def _check_closed(value, field, allowed):
    if value not in allowed:
        raise MonitorError("%s has invalid value %r" % (field, value))
    return value


def _str_tuple(value, field):
    if not isinstance(value, (tuple, list)):
        raise MonitorError("%s must be a tuple/list" % field)
    items = tuple(value)
    for item in items:
        if not isinstance(item, str):
            raise MonitorError("%s items must be str" % field)
    return items


@dataclasses.dataclass(frozen=True)
class Blocker:
    """One classified remaining blocker (never collapsed to BLOCKED)."""
    blocker_class: str
    gate_id: str
    detail: str

    def __post_init__(self):
        _check_closed(self.blocker_class, "blocker_class",
                      BLOCKER_CLASSES)
        if not isinstance(self.gate_id, str) or not self.gate_id:
            raise MonitorError("gate_id must be a non-empty str")
        if not isinstance(self.detail, str):
            raise MonitorError("detail must be str")

    def to_dict(self):
        return {"blocker_class": self.blocker_class,
                "gate_id": self.gate_id, "detail": self.detail}


def source_status(latest_stored_timestamp, source_rows):
    """Deterministic source-freshness condition (no wall-clock).

    Returns ``(state, newest_source_timestamp)`` where state is
    CURRENT when the source holds at least one observation beyond
    the latest stored one, else NO_NEW_SOURCE_DATA. Timestamps
    come from source data only.
    """
    newest = None
    for row in source_rows or ():
        if not isinstance(row, dict):
            continue
        ts = row.get("time")
        if isinstance(ts, int) and not isinstance(ts, bool):
            if newest is None or ts > newest:
                newest = ts
    if newest is not None and newest > int(latest_stored_timestamp):
        return "CURRENT", newest
    return "NO_NEW_SOURCE_DATA", newest


def classify_blockers(report, hypothesis_count=0,
                       repository_forensic_status="BLOCKED"):
    """Map every non-VERIFIED gate to an explicit blocker class."""
    _check_closed(repository_forensic_status,
                  "repository_forensic_status", REPO_FORENSIC_STATES)
    blockers = []
    by_id = {g.gate_id: g for g in report.gates}
    hypo = by_id.get("hypothesis_preregistration")
    if hypo is not None and hypo.status != "VERIFIED":
        if int(hypothesis_count) == 0:
            blockers.append(Blocker(
                "NO_ELIGIBLE_HYPOTHESES",
                "hypothesis_preregistration",
                "no frozen eligible hypotheses exist; upstream "
                "discovery produced nothing preregistrable"))
        else:
            blockers.append(Blocker(
                "PREREGISTRATION_REQUIRED",
                "hypothesis_preregistration",
                "hypotheses exist but no verifying frozen "
                "preregistration binds them"))
    for gate_id in ("frozen_boundary", "dataset_contiguity"):
        gate = by_id.get(gate_id)
        if gate is not None and gate.status != "VERIFIED":
            blockers.append(Blocker(
                "DATA_INSUFFICIENT", gate_id,
                "%s: %s" % (gate.observed, gate.detail)))
    gate = by_id.get("zero_overlap")
    if gate is not None and gate.status == "BLOCKED":
        blockers.append(Blocker(
            "DATA_INSUFFICIENT", "zero_overlap",
            "%s: %s" % (gate.observed, gate.detail)))
    elif gate is not None and gate.status == "UNAVAILABLE":
        blockers.append(Blocker(
            "OPERATOR_PREREQUISITE", "zero_overlap",
            "discovery observation set unavailable; overlap against "
            "discovery cannot be verified"))
    for gate_id in ("minimum_bar_count", "fresh_oos_bar_count"):
        gate = by_id.get(gate_id)
        if gate is not None and gate.status != "VERIFIED":
            blockers.append(Blocker(
                "DATA_TIME_BOUND", gate_id,
                "%s; missing bars must genuinely occur after the "
                "frozen boundary" % gate.observed))
    gate = by_id.get("minimum_fill_requirement")
    if gate is not None and gate.status != "VERIFIED":
        blockers.append(Blocker(
            "NO_FILLS", "minimum_fill_requirement",
            "%s; fills count only from research execution evidence"
            % gate.observed))
    for gate_id in tuple("economics_" + f for f in
                         _eval.ECONOMICS_FIELDS):
        gate = by_id.get(gate_id)
        if gate is not None and gate.status != "VERIFIED":
            blockers.append(Blocker(
                "ECONOMICS_UNAVAILABLE", gate_id,
                "%s: %s" % (gate.observed, gate.detail)))
    gate = by_id.get("microstructure_evidence")
    if gate is not None and gate.status != "VERIFIED":
        blockers.append(Blocker(
            "MICROSTRUCTURE_UNAVAILABLE", "microstructure_evidence",
            "%s: %s" % (gate.observed, gate.detail)))
    for gate_id in ("symbol_metadata", "regime_metadata",
                    "directional_metadata"):
        gate = by_id.get(gate_id)
        if gate is not None and gate.status == "UNAVAILABLE":
            blockers.append(Blocker(
                "NO_ELIGIBLE_HYPOTHESES", gate_id,
                "empty frozen set declares no %s" % gate_id))
        elif gate is not None and gate.status == "INCONCLUSIVE":
            blockers.append(Blocker(
                "PREREGISTRATION_REQUIRED", gate_id,
                "hypotheses exist but declare no %s" % gate_id))
    if repository_forensic_status == "BLOCKED":
        blockers.append(Blocker(
            "REPOSITORY_FORENSIC_BLOCK", "repository",
            "historical pins/dirt/ancestry intentionally preserved; "
            "repository-wide certification stays blocked"))
    return tuple(blockers)


def derive_handoff(report, hypothesis_count=0):
    """Derive the terminal handoff state from gate statuses only."""
    by_id = {g.gate_id: g for g in report.gates}

    def unmet(*gate_ids):
        return any(by_id[g].status != "VERIFIED" for g in gate_ids
                   if g in by_id)

    if report.final_status == "READINESS_VERIFIED" and not any(
            g.status != "VERIFIED" for g in report.gates):
        return "READY_FOR_OOS_EXECUTION"
    if unmet("frozen_boundary", "dataset_contiguity",
             "zero_overlap", "minimum_bar_count",
             "fresh_oos_bar_count"):
        return "WAITING_FOR_DATA"
    if int(hypothesis_count) == 0:
        return "WAITING_FOR_HYPOTHESES"
    if unmet("minimum_fill_requirement"):
        return "WAITING_FOR_FILLS"
    if unmet(*["economics_" + f for f in _eval.ECONOMICS_FIELDS]):
        return "WAITING_FOR_ECONOMICS"
    if unmet("microstructure_evidence"):
        return "WAITING_FOR_MICROSTRUCTURE"
    return "READY_FOR_PREREGISTRATION"


def _aggregate(statuses):
    if all(s == "VERIFIED" for s in statuses):
        return "VERIFIED"
    if any(s == "BLOCKED" for s in statuses):
        return "BLOCKED"
    if any(s == "UNAVAILABLE" for s in statuses):
        return "UNAVAILABLE"
    return "INCONCLUSIVE"


@dataclasses.dataclass(frozen=True)
class ReadinessSnapshot:
    """Immutable deterministic readiness snapshot (research-only)."""

    schema_version: str
    snapshot_type: str
    snapshot_id: str
    identity_algorithm: str
    protocol_id: str
    dataset_id: str
    report_id: str
    frozen_boundary: int
    oos_window_start: int
    latest_observed_timestamp: object
    required_contiguous_bars: int
    available_contiguous_bars: int
    required_fresh_bars: int
    available_fresh_bars: int
    fresh_bar_gap: int
    required_fills: int
    available_fills: int
    fill_gap: int
    hypothesis_count: int
    preregistration_status: str
    preregistration_id: str
    economics_status: str
    microstructure_status: str
    symbol_metadata_status: str
    regime_metadata_status: str
    directional_metadata_status: str
    deterministic_identity_status: str
    production_isolation_status: str
    source_status: str
    overall_readiness: str
    handoff_state: str
    blockers: tuple
    limitations: tuple
    production_isolation: bool = True
    is_production_ready: bool = False

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise MonitorError("schema_version must be %r"
                               % SCHEMA_VERSION)
        if self.snapshot_type != SNAPSHOT_TYPE:
            raise MonitorError("snapshot_type must be %r"
                               % SNAPSHOT_TYPE)
        if self.identity_algorithm != IDENTITY_ALGORITHM:
            raise MonitorError("identity_algorithm must be %r"
                               % IDENTITY_ALGORITHM)
        for field in ("protocol_id", "dataset_id", "report_id",
                      "preregistration_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise MonitorError(
                    "%s must be a non-empty str" % field)
        for field in ("frozen_boundary", "oos_window_start",
                      "required_contiguous_bars",
                      "available_contiguous_bars", "required_fresh_bars",
                      "available_fresh_bars", "fresh_bar_gap",
                      "required_fills", "available_fills", "fill_gap",
                      "hypothesis_count"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise MonitorError("%s must be int" % field)
            if value < 0 and field not in ("available_fills",):
                raise MonitorError("%s must be >= 0" % field)
        latest = self.latest_observed_timestamp
        if latest is not None and (
                not isinstance(latest, int) or isinstance(latest, bool)):
            raise MonitorError(
                "latest_observed_timestamp must be int or None")
        for field, allowed in (
                ("preregistration_status",
                 ("VERIFIED", "BLOCKED", "UNAVAILABLE")),
                ("economics_status", ("VERIFIED", "BLOCKED",
                                      "UNAVAILABLE", "INCONCLUSIVE")),
                ("microstructure_status", ("VERIFIED", "BLOCKED",
                                           "UNAVAILABLE",
                                           "INCONCLUSIVE")),
                ("symbol_metadata_status", ("VERIFIED", "BLOCKED",
                                            "UNAVAILABLE",
                                            "INCONCLUSIVE")),
                ("regime_metadata_status", ("VERIFIED", "BLOCKED",
                                            "UNAVAILABLE",
                                            "INCONCLUSIVE")),
                ("directional_metadata_status", ("VERIFIED", "BLOCKED",
                                                 "UNAVAILABLE",
                                                 "INCONCLUSIVE")),
                ("deterministic_identity_status", ("VERIFIED", "BLOCKED")),
                ("production_isolation_status", ("VERIFIED", "BLOCKED")),
                ("source_status", SOURCE_STATES),
                ("overall_readiness",
                 ("READINESS_VERIFIED", "BLOCKED")),
                ("handoff_state", HANDOFF_STATES)):
            _check_closed(getattr(self, field), field, allowed)
        object.__setattr__(self, "blockers",
                           tuple(self.blockers or ()))
        for item in self.blockers:
            if not isinstance(item, Blocker):
                raise MonitorError(
                    "blockers must be Blocker, got %s"
                    % type(item).__name__)
        object.__setattr__(self, "limitations",
                           _str_tuple(self.limitations, "limitations"))
        if self.production_isolation is not True:
            raise MonitorError("production_isolation must be True")
        if self.is_production_ready is not False:
            raise MonitorError("is_production_ready must be False")
        if (self.overall_readiness == "READINESS_VERIFIED"
                and self.handoff_state != "READY_FOR_OOS_EXECUTION"):
            raise MonitorError(
                "READINESS_VERIFIED requires the READY_FOR_OOS_"
                "EXECUTION handoff")
        if (self.handoff_state == "READY_FOR_OOS_EXECUTION"
                and (self.overall_readiness != "READINESS_VERIFIED"
                     or self.blockers)):
            raise MonitorError(
                "READY_FOR_OOS_EXECUTION forbids blockers and "
                "requires READINESS_VERIFIED")
        expected = content_hash(self._identity_payload())
        if self.snapshot_id != expected:
            raise MonitorError(
                "snapshot_id mismatch (expected %s)" % expected)

    @staticmethod
    def _identity_payload_for(**fields):
        payload = {"schema_version": SCHEMA_VERSION,
                   "snapshot_type": SNAPSHOT_TYPE}
        payload.update(fields)
        return payload

    def _identity_payload(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "snapshot_type": SNAPSHOT_TYPE,
            "protocol_id": self.protocol_id,
            "dataset_id": self.dataset_id,
            "report_id": self.report_id,
            "frozen_boundary": self.frozen_boundary,
            "oos_window_start": self.oos_window_start,
            "latest_observed_timestamp":
                self.latest_observed_timestamp,
            "required_contiguous_bars":
                self.required_contiguous_bars,
            "available_contiguous_bars":
                self.available_contiguous_bars,
            "required_fresh_bars": self.required_fresh_bars,
            "available_fresh_bars": self.available_fresh_bars,
            "fresh_bar_gap": self.fresh_bar_gap,
            "required_fills": self.required_fills,
            "available_fills": self.available_fills,
            "fill_gap": self.fill_gap,
            "hypothesis_count": self.hypothesis_count,
            "preregistration_status": self.preregistration_status,
            "preregistration_id": self.preregistration_id,
            "economics_status": self.economics_status,
            "microstructure_status": self.microstructure_status,
            "symbol_metadata_status": self.symbol_metadata_status,
            "regime_metadata_status": self.regime_metadata_status,
            "directional_metadata_status":
                self.directional_metadata_status,
            "deterministic_identity_status":
                self.deterministic_identity_status,
            "production_isolation_status":
                self.production_isolation_status,
            "source_status": self.source_status,
            "overall_readiness": self.overall_readiness,
            "handoff_state": self.handoff_state,
            "blockers": [b.to_dict() for b in self.blockers],
            "limitations": list(self.limitations),
            "production_isolation": True,
            "is_production_ready": False,
        }

    def to_dict(self):
        body = self._identity_payload()
        ordered = {
            "schema_version": self.schema_version,
            "snapshot_type": self.snapshot_type,
            "snapshot_id": self.snapshot_id,
            "identity_algorithm": self.identity_algorithm,
        }
        ordered.update(body)
        return ordered


def run_monitor(preregistration, *, dataset, dataset_identity,
                fills_observed, economics, microstructure,
                provenance=None, latest_stored_timestamp=None,
                source_rows=(), repository_forensic_status="BLOCKED"):
    """Run one monitor pass: evaluate, snapshot, stop.

    Never executes OOS, never fetches network, never mutates
    inputs. ``provenance`` is the acquisition provenance mapping
    (tier must read ``A-DIRECT``); rows without compliant
    provenance are recorded with an OPERATOR_PREREQUISITE
    blocker -- synthetic futures can never pass as genuine.
    """
    report = _eval.evaluate(
        preregistration, dataset=dataset,
        fills_observed=fills_observed, economics=economics,
        microstructure=microstructure)
    hypo_count = len(preregistration.hypotheses) if (
        preregistration is not None) else 0
    blockers = list(classify_blockers(
        report, hypothesis_count=hypo_count,
        repository_forensic_status=repository_forensic_status))
    provenance_tier = None
    if isinstance(provenance, dict):
        provenance_tier = provenance.get("tier")
    if provenance_tier != "A-DIRECT":
        blockers.append(Blocker(
            "OPERATOR_PREREQUISITE", "dataset_provenance",
            "acquisition provenance is not A-DIRECT (got %r); "
            "rows cannot be accepted as genuine source "
            "observations" % (provenance_tier,)))
    handoff = derive_handoff(report, hypothesis_count=hypo_count)
    overall = report.final_status
    if provenance_tier != "A-DIRECT":
        # Dataset genuineness is snapshot-level: unprovenanced rows
        # can never underwrite a VERIFIED overall or a READY
        # handoff, while the underlying gate report is left
        # untouched (separation of evaluation vs acceptance).
        overall = "BLOCKED"
        if handoff == "READY_FOR_OOS_EXECUTION":
            handoff = "WAITING_FOR_DATA"
    by_id = {g.gate_id: g for g in report.gates}

    def status_of(*gate_ids, default="UNAVAILABLE"):
        states = [by_id[g].status for g in gate_ids if g in by_id]
        if not states:
            return default
        return _aggregate(states)

    econ = status_of(*["economics_" + f for f in
                       _eval.ECONOMICS_FIELDS])
    micro = status_of("microstructure_evidence")
    if dataset is None:
        available_bars = 0
        available_contiguous = 0
        latest = None
    else:
        available_bars = int(dataset.get("fresh_bar_count", 0))
        available_contiguous = int(dataset.get(
            "max_contiguous_clean_bars", 0))
        latest = None
    if latest_stored_timestamp is not None:
        try:
            latest = int(latest_stored_timestamp)
        except (TypeError, ValueError):
            latest = None
    required_bars = int(_eval.required_fresh_bars())
    fills = report.available_fills
    fills = int(fills) if fills is not None and fills >= 0 else -1
    oos_boundary = (preregistration.oos_boundary
                    if preregistration is not None else 0)
    discovery = (preregistration.discovery_boundary
                 if preregistration is not None else 0)
    hypo_gate = by_id.get("hypothesis_preregistration")
    if hypo_gate is None:
        pre_status = "UNAVAILABLE"
    elif hypo_gate.status == "VERIFIED":
        pre_status = "VERIFIED"
    else:
        pre_status = "BLOCKED"
    src_state, newest = source_status(
        latest if latest is not None else -1, source_rows)
    if latest is None:
        latest = newest
    identity_ok = content_hash(
        report._identity_payload()) == report.report_id
    fields = {
        "protocol_id": PROTOCOL_ID,
        "dataset_id": str(dataset_identity),
        "report_id": report.report_id,
        "frozen_boundary": int(discovery),
        "oos_window_start": int(oos_boundary) if oos_boundary
        else 0,
        "latest_observed_timestamp": latest,
        "required_contiguous_bars":
            int(_eval.REQUIRED_CONTIGUOUS_CLEAN_BARS),
        "available_contiguous_bars": available_contiguous,
        "required_fresh_bars": required_bars,
        "available_fresh_bars": available_bars,
        "fresh_bar_gap": max(0, required_bars - available_bars),
        "required_fills": int(report.required_fills),
        "available_fills": fills,
        "fill_gap": max(0, int(report.required_fills) - fills)
        if fills >= 0 else int(report.required_fills),
        "hypothesis_count": int(hypo_count),
        "preregistration_status": pre_status,
        "preregistration_id": (
            preregistration.preregistration_id
            if preregistration is not None else "UNREGISTERED"),
        "economics_status": econ,
        "microstructure_status": micro,
        "symbol_metadata_status": status_of("symbol_metadata"),
        "regime_metadata_status": status_of("regime_metadata"),
        "directional_metadata_status": status_of(
            "directional_metadata"),
        "deterministic_identity_status": (
            "VERIFIED" if identity_ok else "BLOCKED"),
        "production_isolation_status": "VERIFIED",
        "source_status": src_state,
        "overall_readiness": overall,
        "handoff_state": handoff,
        "blockers": blockers,
        "limitations": (
            "snapshot binds exact dataset rows; any row change "
            "yields a different dataset identity",
            "time-bound gaps use source timestamps only; no "
            "completion date is predicted",
            "READY_FOR_OOS_EXECUTION is a handoff for a separate "
            "authorized task, never an execution"),
        "production_isolation": True,
        "is_production_ready": False,
    }
    snapshot_id = content_hash(
        ReadinessSnapshot._identity_payload_for(
            **dict(fields, blockers=[b.to_dict() for b in blockers],
                   limitations=list(fields["limitations"]))))
    return ReadinessSnapshot(
        schema_version=SCHEMA_VERSION,
        snapshot_type=SNAPSHOT_TYPE, snapshot_id=snapshot_id,
        identity_algorithm=IDENTITY_ALGORITHM, **fields)
