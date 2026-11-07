"""Bounded, credential-free capture of Delta public WebSocket evidence.

The utility never authenticates or places orders.  When ``--output`` is used,
it writes a JSON evidence bundle containing public frames, a receipt ordinal,
and capture metadata.  The bundle intentionally does not claim that a frame
is final, sequenced, or gap-free merely because it was received.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
import hashlib
from collections import Counter


CHANNELS = ("trades", "candlestick_1m", "ob_l1", "ob_l2", "ticker")


def capture(
    endpoint: str,
    symbol: str,
    timeout: float,
    *,
    max_frames: int = 500,
    channels: tuple[str, ...] = CHANNELS,
    include_control_frames: bool = False,
) -> dict[str, Any]:
    """Collect a bounded, ordered public-frame evidence bundle."""
    from websockets.sync.client import connect

    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if max_frames <= 0:
        raise ValueError("max_frames must be positive")
    if not channels or any(channel not in CHANNELS for channel in channels):
        raise ValueError("channels must be a non-empty subset of supported public channels")
    started = time.time()
    records: list[dict[str, Any]] = []
    control_frames = 0
    malformed_frames = 0
    with connect(endpoint, open_timeout=min(timeout, 15)) as socket:
        socket.send(json.dumps({
            "type": "subscribe",
            "payload": {"channels": [
                {"name": channel, "symbols": [symbol]} for channel in channels
            ]},
        }))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(records) < max_frames:
            try:
                raw = socket.recv(timeout=max(0.1, deadline - time.monotonic()))
                frame = json.loads(raw)
            except TimeoutError:
                break
            except (TypeError, ValueError, json.JSONDecodeError):
                malformed_frames += 1
                continue
            if not isinstance(frame, dict):
                malformed_frames += 1
                continue
            channel = frame.get("type")
            if channel not in channels:
                control_frames += 1
                if include_control_frames:
                    records.append({
                        "receipt_ordinal": len(records) + 1,
                        "receipt_unix_ns": time.time_ns(),
                        "frame": frame,
                        "classification": "control_or_unrequested",
                    })
                continue
            records.append({
                "receipt_ordinal": len(records) + 1,
                "receipt_unix_ns": time.time_ns(),
                "frame": frame,
                "classification": "requested_public_data",
            })
    observed = sorted({record["frame"]["type"] for record in records})
    bundle = {
        "schema": "quantengine.delta-public-capture.v1",
        "endpoint": endpoint,
        "symbol": symbol,
        "started_unix": started,
        "timeout_seconds": timeout,
        "max_frames": max_frames,
        "requested_channels": list(channels),
        "include_control_frames": include_control_frames,
        "frames": records,
        "observed_channels": observed,
        "control_frames": control_frames,
        "malformed_frames": malformed_frames,
        "capture_complete": len(records) < max_frames,
        "limitations": [
            "Public receipt order is not a documented exchange sequence.",
            "No candle frame is considered closed without an evidenced finality rule.",
            "Absence of frames during this bounded capture is not proof of channel absence.",
        ],
    }
    bundle["content_identity"] = _content_identity(bundle)
    return bundle


def _content_identity(bundle: dict[str, Any]) -> str:
    payload = {
        "schema": bundle.get("schema"),
        "endpoint": bundle.get("endpoint"),
        "symbol": bundle.get("symbol"),
        "requested_channels": bundle.get("requested_channels"),
        "include_control_frames": bundle.get("include_control_frames"),
        "frames": [
            {
                "receipt_ordinal": record.get("receipt_ordinal"),
                "classification": record.get("classification"),
                "frame": record.get("frame"),
            }
            for record in bundle.get("frames", [])
            if isinstance(record, dict)
        ],
    }
    import json as _json
    encoded = _json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def control_frame_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic control-frame type/count metadata."""
    counts = Counter()
    for record in bundle.get("frames", []):
        if not isinstance(record, dict):
            continue
        if record.get("classification") != "control_or_unrequested":
            continue
        frame = record.get("frame")
        if isinstance(frame, dict):
            counts[str(frame.get("type", "UNKNOWN"))] += 1
    return {
        "total": sum(counts.values()),
        "types": dict(sorted(counts.items())),
    }


def deterministic_fixture(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build a redacted, deterministic fixture from a live capture bundle.

    Local receipt clocks and capture start time are intentionally removed.
    Public frame payloads are retained because they contain no credentials.
    The result is a fixture for parser/evidence regression, not authenticity.
    """
    frames = []
    for record in bundle.get("frames", []):
        if not isinstance(record, dict) or not isinstance(record.get("frame"), dict):
            continue
        frames.append({
            "receipt_ordinal": record.get("receipt_ordinal"),
            "classification": record.get("classification"),
            "frame": record.get("frame"),
        })
    fixture = {
        "schema": "quantengine.delta-public-capture-fixture.v1",
        "source_schema": bundle.get("schema"),
        "endpoint": bundle.get("endpoint"),
        "symbol": bundle.get("symbol"),
        "requested_channels": bundle.get("requested_channels", []),
        "include_control_frames": bool(bundle.get("include_control_frames")),
        "frames": frames,
        "control_frame_summary": control_frame_summary(bundle),
        "limitations": [
            "Deterministic redaction removes local receipt-clock timestamps.",
            "Public frame payloads are retained for parser/evidence regression.",
            "Fixture identity is content integrity only, not venue authenticity.",
        ],
    }
    fixture["fixture_identity"] = _fixture_identity(fixture)
    return fixture


def _fixture_identity(fixture: dict[str, Any]) -> str:
    payload = dict(fixture)
    payload.pop("fixture_identity", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def write_bundle(bundle: dict[str, Any], output: str, *, deterministic: bool = False) -> None:
    """Write a capture bundle or deterministic redacted fixture."""
    payload = deterministic_fixture(bundle) if deterministic else bundle
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture_reconnect_observation(
    endpoint: str,
    symbol: str,
    timeout: float,
    *,
    channels: tuple[str, ...],
    max_frames: int,
    sessions: int,
) -> dict[str, Any]:
    """Open bounded public sessions serially to evidence client re-subscribe.

    Each session is deliberately closed by this client before the next begins.
    It is not a simulation of a provider outage and must not be presented as
    server-initiated reconnect evidence.
    """
    if sessions < 2:
        raise ValueError("reconnect observation requires at least two sessions")
    bundles = [
        capture(
            endpoint, symbol, timeout, max_frames=max_frames,
            channels=channels, include_control_frames=True,
        )
        for _ in range(sessions)
    ]
    return {
        "schema": "quantengine.delta-public-reconnect-observation.v1",
        "endpoint": endpoint,
        "symbol": symbol,
        "requested_channels": list(channels),
        "sessions": bundles,
        "limitations": [
            "Sessions are client-initiated closes, not provider disconnects.",
            "A subscription echo does not prove candle continuity across sessions.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="wss://public-socket.delta.exchange")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--max-frames", type=int, default=500)
    parser.add_argument(
        "--channels", default=",".join(CHANNELS),
        help="Comma-separated subset of: " + ", ".join(CHANNELS),
    )
    parser.add_argument(
        "--reconnect-sessions", type=int, default=0,
        help="Open this many serial client sessions (minimum 2) for re-subscribe evidence",
    )
    parser.add_argument(
        "--include-control-frames", action="store_true",
        help="Retain public control/unrequested mapping frames for protocol evidence",
    )
    parser.add_argument("--output", help="Optional JSON evidence-bundle path")
    parser.add_argument("--deterministic-fixture", action="store_true",
                        help="Write a redacted deterministic fixture instead of receipt-clock metadata")
    args = parser.parse_args(argv)
    channels = tuple(channel.strip() for channel in args.channels.split(",") if channel.strip())
    if args.reconnect_sessions:
        bundle = capture_reconnect_observation(
            args.endpoint, args.symbol, args.timeout, channels=channels,
            max_frames=args.max_frames, sessions=args.reconnect_sessions,
        )
    else:
        bundle = capture(
            args.endpoint, args.symbol, args.timeout,
            max_frames=args.max_frames, channels=channels,
            include_control_frames=args.include_control_frames,
        )
    if args.output:
        write_bundle(bundle, args.output, deterministic=args.deterministic_fixture)
    print(json.dumps(bundle, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
