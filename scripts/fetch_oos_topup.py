"""
====================================================
QuantEngine -- OOS top-up acquisition (operator-run).

READ-ONLY acquisition: downloads BTCUSDT 1m candles for the
full post-Gate-A span (strictly after 1788601440) via the
existing paginated HistoricalLoader, merges with the existing post-Gate-A cache through the strict
research acquisition accumulator: identical duplicate candles are
deduplicated, conflicting same-timestamp candles fail closed, and
gaps are preserved (never filled), and writes a NEW
git-ignored cache. Phase-17/Phase-19 caches and all research
artifacts are never overwritten.

Output (git-ignored, cache for reproducible re-runs):
  data/history/BTCUSDT_1m_oos_topup.json
  data/history/BTCUSDT_1m_oos_topup.provenance.json

Dataset identity reuses the Phase-19 construction
(test_oos_data_extension_19.TestDatasetIdentity.
test_dataset_hash_matches): sha256 over
json.dumps(sorted(rows by time), sort_keys=True,
separators=(",", ":")).

No strategy, execution, risk, paper or live code is
touched; nothing is traded. Tier A direct target-venue
only (DELTA BTCUSDT perpetual 1m); no proxy, no synthetic,
no forward-fill, no interpolation, no timestamp alteration.
Public market data only: no credentials required or used.
====================================================
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import argparse
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.historical_loader import HistoricalLoader

OUT = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
PROV_OUT = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.provenance.json"
ROW_PROV_OUT = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.row_provenance.json"
PRIOR = ROOT / "data" / "history" / "BTCUSDT_1m_phase19_extension.json"
ROW_PROV_SCHEMA = "row-provenance-v1"

SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
SCHEMA_VERSION = "gate-a-raw-v1"
GATE_A_END = 1788601440


def dataset_identity(rows_asc):
    """Phase-19 dataset-hash construction (reuse, not a new scheme)."""
    blob = json.dumps(sorted(rows_asc, key=lambda r: r["time"]),
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Deterministic post-Gate-A OOS acquisition")
    parser.add_argument(
        "--end-timestamp", type=int, required=True,
        help="Explicit Unix-second acquisition anchor; no wall clock is used")
    parser.add_argument(
        "--extra-candles", type=int, default=120,
        help="Deterministic trailing request cushion (default: 120)")
    args = parser.parse_args(argv)
    if args.end_timestamp <= GATE_A_END:
        parser.error("--end-timestamp must be strictly after GATE_A_END")
    if args.extra_candles < 0:
        parser.error("--extra-candles must be non-negative")
    return args


def main(argv=None):
    args = _parse_args(argv)
    loader = HistoricalLoader()
    try:
        total = max((args.end_timestamp - GATE_A_END) // 60 +
                    args.extra_candles, 1000)
        data = loader.candles_paginated(
            SYMBOL, TIMEFRAME, total_candles=total,
            end_timestamp=args.end_timestamp)
    finally:
        loader.close()
    live = [r for r in data.get("result", [])
            if isinstance(r.get("time"), int) and r["time"] > GATE_A_END]
    prior_rows = []
    prior_provenance = []
    if OUT.exists() and ROW_PROV_OUT.exists():
        with io.open(str(OUT), encoding="utf-8") as fh:
            prior_rows = [r for r in json.load(fh).get("raw", [])
                          if isinstance(r, dict)]
        with io.open(str(ROW_PROV_OUT), encoding="utf-8") as fh:
            prior_provenance = json.load(fh).get("records", [])
    elif PRIOR.exists():
        with io.open(str(PRIOR), encoding="utf-8") as fh:
            prior_rows = [r for r in json.load(fh).get("raw", [])
                          if isinstance(r, dict)]
    from core.research.extension.provenance import (
        SCHEMA_VERSION as ROW_PROVENANCE_SCHEMA,
        build_row_provenance, provenance_identity,
    )
    from core.research.acquisition.accumulator import accumulate
    if not prior_provenance:
        prior_provenance = build_row_provenance(
            [r for r in prior_rows if isinstance(r.get("time"), int)
             and r["time"] > GATE_A_END],
            venue="DELTA",
            acquisition_source="Delta /v2/history/candles",
            acquisition_method="HistoricalLoader.candles_paginated",
            symbol=SYMBOL, timeframe=TIMEFRAME)
    live_provenance = build_row_provenance(
        live, venue="DELTA",
        acquisition_source="Delta /v2/history/candles",
        acquisition_method="HistoricalLoader.candles_paginated",
        symbol=SYMBOL, timeframe=TIMEFRAME)
    merged = accumulate(
        [r for r in prior_rows if isinstance(r.get("time"), int)
         and r["time"] > GATE_A_END],
        live, prior_provenance, live_provenance,
        boundary=GATE_A_END, expected_venue="DELTA",
        expected_source="Delta /v2/history/candles",
        expected_method="HistoricalLoader.candles_paginated",
        expected_symbol=SYMBOL, expected_timeframe=TIMEFRAME)
    merged_asc = merged["rows"]
    identity = dataset_identity(merged_asc)
    merged_desc = sorted(merged_asc, key=lambda r: r["time"], reverse=True)
    envelope = {"symbol": SYMBOL, "timeframe": TIMEFRAME,
                "schema_version": SCHEMA_VERSION,
                "fresh_after": GATE_A_END,
                "requested": total, "received": len(merged_desc),
                "prior_received": len(prior_rows),
                "live_received": len(live),
                "dataset_identity": identity,
                "raw": merged_desc}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(OUT), "w", encoding="utf-8", newline="") as fh:
        json.dump(envelope, fh, indent=2, sort_keys=True)
        fh.write("\n")
    row_records = build_row_provenance(
        merged_asc,
        venue="DELTA",
        acquisition_source="Delta /v2/history/candles",
        acquisition_method="HistoricalLoader.candles_paginated",
        symbol=SYMBOL, timeframe=TIMEFRAME,
    )
    row_identity = provenance_identity(row_records)
    row_prov = {"schema_version": ROW_PROVENANCE_SCHEMA,
                "venue": "DELTA",
                "acquisition_source": "Delta /v2/history/candles",
                "acquisition_method": "HistoricalLoader.candles_paginated",
                "symbol": SYMBOL, "timeframe": TIMEFRAME,
                "fresh_after": GATE_A_END,
                "row_count": len(row_records),
                "provenance_identity": row_identity,
                "records": row_records}
    with io.open(str(ROW_PROV_OUT), "w", encoding="utf-8", newline="") as fh:
        json.dump(row_prov, fh, indent=2, sort_keys=True)
        fh.write("\n")
    prov = {"venue": "DELTA",
            "acquisition_source": "Delta /v2/history/candles",
            "acquisition_method": "HistoricalLoader.candles_paginated",
            "merge_authority": "phase32 strict accumulator; identical duplicates only; conflicting duplicates fail closed",
            "identity_authority": "phase19 dataset_hash construction",
            "symbol": SYMBOL, "timeframe": TIMEFRAME,
            "schema_version": SCHEMA_VERSION,
            "fresh_after": GATE_A_END,
            "requested": total, "received": len(merged_desc),
            "dataset_identity": identity,
            "row_provenance_schema": ROW_PROVENANCE_SCHEMA,
            "row_provenance_identity": row_identity,
            "tier": "A-DIRECT"}
    with io.open(str(PROV_OUT), "w", encoding="utf-8", newline="") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("topup bars: %d (prior %d + live %d, strictly after %d)"
          % (len(merged_desc), len(prior_rows), len(live), GATE_A_END))
    print("dataset_identity: %s" % identity)
    if merged_desc:
        print("range: %d -> %d" % (merged_desc[-1]["time"],
                                   merged_desc[0]["time"]))


if __name__ == "__main__":
    main()
