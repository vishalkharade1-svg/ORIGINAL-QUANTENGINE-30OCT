"""Fail-closed certification of authenticated execution economics.

This gate does not capture venue data. It answers a narrower question:
are independently captured fee, funding, market-friction, and authenticated
fill artifacts mutually consistent enough to be admitted to an OOS economic
certification?

No artifact is upgraded to REAL here. Provenance must already be REAL at each
input boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ExecutionEconomicsCertification:
    status: str
    venue: str
    environment: str
    symbol: str
    start_timestamp_ms: int | None
    end_timestamp_ms: int | None
    reasons: tuple[str, ...]
    fee_evidence_sha256: str | None = None
    funding_evidence_sha256: str | None = None
    friction_evidence_sha256: str | None = None
    fill_evidence_sha256: str | None = None
    binding_sha256: str | None = None

    @property
    def certifiable(self) -> bool:
        return self.status == "CERTIFIABLE"


def _status(obj: Any) -> str:
    return str(getattr(obj, "provenance_status", "UNKNOWN"))


def _sha(obj: Any, *names: str) -> str | None:
    for name in names:
        if isinstance(obj, Mapping):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)
        if value:
            return str(value)
    return None


def _interval(obj: Any) -> tuple[int | None, int | None]:
    start = getattr(obj, "start_timestamp_ms", None)
    end = getattr(obj, "end_timestamp_ms", None)
    if start is not None and end is not None:
        return int(start), int(end)
    start = getattr(obj, "start", None)
    end = getattr(obj, "end", None)
    if start is not None and end is not None:
        # Funding timestamps are venue epoch timestamps; caller should supply
        # the same unit for the requested OOS interval rather than guessing.
        return int(start), int(end)
    return None, None


def assess(*, fee_artifact: Any = None, funding_artifact: Any = None,
           friction_artifact: Any = None, fill_artifact: Any = None,
           fill_friction_binding: Mapping[str, Any] | None = None,
           venue: str = "delta", environment: str | None = None,
           symbol: str | None = None,
           oos_start: int | None = None, oos_end: int | None = None,
           require_historical_fee_window: bool = True) -> ExecutionEconomicsCertification:
    """Assess whether captured economics can enter an OOS certification.

    All timestamps supplied by the caller must use milliseconds. Funding
    artifacts expose venue timestamps in their native unit; therefore a
    funding coverage check is performed only when the artifact explicitly
    exposes ``coverage_start_ms``/``coverage_end_ms``. Otherwise the gate
    blocks historical certification rather than guessing units.
    """
    reasons: list[str] = []

    artifacts = {
        "fee": fee_artifact,
        "funding": funding_artifact,
        "friction": friction_artifact,
        "fill": fill_artifact,
    }
    for name, artifact in artifacts.items():
        if artifact is None:
            reasons.append(f"{name} evidence is missing")
        elif _status(artifact) != "REAL":
            reasons.append(f"{name} evidence is not genuine venue evidence")

    if symbol is None:
        reasons.append("certification symbol is required")

    # Exact identity binding. Never infer a symbol or environment from a
    # neighboring artifact.
    if symbol is not None:
        for name, artifact in artifacts.items():
            if artifact is None:
                continue
            actual = getattr(artifact, "symbol", None)
            if actual is not None and str(actual) != str(symbol):
                reasons.append(f"{name} symbol mismatch")

    if environment is not None and fill_artifact is not None:
        actual_env = getattr(fill_artifact, "environment", None)
        if actual_env is not None and str(actual_env) != str(environment):
            reasons.append("fill environment mismatch")

    # Venue must agree everywhere it is declared.
    for name, artifact in artifacts.items():
        if artifact is None:
            continue
        actual_venue = getattr(artifact, "venue", None)
        if actual_venue is not None and str(actual_venue).lower() != str(venue).lower():
            reasons.append(f"{name} venue mismatch")

    fee_sha = _sha(fee_artifact, "evidence_sha256")
    funding_sha = _sha(funding_artifact, "funding_evidence_sha256", "evidence_sha256")
    friction_sha = _sha(friction_artifact, "evidence_sha256")
    fill_sha = _sha(fill_artifact, "evidence_sha256")

    if require_historical_fee_window and fee_artifact is not None and oos_start is not None and oos_end is not None:
        fs = getattr(fee_artifact, "coverage_start_ms", None)
        fe = getattr(fee_artifact, "coverage_end_ms", None)
        if fs is None or fe is None:
            reasons.append("historical OOS fee coverage window is missing")
        elif int(fs) > int(oos_start) or int(fe) < int(oos_end):
            reasons.append("fee evidence does not cover the requested OOS interval")

    # Funding coverage is accepted only if the artifact exposes an explicitly
    # millisecond-normalized coverage window. Never reinterpret native units.
    if funding_artifact is not None and oos_start is not None and oos_end is not None:
        fs = getattr(funding_artifact, "coverage_start_ms", None)
        fe = getattr(funding_artifact, "coverage_end_ms", None)
        if fs is None or fe is None:
            reasons.append("funding coverage is not exposed in milliseconds")
        elif int(fs) > int(oos_start) or int(fe) < int(oos_end):
            reasons.append("funding evidence does not cover the requested OOS interval")

    if friction_artifact is not None and oos_start is not None and oos_end is not None:
        fs, fe = _interval(friction_artifact)
        if fs is None or fe is None:
            reasons.append("market-friction coverage interval is missing")
        elif fs > int(oos_start) or fe < int(oos_end):
            reasons.append("market-friction evidence does not cover the requested OOS interval")

    if fill_artifact is not None and oos_start is not None and oos_end is not None:
        fills = getattr(fill_artifact, "fills", ())
        if not fills:
            reasons.append("authenticated fill ledger is empty")
        else:
            for fill in fills:
                ts = int(fill["timestamp"])
                if ts < int(oos_start) or ts > int(oos_end):
                    reasons.append(f"fill {fill['fill_id']} lies outside requested OOS interval")

    if fill_friction_binding is None:
        reasons.append("authenticated fills are not bound to contemporaneous market friction")
    else:
        if fill_friction_binding.get("status") != "MATCHED":
            reasons.append("fill/friction reconciliation is not MATCHED")
        if fill_sha and str(fill_friction_binding.get("fill_evidence_sha256", fill_sha)) != fill_sha:
            reasons.append("fill/friction binding references a different fill artifact")
        if friction_sha and str(fill_friction_binding.get("friction_evidence_sha256", friction_sha)) != friction_sha:
            reasons.append("fill/friction binding references a different friction artifact")
        if int(fill_friction_binding.get("fill_count", 0)) <= 0:
            reasons.append("fill/friction binding contains no matched fills")

    # A certificate must have all four immutable fingerprints. This prevents a
    # partially reconstructed certificate from being mistaken for evidence.
    if not fee_sha:
        reasons.append("fee evidence fingerprint is missing")
    if not funding_sha:
        reasons.append("funding evidence fingerprint is missing")
    if not friction_sha:
        reasons.append("market-friction evidence fingerprint is missing")
    if not fill_sha:
        reasons.append("fill evidence fingerprint is missing")

    return ExecutionEconomicsCertification(
        status="CERTIFIABLE" if not reasons else "BLOCKED",
        venue=str(venue),
        environment=str(environment or getattr(fill_artifact, "environment", "UNKNOWN")),
        symbol=str(symbol or getattr(fill_artifact, "symbol", "")),
        start_timestamp_ms=oos_start,
        end_timestamp_ms=oos_end,
        reasons=tuple(dict.fromkeys(reasons)),
        fee_evidence_sha256=fee_sha,
        funding_evidence_sha256=funding_sha,
        friction_evidence_sha256=friction_sha,
        fill_evidence_sha256=fill_sha,
        binding_sha256=_sha(fill_friction_binding, "binding_sha256") if fill_friction_binding else None,
    )
