#!/usr/bin/env python3
"""Capture GENUINE Delta Global funding evidence bound to the frozen
OOS market-data bytes (Phase 25, P25-E).

READ-ONLY acquisition: fetches the public ``FUNDING:<symbol>`` history
from https://api.delta.exchange/v2/history/candles over a window that
fully covers the frozen OOS candle interval, then builds the strict
fingerprinted artifact via ``research.economics.funding_evidence`` with
``provenance_status="REAL"`` and the exact market-data file hash.  No
credentials are used; nothing is traded; no frozen artifact is modified.

Output (new files only; existing evidence is never overwritten):
    research/captures/phase25/global_<symbol>_funding_<tf>.json
        (the raw fingerprinted evidence)
    reports/evidence/phase25/<symbol>_funding_bound_to_oos.json
        (the strict artifact bound to the OOS market-data bytes;
        reports/ keeps generated evidence out of the frozen research
        tree, which must stay byte-clean per the 11G/Stage-4 guards)

Usage:
    python scripts/capture_funding_evidence.py \
        [--symbol BTCUSDT] [--market-data data/history/BTCUSDT_1m_oos_topup.json]

Exit codes: 0 success; 2 fail-closed (unreachable, empty, non-covering).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAW_DIR = REPO_ROOT / "research" / "captures" / "phase25"
BOUND_DIR = REPO_ROOT / "reports" / "evidence" / "phase25"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_oos_window(path: Path) -> tuple[int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("raw") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise SystemExit("FAIL_CLOSED: market-data file has no rows")
    stamps = [int(row["time"]) for row in rows]
    return min(stamps), max(stamps)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 25 genuine funding-evidence capture")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--resolution", default="1h")
    parser.add_argument("--market-data",
                        default="data/history/BTCUSDT_1m_oos_topup.json")
    parser.add_argument("--pad-seconds", type=int, default=3600,
                        help="extra coverage margin on both ends")
    args = parser.parse_args(argv)

    market_path = REPO_ROOT / args.market_data
    if not market_path.exists():
        print("FAIL_CLOSED: market-data file missing: %s" % market_path)
        return 2

    first, last = _read_oos_window(market_path)
    start = first - int(args.pad_seconds)
    end = last + int(args.pad_seconds)
    print("OOS window: %d .. %d; funding request: %d .. %d (pad %ds)"
          % (first, last, start, end, args.pad_seconds))

    from core.exchanges.delta.delta_history import DeltaHistory

    history = DeltaHistory()
    try:
        evidence = history.funding_evidence(
            args.symbol, resolution=args.resolution,
            start=start, end=end,
        )
    except Exception as exc:  # noqa: BLE001 (fail closed)
        print("FAIL_CLOSED: funding fetch failed: %s: %s"
              % (type(exc).__name__, exc))
        return 2

    events = evidence.get("events") or []
    if not events:
        print("FAIL_CLOSED: funding endpoint returned no events")
        return 2
    coverage_first = int(events[0]["time"])
    coverage_last = int(events[-1]["time"])
    if coverage_last < last:
        print("FAIL_CLOSED: funding coverage %d..%d does not reach the "
              "OOS candle interval end %d"
              % (coverage_first, coverage_last, last))
        return 2
    uncovered_head = max(0, first - coverage_first)
    if uncovered_head:
        print("NOTE: venue funding history starts %ds after the OOS "
              "candle interval start; the first %ds (%.2f%% of the "
              "dataset) has NO genuine funding evidence and must be "
              "replayed as a separate funding-unavailable segment"
              % (uncovered_head, uncovered_head,
                 100.0 * uncovered_head / max(1, last - first)))

    from research.economics.funding_evidence import (
        build_artifact,
        write_artifact,
    )

    artifact = build_artifact(
        evidence,
        market_data_path=market_path,
        provenance_status="REAL",
        captured_at=_utc_now(),
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    BOUND_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / ("global_%s_funding_%s.json"
                          % (args.symbol.lower(), args.resolution))
    bound_path = BOUND_DIR / ("%s_funding_bound_to_oos.json"
                              % args.symbol.lower())
    write_artifact(artifact, bound_path)
    raw_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("CAPTURED funding events=%d coverage=%d..%d"
          % (len(events), coverage_first, coverage_last))
    print("RAW_EVIDENCE %s" % raw_path)
    print("BOUND_ARTIFACT %s" % bound_path)
    print("MARKET_DATA_SHA256 %s" % artifact.market_data_sha256)
    print("FUNDING_EVIDENCE_SHA256 %s" % artifact.funding_evidence_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
