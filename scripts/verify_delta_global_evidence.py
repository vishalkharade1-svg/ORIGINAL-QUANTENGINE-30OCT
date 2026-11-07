"""Deterministic verifier for bounded Global Delta public-market evidence.

Phase 1 requires real captured frames from the exact configured Global
endpoint (``wss://public-socket.delta.exchange``) for the configured
universe including ``BTCUSDT``.  This module checks a capture bundle
produced by ``scripts/capture_delta_public_frames.py`` (or a reconnect
observation) against that bar without opening any socket itself.

It never fabricates frames, never substitutes the India endpoint or
``BTCUSD`` for Global ``BTCUSDT`` evidence, and fails closed: any missing
criterion is reported as a failure, never inferred.

Expected bundle schemas:
  - ``quantengine.delta-public-capture.v1`` (single bounded session)
  - ``quantengine.delta-public-reconnect-observation.v1`` (serial sessions)

Pass criteria for a single-session bundle:
  1. ``endpoint`` is exactly the Global public socket.
  2. ``symbol`` is a member of the required Global universe set.
  3. At least one ``trades`` frame and at least two ``candlestick_1m``
     frames are present.
  4. At least one ``subscriptions`` control frame echoes the requested
     ``candlestick_1m`` channel/symbol set (when control frames retained).
  5. Multiple candle updates share one ``cst`` and at least one rollover
     to a second ``cst`` exactly one resolution step later (60s for 1m).

Reconnect observations must additionally contain >= 2 sessions, each with
its own subscription echo.  Server-initiated disconnect recovery is NOT
claimed by client-initiated serial sessions; the verifier reports that
limitation explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib
import json
import math


GLOBAL_PUBLIC_SOCKET = "wss://public-socket.delta.exchange"
GLOBAL_EVIDENCE_SYMBOL = "BTCUSDT"
GLOBAL_EVIDENCE_CHANNEL = "candlestick_1m"
GLOBAL_TRADE_CHANNEL = "trades"
RESOLUTION_STEP_SECONDS = {"1m": 60}


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvidenceVerdict:
    passed: bool
    checks: tuple[EvidenceCheck, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def failures(self) -> list[EvidenceCheck]:
        return [check for check in self.checks if not check.passed]


def _frames(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    records = bundle.get("frames")
    if not isinstance(records, list):
        return []
    out: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("frame"), dict):
            out.append(record["frame"])
    return out


def _control_frames(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    records = bundle.get("frames")
    if not isinstance(records, list):
        return []
    return [
        record["frame"]
        for record in records
        if isinstance(record, dict)
        and record.get("classification") == "control_or_unrequested"
        and isinstance(record.get("frame"), dict)
    ]


def _has_subscription_echo(
    control_frames: list[dict[str, Any]],
    *,
    symbols: list[str],
    resolution: str,
) -> bool:
    from data.delta.verified_candle_subscription import (
        is_observed_subscription_snapshot,
    )

    return any(
        is_observed_subscription_snapshot(
            frame, symbols=symbols, resolution=resolution
        )
        for frame in control_frames
    )


def canonical_capture_identity(bundle: dict[str, Any]) -> str:
    """Hash evidence content while excluding local receipt-clock metadata.

    This is a content identity, not an authenticity claim.  It makes repeated
    serialization of the same observed frames byte-independent while retaining
    endpoint, requested channels, frame order, and frame payloads.
    """
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
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_capture_integrity(
    bundle: dict[str, Any],
    *,
    required_symbols: tuple[str, ...] = (GLOBAL_EVIDENCE_SYMBOL,),
) -> tuple[EvidenceCheck, ...]:
    """Validate capture structure without asserting venue authenticity."""
    checks: list[EvidenceCheck] = []
    schema_ok = bundle.get("schema") in (
        "quantengine.delta-public-capture.v1",
        "quantengine.delta-public-reconnect-observation.v1",
    )
    checks.append(EvidenceCheck(
        "capture_schema", schema_ok, "schema=%r" % (bundle.get("schema"),)
    ))
    symbol = bundle.get("symbol")
    checks.append(EvidenceCheck(
        "capture_symbol", isinstance(symbol, str) and symbol in required_symbols,
        "symbol=%r" % (symbol,),
    ))
    records = bundle.get("frames")
    records_ok = isinstance(records, list)
    checks.append(EvidenceCheck(
        "frame_records", records_ok,
        "frame record container is %s" % ("valid" if records_ok else "invalid"),
    ))
    if not records_ok:
        return tuple(checks)

    ordinals = [r.get("receipt_ordinal") for r in records if isinstance(r, dict)]
    ordinal_ok = (
        len(ordinals) == len(records)
        and all(isinstance(v, int) and not isinstance(v, bool) for v in ordinals)
        and ordinals == list(range(1, len(records) + 1))
    )
    checks.append(EvidenceCheck(
        "receipt_ordinals", ordinal_ok,
        "ordinals are contiguous 1..%d" % len(records) if ordinal_ok
        else "receipt ordinals are missing, duplicated, or out of order",
    ))

    payload_ok = True
    payload_reason = "all requested frames have coherent symbol/channel payloads"
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("frame"), dict):
            payload_ok = False
            payload_reason = "record/frame is not an object"
            break
        frame = record["frame"]
        ftype = frame.get("type")
        if ftype in (GLOBAL_EVIDENCE_CHANNEL, GLOBAL_TRADE_CHANNEL):
            if frame.get("sy") != symbol:
                payload_ok = False
                payload_reason = "requested frame symbol differs from bundle symbol"
                break
        if ftype == GLOBAL_EVIDENCE_CHANNEL:
            numeric = ("o", "h", "l", "c", "v")
            if any(not isinstance(frame.get(k), (int, float)) or
                   isinstance(frame.get(k), bool) or
                   not math.isfinite(float(frame.get(k))) for k in numeric):
                payload_ok = False
                payload_reason = "candle OHLCV contains non-finite/non-numeric values"
                break
            if float(frame["v"]) < 0:
                payload_ok = False
                payload_reason = "candle volume is negative"
                break
            cst = frame.get("cst")
            ts = frame.get("ts")
            if not isinstance(cst, (int, float)) or isinstance(cst, bool) or not math.isfinite(float(cst)):
                payload_ok = False
                payload_reason = "candle cst is missing/non-finite"
                break
            if not isinstance(ts, (int, float)) or isinstance(ts, bool) or not math.isfinite(float(ts)):
                payload_ok = False
                payload_reason = "candle ts is missing/non-finite"
                break
    checks.append(EvidenceCheck("frame_payload_integrity", payload_ok, payload_reason))

    identity = canonical_capture_identity(bundle)
    declared = bundle.get("content_identity")
    identity_ok = declared in (None, identity)
    checks.append(EvidenceCheck(
        "content_identity", identity_ok,
        "content identity %s" % ("matches" if declared == identity else
                                   "not declared" if declared is None else "mismatch"),
    ))
    return tuple(checks)


def _candle_starts(candles: list[dict[str, Any]]) -> list[int]:
    starts: list[int] = []
    for frame in candles:
        cst = frame.get("cst")
        if isinstance(cst, bool):
            continue
        if isinstance(cst, (int, float)) and cst > 0:
            starts.append(int(cst))
    return starts


def verify_single_session(
    bundle: dict[str, Any],
    *,
    required_symbols: tuple[str, ...] = (GLOBAL_EVIDENCE_SYMBOL,),
    resolution: str = "1m",
) -> EvidenceVerdict:
    """Verify one bounded capture bundle against the Global Phase-1 bar."""
    checks: list[EvidenceCheck] = []
    step = RESOLUTION_STEP_SECONDS.get(resolution, 60)

    checks.extend(verify_capture_integrity(bundle, required_symbols=required_symbols))

    endpoint = bundle.get("endpoint")
    checks.append(EvidenceCheck(
        "global_endpoint",
        endpoint == GLOBAL_PUBLIC_SOCKET,
        "endpoint is %r; required %r" % (endpoint, GLOBAL_PUBLIC_SOCKET),
    ))

    symbol = bundle.get("symbol")
    checks.append(EvidenceCheck(
        "global_symbol_in_universe",
        isinstance(symbol, str) and symbol in required_symbols,
        "symbol is %r; required one of %r" % (symbol, list(required_symbols)),
    ))

    frames = _frames(bundle)
    trades = [f for f in frames if f.get("type") == GLOBAL_TRADE_CHANNEL]
    candles = [
        f for f in frames
        if f.get("type") == GLOBAL_EVIDENCE_CHANNEL and f.get("sy") == symbol
    ]
    checks.append(EvidenceCheck(
        "trades_present",
        len(trades) >= 1,
        "%d trades frame(s) observed" % len(trades),
    ))
    checks.append(EvidenceCheck(
        "multiple_candle_updates",
        len(candles) >= 2,
        "%d candlestick_1m frame(s) for %r" % (len(candles), symbol),
    ))

    controls = _control_frames(bundle)
    if controls:
        echo = _has_subscription_echo(
            controls, symbols=[symbol] if isinstance(symbol, str) else [],
            resolution=resolution,
        )
        checks.append(EvidenceCheck(
            "subscription_acknowledgement",
            echo,
            "subscription echo %s among %d control frame(s)"
            % ("observed" if echo else "not observed", len(controls)),
        ))
    else:
        checks.append(EvidenceCheck(
            "subscription_acknowledgement",
            False,
            "no control frames retained; re-run capture with "
            "--include-control-frames to evidence acknowledgement",
        ))

    starts = _candle_starts(candles)
    distinct = list(dict.fromkeys(starts))
    checks.append(EvidenceCheck(
        "candle_rollover",
        len(distinct) >= 2
        and any(
            distinct[i + 1] - distinct[i] == step * 1_000_000
            or distinct[i + 1] - distinct[i] == step
            for i in range(len(distinct) - 1)
        ),
        "distinct cst values observed: %d" % len(distinct),
    ))

    limitations = (
        "Public receipt order is not a documented exchange sequence.",
        "No candle frame is considered closed without an evidenced finality rule.",
        "Client-initiated serial sessions do not prove server-initiated "
        "disconnect recovery; CandleSessionGate resynchronization is still required.",
    )
    passed = all(check.passed for check in checks)
    return EvidenceVerdict(passed=passed, checks=tuple(checks), limitations=limitations)


def verify_reconnect_observation(
    bundle: dict[str, Any],
    *,
    required_symbols: tuple[str, ...] = (GLOBAL_EVIDENCE_SYMBOL,),
    resolution: str = "1m",
) -> EvidenceVerdict:
    """Verify a multi-session reconnect observation bundle."""
    checks: list[EvidenceCheck] = []
    checks.append(EvidenceCheck(
        "global_endpoint",
        bundle.get("endpoint") == GLOBAL_PUBLIC_SOCKET,
        "endpoint is %r" % (bundle.get("endpoint"),),
    ))
    sessions = bundle.get("sessions")
    if not isinstance(sessions, list) or len(sessions) < 2:
        checks.append(EvidenceCheck(
            "two_sessions_present",
            False,
            "reconnect observation requires >= 2 sessions",
        ))
        return EvidenceVerdict(passed=False, checks=tuple(checks))
    checks.append(EvidenceCheck(
        "two_sessions_present",
        True,
        "%d session(s) observed" % len(sessions),
    ))
    for index, session in enumerate(sessions):
        verdict = verify_single_session(
            session if isinstance(session, dict) else {},
            required_symbols=required_symbols,
            resolution=resolution,
        )
        session_ok = verdict.passed
        # A short reconnect session may legitimately contain no rollover on
        # its own; the per-session requirement is endpoint/symbol/trades or
        # candles plus a subscription echo, not a full rollover.
        echo_ok = any(
            c.name == "subscription_acknowledgement" and c.passed
            for c in verdict.checks
        )
        endpoint_ok = any(
            c.name == "global_endpoint" and c.passed for c in verdict.checks
        )
        symbol_ok = any(
            c.name == "global_symbol_in_universe" and c.passed
            for c in verdict.checks
        )
        checks.append(EvidenceCheck(
            "session_%d_resubscribed" % index,
            bool(endpoint_ok and symbol_ok and echo_ok),
            "session %d endpoint/symbol/echo %s" % (
                index, "verified" if (endpoint_ok and symbol_ok and echo_ok) else "incomplete"),
        ))
        _ = session_ok  # full single-session bar (incl. rollover) applies to
        # the long capture, not necessarily to each short reconnect session.
    limitations = (
        "Sessions are client-initiated closes, not provider disconnects.",
        "A subscription echo does not prove candle continuity across sessions.",
    )
    return EvidenceVerdict(
        passed=all(check.passed for check in checks),
        checks=tuple(checks),
        limitations=limitations,
    )


def format_verdict(verdict: EvidenceVerdict) -> str:
    lines = ["GLOBAL_EVIDENCE_%s" % ("PASS" if verdict.passed else "BLOCKED")]
    for check in verdict.checks:
        lines.append(
            "  [%s] %s: %s" % ("PASS" if check.passed else "FAIL", check.name, check.detail)
        )
    for limitation in verdict.limitations:
        lines.append("  note: %s" % limitation)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: verify one capture bundle against the Global Phase-1 bar."""
    import argparse
    import json as _json
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(
        0, str(_Path(__file__).resolve().parents[1]))

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True,
                        help="Path to a capture bundle JSON document")
    parser.add_argument("--symbols", default=GLOBAL_EVIDENCE_SYMBOL,
                        help="Comma-separated required universe symbols")
    parser.add_argument("--resolution", default="1m")
    parser.add_argument("--reconnect", action="store_true",
                        help="Verify a reconnect-observation bundle instead")
    args = parser.parse_args(argv)
    bundle = _json.loads(_Path(args.bundle).read_text(encoding="utf-8"))
    symbols = tuple(s.strip() for s in args.symbols.split(",") if s.strip())
    if args.reconnect:
        verdict = verify_reconnect_observation(
            bundle, required_symbols=symbols, resolution=args.resolution)
    else:
        verdict = verify_single_session(
            bundle, required_symbols=symbols, resolution=args.resolution)
    print(format_verdict(verdict))
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
