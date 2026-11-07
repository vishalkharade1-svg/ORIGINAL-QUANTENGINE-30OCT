"""Phase 11F-2 determinism certification (3x runs, hashes, harness).

Same input + same configuration + same code must yield identical
feature values, structure timestamps, Fibonacci levels, candidate
signals, setup IDs, serializations, and hashes. Architecture-level
only: tiny synthetic bars, never D1/D2/D3, never ranked/selected.
"""

import hashlib
import json
import unittest

from research.phase11f import candidates as C
from research.phase11f import contracts as K
from research.phase11f import features as F
from research.phase11f import fibonacci as FIB
from research.phase11f import harness as H


def _bars(n=90, start=1787000000, base=100.0):
    import math
    out = []
    prev = base
    for i in range(n):
        c = base + 3.0 * math.sin(i / 5.0)
        out.append({"time": start + 60 * i, "open": prev,
                    "high": max(prev, c) + 0.5, "low": min(prev, c) - 0.5,
                    "close": c, "volume": 10.0 + (i % 7)})
        prev = c
    return out


class _OneShot:
    id = "H11F-DET"

    def signals(self, idx, bars, ctx):
        if idx == 12:
            entry = float(bars[idx]["close"])
            return [{"direction": "BULLISH", "entry": entry,
                     "stop": entry - 1.0, "take_profit": entry + 2.0,
                     "setup_id": "DET-12", "confidence": 80.0}]
        return []


def _snapshot(bars):
    t = len(bars) - 1
    sigs = {}
    for cls in C.ALL:
        inst = cls()
        seq = []
        for idx in range(len(bars)):
            seq.append(inst.signals(idx, bars, None) or [])
        sigs[cls.id] = seq
    return {
        "atr": F.atr14(bars),
        "rsi": F.rsi14(bars),
        "swings": F.swings(bars),
        "levels": F.equal_levels(bars),
        "sweeps": F.sweeps(bars),
        "disp": F.displacement(bars),
        "fvg": F.fvg_zones(bars),
        "rng": F.range_state(bars),
        "fib_r": FIB.fib_retracements(bars),
        "fib_e": FIB.fib_extensions(bars),
        "signals": sigs,
    }


def _freeze(obj):
    return json.dumps(obj, sort_keys=True, default=str)


class TestTripleRunDeterminism(unittest.TestCase):
    def test_three_runs_bit_identical(self):
        runs = [_freeze(_snapshot(_bars())) for _ in range(3)]
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[1], runs[2])
        digests = [hashlib.sha256(r.encode()).hexdigest() for r in runs]
        self.assertEqual(len(set(digests)), 1)

    def test_harness_three_runs_identical(self):
        runs = [H.run_candidate(_bars(40), _OneShot(), "BTCUSDT", cost_key="C")
                for _ in range(3)]
        frozen = [_freeze(r) for r in runs]
        self.assertEqual(frozen[0], frozen[1])
        self.assertEqual(frozen[1], frozen[2])

    def test_setup_ids_stable(self):
        first = _snapshot(_bars())["signals"]
        second = _snapshot(_bars())["signals"]
        for hid in first:
            ids_first = [s["setup_id"] for seq in first[hid] for s in seq]
            ids_second = [s["setup_id"] for seq in second[hid] for s in seq]
            self.assertEqual(ids_first, ids_second, hid)


class TestSerializationDeterminism(unittest.TestCase):
    def test_canonical_hashes_key_order_independent(self):
        self.assertEqual(K.sha256_canonical({"b": 1, "a": 2}),
                         K.sha256_canonical({"a": 2, "b": 1}))

    def test_logged_hashes_reproduce(self):
        from pathlib import Path
        research = Path("research/phase11f")
        log = json.loads((research / "research_log.json").read_text())
        hyps = json.loads((research / "hypotheses.json").read_text())
        ds = json.loads((research / "datasets.json").read_text())
        self.assertEqual(log["dataset_spec_hash"], K.sha256_canonical(ds))
        by_id = {h["hypothesis_id"]: h for h in hyps["hypotheses"]}
        for entry in log["entries"]:
            h = by_id[entry["id"]]
            self.assertEqual(entry["hypothesis_hash"], K.sha256_canonical(h))
            param_spec = {"frozen": h["frozen_parameters"],
                          "allowed": h["allowed_research_parameters"],
                          "forbidden": h["forbidden_optimization_dimensions"]}
            self.assertEqual(entry["parameter_spec_hash"], K.sha256_canonical(param_spec))

    def test_manifest_hashes_reproduce(self):
        # Frozen INPUTS still match, except research_log.json: the 11F-4
        # authorized update lawfully appended result halves to the
        # ledger (Step 21). Its registration halves still verify
        # field-wise (see test_logged_hashes_reproduce above).
        from pathlib import Path
        research = Path("research/phase11f")
        manifest = json.loads((research / "freeze_manifest.json").read_text())
        for name, recorded in manifest["sha256"].items():
            if name == "research_log.json":
                continue
            self.assertEqual(K.sha256_file(research / name), recorded, name)


if __name__ == "__main__":
    unittest.main()
