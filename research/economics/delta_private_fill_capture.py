"""Fail-closed authenticated Delta private user-trade capture.

Captures raw ``v2/user_trades`` frames after ``key-auth`` succeeds, validates
per-symbol sequence continuity, normalizes fills, and reconciles the socket
fills against an authenticated REST fill artifact.  This module never creates
REAL evidence from fixtures or caller-supplied frames.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from research.economics.delta_fill_evidence import DeltaFillEvidenceArtifact, build_artifact, fingerprint

PRIVATE_WS_PRODUCTION = "wss://socket.india.delta.exchange"
PRIVATE_WS_SANDBOX = "wss://socket-ind.testnet.deltaex.org"


def key_auth_message(api_key: str, api_secret: str, *, timestamp: int | None = None) -> dict[str, Any]:
    if not api_key or not api_secret:
        raise ValueError("api key and secret are required")
    ts = int(time.time()) if timestamp is None else int(timestamp)
    signature = hmac.new(api_secret.encode(), f"GET{ts}/live".encode(), hashlib.sha256).hexdigest()
    return {"type": "key-auth", "payload": {"api-key": api_key, "signature": signature, "timestamp": ts}}


def subscription(symbol: str) -> dict[str, Any]:
    if not symbol:
        raise ValueError("explicit symbol is required")
    return {"type": "subscribe", "payload": {"channels": [{"name": "v2/user_trades", "symbols": [symbol]}]}}


def decode_frame(raw: str | bytes) -> Mapping[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, Mapping):
        raise ValueError("private websocket frame must be an object")
    return value


def normalize_ws_fill(frame: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one observed ``v2/user_trades`` frame.

    Venue-observed schema (Testnet, 2026-10-11): ``t`` is the event
    timestamp in MICROSECONDS; there is NO per-fill sequence field
    (``u`` is a user id, ``i`` the product id). ``c`` echoes the
    client order id when the order carried one. Legacy ``timestamp``
    / ``seq_no`` keys are still accepted when present (fixtures and
    older captures), with ``seq_no`` optional.
    """
    if frame.get("type") != "v2/user_trades":
        raise ValueError("frame is not v2/user_trades")
    required = {"sy", "f", "o", "S", "s", "p", "r"}
    missing = required.difference(frame)
    if missing:
        raise ValueError(f"user trade frame missing fields: {sorted(missing)}")
    raw_ts = frame.get("t", frame.get("timestamp"))
    if raw_ts is None:
        raise ValueError("user trade frame missing fields: ['t']")
    try:
        timestamp = int(raw_ts)
    except (TypeError, ValueError):
        raise ValueError("user trade timestamp is invalid")
    if timestamp <= 0:
        raise ValueError("user trade timestamp is invalid")
    raw_seq = frame.get("seq_no")
    try:
        seq_no = None if raw_seq is None else int(raw_seq)
    except (TypeError, ValueError):
        raise ValueError("user trade seq_no is invalid")
    return {
        "fill_id": str(frame["f"]), "order_id": str(frame["o"]), "symbol": str(frame["sy"]),
        "side": str(frame["S"]).lower(), "size": str(frame["s"]), "price": str(frame["p"]),
        "role": str(frame["r"]).lower(), "timestamp": timestamp,
        "timestamp_unit": "microseconds" if "t" in frame else "as_received",
        "fill_type": str(frame.get("R") or "normal"),
        "client_order_id": str(frame.get("c") or ""),
        "seq_no": seq_no,
    }


@dataclass(frozen=True, slots=True)
class PrivateFillCapture:
    symbol: str
    frames: tuple[Mapping[str, Any], ...]
    fills: tuple[Mapping[str, Any], ...]
    first_seq: int | None
    last_seq: int | None
    authenticated: bool = True

    def validate(self) -> None:
        if not self.authenticated or not self.frames or not self.fills:
            raise ValueError("authenticated non-empty capture required")
        seen = set()
        previous_ts = None
        seqs = []
        for frame, fill in zip(self.frames, self.fills):
            if fill["symbol"] != self.symbol:
                raise ValueError("private fill symbol mismatch")
            ts = int(fill["timestamp"])
            if previous_ts is not None and ts < previous_ts:
                raise ValueError("private fills out of timestamp order")
            previous_ts = ts
            if fill["fill_id"] in seen:
                raise ValueError("duplicate websocket fill id")
            seen.add(fill["fill_id"])
            if fill.get("seq_no") is not None:
                seqs.append(int(fill["seq_no"]))
        if seqs:
            # Sequence continuity is enforceable only when the venue
            # supplies per-fill sequence numbers on every frame.
            if len(seqs) != len(self.fills):
                raise ValueError("mixed sequenced/unsequenced frames")
            for expected, got in zip(range(seqs[0], seqs[0] + len(seqs)), seqs):
                if got != expected:
                    raise ValueError("private fill sequence gap")
            if self.first_seq != seqs[0] or self.last_seq != seqs[-1]:
                raise ValueError("capture sequence metadata mismatch")
        elif self.first_seq is not None or self.last_seq is not None:
            raise ValueError("capture sequence metadata mismatch")


def capture_from_frames(frames: Sequence[Mapping[str, Any]], *, symbol: str, authenticated: bool = True) -> PrivateFillCapture:
    if not authenticated:
        raise RuntimeError("authenticated private websocket is required")
    if not frames:
        raise ValueError("no private websocket frames")
    fills: list[dict[str, Any]] = []
    kept: list[Mapping[str, Any]] = []
    for frame in frames:
        if frame.get("type") in {"heartbeat", "subscriptions"}:
            continue
        if frame.get("type") == "key-auth":
            if frame.get("success") is not True:
                raise RuntimeError("Delta private websocket authentication failed")
            continue
        if frame.get("type") != "v2/user_trades":
            continue
        fill = normalize_ws_fill(frame)
        if fill["symbol"] != symbol:
            raise ValueError("unexpected private fill symbol")
        fills.append(fill); kept.append(dict(frame))
    if not fills:
        raise ValueError("no v2/user_trades frames")
    seqs = [f["seq_no"] for f in fills]
    if any(s is None for s in seqs):
        first_seq = last_seq = None
    else:
        first_seq, last_seq = int(seqs[0]), int(seqs[-1])
    cap = PrivateFillCapture(symbol, tuple(kept), tuple(fills), first_seq, last_seq, True)
    cap.validate()
    return cap


def reconcile_with_rest(capture: PrivateFillCapture, rest_artifact: DeltaFillEvidenceArtifact) -> dict[str, Any]:
    capture.validate()
    if rest_artifact.provenance_status != "REAL":
        raise ValueError("REST fill artifact is not REAL")
    if rest_artifact.symbol != capture.symbol:
        raise ValueError("REST/private fill symbol mismatch")
    ws = {str(x["fill_id"]): x for x in capture.fills}
    rest = {str(x["fill_id"]): x for x in rest_artifact.fills}
    missing_from_rest = sorted(set(ws) - set(rest))
    missing_from_ws = sorted(set(rest) - set(ws))
    common = sorted(set(ws) & set(rest))
    mismatches: list[dict[str, Any]] = []
    for fid in common:
        for field in ("order_id", "symbol", "side", "size", "price", "role"):
            if str(ws[fid][field]) != str(rest[fid][field]):
                mismatches.append({"fill_id": fid, "field": field, "websocket": ws[fid][field], "rest": rest[fid][field]})
    if missing_from_rest or missing_from_ws or mismatches:
        raise ValueError(json.dumps({"missing_from_rest": missing_from_rest, "missing_from_ws": missing_from_ws, "mismatches": mismatches}, sort_keys=True))
    return {"status": "MATCHED", "fill_count": len(common), "fill_ids": common,
            "rest_evidence_sha256": rest_artifact.evidence_sha256,
            "websocket_first_seq": capture.first_seq, "websocket_last_seq": capture.last_seq}


def reconcile_with_rest_windowed(
    capture: PrivateFillCapture,
    rest_artifact: DeltaFillEvidenceArtifact,
    *,
    window_ms: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Window-scoped reconciliation for a BOUNDED capture.

    Every REST fill is classified as pre-window, in-window or post-window. The
    in-window set must match the socket set exactly; out-of-window fills are
    reported with their ids. ``window_ms`` defaults to the socket fill span and
    must then be derivable, which requires venue microsecond timestamps.
    """
    capture.validate()
    if rest_artifact.provenance_status != "REAL":
        raise ValueError("REST fill artifact is not REAL")
    if rest_artifact.symbol != capture.symbol:
        raise ValueError("REST/private fill symbol mismatch")

    ws = {str(x["fill_id"]): x for x in capture.fills}
    rest = {str(x["fill_id"]): x for x in rest_artifact.fills}

    ws_ms: dict[str, int] = {}
    for fid, fill in ws.items():
        unit = str(fill.get("timestamp_unit", "as_received"))
        if unit != "microseconds":
            raise ValueError(json.dumps({
                "error": "socket fill timestamp unit is not venue microseconds",
                "fill_id": fid, "timestamp_unit": unit,
                "note": "the windowed reconciler never guesses a unit; pass a "
                        "capture with venue 't' timestamps",
            }, sort_keys=True))
        ws_ms[fid] = int(fill["timestamp"]) // 1000

    if window_ms is None:
        stamps = sorted(ws_ms.values())
        start, end = stamps[0], stamps[-1]
        window_source = "socket_fill_span"
    else:
        start, end = int(window_ms[0]), int(window_ms[1])
        window_source = "explicit"
        if start > end:
            raise ValueError("reconciliation window start is after its end")
        outside = sorted(fid for fid, t in ws_ms.items() if t < start or t > end)
        if outside:
            raise ValueError(json.dumps({
                "error": "declared window excludes socket fills",
                "socket_fills_outside_window": outside,
            }, sort_keys=True))

    in_window: dict[str, Mapping[str, Any]] = {}
    pre: list[str] = []
    post: list[str] = []
    for fid, row in rest.items():
        t = int(row["timestamp"])
        if t < start:
            pre.append(fid)
        elif t > end:
            post.append(fid)
        else:
            in_window[fid] = row

    missing_from_ws = sorted(set(in_window) - set(ws))
    missing_from_rest = sorted(set(ws) - set(in_window))
    mismatches: list[dict[str, Any]] = []
    for fid in sorted(set(ws) & set(in_window)):
        for field in ("order_id", "symbol", "side", "size", "price", "role"):
            if str(ws[fid][field]) != str(in_window[fid][field]):
                mismatches.append({
                    "fill_id": fid, "field": field,
                    "websocket": ws[fid][field], "rest": in_window[fid][field],
                })
    if missing_from_rest or missing_from_ws or mismatches:
        raise ValueError(json.dumps({
            "missing_from_rest": missing_from_rest,
            "missing_from_ws": missing_from_ws,
            "mismatches": mismatches,
            "window_ms": {"start": start, "end": end},
        }, sort_keys=True))

    record: dict[str, Any] = {
        "status": "MATCHED_WINDOWED",
        "claim": ("window-scoped only: the in-window REST fill set matches the "
                  "socket set exactly; out-of-window fills are classified, "
                  "never reconciled"),
        "window_ms": {"start": start, "end": end},
        "window_source": window_source,
        "matched_fill_count": len(in_window),
        "matched_fill_ids": sorted(in_window),
        "pre_window_fill_ids": sorted(pre),
        "post_window_fill_ids": sorted(post),
        "rest_evidence_sha256": rest_artifact.evidence_sha256,
        "websocket_first_seq": capture.first_seq,
        "websocket_last_seq": capture.last_seq,
    }
    record["reconciliation_sha256"] = fingerprint({
        "window_ms": record["window_ms"],
        "window_source": record["window_source"],
        "matched_fill_ids": record["matched_fill_ids"],
        "pre_window_fill_ids": record["pre_window_fill_ids"],
        "post_window_fill_ids": record["post_window_fill_ids"],
        "rest_evidence_sha256": record["rest_evidence_sha256"],
        "websocket_first_seq": record["websocket_first_seq"],
        "websocket_last_seq": record["websocket_last_seq"],
    })
    return record


async def capture_live(*, endpoint: str, api_key: str, api_secret: str, symbol: str, duration_seconds: float = 30.0) -> PrivateFillCapture:
    if endpoint not in {PRIVATE_WS_PRODUCTION, PRIVATE_WS_SANDBOX}:
        raise ValueError("unrecognized Delta private websocket endpoint")
    if duration_seconds <= 0:
        raise ValueError("duration must be positive")
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("websockets package is required") from exc
    frames: list[Mapping[str, Any]] = []
    deadline = time.monotonic() + duration_seconds
    async with websockets.connect(endpoint, ping_interval=20, ping_timeout=5, close_timeout=5, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps(key_auth_message(api_key, api_secret), separators=(",", ":")))
        authenticated = False
        while time.monotonic() < deadline:
            timeout = max(0.1, deadline - time.monotonic())
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                break
            frame = decode_frame(raw)
            frames.append(frame)
            if frame.get("type") == "key-auth":
                if frame.get("success") is not True:
                    raise RuntimeError(f"Delta private websocket authentication failed: {dict(frame)}")
                authenticated = True
                await ws.send(json.dumps(subscription(symbol), separators=(",", ":")))
            if frame.get("type") == "v2/user_trades" and authenticated:
                pass
    return capture_from_frames(frames, symbol=symbol, authenticated=authenticated)


def archive_hash(frames: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps([dict(x) for x in frames], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def build_private_archive(capture: PrivateFillCapture) -> dict[str, Any]:
    capture.validate()
    genesis = "0" * 64
    chain = genesis
    records = []
    for frame in capture.frames:
        canonical = json.dumps(dict(frame), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        frame_hash = hashlib.sha256(canonical.encode()).hexdigest()
        chain = hashlib.sha256((chain + frame_hash).encode()).hexdigest()
        records.append({"frame": dict(frame), "frame_sha256": frame_hash, "chain_sha256": chain})
    return {
        "schema_version": 1,
        "venue": "delta",
        "transport": "LIVE_CAPTURE",
        "channel": "v2/user_trades",
        "symbol": capture.symbol,
        "first_seq": capture.first_seq,
        "last_seq": capture.last_seq,
        "frames": records,
        "archive_sha256": hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        "provenance_status": "REAL",
    }


def verify_private_archive(archive: Mapping[str, Any]) -> PrivateFillCapture:
    if archive.get("schema_version") != 1 or archive.get("transport") != "LIVE_CAPTURE" or archive.get("channel") != "v2/user_trades":
        raise ValueError("invalid private fill archive identity")
    if archive.get("provenance_status") != "REAL":
        raise ValueError("private fill archive is not REAL")
    records = archive.get("frames")
    if not isinstance(records, list) or not records:
        raise ValueError("private fill archive is empty")
    expected_chain = "0" * 64
    frames = []
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("frame"), Mapping):
            raise ValueError("malformed private archive record")
        frame = dict(record["frame"])
        canonical = json.dumps(frame, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        fh = hashlib.sha256(canonical.encode()).hexdigest()
        if record.get("frame_sha256") != fh:
            raise ValueError("private archive frame hash mismatch")
        expected_chain = hashlib.sha256((expected_chain + fh).encode()).hexdigest()
        if record.get("chain_sha256") != expected_chain:
            raise ValueError("private archive chain mismatch")
        frames.append(frame)
    expected_archive = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if archive.get("archive_sha256") != expected_archive:
        raise ValueError("private archive fingerprint mismatch")
    return capture_from_frames(frames, symbol=str(archive.get("symbol", "")), authenticated=True)
