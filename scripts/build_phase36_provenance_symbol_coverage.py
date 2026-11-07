"""Build deterministic symbol coverage from bound row-level provenance."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.research.readiness.symbol_coverage import audit

CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
ROW_PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.row_provenance.json"
OUT = ROOT / "research" / "results" / "phase36_provenance_symbol_coverage.json"


def main():
    env = json.loads(CACHE.read_text(encoding="utf-8"))
    prov_env = json.loads(ROW_PROV.read_text(encoding="utf-8"))
    rows = env.get("raw", [])
    provenance = prov_env.get("records", [])
    result = audit(rows, required_bars=300000, required_trades=60,
                   provenance=provenance)
    artifact = {
        "phase": 36,
        "purpose": "prove symbol coverage from existing bound row-level provenance",
        "dataset_identity": env.get("dataset_identity"),
        "provenance_identity": prov_env.get("provenance_identity"),
        "coverage": result,
        "universal_validation": False,
        "production_ready": False,
        "is_production_ready": False,
        "limitations": [
            "row-level provenance establishes the observed symbol only; it does not create additional symbols",
            "current evidence contains one explicitly provenance-bound symbol",
            "cross-symbol consistency remains unavailable until additional symbol evidence exists",
            "OOS trade-count and period gates remain independently unsatisfied",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print("phase36_symbols=%d" % len(result["symbols"]))
    print("missing_symbol_rows=%d" % result["missing_symbol_rows"])
    print("symbol_source=%s" % result["symbol_source"])
    print("audit_id=%s" % result["audit_id"])


if __name__ == "__main__":
    main()
