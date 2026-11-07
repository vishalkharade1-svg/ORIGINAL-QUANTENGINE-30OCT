"""Phase 11G-D fresh-data access (BTC oos_fresh ONLY; D3 never touched).

Freshness registry distinguishes FRESH / CONTAMINATED / SEALED /
UNKNOWN without opening anything but the explicitly authorized fresh
file. Loader returns CHRONOLOGICAL bars (stored newest-first).
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

FRESHNESS = {
    "oos_fresh": "FRESH",
    "D1_BTC": "CONTAMINATED",
    "D1_ETH": "CONTAMINATED",
    "D2_BTC": "CONTAMINATED",
    "D2_ETH": "CONTAMINATED",
    "gate_a_snapshot": "CONTAMINATED",
    "phase7_file": "CONTAMINATED",
    "D3_BTC": "SEALED",
    "D3_ETH": "SEALED",
}

D3_ACCESS_11GD = {"read": 0, "hash": 0, "load": 0}


class SealedHoldoutError(RuntimeError):
    pass


def freshness(name):
    if "D3" in str(name) or str(name).endswith("D3"):
        raise SealedHoldoutError("D3 is SEALED: %s" % name)
    if name not in FRESHNESS:
        return "UNKNOWN"
    return FRESHNESS[name]


def load_fresh_btc():
    """Authorized fresh bars, chronological. The ONLY 11G-D dataset."""
    from research.phase11e.common import load_raw_bars
    doc = json.loads((BASE_DIR / "research/phase11e/data/oos_fresh.json").read_text())
    bars, meta = load_raw_bars(doc)
    assert meta["symbol"] == "BTCUSDT"
    assert len(bars) == 2499
    return bars


def wf_feasible(n_bars, train_min=2000, test=1000, purge=150, embargo=25,
                step=1000, n_folds=4):
    """True iff the frozen 4-fold geometry fits (else INSUFFICIENT_FRESH_SAMPLE)."""
    need = (n_folds - 1) * step + train_min + purge + embargo + test
    return n_bars >= need, need
