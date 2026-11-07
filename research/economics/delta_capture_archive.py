"""Tamper-evident persistence for genuine Delta order-book capture sessions.

This layer stores the exact decoded provider frames used to build a friction
artifact. It does not create venue provenance: the caller must already have a
LIVE_CAPTURE identity and a validated capture session. Frames are canonicalized
and hash-chained so replay can prove that the evidence was not silently edited.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.economics.market_friction_capture import CaptureIdentity

SCHEMA_VERSION = 1
_GENESIS = "0" * 64


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False) + "\n").encode("utf-8")


def frame_hash(frame: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(frame)).hexdigest()


def chain_hash(previous_hash: str, frame: Mapping[str, Any]) -> str:
    if len(previous_hash) != 64:
        raise ValueError("previous hash must be SHA-256 hex")
    payload = previous_hash.encode("ascii") + b"\n" + _canonical(frame)
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class CaptureArchive:
    schema_version: int
    identity: dict[str, Any]
    frames: tuple[dict[str, Any], ...]
    frame_hashes: tuple[str, ...]
    chain_hashes: tuple[str, ...]
    final_chain_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity,
            "frames": list(self.frames),
            "frame_hashes": list(self.frame_hashes),
            "chain_hashes": list(self.chain_hashes),
            "final_chain_hash": self.final_chain_hash,
        }


def build_archive(identity: CaptureIdentity, frames: Iterable[Mapping[str, Any]]) -> CaptureArchive:
    identity.validate()
    normalized = tuple(dict(f) for f in frames)
    if not normalized:
        raise ValueError("capture archive cannot be empty")
    frame_hashes: list[str] = []
    chain_hashes: list[str] = []
    previous = _GENESIS
    for frame in normalized:
        if not isinstance(frame, Mapping):
            raise ValueError("capture frame must be an object")
        fh = frame_hash(frame)
        ch = chain_hash(previous, frame)
        frame_hashes.append(fh)
        chain_hashes.append(ch)
        previous = ch
    return CaptureArchive(
        schema_version=SCHEMA_VERSION,
        identity={
            "venue": identity.venue,
            "environment": identity.environment,
            "symbol": identity.symbol,
            "source_endpoint": identity.source_endpoint,
            "transport": identity.transport,
            "capture_id": identity.capture_id,
        },
        frames=normalized,
        frame_hashes=tuple(frame_hashes),
        chain_hashes=tuple(chain_hashes),
        final_chain_hash=previous,
    )


def write_archive(archive: CaptureArchive, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(archive.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_and_verify(path: str | Path) -> CaptureArchive:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported capture archive schema")
    identity = CaptureIdentity(**raw["identity"])
    identity.validate()
    frames = tuple(dict(x) for x in raw.get("frames", []))
    expected_fh = tuple(raw.get("frame_hashes", []))
    expected_ch = tuple(raw.get("chain_hashes", []))
    if len(frames) != len(expected_fh) or len(frames) != len(expected_ch) or not frames:
        raise ValueError("capture archive frame/hash lengths are inconsistent")
    actual_fh: list[str] = []
    actual_ch: list[str] = []
    previous = _GENESIS
    for frame in frames:
        fh = frame_hash(frame)
        ch = chain_hash(previous, frame)
        actual_fh.append(fh)
        actual_ch.append(ch)
        previous = ch
    if tuple(actual_fh) != expected_fh or tuple(actual_ch) != expected_ch:
        raise ValueError("capture archive integrity verification failed")
    if raw.get("final_chain_hash") != previous:
        raise ValueError("capture archive final chain hash mismatch")
    return CaptureArchive(
        schema_version=SCHEMA_VERSION,
        identity=identity.__dict__ if hasattr(identity, "__dict__") else {
            "venue": identity.venue, "environment": identity.environment,
            "symbol": identity.symbol, "source_endpoint": identity.source_endpoint,
            "transport": identity.transport, "capture_id": identity.capture_id,
        },
        frames=frames, frame_hashes=tuple(actual_fh),
        chain_hashes=tuple(actual_ch), final_chain_hash=previous,
    )


def verify_archive_matches_artifact(archive: CaptureArchive, artifact: Any) -> None:
    """Verify that an evidence artifact is derived from exactly these frames.

    This compares the canonical top-of-book observations produced by the same
    Phase-76 state machine, rather than trusting a caller-provided sample list.
    The artifact must have the same venue identity and sequence-derived sample
    timestamps/prices. Provenance is not upgraded by this check.
    """
    from research.economics.delta_ws_friction_capture import DeltaOrderbookState

    if artifact.provenance_status != "REAL":
        raise ValueError("artifact provenance must already be REAL")
    if archive.identity["symbol"] != artifact.symbol:
        raise ValueError("archive/artifact symbol mismatch")
    if archive.identity["venue"] != artifact.venue:
        raise ValueError("archive/artifact venue mismatch")
    state = DeltaOrderbookState(artifact.symbol)
    observations = []
    for frame in archive.frames:
        obs = state.apply(frame)
        if obs is not None:
            observations.append(obs.to_sample())
    if len(observations) != len(artifact.samples):
        raise ValueError("archive/artifact observation count mismatch")
    for actual, expected in zip(observations, artifact.samples):
        if (actual["symbol"], actual["timestamp_ms"], actual["best_bid"], actual["best_ask"]) != (
            expected["symbol"], expected["timestamp_ms"], expected["best_bid"], expected["best_ask"]
        ):
            raise ValueError("archive/artifact observation mismatch")
