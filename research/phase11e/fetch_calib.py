"""Phase 11E-Closure calibration fetch (research-only read).

Fetches BTCUSDT 1m strictly BEFORE the D2 window start, for
per-fold causal regime calibration. No overlap with any OOS
fold. Records fetch metadata + sha256. Read-only exchange
access (candles endpoint). No orders, no LIVE.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.exchanges.delta.delta_history import DeltaHistory

D2_START = 1787575500  # first D2 bar (2026-08-24T12:45Z)
TARGET_BARS = 10000
OUT = Path(__file__).resolve().parent / "data" / "calib_pre_d2.json"


def main():
    fetched_at = datetime.now(timezone.utc)
    history = DeltaHistory()
    candles = history.candles(
        "BTCUSDT", resolution="1m",
        start=D2_START - TARGET_BARS * 60, end=D2_START - 60,
    )
    rows = [
        {
            "time": int(c.timestamp),
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candles
        if int(c.timestamp) < D2_START
    ]
    rows.sort(key=lambda r: r["time"])
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "window": {"start": D2_START - TARGET_BARS * 60, "end": D2_START - 60},
        "constraint": "all bars strictly before D2_START",
        "fetched_at": fetched_at.isoformat(),
        "fetched_count": len(rows),
        "candles": rows,
    }
    blob = json.dumps(payload, indent=1).encode()
    payload["sha256"] = hashlib.sha256(blob).hexdigest()
    OUT.write_text(json.dumps(payload, indent=1))
    print(json.dumps({
        "bars": len(rows),
        "first": rows[0]["time"] if rows else None,
        "last": rows[-1]["time"] if rows else None,
        "all_prior": all(r["time"] < D2_START for r in rows),
        "sha256": payload["sha256"],
    }))


if __name__ == "__main__":
    main()
