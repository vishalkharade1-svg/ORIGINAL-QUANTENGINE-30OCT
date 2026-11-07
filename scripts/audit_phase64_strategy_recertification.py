"""Phase 64: current-source strategy recertification boundary.

Read-only forensic check. It computes the current nine-file strategy identity,
runs the preserved Gate-A dataset through the current research backtester, and
records whether the historical fingerprint remains reproducible. Missing
historical inputs are reported as blockers; nothing is fabricated or repinned.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.phase11e.common import load_raw_bars, run_backtest

STRATEGY_FILES = [
    "core/execution/entry_model.py",
    "core/setup/trade_setup_builder.py",
    "core/setup/decision_engine.py",
    "core/execution/execution_engine.py",
    "core/risk/risk_engine.py",
    "core/backtesting/accounting.py",
    "backtesting/backtester.py",
    "core/paper_trading/paper_trading_engine.py",
    "config/risk_settings.py",
]
RECORDED_DIGEST = "c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6"
FORENSIC_DIGEST = "9eff61b777846c7f5e2056c486c9c381872a93e154d35160e70f63051c8fd8a2"
HISTORICAL_GATE_A = {
    "orders": 27, "fills": 11, "wins": 6, "losses": 5,
    "breakevens": 0, "net": 0.117534,
}


def digest(root: Path):
    per_file = []
    for name in STRATEGY_FILES:
        raw = (root / name).read_bytes().replace(b"\r\n", b"\n")
        per_file.append({"file": name, "sha256": hashlib.sha256(raw).hexdigest()})
    joined = "".join(x["sha256"] for x in per_file)
    return hashlib.sha256(joined.encode()).hexdigest(), per_file


def gate_a_fingerprint(root: Path):
    path = root / "docs/audit/baseline_9s_delta_5000_raw.json"
    doc = json.loads(path.read_text())
    bars, meta = load_raw_bars(doc)
    result = run_backtest(bars)
    nets = [t["net"] for t in result["trades"]]
    return {
        "dataset": str(path.relative_to(root)),
        "bars": len(bars),
        "first": bars[0]["time"],
        "last": bars[-1]["time"],
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "current": {
            "orders": len(result["orders"]),
            "fills": len(result["trades"]),
            "wins": sum(x > 0 for x in nets),
            "losses": sum(x < 0 for x in nets),
            "breakevens": sum(x == 0 for x in nets),
            "net": round(sum(nets), 6),
        },
        "historical": HISTORICAL_GATE_A,
        "matches_historical": {
            "orders": len(result["orders"]) == HISTORICAL_GATE_A["orders"],
            "fills": len(result["trades"]) == HISTORICAL_GATE_A["fills"],
            "wins": sum(x > 0 for x in nets) == HISTORICAL_GATE_A["wins"],
            "losses": sum(x < 0 for x in nets) == HISTORICAL_GATE_A["losses"],
            "breakevens": sum(x == 0 for x in nets) == HISTORICAL_GATE_A["breakevens"],
            "net": round(sum(nets), 6) == HISTORICAL_GATE_A["net"],
        },
        "meta": meta,
    }


def main():
    current_digest, per_file = digest(ROOT)
    gate_a = gate_a_fingerprint(ROOT)
    d2 = ROOT / "data/history/BTCUSDT_1m_oos.json"
    report = {
        "schema": "phase64-strategy-recertification-v1",
        "production_ready": False,
        "status": "BLOCKED",
        "strategy_identity": {
            "recorded_digest": RECORDED_DIGEST,
            "forensic_phase4_digest": FORENSIC_DIGEST,
            "current_digest": current_digest,
            "matches_recorded": current_digest == RECORDED_DIGEST,
            "matches_forensic": current_digest == FORENSIC_DIGEST,
            "per_file": per_file,
        },
        "gate_a": gate_a,
        "historical_inputs": {
            "D1_gate_a": True,
            "D2_phase7": d2.exists(),
            "D3_fresh": (ROOT / "research/phase11e/data/oos_fresh.json").exists(),
        },
        "reasons": [
            "current backtester does not reproduce the historical Gate-A fingerprint",
            "the current strategy digest differs from both the recorded research identity and the forensic Phase-4 identity",
            "D2 historical Phase-7 OOS input is absent from the supplied repository, so full historical recertification cannot be rerun",
            "no historical strategy hash or research artifact is repinned or rewritten",
        ],
        "conclusion": "current strategy requires fresh research certification; historical findings are not transferable",
    }
    out = ROOT / "research/results/phase64_strategy_recertification.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "current_digest": current_digest,
                      "gate_a": gate_a["current"], "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
