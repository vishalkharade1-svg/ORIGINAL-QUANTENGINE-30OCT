"""
====================================================
QuantEngine -- Phase 17 fresh-data fetch (operator-run).

READ-ONLY acquisition: downloads BTCUSDT 1m candles
strictly AFTER the frozen Gate-A window end
(GATE_A_END = 1788601440) via the existing paginated
HistoricalLoader. No strategy, execution, risk, paper or
live code is touched; nothing is traded.

Output (git-ignored, cache for reproducible re-runs):
  data/history/BTCUSDT_1m_phase17_fresh.json
  data/history/BTCUSDT_1m_phase17_fresh.provenance.json

The committed Phase-17 artifact records only hashes +
manifest facts, never wall-clock fetch metadata as IDs.
====================================================
"""

from __future__ import annotations

import io
import json
import pathlib
import time

from data.historical_loader import HistoricalLoader

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
PROV_OUT = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.provenance.json"

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
SCHEMA_VERSION = "gate-a-raw-v1"
# Frozen Gate-A window end (docs/audit/baseline_9s_delta_5000_raw.json).
# Fresh means STRICTLY AFTER: no overlap with discovery data.
GATE_A_END = 1788601440


def main():
    loader = HistoricalLoader()
    try:
        # Upper bound: every minute since Gate-A end + margin.
        total = int(time.time()) - GATE_A_END
        total = max(total // 60 + 120, 1000)
        data = loader.candles_paginated(
            SYMBOL, TIMEFRAME, total_candles=total)
    finally:
        loader.close()
    rows = [r for r in data.get("result", [])
            if isinstance(r.get("time"), int) and r["time"] > GATE_A_END]
    rows.sort(key=lambda r: r["time"], reverse=True)
    envelope = {"symbol": SYMBOL, "timeframe": TIMEFRAME,
                "schema_version": SCHEMA_VERSION,
                "fresh_after": GATE_A_END,
                "requested": total, "received": len(rows),
                "raw": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(OUT), "w", encoding="utf-8", newline="") as fh:
        json.dump(envelope, fh, indent=2, sort_keys=True)
        fh.write("\n")
    prov = {"venue": "DELTA",
            "acquisition_source": "Delta /v2/history/candles",
            "acquisition_method": "HistoricalLoader.candles_paginated",
            "symbol": SYMBOL, "timeframe": TIMEFRAME,
            "schema_version": SCHEMA_VERSION,
            "fresh_after": GATE_A_END,
            "requested": total, "received": len(rows)}
    with io.open(str(PROV_OUT), "w", encoding="utf-8",
                 newline="") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("fresh bars: %d (strictly after %d)" % (len(rows), GATE_A_END))
    if rows:
        print("range: %d -> %d" % (rows[-1]["time"], rows[0]["time"]))


if __name__ == "__main__":
    main()
