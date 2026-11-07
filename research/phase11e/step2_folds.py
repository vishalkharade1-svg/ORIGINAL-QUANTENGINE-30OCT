"""11E step 2: IS statistics (regime cutoffs, random-entry k) + walk-forward folds.

IS = D1 + D2 (contaminated lineage, used for thresholds only — never
as OOS evidence for the edge claim). Fold runs use the frozen config.
Costs applied arithmetically per trade (exact: fills independent of
costs — proven by a rerun-equality check on F1).
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11e.common import (
    apply_costs, load_raw_bars, run_backtest, trade_metrics,
)

OUT = Path(__file__).resolve().parent / "data"


def load_all():
    docs = {}
    for name, rel in (("D1", "docs/audit/baseline_9s_delta_5000_raw.json"),
                      ("D2", "data/history/BTCUSDT_1m_oos.json"),
                      ("D3", "research/phase11e/data/oos_fresh.json")):
        doc = json.loads((BASE_DIR / rel).read_text())
        bars, _ = load_raw_bars(doc)
        docs[name] = bars
    return docs


def closes(bars):
    return [float(b["close"]) for b in bars]


def atr14_list(bars):
    """ATR(14) per bar from past data only (Wilder)."""
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    cl = closes(bars)
    trs = []
    for i in range(len(bars)):
        if i == 0:
            trs.append(highs[0] - lows[0])
        else:
            trs.append(max(highs[i] - lows[i], abs(highs[i] - cl[i - 1]),
                           abs(lows[i] - cl[i - 1])))
    out = [None] * len(bars)
    if len(trs) >= 14:
        seed = sum(trs[1:15]) / 14.0
        out[14] = seed
        prev = seed
        for i in range(15, len(trs)):
            prev = (prev * 13.0 + trs[i]) / 14.0
            out[i] = prev
    return out


def sma50_list(bars):
    cl = closes(bars)
    out = [None] * len(bars)
    window = []
    for i, c in enumerate(cl):
        window.append(c)
        if len(window) > 50:
            window.pop(0)
        if len(window) == 50:
            out[i] = sum(window) / 50.0
    return out


def quantiles(xs, qs):
    s = sorted(xs)
    return {q: s[min(len(s) - 1, int(len(s) * q))] for q in qs}


def main():
    docs = load_all()
    is_bars = docs["D1"] + [b for b in docs["D2"] if b["time"] < docs["D1"][0]["time"]]
    is_bars = sorted(is_bars, key=lambda b: b["time"])
    print("IS bars:", len(is_bars))

    # IS regime cutoffs (ATR14/close quantiles over IS only).
    atr = atr14_list(is_bars)
    cl = closes(is_bars)
    ratios = [a / c for a, c in zip(atr, cl) if a is not None and c]
    cuts = quantiles(ratios, [1 / 3, 2 / 3])
    print("vol cutoffs:", cuts)

    # Frozen random-entry k: median stop_dist/ATR14 over IS TRADES.
    ks = []
    is_trades = []
    for name, bars in (("D1", docs["D1"]), ("D2", docs["D2"])):
        res = run_backtest(bars)
        print(name, "orders/fills:", len(res["orders"]), len(res["trades"]))
        is_trades.extend(res["trades"])
        a = atr14_list(bars)
        by_ts = {b["time"]: i for i, b in enumerate(bars)}
        for t in res["trades"]:
            i = by_ts.get(t["entry_time"])
            if i is not None and a[i]:
                dist = abs(t["entry"] - t["stop"])
                if dist > 0:
                    ks.append(dist / a[i])
    ks.sort()
    k_med = ks[len(ks) // 2] if ks else 0.0
    print("k median:", k_med, "from", len(ks), "IS trades")

    spec_update = {"vol_cutoffs": cuts, "k_median": k_med, "k_n": len(ks)}
    (OUT / "step2_is_stats.json").write_text(json.dumps(spec_update, indent=1))


if __name__ == "__main__":
    main()
