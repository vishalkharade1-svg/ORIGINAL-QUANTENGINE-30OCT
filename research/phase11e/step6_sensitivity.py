"""11E step 6: pre-registered sensitivity neighborhood (§12).

Six variants (baseline + 5 perturbations from spec.json) on pooled
OOS (D2 + D3), each at zero-cost and scenario C. Overrides apply
via mock.patch of risk_settings inside research runs only.
Full matrix reported; no selection.
"""
import json
import sys
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import risk_settings
from research.phase11e.common import (
    COST_SCENARIOS, load_raw_bars, run_backtest, trade_metrics,
)

OUT = Path(__file__).resolve().parent / "data"
VARIANTS = [
    ("baseline", {}),
    ("wait25", {"MAX_WAIT_BARS": 25}),
    ("wait35", {"MAX_WAIT_BARS": 35}),
    ("delay2", {"ENTRY_DELAY_BARS": 2}),
    ("width008", {"MIN_RISK_WIDTH_ATR": 0.08}),
    ("width012", {"MIN_RISK_WIDTH_ATR": 0.12}),
]


def main():
    docs = {}
    for name, rel in (("D2", "data/history/BTCUSDT_1m_oos.json"),
                      ("D3", "research/phase11e/data/oos_fresh.json")):
        doc = json.loads((BASE_DIR / rel).read_text())
        bars, _ = load_raw_bars(doc)
        docs[name] = bars
    pooled_bars = docs["D2"] + [b for b in docs["D3"]]
    pooled_bars.sort(key=lambda b: b["time"])
    matrix = {}
    for vname, overrides in VARIANTS:
        row = {}
        with mock.patch.multiple(
                risk_settings, **overrides) if overrides else _nullcontext():
            res = run_backtest(pooled_bars)
            row["A_zero"] = trade_metrics(res["trades"])
            cset = dict(COST_SCENARIOS["C_moderate"])
            with mock.patch.object(risk_settings, "COMMISSION_PER_TRADE", cset["COMMISSION_PER_TRADE"]), \
                 mock.patch.object(risk_settings, "COMMISSION_RATE", cset["COMMISSION_RATE"]), \
                 mock.patch.object(risk_settings, "SLIPPAGE_BPS", cset["SLIPPAGE_BPS"]):
                rerun = run_backtest(pooled_bars)
            assert [t["trade_id"] for t in rerun["trades"]] == \
                [t["trade_id"] for t in res["trades"]], "fills moved under costs"
            row["C_moderate"] = trade_metrics(rerun["trades"])
        matrix[vname] = {
            "orders": len(res["orders"]), "fills": len(res["trades"]),
            "netA": row["A_zero"]["net_pnl"], "netC": row["C_moderate"]["net_pnl"],
            "expC": row["C_moderate"]["expectancy"],
            "W/L": [row["C_moderate"]["wins"], row["C_moderate"]["losses"]],
        }
        print(vname, matrix[vname], flush=True)
    (OUT / "step6_sensitivity.json").write_text(json.dumps(matrix, indent=1, default=str))
    print("STEP6-DONE", flush=True)


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


if __name__ == "__main__":
    main()
