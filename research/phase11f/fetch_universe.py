"""Phase 11F universe fetch (research-only reads).

Fetches frozen-universe windows (BTCUSDT + ETHUSDT, 1m) and writes
raw JSON with fetch metadata + sha256. Read-only candles endpoint.
No orders, no LIVE. Fetched data is NOT evaluated here.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.exchanges.delta.delta_history import DeltaHistory

OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# D1 = D2-file bars [500:7000]; D2-val = bars [7000:10000].
# Boundaries are resolved from the BTC file at runtime so ETH
# windows match exactly. D3-new = after oos_fresh end.
D1_SLICE = (500, 7000)
D2_SLICE = (7000, 10000)


def btc_file_bars():
    from research.phase11e.common import load_raw_bars
    doc = json.loads((BASE_DIR / "data/history/BTCUSDT_1m_oos.json").read_text())
    bars, _ = load_raw_bars(doc)
    return bars


def d3_start():
    doc = json.loads((BASE_DIR / "research/phase11e/data/oos_fresh.json").read_text())
    return max(int(c["time"]) for c in doc["candles"]) + 60


def fetch(symbol, start, end):
    history = DeltaHistory()
    if end is None:
        end = int(datetime.now(timezone.utc).timestamp())
    candles = history.candles(symbol, resolution="1m", start=start, end=end)
    rows = sorted((
        {
            "time": int(c.timestamp),
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candles
    ), key=lambda r: r["time"])
    return rows, end


def main():
    fetched_at = datetime.now(timezone.utc).isoformat()
    btc = btc_file_bars()
    d1 = btc[D1_SLICE[0]:D1_SLICE[1]]
    d2 = btc[D2_SLICE[0]:D2_SLICE[1]]
    d3s = d3_start()
    windows = {
        "D3_BTC": ("BTCUSDT", d3s, None),
        "D3_ETH": ("ETHUSDT", d3s, None),
        "D1_BTC": ("BTCUSDT", d1[0]["time"], d1[-1]["time"]),
        "D1_ETH": ("ETHUSDT", d1[0]["time"], d1[-1]["time"]),
        "D2_BTC": ("BTCUSDT", d2[0]["time"], d2[-1]["time"]),
        "D2_ETH": ("ETHUSDT", d2[0]["time"], d2[-1]["time"]),
    }
    for name, (symbol, start, end) in windows.items():
        rows, end_used = fetch(symbol, start, end)
        payload = {
            "symbol": symbol, "timeframe": "1m",
            "window": {"start": start, "end": end_used},
            "fetched_at": fetched_at,
            "fetched_count": len(rows),
            "candles": rows,
        }
        blob = json.dumps(payload, indent=1).encode()
        payload["sha256"] = hashlib.sha256(blob).hexdigest()
        path = OUT_DIR / ("universe_%s.json" % name)
        path.write_text(json.dumps(payload, indent=1))
        first = rows[0]["time"] if rows else None
        last = rows[-1]["time"] if rows else None
        print("%s %s n=%d range=%s..%s sha=%.12s" % (
            name, symbol, len(rows), first, last, payload["sha256"]),
            flush=True)


if __name__ == "__main__":
    main()
