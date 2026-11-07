"""11G-H public read-only acquisition probes (no auth, no writes).

Fetches SMALL shape-proving samples only: 15m candles (REAL HTF proof),
recent trades (recent-only proof), L2 snapshot (live-only proof),
ticker (live OI/funding snapshot proof). Raw responses stored
byte-identically with provenance sidecars. Nothing here is research
evidence — shapes inform the capability verdict.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g.storage import store as ST  # noqa: E402

BASE_URL = "https://api.delta.exchange"
OUT_DIR = Path(__file__).resolve().parent / "probes"
SYMBOL = "BTCUSDT"
HEADERS = {"User-Agent": "python-quantengine-probe", "Accept": "application/json"}


def _get(client, path, params):
    r = client.get(BASE_URL + path, params=params)
    r.raise_for_status()
    return r.json()


def main():
    import httpx
    client = httpx.Client(timeout=15, headers=HEADERS)
    acquired_at = datetime.now(timezone.utc).isoformat()
    jobs = {
        "candles_15m": ("/v2/history/candles",
                        {"symbol": SYMBOL, "resolution": "15m",
                         "start": 1788700000, "end": 1788700000 + 900 * 5}),
        "recent_trades": ("/v2/trades/" + SYMBOL, {}),
        "l2_snapshot": ("/v2/l2orderbook/" + SYMBOL, {}),
        "ticker": ("/v2/tickers/" + SYMBOL, {}),
    }
    manifest = {"acquired_at": acquired_at, "symbol": SYMBOL, "probes": {}}
    for name, (path, params) in jobs.items():
        t0 = time.time()
        body = _get(client, path, params)
        blob = json.dumps(body, sort_keys=True).encode()
        meta = ST.write_raw(OUT_DIR, name + ".json", blob, overwrite=True)
        result = body.get("result")
        n = len(result) if isinstance(result, list) else "object"
        manifest["probes"][name] = {
            "path": path, "params": params, "http": 200,
            "seconds": round(time.time() - t0, 2),
            "result_shape": n, "sha256": meta["sha256"]}
        print("%-14s n=%s sha=%.12s" % (name, n, meta["sha256"]), flush=True)
    (OUT_DIR / "probe_manifest.json").write_text(json.dumps(manifest, indent=1))
    client.close()


if __name__ == "__main__":
    main()
