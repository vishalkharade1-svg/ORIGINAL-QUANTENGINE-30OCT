"""Phase 11E D3 fetch: post-freeze clean OOS window (research-only read).

Fetches BTCUSDT 1m from the end of the Gate A window to now,
records fetch metadata + sha256, writes research/phase11e/data/oos_fresh.json.
Read-only exchange access (candles endpoint). No orders, no LIVE.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.exchanges.delta.delta_history import DeltaHistory

GATEA_END = 1788301500 + 4999 * 60  # last Gate A bar (2026-09-05T09:44Z)
OUT = Path(__file__).resolve().parent / "data" / "oos_fresh.json"


def main():
    fetched_at = datetime.now(timezone.utc)
    history = DeltaHistory()
    candles = history.candles(
        "BTCUSDT", resolution="1m", start=GATEA_END + 60, end=int(fetched_at.timestamp())
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
    ]
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "window": {"start": GATEA_END + 60, "end": int(fetched_at.timestamp())},
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
        "sha256": payload["sha256"],
        "path": str(OUT),
    }))


if __name__ == "__main__":
    main()
