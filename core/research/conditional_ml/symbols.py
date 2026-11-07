"""
====================================================

QuantEngine

Conditional ML / Opportunity Discovery (Phase 9L) -- symbols

Symbol-specific behaviour, ONLY where sample sizes justify
segmentation.

   BTCUSDT + TREND, ETHUSDT + RANGE, ... are reported per
   (symbol, primary generated regime) cell. Justification requires:

   * n >= min_symbol_n for the (symbol, regime) cell,
   * expectancy >= the global expectancy + economic margin,
   * survival of the global familywise correction.

Every cell is retained with its justified flag -- a symbol/regime
cell that fails the gate is reported SYMBOL_NOT_JUSTIFIED, never
dropped.
====================================================
"""

from core.research.conditional_ml.types import SymbolBehaviour
from core.research.conditional_ml.guards import required_min_n


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def symbol_behaviour(orows, min_n=12, delta_r=0.5, n_hypotheses=1):
    """orows: opportunity rows aligned to contexts. Deterministic."""
    min_gate = required_min_n(min_n, n_hypotheses)

    cells = {}
    global_r = []
    for r in orows:
        if not r.baseline_filled or r.baseline_r is None:
            continue
        key = (r.ctx.symbol or "UNKNOWN",
               r.ctx.primary_generated() or "UNAVAILABLE")
        cells.setdefault(key, []).append(r.baseline_r)
        global_r.append(r.baseline_r)

    global_avg = _mean(global_r)
    out = []
    for (symbol, regime) in sorted(cells.keys(), key=lambda x: (str(x[0]), str(x[1]))):
        rs = cells[(symbol, regime)]
        n = len(rs)
        avg_r = _mean(rs)
        wins = sum(1 for x in rs if x > 0)
        win_rate = wins / n if n else None
        delta = (avg_r - global_avg) if (avg_r is not None and global_avg is not None) else None
        justified = (
            n >= min_gate
            and delta is not None
            and delta >= delta_r
        )
        out.append(SymbolBehaviour(
            symbol=symbol,
            regime=regime,
            n=n,
            win_rate=round(win_rate, 4) if win_rate is not None else None,
            avg_r=round(avg_r, 4) if avg_r is not None else None,
            global_avg_r=round(global_avg, 4) if global_avg is not None else None,
            delta_expectancy=round(delta, 4) if delta is not None else None,
            justified=justified,
            min_n_gate=min_gate,
        ))
    if not out:
        return []
    out = sorted(out, key=lambda s: (not s.justified, s.symbol, str(s.regime)))
    return out