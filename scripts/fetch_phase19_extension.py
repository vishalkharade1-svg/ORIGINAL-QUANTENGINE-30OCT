"""
====================================================
QuantEngine -- Phase 19 extension-data fetch (operator-run).

READ-ONLY acquisition: downloads BTCUSDT 1m candles for
the full post-Gate-A span (strictly after 1788601440) via
the existing paginated HistoricalLoader, merges with the
Phase-17 fresh cache by timestamp (dedupe, no fabrication),
and writes a NEW git-ignored cache. Phase-18 dataset and
artifacts are never overwritten.

Output (git-ignored, cache for reproducible re-runs):
  data/history/BTCUSDT_1m_phase19_extension.json
  data/history/BTCUSDT_1m_phase19_extension.provenance.json

No strategy, execution, risk, paper or live code is
touched; nothing is traded. Tier A direct target-venue
only (DELTA BTCUSDT perpetual 1m); no proxy, no synthetic.
====================================================
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.historical_loader import HistoricalLoader

OUT = ROOT / "data" / "history" / "BTCUSDT_1m_phase19_extension.json"
PROV_OUT = ROOT / "data" / "history" / "BTCUSDT_1m_phase19_extension.provenance.json"
PRIOR = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
SCHEMA_VERSION = "gate-a-raw-v1"
GATE_A_END = 1788601440


def main():
    loader = HistoricalLoader()
    try:
        total = int(time.time()) - GATE_A_END
        total = max(total // 60 + 120, 1000)
        data = loader.candles_paginated(SYMBOL, TIMEFRAME,
                                        total_candles=total)
    finally:
        loader.close()
    live = [r for r in data.get("result", [])
            if isinstance(r.get("time"), int) and r["time"] > GATE_A_END]
    prior_rows = []
    if PRIOR.exists():
        with io.open(str(PRIOR), encoding="utf-8") as fh:
            prior_rows = [r for r in json.load(fh).get("raw", [])
                          if isinstance(r.get("time"), int)
                          and r["time"] > GATE_A_END]
    from core.research.extension.extension import dedupe_merge
    merged_asc = dedupe_merge(prior_rows, live, GATE_A_END)
    merged_desc = sorted(merged_asc, key=lambda r: r["time"], reverse=True)
    envelope = {"symbol": SYMBOL, "timeframe": TIMEFRAME,
                "schema_version": SCHEMA_VERSION,
                "fresh_after": GATE_A_END,
                "requested": total, "received": len(merged_desc),
                "prior_received": len(prior_rows),
                "live_received": len(live),
                "raw": merged_desc}
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
            "requested": total, "received": len(merged_desc),
            "tier": "A-DIRECT"}
    with io.open(str(PROV_OUT), "w", encoding="utf-8", newline="") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("extension bars: %d (prior %d + live %d, strictly after %d)"
          % (len(merged_desc), len(prior_rows), len(live), GATE_A_END))
    if merged_desc:
        print("range: %d -> %d" % (merged_desc[-1]["time"],
                                   merged_desc[0]["time"]))


if __name__ == "__main__":
    main()
