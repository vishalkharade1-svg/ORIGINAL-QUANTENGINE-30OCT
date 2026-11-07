"""11G-O archive availability probe (research-only, network-dependent).

Records which Binance Vision daily aggTrade files exist (via CHECKSUM
HEADs, no bulk download). Output is an OBSERVATION with an explicit
observation date (provenance metadata) — never a deterministic
research input. Tests must not depend on it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

SYMBOLS = ("BTCUSDT", "ETHUSDT")
BASE_URL = "https://data.binance.vision/data/futures/um/daily/aggTrades"


def probe(client, symbols=SYMBOLS, dates=()):
    rows = {}
    for sym in symbols:
        for date in dates:
            url = "%s/%s/%s-aggTrades-%s.zip.CHECKSUM" % (BASE_URL, sym, sym, date)
            try:
                r = client.get(url)
                rows["%s/%s" % (sym, date)] = r.status_code
            except Exception as exc:  # noqa: BLE001 (observation only)
                rows["%s/%s" % (sym, date)] = "ERROR:%s" % type(exc).__name__
    return {"observed_at": datetime.now(timezone.utc).isoformat(),
            "status": rows}


if __name__ == "__main__":
    import httpx
    dates = sys.argv[1:] or ["2026-09-%02d" % d for d in range(9, 16)]
    client = httpx.Client(timeout=60,
                          headers={"User-Agent": "python-quantengine-probe"})
    try:
        print(json.dumps(probe(client, dates=dates), indent=1, sort_keys=True))
    finally:
        client.close()
