"""11G-I Binance Vision acquisition (reproducible, read-only, public).

Downloads UM-futures daily aggTrades (+ CHECKSUM) and 1m klines for
cross-validation. Verifies every zip against its provider CHECKSUM
before writing to the immutable raw store. No auth, no writes to the
provider, polite single-flight requests.

Usage:
  python research/phase11g_i/acquisition/fetch_binance.py --date 2026-09-05 --symbol BTCUSDT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g.storage import store as ST  # noqa: E402

BASE_URL = "https://data.binance.vision/data/futures/um"
RAW_DIR = Path(__file__).resolve().parent / "raw"
HEADERS = {"User-Agent": "python-quantengine-probe", "Accept": "*/*"}


def _get(client, url):
    r = client.get(url)
    r.raise_for_status()
    return r.content


def fetch_day(client, symbol, date):
    """Returns manifest entries for the day's artifacts."""
    jobs = {
        "aggTrades": "daily/aggTrades/%s/%s-aggTrades-%s.zip" % (symbol, symbol, date),
        "klines": "daily/klines/%s/1m/%s-1m-%s.zip" % (symbol, symbol, date),
    }
    out = {"symbol": symbol, "date": date, "acquired_at": None, "files": {}}
    for kind, rel in jobs.items():
        url = BASE_URL + "/" + rel
        t0 = time.time()
        blob = _get(client, url)
        chk_raw = _get(client, url + ".CHECKSUM").decode().strip()
        seconds = round(time.time() - t0, 2)
        expected = chk_raw.split()[0]
        actual = hashlib.sha256(blob).hexdigest()
        if actual != expected:
            raise ValueError("CHECKSUM mismatch for %s" % rel)
        name = rel.split("/")[-1]
        meta = ST.write_raw(RAW_DIR / symbol / date, name, blob)
        chk_meta = ST.write_raw(RAW_DIR / symbol / date, name + ".CHECKSUM",
                                (chk_raw + "\n").encode())
        out["files"][kind] = {
            "url": url, "bytes": len(blob), "seconds": seconds,
            "provider_sha256": expected, "local_sha256": meta["sha256"],
            "checksum_match": True, "checksum_file_sha256": chk_meta["sha256"]}
    out["acquired_at"] = datetime.now(timezone.utc).isoformat()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--symbol", default="BTCUSDT")
    args = ap.parse_args()
    import httpx
    client = httpx.Client(timeout=300, headers=HEADERS)
    try:
        manifest = fetch_day(client, args.symbol, args.date)
    finally:
        client.close()
    path = RAW_DIR / args.symbol / args.date / "acquisition_manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}, indent=1))
    for kind, info in manifest["files"].items():
        print("%s bytes=%d sha=%.12s checksum_match=%s" % (
            kind, info["bytes"], info["local_sha256"], info["checksum_match"]))


if __name__ == "__main__":
    main()
