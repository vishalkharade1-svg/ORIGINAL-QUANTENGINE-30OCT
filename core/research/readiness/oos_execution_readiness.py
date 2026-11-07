"""Frozen-OOS execution readiness evaluator (research-only).

Answers exactly one question:

    "Are we actually ready to run the frozen OOS experiment?"

It never answers whether a strategy works, is profitable, or may
trade live. It never executes the OOS phase, never modifies the
dataset or the frozen hypothesis set, and never infers missing
evidence (no UNAVAILABLE -> PASS, no 0-fills -> satisfied, no
missing-fees -> zero-fees).

Reuse (no duplicate systems):

* freshness ......... ``core.research.oos_validation.periods``
  ``validate_freshness`` (the exact repository definition of the
  strictly-after discovery boundary);
* sample arithmetic  ``core.research.readiness.sample_math``
  (``required_bars`` / ``oos_span_bars`` -- rates are measured
  Gate-A quantities documented in STATUS Phase-15, never fitted);
* protocol numbers .. ``core.research.oos.constants`` (6 periods,
  10 trades/period, 60 total, purge/embargo 0);
* economics ......... ``core.risk.costs`` (explicit-zero defaults;
  venue schedules NOT configured) and
  ``core.research.readiness.scenarios`` (structural zero-cost,
  fees ASSUMED-only, funding UNAVAILABLE);
* identity .......... ``research.phase11g.provenance.model.content_hash``.

Documented thresholds (explicit arithmetic, never rounded):

* REQUIRED_CONTIGUOUS_CLEAN_BARS = 6175 (11G-Q gate, phase11g_O:
  FULL_WF needs 6,175 contiguous zero-overlap clean bars);
* MEASURED_ORDER_RATE = 0.005, MEASURED_FILL_RATE = 0.08 (Gate-A
  25 orders / 5000 bars, 2 fills / 25 orders -- STATUS Phase-15);
* required_per_period_bars = required_bars(10, 0.005, 0.08) = 25000;
* required_fresh_bars = oos_span_bars(25000, 6, 0.5) = 300000
  (6 OOS periods plus the frozen 50% discovery headroom);
* required_fills = MIN_TOTAL_OOS_TRADES = 60 (a fill counts only
  when the research execution authority recorded one -- persisted
  evidence is read, never re-executed here).

Gate vocabulary is closed: VERIFIED / BLOCKED / UNAVAILABLE /
INCONCLUSIVE. Final status is BLOCKED until every mandatory gate
is VERIFIED. ``is_production_ready`` is hard-wired False.
"""

from __future__ import annotations

import dataclasses

from core.research.oos import constants as _protocol
from core.research.oos_validation import periods as _periods
from core.research.readiness import sample_math as _math
from research.phase11g.provenance.model import content_hash


SCHEMA_VERSION = "1"
REPORT_TYPE = "OOS_EXECUTION_READINESS"
IDENTITY_ALGORITHM = (
    "content_hash:research.phase11g.provenance.model:"
    "sha256-canonical-json"
)

GATE_STATUS = ("VERIFIED", "BLOCKED", "UNAVAILABLE", "INCONCLUSIVE")

FINAL_STATUS = ("READINESS_VERIFIED", "BLOCKED")

# 11G-Q contiguous-data gate (docs/audit/phase11g_O_fresh_data_expansion
# ... "FULL_WF remains INFEASIBLE (need 6,175)").
REQUIRED_CONTIGUOUS_CLEAN_BARS = 6175

# Measured Gate-A rates (STATUS Phase-15: 25 orders / 5000 bars,
# 2 fills / 25 orders). Inputs to sample_math, never fitted here.
MEASURED_ORDERS_PER_BAR = 0.005
MEASURED_FILL_RATE = 0.08

# STATUS Phase-15 lower bound for the older 3-period context, kept
# as an informational cross-check (the frozen 6-period protocol
# derives 300000 below; both are reported, neither is rounded).
DOCUMENTED_FRESH_BAR_FLOOR = 75000

ECONOMICS_FIELDS = ("maker_fee", "taker_fee", "funding",
                    "contract_value", "slippage")


class ReadinessError(ValueError):
    """A readiness observation, gate, or report is invalid."""


def required_per_period_bars():
    """Bars per 10-fill period at measured Gate-A rates (25000.0)."""
    return _math.required_bars(
        _protocol.MIN_OOS_TRADES_PER_PERIOD,
        MEASURED_ORDERS_PER_BAR, MEASURED_FILL_RATE)


def required_fresh_bars():
    """Fresh bars for 6 OOS periods + discovery headroom (300000.0)."""
    return _math.oos_span_bars(
        required_per_period_bars(),
        _protocol.OOS_PERIODS, _protocol.DISCOVERY_FRACTION)


def _check_status(value, field):
    if value not in GATE_STATUS:
        raise ReadinessError("%s has invalid status %r" % (field, value))
    return value


def _str_tuple(value, field):
    if not isinstance(value, (tuple, list)):
        raise ReadinessError("%s must be a tuple/list" % field)
    items = tuple(value)
    for item in items:
        if not isinstance(item, str):
            raise ReadinessError("%s items must be str" % field)
    return items


@dataclasses.dataclass(frozen=True)
class GateVerdict:
    """One readiness gate: closed status plus explicit reason."""
    gate_id: str
    status: str
    detail: str = ""
    observed: str = ""
    required: str = ""

    def __post_init__(self):
        if not isinstance(self.gate_id, str) or not self.gate_id:
            raise ReadinessError("gate_id must be a non-empty str")
        _check_status(self.status, "gate %s status" % self.gate_id)
        for field in ("detail", "observed", "required"):
            if not isinstance(getattr(self, field), str):
                raise ReadinessError("gate %s %s must be str"
                                     % (self.gate_id, field))

    def to_dict(self):
        return {"gate_id": self.gate_id, "status": self.status,
                "detail": self.detail, "observed": self.observed,
                "required": self.required}


def observe_dataset(rows, discovery_boundary, discovery_timestamps=None):
    """Reduce candle rows to deterministic readiness observations.

    Pure function over ``{time,...}`` rows (only ``time`` is read;
    rows must already be normalized elsewhere). Returns plain
    dicts of ints/bools -- no inference, no execution:

    * ``fresh_rows``: timestamps strictly after the boundary;
    * ``max_contiguous``: longest run of exact 60s steps with no
      duplicate timestamp inside the fresh set;
    * ``duplicate_timestamps``: count of repeated stamps (overlap);
    * ``reused_observations``: fresh stamps also present in the
      caller-supplied discovery set (None when the discovery set
      is not supplied -- reuse then stays UNKNOWN, never assumed
      zero);
    * ``freshness``: the repository ``validate_freshness`` verdict
      over the fresh rows (exact repo definition of the boundary).
    """
    stamps = []
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        ts = row.get("time")
        if isinstance(ts, int) and not isinstance(ts, bool):
            stamps.append(ts)
    fresh = sorted(ts for ts in stamps if ts > discovery_boundary)
    unique = sorted(set(fresh))
    duplicates = len(fresh) - len(unique)
    best = 0
    run = 0
    prev = None
    for ts in unique:
        if prev is not None and ts - prev == 60:
            run += 1
        else:
            run = 1
        prev = ts
        if run > best:
            best = run
    if discovery_timestamps is None:
        reused = None
    else:
        reused = len(set(unique) & set(discovery_timestamps))
    try:
        freshness = _periods.validate_freshness(
            [{"time": ts} for ts in unique], discovery_boundary)
        strictly_after = bool(freshness.get("strictly_after", False))
    except Exception:  # noqa: BLE001 (boundary check is best-effort)
        strictly_after = len(unique) > 0 and min(unique) > (
            discovery_boundary)
    return {"fresh_bar_count": len(unique),
            "max_contiguous_clean_bars": best,
            "duplicate_timestamps": duplicates,
            "reused_observations": reused,
            "strictly_after_boundary": strictly_after}


def _verdict(gate_id, ok, observed, required, detail):
    return GateVerdict(gate_id=gate_id,
                       status="VERIFIED" if ok else "BLOCKED",
                       detail=detail, observed=str(observed),
                       required=str(required))


def evaluate(preregistration, *, dataset, fills_observed,
             economics, microstructure):
    """Evaluate every readiness gate; never executes OOS.

    * ``preregistration``: a ``FrozenPreregistration`` (identity
      must verify or the hypothesis gate is REJECTED);
    * ``dataset``: an ``observe_dataset`` observation dict;
    * ``fills_observed``: int fills from persisted research
      execution evidence (None = unavailable; never inferred);
    * ``economics``: dict field -> (status, note) over
      ECONOMICS_FIELDS with venue provenance (missing fields are
      UNAVAILABLE, never zero);
    * ``microstructure``: (status, note) for microstructure
      evidence (structural UNAVAILABLE until an authority
      provides trades/depth/footprint).
    """
    gates = []

    identity_ok = bool(preregistration is not None) and (
        preregistration.verify_identity())
    if preregistration is None or not preregistration.hypotheses:
        gates.append(GateVerdict(
            gate_id="hypothesis_preregistration", status="BLOCKED",
            detail="no frozen hypothesis set preregistered",
            observed="hypotheses=0", required="hypotheses>=1"))
    elif not identity_ok:
        gates.append(GateVerdict(
            gate_id="hypothesis_preregistration", status="BLOCKED",
            detail="preregistration identity does not verify; "
                   "frozen set rejected, new phase required",
            observed="verify_identity=False",
            required="verify_identity=True"))
    else:
        gates.append(GateVerdict(
            gate_id="hypothesis_preregistration", status="VERIFIED",
            detail="frozen set verifies",
            observed="hypotheses=%d" % len(
                preregistration.hypotheses),
            required="hypotheses>=1"))
    hypo_count = len(preregistration.hypotheses) if (
        preregistration is not None) else 0

    if dataset is None:
        for gate_id in ("frozen_boundary", "dataset_contiguity",
                        "zero_overlap", "minimum_bar_count",
                        "fresh_oos_bar_count"):
            gates.append(GateVerdict(
                gate_id=gate_id, status="UNAVAILABLE",
                detail="no dataset observation supplied",
                observed="UNAVAILABLE", required="observation"))
        contiguous = fresh = 0
        duplicates = reused = None
        strictly_after = False
    else:
        contiguous = int(dataset.get("max_contiguous_clean_bars", 0))
        fresh = int(dataset.get("fresh_bar_count", 0))
        duplicates = int(dataset.get("duplicate_timestamps", 0))
        reused = dataset.get("reused_observations")
        strictly_after = bool(dataset.get("strictly_after_boundary",
                                          False))
        gates.append(_verdict(
            "frozen_boundary", strictly_after,
            "strictly_after=%s" % strictly_after,
            "oos_start>discovery_boundary",
            "repository validate_freshness verdict over fresh rows"))
        gates.append(_verdict(
            "dataset_contiguity",
            contiguous >= REQUIRED_CONTIGUOUS_CLEAN_BARS,
            "max_contiguous=%d" % contiguous,
            "max_contiguous>=%d" % REQUIRED_CONTIGUOUS_CLEAN_BARS,
            "11G-Q gate: longest exact-60s run inside the fresh set"))
        if reused is None:
            gates.append(GateVerdict(
                gate_id="zero_overlap", status="UNAVAILABLE",
                detail="discovery observation set unavailable; "
                       "reuse cannot be verified",
                observed="reused=UNKNOWN", required="reused=0"))
        else:
            overlap_ok = duplicates == 0 and reused == 0
            gates.append(_verdict(
                "zero_overlap", overlap_ok,
                "duplicates=%d reused=%d" % (duplicates, reused),
                "duplicates=0 reused=0",
                "duplicate bars, reused OOS observations, and "
                "overlapping windows all refuse"))
        need_fresh = required_fresh_bars()
        gates.append(_verdict(
            "minimum_bar_count", fresh >= need_fresh,
            "fresh_bars=%d" % fresh, "fresh_bars>=%d" % int(need_fresh),
            "frozen 6-period span + discovery headroom at measured "
            "Gate-A rates (sample_math, never rounded)"))
        gates.append(GateVerdict(
            gate_id="fresh_oos_bar_count",
            status=("VERIFIED" if fresh >= DOCUMENTED_FRESH_BAR_FLOOR
                    else "BLOCKED"),
            detail="STATUS Phase-15 documented floor cross-check",
            observed="fresh_bars=%d" % fresh,
            required="fresh_bars>=%d" % DOCUMENTED_FRESH_BAR_FLOOR))

    if fills_observed is None:
        gates.append(GateVerdict(
            gate_id="minimum_fill_requirement", status="UNAVAILABLE",
            detail="no persisted fill evidence supplied; fills are "
                   "never inferred from candles/signals/opportunities",
            observed="fills=UNKNOWN",
            required="fills>=%d" % _protocol.MIN_TOTAL_OOS_TRADES))
        fills = None
    else:
        fills = int(fills_observed)
        gates.append(_verdict(
            "minimum_fill_requirement",
            fills >= _protocol.MIN_TOTAL_OOS_TRADES,
            "fills=%d" % fills,
            "fills>=%d" % _protocol.MIN_TOTAL_OOS_TRADES,
            "fills count only from research execution evidence; "
            "0 fills is data, never satisfied"))

    economics = economics or {}
    for field in ECONOMICS_FIELDS:
        status, note = economics.get(field, ("UNAVAILABLE",
                                             "field not observed"))
        try:
            _check_status(status, "economics." + field)
        except ReadinessError:
            status, note = "UNAVAILABLE", "invalid status supplied"
        gates.append(GateVerdict(
            gate_id="economics_" + field,
            status=("VERIFIED" if status == "VERIFIED" else
                    "BLOCKED" if status in ("BLOCKED", "UNAVAILABLE")
                    else status),
            detail=str(note),
            observed="economics_%s=%s" % (field, status),
            required="economics_%s=VERIFIED" % field))

    micro_status, micro_note = microstructure or (
        "UNAVAILABLE", "no microstructure observation supplied")
    try:
        _check_status(micro_status, "microstructure")
    except ReadinessError:
        micro_status, micro_note = "UNAVAILABLE", "invalid status"
    gates.append(GateVerdict(
        gate_id="microstructure_evidence",
        status=("VERIFIED" if micro_status == "VERIFIED" else
                "BLOCKED" if micro_status in ("BLOCKED", "UNAVAILABLE")
                else micro_status),
        detail=str(micro_note),
        observed="microstructure=%s" % micro_status,
        required="microstructure=VERIFIED"))

    if preregistration is None or not preregistration.hypotheses:
        for gate_id in ("symbol_metadata", "regime_metadata",
                        "directional_metadata"):
            gates.append(GateVerdict(
                gate_id=gate_id, status="UNAVAILABLE",
                detail="no frozen hypotheses declare %s" % gate_id,
                observed="%s=UNKNOWN" % gate_id,
                required="%s=declared" % gate_id))
    else:
        symbols = sorted({h.symbol for h in preregistration.hypotheses
                          if h.symbol})
        regimes = sorted({str(h.regime_label) for h in
                          preregistration.hypotheses if h.regime_label})
        directions = sorted({h.direction for h in
                             preregistration.hypotheses if h.direction})
        gates.append(GateVerdict(
            gate_id="symbol_metadata",
            status="VERIFIED" if symbols else "INCONCLUSIVE",
            detail="declared symbols", observed=",".join(symbols) or
            "none", required="declared"))
        gates.append(GateVerdict(
            gate_id="regime_metadata",
            status="VERIFIED" if regimes else "INCONCLUSIVE",
            detail="declared regimes (conditional claims stay "
                   "conditional)", observed=",".join(regimes) or "none",
            required="declared"))
        gates.append(GateVerdict(
            gate_id="directional_metadata",
            status="VERIFIED" if directions else "INCONCLUSIVE",
            detail="declared directions (LONG never implies SHORT)",
            observed=",".join(directions) or "none",
            required="declared"))

    report = OOSExecutionReadinessReport.create(
        preregistration_id=(
            preregistration.preregistration_id
            if preregistration is not None else "UNREGISTERED"),
        hypothesis_set_id=(
            "hypotheses=%d" % hypo_count),
        dataset_id="fresh_bars=%d contiguous=%d" % (fresh, contiguous),
        gates=gates,
        available_bars=fresh,
        required_bars=int(required_fresh_bars()),
        available_fills=fills if fills is not None else -1,
        required_fills=_protocol.MIN_TOTAL_OOS_TRADES,
        limitations=(
            "synthetic inputs prove gate logic only, never a trading "
            "edge",
            "documented 75000-bar floor is the older 3-period context; "
            "the frozen 6-period requirement derives 300000",
            "economics/microstructure must come from venue authorities; "
            "absence is UNAVAILABLE, never zero"),
        is_production_ready=False)
    return report


@dataclasses.dataclass(frozen=True)
class OOSExecutionReadinessReport:
    """Immutable deterministic readiness report (research-only)."""

    schema_version: str
    report_type: str
    report_id: str
    identity_algorithm: str
    preregistration_id: str
    hypothesis_set_id: str
    dataset_id: str
    gates: tuple
    blockers: tuple
    available_bars: int
    required_bars: int
    available_fills: int
    required_fills: int
    limitations: tuple
    production_isolation: bool = True
    is_production_ready: bool = False
    final_status: str = "BLOCKED"

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ReadinessError("schema_version must be %r"
                                 % SCHEMA_VERSION)
        if self.report_type != REPORT_TYPE:
            raise ReadinessError("report_type must be %r" % REPORT_TYPE)
        if self.identity_algorithm != IDENTITY_ALGORITHM:
            raise ReadinessError("identity_algorithm must be %r"
                                 % IDENTITY_ALGORITHM)
        gates = self.gates
        if not isinstance(gates, (tuple, list)):
            raise ReadinessError("gates must be a tuple/list")
        gates = tuple(gates)
        object.__setattr__(self, "gates", gates)
        for item in gates:
            if not isinstance(item, GateVerdict):
                raise ReadinessError(
                    "gates must be GateVerdict, got %s"
                    % type(item).__name__)
        object.__setattr__(self, "blockers",
                           _str_tuple(self.blockers, "blockers"))
        for field in ("available_bars", "required_bars",
                      "available_fills", "required_fills"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ReadinessError(
                    "%s must be int" % field)
        object.__setattr__(self, "limitations",
                           _str_tuple(self.limitations, "limitations"))
        if self.production_isolation is not True:
            raise ReadinessError("production_isolation must be True")
        if self.is_production_ready is not False:
            raise ReadinessError("is_production_ready must be False")
        if self.final_status not in FINAL_STATUS:
            raise ReadinessError("final_status must be one of %r"
                                 % (FINAL_STATUS,))
        if self.final_status == "READINESS_VERIFIED" and self.blockers:
            raise ReadinessError(
                "READINESS_VERIFIED forbids blockers")
        if (self.final_status == "READINESS_VERIFIED" and any(
                g.status != "VERIFIED" for g in gates)):
            raise ReadinessError(
                "READINESS_VERIFIED requires every gate VERIFIED")
        expected = content_hash(self._identity_payload())
        if self.report_id != expected:
            raise ReadinessError(
                "report_id mismatch (expected %s)" % expected)

    @staticmethod
    def _identity_payload_for(*, preregistration_id,
                              hypothesis_set_id, dataset_id, gates,
                              blockers, available_bars, required_bars,
                              available_fills, required_fills,
                              limitations, final_status):
        return {
            "schema_version": SCHEMA_VERSION,
            "report_type": REPORT_TYPE,
            "preregistration_id": preregistration_id,
            "hypothesis_set_id": hypothesis_set_id,
            "dataset_id": dataset_id,
            "gates": [g.to_dict() for g in tuple(gates)],
            "blockers": list(blockers),
            "available_bars": available_bars,
            "required_bars": required_bars,
            "available_fills": available_fills,
            "required_fills": required_fills,
            "limitations": list(limitations),
            "production_isolation": True,
            "is_production_ready": False,
            "final_status": final_status,
        }

    def _identity_payload(self):
        return self._identity_payload_for(
            preregistration_id=self.preregistration_id,
            hypothesis_set_id=self.hypothesis_set_id,
            dataset_id=self.dataset_id, gates=self.gates,
            blockers=self.blockers, available_bars=self.available_bars,
            required_bars=self.required_bars,
            available_fills=self.available_fills,
            required_fills=self.required_fills,
            limitations=self.limitations,
            final_status=self.final_status)

    @classmethod
    def create(cls, *, preregistration_id, hypothesis_set_id,
               dataset_id, gates, available_bars, required_bars,
               available_fills, required_fills, limitations,
               is_production_ready=False):
        """Build a report; final status derives from the gates."""
        gates = tuple(gates)
        blockers = tuple(
            "%s=%s" % (g.gate_id, g.status) for g in gates
            if g.status != "VERIFIED")
        final = "READINESS_VERIFIED" if not blockers else "BLOCKED"
        if is_production_ready is not False:
            raise ReadinessError("is_production_ready must be False")
        report_id = content_hash(cls._identity_payload_for(
            preregistration_id=preregistration_id,
            hypothesis_set_id=hypothesis_set_id,
            dataset_id=dataset_id, gates=gates, blockers=blockers,
            available_bars=available_bars, required_bars=required_bars,
            available_fills=available_fills, required_fills=required_fills,
            limitations=limitations, final_status=final))
        return cls(
            schema_version=SCHEMA_VERSION,
            report_type=REPORT_TYPE, report_id=report_id,
            identity_algorithm=IDENTITY_ALGORITHM,
            preregistration_id=preregistration_id,
            hypothesis_set_id=hypothesis_set_id,
            dataset_id=dataset_id, gates=gates, blockers=blockers,
            available_bars=available_bars, required_bars=required_bars,
            available_fills=available_fills,
            required_fills=required_fills,
            limitations=tuple(limitations),
            production_isolation=True, is_production_ready=False,
            final_status=final)

    def gate(self, gate_id):
        """Return the verdict for one gate (KeyError when absent)."""
        for item in self.gates:
            if item.gate_id == gate_id:
                return item
        raise KeyError(gate_id)

    def to_dict(self):
        body = self._identity_payload()
        ordered = {
            "schema_version": self.schema_version,
            "report_type": self.report_type,
            "report_id": self.report_id,
            "identity_algorithm": self.identity_algorithm,
        }
        ordered.update(body)
        return ordered
