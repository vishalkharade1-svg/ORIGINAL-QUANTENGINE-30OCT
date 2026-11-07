"""Build the deterministic Phase 35 multi-symbol coverage artifact."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.research.readiness.symbol_coverage import audit

CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
OUT = ROOT / "research" / "results" / "phase35_symbol_coverage.json"


def main():
    env = json.loads(CACHE.read_text(encoding="utf-8"))
    rows = env.get("raw", [])
    result = audit(rows, required_bars=300000, required_trades=60)
    artifact = {
        "phase": 35,
        "purpose": "multi-symbol OOS evidence coverage only",
        "dataset_identity": env.get("dataset_identity"),
        "coverage": result,
        "universal_validation": False,
        "production_ready": False,
        "is_production_ready": False,
        "limitations": [
            "current OOS candle cache has no explicit per-row symbol field",
            "single-symbol filenames are not used to synthesize symbol metadata",
            "no universal claim is permitted from one symbol",
            "additional explicit-symbol evidence is required for cross-symbol consistency",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print("phase35_symbols=%d" % len(result["symbols"]))
    print("missing_symbol_rows=%d" % result["missing_symbol_rows"])
    print("audit_id=%s" % result["audit_id"])


if __name__ == "__main__":
    main()
