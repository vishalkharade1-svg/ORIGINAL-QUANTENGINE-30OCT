"""Executable Delta public-WebSocket LIVE_CAPTURE runner.

This module is deliberately fail-closed: only a real websocket transport may
produce a REAL market-friction artifact. Socket failures, provider errors,
sequence gaps, missing snapshots, or insufficient observations produce no
REAL evidence files.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, AsyncIterable, Mapping

from research.economics.delta_capture_archive import (
    build_archive,
    verify_archive_matches_artifact,
    write_archive,
)
from research.economics.delta_friction_capture_session import DeltaFrictionCaptureSession
from research.economics.market_friction_capture import (
    CaptureIdentity,
    capture_manifest,
    write_capture_manifest,
)

DEFAULT_INDIA_ENDPOINT = "wss://public-socket.india.delta.exchange"
DEFAULT_GLOBAL_ENDPOINT = "wss://public-socket.delta.exchange"
DEFAULT_INDIA_TESTNET_ENDPOINT = "wss://socket-ind-pub.testnet.deltaex.org"


def subscription(symbol: str) -> dict[str, Any]:
    if not symbol or symbol == "all":
        raise ValueError("ob_updates LIVE_CAPTURE requires one explicit symbol")
    return {
        "type": "subscribe",
        "payload": {"channels": [{"name": "ob_updates", "symbols": [symbol]}]},
    }


def decode_frame(raw: str | bytes) -> Mapping[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, Mapping):
        raise ValueError("Delta websocket frame must decode to an object")
    return value


def process_frames(
    frames: list[Mapping[str, Any]],
    *,
    identity: CaptureIdentity,
    alignment_ms: int = 1000,
    captured_at: str | None = None,
    min_observations: int = 2,
) -> tuple[Any, Any, dict[str, Any]]:
    """Build artifact/archive from provider frames and verify their exact binding."""
    if not frames:
        raise ValueError("no websocket frames captured")
    session = DeltaFrictionCaptureSession(identity, alignment_ms=alignment_ms)
    for frame in frames:
        session.ingest(frame)
    if session.stats.observations_emitted < min_observations:
        raise ValueError(
            f"insufficient orderbook observations: {session.stats.observations_emitted} < {min_observations}"
        )
    artifact = session.finalize(captured_at=captured_at)
    archive = build_archive(identity, frames)
    verify_archive_matches_artifact(archive, artifact)
    manifest = capture_manifest(artifact, identity)
    manifest["messages_seen"] = session.stats.messages_seen
    manifest["observations_emitted"] = session.stats.observations_emitted
    manifest["first_sequence"] = session.stats.first_sequence
    manifest["last_sequence"] = session.stats.last_sequence
    manifest["continuity_failures"] = session.stats.continuity_failures
    return artifact, archive, manifest


async def capture_live(
    *,
    endpoint: str,
    symbol: str,
    duration_seconds: float,
    identity: CaptureIdentity,
    alignment_ms: int = 1000,
    min_observations: int = 2,
) -> list[Mapping[str, Any]]:
    """Capture decoded frames from the real Delta public websocket."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    identity.validate()
    if identity.source_endpoint != endpoint:
        raise ValueError("identity endpoint must equal capture websocket endpoint")

    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - dependency is pinned in requirements
        raise RuntimeError("websockets package is required for LIVE_CAPTURE") from exc

    frames: list[Mapping[str, Any]] = []
    deadline = time.monotonic() + duration_seconds
    async with websockets.connect(
        endpoint,
        ping_interval=20,
        ping_timeout=5,
        close_timeout=5,
        max_size=8 * 1024 * 1024,
    ) as ws:
        await ws.send(json.dumps(subscription(symbol), separators=(",", ":")))
        while time.monotonic() < deadline:
            timeout = max(0.1, deadline - time.monotonic())
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                break
            frame = decode_frame(raw)
            if frame.get("type") == "heartbeat":
                continue
            if frame.get("type") == "subscriptions":
                continue
            if frame.get("type") == "ob_updates" or frame.get("action") in {"snapshot", "update", "error"}:
                frames.append(frame)
            if frame.get("type") == "ob_updates" and frame.get("action") == "error":
                raise RuntimeError(f"Delta ob_updates provider error: {dict(frame)}")

    if not frames:
        raise RuntimeError("Delta websocket returned no ob_updates frames")
    return frames


def write_result(
    *,
    output_dir: str | Path,
    artifact: Any,
    archive: Any,
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifact_path = out / "market_friction_evidence.json"
    archive_path = out / "delta_ob_updates_archive.json"
    manifest_path = out / "capture_manifest.json"
    from research.economics.market_friction_evidence import write_artifact
    write_artifact(artifact, artifact_path)
    write_archive(archive, archive_path)
    write_capture_manifest(manifest, manifest_path)
    return {
        "artifact": str(artifact_path),
        "archive": str(archive_path),
        "manifest": str(manifest_path),
    }


async def run_cli(args: argparse.Namespace) -> dict[str, str]:
    endpoint = args.endpoint
    identity = CaptureIdentity(
        venue="delta",
        environment=args.environment,
        symbol=args.symbol,
        source_endpoint=endpoint,
        transport="LIVE_CAPTURE",
        capture_id=args.capture_id,
    )
    frames = await capture_live(
        endpoint=endpoint,
        symbol=args.symbol,
        duration_seconds=args.duration,
        identity=identity,
        alignment_ms=args.alignment_ms,
        min_observations=args.min_observations,
    )
    captured_at = datetime.now(timezone.utc).isoformat()
    artifact, archive, manifest = process_frames(
        frames,
        identity=identity,
        alignment_ms=args.alignment_ms,
        captured_at=captured_at,
        min_observations=args.min_observations,
    )
    return write_result(output_dir=args.output_dir, artifact=artifact, archive=archive, manifest=manifest)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Capture genuine Delta ob_updates market-friction evidence")
    p.add_argument("--symbol", default="BTCUSD")
    p.add_argument("--endpoint", default=DEFAULT_INDIA_ENDPOINT)
    p.add_argument("--environment", choices=("PRODUCTION", "SANDBOX"), default="PRODUCTION")
    p.add_argument("--capture-id", required=True)
    p.add_argument("--duration", type=float, default=30.0)
    p.add_argument("--alignment-ms", type=int, default=1000)
    p.add_argument("--min-observations", type=int, default=10)
    p.add_argument("--output-dir", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = asyncio.run(run_cli(args))
    except Exception as exc:
        # No evidence is written before the full verification path succeeds.
        print(f"LIVE_CAPTURE FAILED CLOSED: {type(exc).__name__}: {exc}")
        return 2
    print(json.dumps({"status": "REAL_CAPTURE_COMPLETE", "paths": paths}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
