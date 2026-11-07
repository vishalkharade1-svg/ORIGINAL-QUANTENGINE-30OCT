"""Immutable funding-evidence capture and replay boundary.

This module deliberately separates *capture machinery* from *genuine venue
capture*. A fixture can exercise the machinery, but it can never be marked
as venue evidence merely because it has the right schema.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.execution.economics import FundingEvent, FundingSchedule


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FundingEvidenceArtifact:
    venue: str
    symbol: str
    resolution: str
    start: int
    end: int
    events: tuple[dict[str, Any], ...]
    market_data_sha256: str
    funding_evidence_sha256: str
    provenance_status: str
    source_endpoint: str
    captured_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "venue": self.venue,
            "symbol": self.symbol,
            "resolution": self.resolution,
            "start": self.start,
            "end": self.end,
            "events": list(self.events),
            "market_data_sha256": self.market_data_sha256,
            "funding_evidence_sha256": self.funding_evidence_sha256,
            "provenance_status": self.provenance_status,
            "source_endpoint": self.source_endpoint,
            "captured_at": self.captured_at,
        }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_payload(request: Mapping[str, Any], events: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        {"request": dict(request), "events": events},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_artifact(
    evidence: Mapping[str, Any],
    *,
    market_data_path: str | Path,
    provenance_status: str,
    captured_at: str,
) -> FundingEvidenceArtifact:
    """Bind strict venue funding evidence to the exact market-data bytes."""
    if provenance_status not in {"REAL", "FIXTURE", "UNKNOWN"}:
        raise ValueError("invalid provenance_status")
    request = evidence.get("request")
    events = evidence.get("events")
    if not isinstance(request, Mapping) or not isinstance(events, list) or not events:
        raise ValueError("funding evidence must contain request and non-empty events")
    if str(evidence.get("sha256", "")) != hashlib.sha256(
        _canonical_payload(request, events)
    ).hexdigest():
        raise ValueError("funding evidence fingerprint mismatch")
    symbol = str(request.get("symbol", ""))
    if not symbol.startswith("FUNDING:"):
        raise ValueError("funding request must use FUNDING:<symbol>")
    normalized = []
    for row in events:
        if not isinstance(row, Mapping):
            raise ValueError("funding event must be an object")
        normalized.append({"time": int(row["time"]), "rate": float(row["rate"])})
    if any(a["time"] >= b["time"] for a, b in zip(normalized, normalized[1:])):
        raise ValueError("funding events must be strictly ordered")
    return FundingEvidenceArtifact(
        venue="delta",
        symbol=symbol.removeprefix("FUNDING:"),
        resolution=str(request["resolution"]),
        start=int(request["start"]),
        end=int(request["end"]),
        events=tuple(normalized),
        market_data_sha256=sha256_file(market_data_path),
        funding_evidence_sha256=str(evidence["sha256"]),
        provenance_status=provenance_status,
        source_endpoint="/v2/history/candles",
        captured_at=str(captured_at),
    )


def write_artifact(artifact: FundingEvidenceArtifact, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_and_verify(path: str | Path, *, market_data_path: str | Path) -> FundingEvidenceArtifact:
    """Load a captured artifact and verify its market-data binding."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported funding evidence schema")
    actual_market_hash = sha256_file(market_data_path)
    if raw.get("market_data_sha256") != actual_market_hash:
        raise ValueError("market-data evidence hash mismatch")
    events = raw.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("funding artifact has no events")
    if any(int(a["time"]) >= int(b["time"]) for a, b in zip(events, events[1:])):
        raise ValueError("funding artifact events are not strictly ordered")
    request = {
        "symbol": "FUNDING:" + str(raw["symbol"]),
        "resolution": raw["resolution"],
        "start": int(raw["start"]),
        "end": int(raw["end"]),
    }
    expected_fingerprint = hashlib.sha256(
        _canonical_payload(request, events)
    ).hexdigest()
    if raw.get("funding_evidence_sha256") != expected_fingerprint:
        raise ValueError("funding evidence fingerprint mismatch")
    artifact = FundingEvidenceArtifact(
        venue=str(raw["venue"]), symbol=str(raw["symbol"]),
        resolution=str(raw["resolution"]), start=int(raw["start"]),
        end=int(raw["end"]), events=tuple(events),
        market_data_sha256=str(raw["market_data_sha256"]),
        funding_evidence_sha256=str(raw["funding_evidence_sha256"]),
        provenance_status=str(raw["provenance_status"]),
        source_endpoint=str(raw["source_endpoint"]),
        captured_at=str(raw["captured_at"]),
    )
    return artifact


def to_schedule(artifact: FundingEvidenceArtifact) -> FundingSchedule:
    if artifact.provenance_status != "REAL":
        raise ValueError("funding artifact is not genuine venue evidence")
    source = "delta:/v2/history/candles#" + artifact.funding_evidence_sha256
    return FundingSchedule(
        (FundingEvent(int(row["time"]), float(row["rate"]), source)
         for row in artifact.events),
        coverage_start=artifact.start,
        coverage_end=artifact.end,
    )
