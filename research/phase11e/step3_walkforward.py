"""11E step 3: walk-forward folds F1-F4 + cost application + no-feedback proof."""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import risk_settings
from research.phase11e.common import (
    COST_SCENARIOS, apply_costs, load_raw_bars, run_backtest, trade_metrics,
)

OUT = Path(__file__).resolve().parent / "data"


def scenario_settings(key):
    spec = COST_SCENARIOS[key]
    return {
        "COMMISSION_PER_TRADE": spec["COMMISSION_PER_TRADE"],
        "COMMISSION_RATE": spec["COMMISSION_RATE"],
        "SLIPPAGE_BPS": spec["SLIPPAGE_BPS"],
    }


def main():
    docs = {}
    for name, rel in (("D2", "data/history/BTCUSDT_1m_oos.json"),
                      ("D3", "research/phase11e/data/oos_fresh.json")):
        doc = json.loads((BASE_DIR / rel).read_text())
        bars, _ = load_raw_bars(doc)
        docs[name] = bars
    d2 = docs["D2"]
    folds = {
        "F1": d2[0:3333],
        "F2": d2[3333:6666],
        "F3": d2[6666:10000],
        "F4": docs["D3"],
    }
    results = {}
    for name, bars in folds.items():
        res = run_backtest(bars)
        by_cost = {"A_zero": trade_metrics(res["trades"])}
        for scenario in ("B_small", "C_moderate", "D_adverse"):
            rerun = run_backtest(bars, scenario_settings(scenario))
            assert [t["trade_id"] for t in rerun["trades"]] == \
                [t["trade_id"] for t in res["trades"]], \
                "fills must not depend on costs (%s %s)" % (name, scenario)
            by_cost[scenario] = trade_metrics(rerun["trades"])
            (OUT / ("fold_%s_%s.json" % (name, scenario))).write_text(
                json.dumps(rerun["trades"], indent=1))
        results[name] = {
            "bars": len(bars),
            "first": bars[0]["time"],
            "last": bars[-1]["time"],
            "orders": len(res["orders"]),
            "fills": len(res["trades"]),
            "by_cost": by_cost,
            "trade_ids": [t["trade_id"] for t in res["trades"]],
        }
        m = by_cost["A_zero"]
        c = by_cost["C_moderate"]
        print("%s bars=%d orders=%d fills=%d W/L=%d/%d netA=%.4f netC=%.4f" % (
            name, len(bars), len(res["orders"]), len(res["trades"]),
            m["wins"], m["losses"], m["net_pnl"], c["net_pnl"]),
            flush=True)
        # Persist per-fold zero-cost trades for downstream analyses.
        (OUT / ("fold_%s_trades.json" % name)).write_text(
            json.dumps(res["trades"], indent=1))

    results["_production_cost_basis"] = (
        "rerun-based (production books costs on pre-resize sizer "
        "notional; arithmetic on final notional understates — "
        "see report §7; separately-reported production finding)"
    )
    (OUT / "step3_folds.json").write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
