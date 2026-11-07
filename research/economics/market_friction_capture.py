"""Fail-closed recorder for genuine venue market-friction observations.

This module records observations supplied by an actual venue transport. It
never performs network access itself and never upgrades fixtures/replays to
REAL. A caller must explicitly identify the transport as a LIVE_CAPTURE and
provide the venue endpoint/environment identity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research.economics.market_friction_evidence import (
    MarketFrictionEvidenceArtifact,
    build_artifact,
    write_artifact,
)


@dataclass(frozen=True, slots=True)
class CaptureIdentity:
    venue: str
    environment: str
    symbol: str
    source_endpoint: str
    transport: str
    capture_id: str

    def validate(self) -> None:
        if self.environment not in {"PRODUCTION", "SANDBOX"}:
            raise ValueError("capture environment must be PRODUCTION or SANDBOX")
        if self.transport != "LIVE_CAPTURE":
            raise ValueError("market-friction evidence requires LIVE_CAPTURE transport")
        if not self.venue or not self.symbol or not self.source_endpoint or not self.capture_id:
            raise ValueError("capture identity is incomplete")


class MarketFrictionCapture:
    """Collect strictly ordered book/fill observations from a real transport."""

    def __init__(self, identity: CaptureIdentity, *, alignment_ms: int = 1000):
        identity.validate()
        if alignment_ms < 0:
            raise ValueError("alignment_ms must be non-negative")
        self.identity = identity
        self.alignment_ms = alignment_ms
        self._samples: list[dict[str, Any]] = []
        self._closed = False

    @property
    def samples(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._samples)

    def add(self, *, timestamp_ms: int, best_bid: object, best_ask: object,
            fill: Mapping[str, Any] | None = None) -> None:
        if self._closed:
            raise RuntimeError("capture is closed")
        ts = int(timestamp_ms)
        if ts <= 0:
            raise ValueError("timestamp_ms must be positive")
        if self._samples and ts <= self._samples[-1]["timestamp_ms"]:
            raise ValueError("capture timestamps must be strictly ascending")
        row: dict[str, Any] = {
            "symbol": self.identity.symbol,
            "timestamp_ms": ts,
            "best_bid": str(best_bid),
            "best_ask": str(best_ask),
        }
        if fill is not None:
            row["fill"] = dict(fill)
        # build_artifact is the canonical validator; use a one-row validation
        # here so malformed observations never enter the in-memory capture.
        build_artifact(
            samples=[row], symbol=self.identity.symbol,
            captured_at="capture-validation", source_endpoint=self.identity.source_endpoint,
            venue=self.identity.venue, alignment_ms=self.alignment_ms,
            provenance_status="REAL",
        )
        self._samples.append(row)

    def finalize(self, *, captured_at: str | None = None) -> MarketFrictionEvidenceArtifact:
        if self._closed:
            raise RuntimeError("capture is already closed")
        self._closed = True
        if not self._samples:
            raise ValueError("cannot finalize empty market-friction capture")
        return build_artifact(
            samples=self._samples, symbol=self.identity.symbol,
            captured_at=captured_at or datetime.now(timezone.utc).isoformat(),
            source_endpoint=self.identity.source_endpoint, venue=self.identity.venue,
            alignment_ms=self.alignment_ms, provenance_status="REAL",
        )

    def write(self, path: str | Path, *, captured_at: str | None = None) -> MarketFrictionEvidenceArtifact:
        artifact = self.finalize(captured_at=captured_at)
        write_artifact(artifact, path)
        return artifact


def capture_manifest(artifact: MarketFrictionEvidenceArtifact, identity: CaptureIdentity) -> dict[str, Any]:
    identity.validate()
    if artifact.provenance_status != "REAL":
        raise ValueError("capture manifest requires REAL artifact")
    return {
        "schema_version": 1,
        "capture_id": identity.capture_id,
        "venue": identity.venue,
        "environment": identity.environment,
        "symbol": identity.symbol,
        "source_endpoint": identity.source_endpoint,
        "transport": identity.transport,
        "evidence_sha256": artifact.evidence_sha256,
        "start_timestamp_ms": artifact.start_timestamp_ms,
        "end_timestamp_ms": artifact.end_timestamp_ms,
        "sample_count": len(artifact.samples),
    }


def write_capture_manifest(manifest: Mapping[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
