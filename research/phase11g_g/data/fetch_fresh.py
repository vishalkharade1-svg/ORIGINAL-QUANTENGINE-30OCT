"""Phase 11G-G Tier-1 gap-window fetcher (pre-execution acquisition).

Target: the ONLY recent window overlapping no in-repo dataset —
(D2/phase-7 end, Gate-A start) = [1788175500, 1788301440], ~2100 bars.
Windowed GET /v2/history/candles in two halves (single-request caps),
merged + deduped + sorted. Pre-execution: request bounds fixed here
before any 11G-G run; the window is defined by avoidance-of-overlap,
never by contents (nothing observed yet).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from data.historical_loader import HistoricalLoader  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
RESOLUTION = "1m"
START = 1788175500
END = 1788301440


def fetch_window(loader, symbol, start, end):
    try:
        from core.exchanges.delta.delta_history import DeltaHistory
        hist = DeltaHistory()
        candles = hist.candles(symbol, resolution=RESOLUTION, start=start, end=end)
        rows = [{"time": int(c.timestamp), "open": float(c.open),
                 "high": float(c.high), "low": float(c.low),
                 "close": float(c.close), "volume": float(c.volume)}
                for c in candles]
        return rows
    finally:
        pass


def main():
    loader = HistoricalLoader()
    try:
        mid = (START + END) // 2
        for symbol in SYMBOLS:
            t0 = time.time()
            rows = []
            for s, e in ((START, mid), (mid + 60, END)):
                try:
                    r = loader.candles(symbol, RESOLUTION, start=s, end=e)
                    result = r.get("result", []) if isinstance(r, dict) else r
                except TypeError:
                    result = fetch_window(loader, symbol, s, e)
                rows.extend(result if isinstance(result, list) else [])
                time.sleep(0.3)
            seen, dedup = set(), []
            for r in rows:
                t = int(r["time"])
                if START <= t <= END and t not in seen:
                    seen.add(t)
                    dedup.append(r)
            dedup.sort(key=lambda r: int(r["time"]))
            acquired_at = datetime.now(timezone.utc).isoformat()
            payload = {
                "dataset_id": "11gg_gap_%s" % symbol.lower(),
                "symbol": symbol, "timeframe": RESOLUTION,
                "source": "Delta Exchange", "endpoint": "/v2/history/candles",
                "request": {"resolution": RESOLUTION, "start": START, "end": END,
                            "halves": [[START, mid], [mid + 60, END]],
                            "window_rule": "strictly after D2/phase-7 end, "
                                           "strictly before Gate-A start"},
                "acquired_at": acquired_at,
                "fetch_seconds": round(time.time() - t0, 2),
                "fetched_count": len(dedup),
                "candles": dedup,
            }
            blob = json.dumps(payload, sort_keys=True).encode()
            payload["sha256"] = hashlib.sha256(blob).hexdigest()
            path = OUT_DIR / ("fresh_11gg_gap_%s.json" % symbol.lower())
            path.write_text(json.dumps(payload, indent=1, sort_keys=True))
            first = min(int(r["time"]) for r in dedup)
            last = max(int(r["time"]) for r in dedup)
            print("%s n=%d range=%d..%d expected=%d sha=%.12s" % (
                symbol, len(dedup), first, last,
                (END - START) // 60 + 1, payload["sha256"]), flush=True)
    finally:
        loader.close()


if __name__ == "__main__":
    main()
