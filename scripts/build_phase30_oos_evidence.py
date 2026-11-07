"""Phase 30 -- fresh genuine OOS evidence accumulation.

Research-only.  Consumes the existing direct-venue BTCUSDT 1m top-up cache,
replays the frozen strategy independently over six chronological periods, and
writes a deterministic evidence artifact.  It does not discover hypotheses,
change strategy parameters, submit orders, or mutate runtime state.

The artifact is intentionally an evidence-accumulation record, not a strategy
validation result.  The locked 9M sample gates remain authoritative.
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
ROW_PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.row_provenance.json"
OUT = ROOT / "research" / "results" / "phase30_oos_evidence_accumulation.json"
BOUNDARY = 1788601440
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"


def _load(path):
    with io.open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def _dataset_hash(rows):
    blob = json.dumps(sorted(rows, key=lambda r: r["time"]),
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _periods(rows, n=6):
    total = len(rows)
    base = total // n
    out = []
    for i in range(n):
        s = i * base
        e = (i + 1) * base if i < n - 1 else total
        part = rows[s:e]
        out.append(("OOS_%02d" % (i + 1), s, e, part))
    return out


def _replay(rows):
    from core.research.oos_validation.execution import run_frozen_oos
    from core.research.oos_validation.report import classify_period

    result = []
    for period_id, start_i, end_i, part in _periods(rows):
        funnel = run_frozen_oos(part, symbol=SYMBOL)
        status, reason = classify_period(funnel)
        result.append({
            "period_id": period_id,
            "index_start": start_i,
            "index_end": end_i,
            "start": int(part[0]["time"]),
            "end": int(part[-1]["time"]),
            "bars": len(part),
            "orders": int(funnel["orders"]),
            "fills": int(funnel["fills"]),
            "wins": int(funnel["wins"]),
            "losses": int(funnel["losses"]),
            "breakeven": int(funnel["breakeven"]),
            "gross_pnl": float(funnel["gross_pnl"]),
            "actual_fill_rr": list(funnel["actual_fill_rr"]),
            "terminal": dict(sorted(funnel["terminal"].items())),
            "directional": dict(sorted(funnel["directional"].items())),
            "status": status,
            "reason": reason,
        })
    return result


def main():
    env = _load(CACHE)
    rows = sorted(env["raw"], key=lambda r: r["time"])
    if not rows:
        raise RuntimeError("OOS cache is empty")
    if any(int(r["time"]) <= BOUNDARY for r in rows):
        raise RuntimeError("OOS cache crosses discovery boundary")
    if _dataset_hash(rows) != env["dataset_identity"]:
        raise RuntimeError("OOS dataset identity mismatch")

    provenance = _load(ROW_PROV)
    if provenance.get("row_count") != len(rows):
        raise RuntimeError("row provenance count mismatch")

    periods = _replay(rows)
    fills = sum(p["fills"] for p in periods)
    orders = sum(p["orders"] for p in periods)
    wins = sum(p["wins"] for p in periods)
    losses = sum(p["losses"] for p in periods)
    gross = sum(p["gross_pnl"] for p in periods)
    settled = sum(1 for p in periods if p["fills"] >= 10)

    artifact = {
        "phase": 30,
        "name": "Fresh genuine OOS evidence accumulation",
        "mission": "Accumulate executable observations for the frozen 9M protocol; no promotion.",
        "venue": "DELTA",
        "tier": "A-DIRECT",
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "discovery_boundary": BOUNDARY,
        "dataset": {
            "rows": len(rows),
            "start": int(rows[0]["time"]),
            "end": int(rows[-1]["time"]),
            "dataset_identity": env["dataset_identity"],
            "row_provenance_identity": provenance.get("provenance_identity"),
        },
        "frozen_strategy": True,
        "strategy_parameters_changed": False,
        "hypotheses_tested": 0,
        "periods": periods,
        "totals": {
            "orders": orders,
            "completed_trades": fills,
            "wins": wins,
            "losses": losses,
            "gross_pnl": gross,
            "settled_periods": settled,
        },
        "nine_m_protocol": {
            "required_periods": 6,
            "minimum_trades_per_period": 10,
            "minimum_total_trades": 60,
            "minimum_surviving_periods": 5,
            "current_status": "OOS_BLOCKED",
            "reason": "insufficient completed trades for 9M validation",
        },
        "evidence_classification": "GENUINE_VENUE_HISTORICAL_OHLCV_REPLAY",
        "edge_status": "NOT_ESTABLISHED",
        "production_ready": False,
        "limitations": [
            "No 9L hypothesis was revalidated because no current 9L finding was preregistered against this dataset.",
            "Only %d completed trades were observed; 60 are required by the locked 9M protocol." % fills,
            "Only %d of 6 periods reached the 10-trade settling threshold." % settled,
            "OHLCV-only evidence; microstructure, funding, and venue fee schedule remain unavailable or unverified.",
            "This artifact does not establish profitability or production readiness.",
        ],
    }
    text = json.dumps(artifact, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(OUT), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print("wrote %s" % OUT)
    print("rows=%d orders=%d fills=%d wins=%d losses=%d settled_periods=%d" %
          (len(rows), orders, fills, wins, losses, settled))
    print("status=OOS_BLOCKED")


if __name__ == "__main__":
    main()
