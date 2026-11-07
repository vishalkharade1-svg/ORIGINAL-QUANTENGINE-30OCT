"""11G-K counts-only feasibility probe (NO economics, NO fills, NO P&L).

Counts COMPONENT events per frozen hypothesis on the certified day to
catch MECHANICALLY BROKEN specs (e.g., impossible conjunctions, unit
errors) before freezing. Conjunction sparsity is a legitimate empirical
outcome and NEVER a reason to change a threshold here. This probe
computes no costs, no metrics, no winners.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11g_j.replay import engine as ENG  # noqa: E402
from research.phase11g_j.replay import load as LOAD  # noqa: E402


def main():
    rev = LOAD.load_trades()
    n = len(rev)
    print("events:", n)
    # Component presence checks (counts only).
    # 5m imbalance extremes via coarse minute scan (trade-derived).
    from collections import defaultdict
    per_min = defaultdict(list)
    for t in rev._trades:
        per_min[t.event_ms // 60000].append(t)
    minutes = sorted(per_min)
    ext = 0
    for m in minutes:
        ts = per_min[m]
        b = sum(t.quantity for t in ts if t.aggressor_side == "buy")
        s = sum(t.quantity for t in ts if t.aggressor_side == "sell")
        tot = b + s
        if tot > 0 and abs((b - s) / tot) >= 0.6:
            ext += 1
    print("minutes:", len(minutes), "| |imbalance|>=0.6 minutes:", ext)
    # Displacement/BOS/spring components need 1m OHLCV context: count via
    # the certified kline file (structure-only, no economics).
    import csv
    import zipfile
    z = zipfile.ZipFile(BASE_DIR / "research/phase11g_i/acquisition/raw/BTCUSDT/2026-09-05/BTCUSDT-1m-2026-09-05.zip")
    rows = list(csv.DictReader(__import__("io").StringIO(z.read(z.namelist()[0]).decode())))
    print("kline minutes:", len(rows))
    hi = [float(r["high"]) for r in rows]
    lo = [float(r["low"]) for r in rows]
    rng = [h - l for h, l in zip(hi, lo)]
    import statistics
    med = statistics.median(rng)
    print("median 1m range:", round(med, 2), "| bars >2x median:", sum(1 for r in rng if r > 2 * med))
    out = {"events": n, "minutes": len(minutes),
           "imbalance_extreme_minutes": ext,
           "displacement_candidate_bars": sum(1 for r in rng if r > 2 * med),
           "kline_minutes": len(rows)}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
