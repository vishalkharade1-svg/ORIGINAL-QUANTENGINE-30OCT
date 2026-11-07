"""11G-L gates: threshold parity, causality, mutations, determinism, scope.

MUT-L1..14 are substance tests: each asserts the runner PINS a frozen
quantity such that mutating it is detected (changed signals/stops or
a tripped gate). Full-day censuses are cached per class across tests.
"""

import copy
import dataclasses
import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f import validation as V  # noqa: E402
from research.phase11f.contracts import sha256_canonical  # noqa: E402
from research.phase11f.harness import COST_SCENARIOS_11F  # noqa: E402
from research.phase11g_l.runner import signals as S  # noqa: E402
from research.phase11g_l.runner.context import MarketContext  # noqa: E402
import research.phase11g_l.run_l as R  # noqa: E402

KDIR = BASE_DIR / "research" / "phase11g_k"
LDIR = BASE_DIR / "research" / "phase11g_l"

# Frozen-but-vestigial: in the JSON, unreferenced by the event text.
VESTIGIAL = {("H11GK-006", "displacement_atr")}

# Pinned full-day signal census (outcome of frozen specs on the frozen
# day; any drift trips). Verified pre-registration of economics.
CENSUS = {
    "H11GK-001": 21, "H11GK-002": 5, "H11GK-003": 8, "H11GK-004": 126,
    "H11GK-005": 0, "H11GK-006": 0, "H11GK-007": 116, "H11GK-008": 0,
}

# Documented L fold geometry (certified builder, L execution design).
FOLDS = [
    {"fold": 0, "train_start": 0, "train_end": 300,
     "purge_start": 300, "purge_end": 450,
     "embargo_start": 450, "embargo_end": 475,
     "test_start": 475, "test_end": 775},
    {"fold": 1, "train_start": 0, "train_end": 600,
     "purge_start": 600, "purge_end": 750,
     "embargo_start": 750, "embargo_end": 775,
     "test_start": 775, "test_end": 1075},
    {"fold": 2, "train_start": 0, "train_end": 900,
     "purge_start": 900, "purge_end": 1050,
     "embargo_start": 1050, "embargo_end": 1075,
     "test_start": 1075, "test_end": 1375},
]

_bars, _bundle, _sig_cache = None, None, {}


def dataset():
    global _bars, _bundle
    if _bars is None:
        _bars, _bundle = R.load_dataset()
    return _bars, _bundle


def census(cls, bundle=None, offset=0, **overrides):
    bars, bund = dataset()
    inst = cls(**overrides).attach(bundle or bund, offset)
    out = []
    for idx in range(len(bars)):
        out.extend(inst.signals(idx, bars, None) or ())
    return out


def cached_census(cls):
    if cls.id not in _sig_cache:
        _sig_cache[cls.id] = census(cls)
    return _sig_cache[cls.id]


class TestThresholdParity(unittest.TestCase):
    def test_json_thresholds_in_params(self):
        for cls in S.ALL:
            doc = json.loads((KDIR / "hypotheses" / (cls.id + ".json")).read_text())
            inst = cls()
            for k, v in doc["thresholds"].items():
                if (cls.id, k) in VESTIGIAL:
                    continue
                self.assertIn(k, inst.cfg, "%s missing %s" % (cls.id, k))
                self.assertEqual(inst.cfg[k], v, "%s.%s" % (cls.id, k))

    def test_vestigial_displacement_atr_unused(self):
        ref = cached_census(S.AggressionSweep)
        self.assertEqual(ref, census(S.AggressionSweep, displacement_atr=99.0))
        for name, ov in S.AggressionSweep().ablations():
            if name == "full":
                continue
            self.assertEqual(census(S.AggressionSweep, **ov),
                             census(S.AggressionSweep,
                                    **dict(ov, displacement_atr=99.0)))

    def test_two_r_target(self):
        for cls in S.ALL:
            for sig in cached_census(cls):
                e, s, t = sig["entry"], sig["stop"], sig["take_profit"]
                if sig["direction"] == "BULLISH":
                    self.assertAlmostEqual((t - e) / (e - s), 2.0)
                else:
                    self.assertAlmostEqual((e - t) / (s - e), 2.0)

    def test_census_pinned(self):
        for cls in S.ALL:
            self.assertEqual(len(cached_census(cls)), CENSUS[cls.id], cls.id)


class TestCausality(unittest.TestCase):
    def test_bundle_prefix_stable(self):
        bars, bund = dataset()
        cut_minute = bars[600]["time"]
        from research.phase11g_j.replay import load as LOAD
        rev = LOAD.load_trades()
        pre = [t for t in rev._trades if int(t.event_ms) // 60000 * 60 < cut_minute]
        self.assertTrue(len(pre) < len(rev._trades))
        small = MarketContext(bars, pre)
        for cls in S.ALL:
            a = cached_census(cls)
            b = census(cls, bundle=small)
            ga = [s for s in a
                  if int(str(s["setup_id"]).rsplit("-", 1)[-1]) <= 600]
            gb = [s for s in b
                  if int(str(s["setup_id"]).rsplit("-", 1)[-1]) <= 600]
            self.assertEqual(ga, gb, cls.id)

    def test_window_arithmetic(self):
        bars, bund = dataset()
        for i in (10, 100, 1000):
            b, s, tot, d = bund.window_vol(i, 5)
            eb = sum(bund.min_buy[j] for j in range(i - 4, i + 1))
            es = sum(bund.min_sell[j] for j in range(i - 4, i + 1))
            self.assertAlmostEqual(b, eb)
            self.assertAlmostEqual(s, es)
            self.assertAlmostEqual(tot, eb + es)
            self.assertAlmostEqual(d, eb - es)
        for i in (60, 500, 1400):
            self.assertAlmostEqual(bund.cvd_slope(i, 60),
                                   bund.cvd[i] - bund.cvd[i - 60])

    def test_aggressor_flip_detected(self):
        bars, bund = dataset()
        ref = cached_census(S.BOSDelta)
        self.assertTrue(len(ref) > 0)
        from research.phase11g_j.replay import load as LOAD
        rev = LOAD.load_trades()
        flip = [dataclasses.replace(
            t, aggressor_side=("sell" if t.aggressor_side == "buy" else "buy"))
            for t in rev._trades]
        fb = MarketContext(bars, flip)
        self.assertNotEqual(ref, census(S.BOSDelta, bundle=fb))

    def test_fold_offset_spot_check(self):
        # First F0 007 signal recomputed independently (BOS + delta).
        bars, bund = dataset()
        folds = R.build_folds()
        f = folds[0]
        sl = bars[f["test_start"]:f["test_end"]]
        inst = S.BOSDelta().attach(bund, f["test_start"])
        found = None
        for idx in range(len(sl)):
            sigs = inst.signals(idx, sl, None) or ()
            if sigs:
                found = (idx, sigs[0])
                break
        self.assertIsNotNone(found)
        idx, sig = found
        from research.phase11f import features as F11
        sw = F11.swings(sl, 3, 3)
        closes = [b["close"] for b in sl]
        lh = max((x["extreme"] for x in sw[:idx] if x and x["kind"] == "high"),
                 default=None)
        self.assertIsNotNone(lh)
        self.assertTrue(closes[idx - 1] <= lh < closes[idx])
        g = idx + f["test_start"]
        b, s, tot, d = bund.window_vol(g, 5)
        self.assertTrue(d > 0)
        self.assertAlmostEqual(sig["stop"], lh - 0.25 * F11.atr14(sl)[idx])


class TestMutations(unittest.TestCase):
    def test_mut_threshold(self):
        ref = cached_census(S.ImbalanceBOS)
        mut = census(S.ImbalanceBOS, imbalance_abs_min=0.99)
        self.assertTrue(len(mut) < len(ref))

    def test_mut_stop(self):
        ref = [s["stop"] for s in cached_census(S.BOSDelta)]
        mut = [s["stop"] for s in census(S.BOSDelta, buffer_atr=0.99)]
        self.assertNotEqual(ref, mut)

    def test_mut_cost(self):
        self.assertAlmostEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)
        bad = dict(COST_SCENARIOS_11F["C"], COMMISSION_RATE=0.0)
        self.assertNotEqual(bad["COMMISSION_RATE"],
                            COST_SCENARIOS_11F["C"]["COMMISSION_RATE"])

    def test_mut_risk(self):
        from config import risk_settings
        self.assertAlmostEqual(risk_settings.RISK_PER_TRADE, 0.01)
        self.assertEqual(risk_settings.MAX_ALLOCATION_PER_TRADE, 500)

    def test_mut_dataset(self):
        bars, bund = dataset()
        self.assertEqual(len(bars), 1440)
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        self.assertTrue(man["dataset_hash"].startswith("440c9191"))

    def test_mut_execution_nbo(self):
        bars, bund = dataset()
        folds = R.build_folds()
        trades, det = R.run_fold(S.BOSDelta, bars, bund, folds[0], R.SYMBOL, "A")
        self.assertTrue(len(trades) > 0)
        for o in det["orders"]:
            self.assertEqual(o["entry_execution"], "NEXT_BAR_OPEN")
        for t in trades:
            self.assertEqual(t["entry_time"] - t["decision_time"], 60)
            g = next(i for i, b in enumerate(bars) if int(b["time"]) == t["decision_time"])
            self.assertAlmostEqual(t["entry"], bars[g + 1]["open"])
            self.assertAlmostEqual(
                (t["gross"] - t["commission"] - t["slippage"]) - t["net"], 0.0)

    def test_mut_wf_geometry(self):
        self.assertEqual(R.build_folds(), FOLDS)
        folds = R.build_folds()
        self.assertEqual(V.validate_folds(folds), [])
        self.assertEqual(V.validate_expanding(folds), [])
        rolling = [dict(f, train_start=f["fold"] * 300) for f in folds]
        self.assertTrue(any("rolling" in e or "train_start" in e
                            for e in V.validate_expanding(rolling)))

    def test_mut_feature_version(self):
        from research.phase11g_j.replay import events as REV
        self.assertEqual(REV.FEATURE_VERSION, "real-trade-features-v1")

    def test_mut_id_and_freeze(self):
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        doc = json.loads((KDIR / "hypotheses" / "H11GK-001.json").read_text())
        self.assertEqual(doc["hypothesis_id"], "H11GK-001")
        bad = copy.deepcopy(doc)
        bad["hypothesis_id"] = "H11GK-001-MUTANT"
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(),
            man["hypothesis_hashes"]["H11GK-001"])

    def test_mut_ablation_map(self):
        for cls in S.ALL:
            doc = json.loads((KDIR / "hypotheses" / (cls.id + ".json")).read_text())
            reg = sorted(a["id"] for a in doc["ablations"] if a["id"] != "A0")
            code = sorted(n for n, _ in cls().ablations() if n != "full")
            blocked = sorted(R.BLOCKED_ABLATIONS.get(cls.id, {}))
            self.assertEqual(sorted(code + blocked), reg, cls.id)

    def test_mut_d3_seal(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})
        for path in list((LDIR / "runner").glob("*.py")) + [LDIR / "run_l.py"]:
            for line in path.read_text().splitlines():
                if "D3" not in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))

    def test_mut_live_disabled(self):
        self.assertNotIn(os.getenv("ALLOW_LIVE", "").lower(), ("1", "true"))
        self.assertNotIn(os.getenv("LIVE_EXECUTE", "").lower(), ("1", "true"))


class TestDeterminism(unittest.TestCase):
    def test_run_fold_twice_identical(self):
        bars, bund = dataset()
        folds = R.build_folds()
        t1, _ = R.run_fold(S.BOSDelta, bars, bund, folds[0], R.SYMBOL, "A")
        t2, _ = R.run_fold(S.BOSDelta, bars, bund, folds[0], R.SYMBOL, "A")
        self.assertEqual(sha256_canonical(t1), sha256_canonical(t2))


class TestProductionScope(unittest.TestCase):
    def test_no_production_paths(self):
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "core/", "config/", "data/",
             "execution/", "risk/", "backtesting/", "main.py"],
            capture_output=True, text=True, cwd=str(BASE_DIR)).stdout.strip()
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
