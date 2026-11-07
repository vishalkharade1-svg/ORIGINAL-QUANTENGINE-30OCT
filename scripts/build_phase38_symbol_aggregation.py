"""Build deterministic cross-symbol OOS aggregation from bound symbol coverage."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.research.readiness.symbol_aggregation import aggregate_symbol_results

SRC = ROOT / "research" / "results" / "phase36_provenance_symbol_coverage.json"
OUT = ROOT / "research" / "results" / "phase38_symbol_aggregation.json"


def main():
    source = json.loads(SRC.read_text(encoding="utf-8"))
    coverage = source["coverage"]
    result = aggregate_symbol_results(
        coverage.get("symbols", []), required_symbols=2
    )
    artifact = {
        "phase": 38,
        "purpose": "preserve independent per-symbol OOS evidence during aggregation",
        "source_audit_id": coverage["audit_id"],
        "aggregation": result,
        "universal_validation": False,
        "production_ready": False,
        "is_production_ready": False,
        "limitations": [
            "aggregation does not create absent symbol evidence",
            "one observed symbol cannot establish cross-symbol consistency",
            "UNAVAILABLE and REJECTED remain distinct states",
            "OOS trade-count and multi-period gates remain independently unsatisfied",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
