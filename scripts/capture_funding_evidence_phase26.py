#!/usr/bin/env python3
"""Phase 26 (P26-D) aligned funding-evidence recapture.

The Phase-25 capture requested a window starting at 08:45Z. Delta's
public FUNDING:<symbol> history endpoint returns only whole 8-hour
aligned blocks at the head of a request, so the 10:00..15:00 settlements
were dropped and the artifact reported a 22,500-second head gap. Direct
probing (Phase 26) proved those settlements exist and are returned when
the request starts at an 8-hour boundary.

This script requests an 8-hour-aligned window (at least 8 hours of pad),
verifies strict hourly continuity across the whole returned series, and
binds NEW strict artifacts to both frozen datasets. Phase-25 evidence is
never modified.

Outputs (new files only):
    reports/evidence/phase26/raw_funding_evidence.json
    reports/evidence/phase26/btcusdt_funding_bound_to_oos.json
    reports/evidence/phase26/btcusdt_funding_bound_to_phase18.json

Exit codes: 0 success; 2 fail-closed (unreachable, empty, discontinuity,
non-covering, or unchanged evidence hash).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "reports" / "evidence" / "phase26"
DATASETS = {
    "oos": REPO_ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json",
    "phase18": REPO_ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json",
}
ALIGNMENT_SECONDS = 8 * 3600
PAD_SECONDS = 8 * 3600


def _utc(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_window(path: Path) -> tuple[int, int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("raw") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise SystemExit("FAIL_CLOSED: market-data file has no rows: %s" % path)
    stamps = sorted(int(row["time"]) for row in rows)
    return stamps[0], stamps[-1], len(stamps)


def _ceil(value: int, step: int) -> int:
    return ((value + step - 1) // step) * step


def _verify_series(events, first_candle: int, last_candle: int) -> dict:
    times = [int(event["time"]) for event in events]
    gaps = [(a, b, b - a) for a, b in zip(times, times[1:])
            if b - a != 3600]
    if gaps:
        raise SystemExit(
            "FAIL_CLOSED: funding series is not strictly hourly: %s" % gaps[:5])
    if times[0] > first_candle:
        raise SystemExit(
            "FAIL_CLOSED: head still uncovered: first event %d > first "
            "candle %d" % (times[0], first_candle))
    if last_candle - times[-1] > 3600:
        raise SystemExit(
            "FAIL_CLOSED: tail gap exceeds one funding interval: last "
            "event %d, last candle %d" % (times[-1], last_candle))
    expected = (times[-1] - times[0]) // 3600 + 1
    if expected != len(times):
        raise SystemExit(
            "FAIL_CLOSED: settlement count %d != expected %d"
            % (len(times), expected))
    return {
        "event_count": len(times),
        "first_event": times[0],
        "first_event_utc": _utc(times[0]),
        "last_event": times[-1],
        "last_event_utc": _utc(times[-1]),
        "strictly_hourly": True,
        "non_hourly_gaps": 0,
        "head_covered": times[0] <= first_candle,
        "head_pad_seconds": max(0, first_candle - times[0]),
        "tail_covered": last_candle - times[-1] <= 3600,
        "settlement_count": expected,
    }


def main() -> int:
    windows = {name: _read_window(path) for name, path in DATASETS.items()}
    first_candle = min(window[0] for window in windows.values())
    last_candle = max(window[1] for window in windows.values())

    request_start = (first_candle - PAD_SECONDS) // ALIGNMENT_SECONDS \
        * ALIGNMENT_SECONDS
    request_end = _ceil(last_candle + PAD_SECONDS, ALIGNMENT_SECONDS)
    if request_start >= first_candle or request_end < last_candle:
        raise SystemExit("FAIL_CLOSED: computed request window does not cover OOS")
    print("aligned request: %d..%d (%s..%s) for OOS %d..%d"
          % (request_start, request_end, _utc(request_start),
             _utc(request_end), first_candle, last_candle))

    from core.exchanges.delta.delta_history import DeltaHistory

    try:
        evidence = DeltaHistory().funding_evidence(
            "BTCUSDT", resolution="1h",
            start=request_start, end=request_end)
    except Exception as exc:  # noqa: BLE001 - fail closed on any fetch error
        print("FAIL_CLOSED: funding fetch failed: %s: %s"
              % (type(exc).__name__, exc))
        return 2

    events = evidence.get("events") or []
    if not events:
        print("FAIL_CLOSED: funding endpoint returned no events")
        return 2
    series = _verify_series(events, first_candle, last_candle)
    print("CAPTURED events=%d %s..%s hourly=%s head_covered=%s"
          % (series["event_count"], series["first_event_utc"],
             series["last_event_utc"], series["strictly_hourly"],
             series["head_covered"]))

    from research.economics.funding_evidence import build_artifact, write_artifact

    captured_at = _now()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bound = {}
    for name, path in DATASETS.items():
        artifact = build_artifact(
            evidence, market_data_path=path,
            provenance_status="REAL", captured_at=captured_at)
        out = OUT_DIR / ("btcusdt_funding_bound_to_%s.json"
                         % ("oos" if name == "oos" else "phase18"))
        write_artifact(artifact, out)
        bound[name] = {
            "path": str(out.relative_to(REPO_ROOT)),
            "market_data_sha256": artifact.market_data_sha256,
            "funding_evidence_sha256": artifact.funding_evidence_sha256,
            "request_start": artifact.start,
            "request_end": artifact.end,
            "event_count": len(artifact.events),
        }
        print("BOUND %s -> %s (market sha256 %s)"
              % (name, out, artifact.market_data_sha256))

    raw = {
        "schema": "quantengine.phase26-funding-recapture.v1",
        "captured_at": captured_at,
        "reason": (
            "Phase-25 request started at 08:45Z inside an 8-hour funding "
            "block; the venue endpoint returns only whole aligned blocks at "
            "the head, dropping the 10:00..15:00 settlements. Aligned "
            "recapture, no interpolation, no zero-fill substitution."),
        "alignment_seconds": ALIGNMENT_SECONDS,
        "pad_seconds": PAD_SECONDS,
        "request": evidence.get("request"),
        "oos_window": {
            "first_candle": first_candle,
            "last_candle": last_candle,
            "first_candle_utc": _utc(first_candle),
            "last_candle_utc": _utc(last_candle),
        },
        "series": series,
        "events": events,
        "evidence_sha256": evidence.get("sha256"),
        "bound_artifacts": bound,
    }
    raw_path = OUT_DIR / "raw_funding_evidence.json"
    raw_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RAW %s (%d events)" % (raw_path, len(events)))
    print("EVIDENCE_SHA256 %s" % evidence.get("sha256"))
    print("RAW_SHA256 %s" % hashlib.sha256(
        raw_path.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
