"""Build the deterministic multi-symbol OOS acquisition manifest.

Current snapshot may contain one symbol only; the artifact must then say so.
No symbol is inferred from filenames. Row-level provenance is authoritative.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research.acquisition.multi_symbol import build_manifest
from core.research.extension.provenance import validate_row_provenance

DATA = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.row_provenance.json"
OUT = ROOT / "research" / "results" / "phase37_multi_symbol_oos_manifest.json"
BOUNDARY = 1788601440


def main():
    rows = json.loads(DATA.read_text(encoding="utf-8"))["raw"]
    records = json.loads(PROV.read_text(encoding="utf-8"))["records"]
    validate_row_provenance(rows, records, expected_venue="DELTA",
                             expected_source="Delta /v2/history/candles",
                             expected_method="HistoricalLoader.candles_paginated",
                             expected_symbol="BTCUSDT", expected_timeframe="1m")
    manifest = build_manifest([{"symbol": "BTCUSDT", "rows": rows,
                                "provenance": records}],
                              boundary=BOUNDARY, expected_venue="DELTA",
                              expected_source="Delta /v2/history/candles",
                              expected_method="HistoricalLoader.candles_paginated",
                              expected_timeframe="1m")
    manifest["interpretation"] = {
        "cross_symbol_validation": "UNAVAILABLE",
        "reason": "only one provenance-bound symbol is present",
        "observed_symbols": ["BTCUSDT"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
