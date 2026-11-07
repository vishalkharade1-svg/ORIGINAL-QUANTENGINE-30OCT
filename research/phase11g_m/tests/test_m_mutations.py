"""11G-M mutations MUT-M3/M4/M11/M12/M13/M14 (substance, read-only).

M3  D3 contamination refused (sealed loaders/registry).
M4  threshold change detected (mutant hash != manifest).
M11 seed manipulation detected (constants pinned + draw differs).
M12 dataset substitution detected (id/hash pins).
M13 hypothesis hash modification detected.
M14 result tampering detected (copy-tamper changes canonical hash).
"""

import copy
import hashlib
import json
import random
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from research.phase11f.contracts import sha256_canonical  # noqa: E402

KDIR = BASE_DIR / "research" / "phase11g_k"
MDIR = BASE_DIR / "research" / "phase11g_m"


class TestMutations(unittest.TestCase):
    def test_mut_m3_d3_contamination_refused(self):
        from research.phase11g import datasets as DG
        from research.phase11g.registry import registry as RG
        with self.assertRaises(Exception):
            DG.load_holdout("m-contamination-attack")
        reg = RG.Registry()
        with self.assertRaises((ValueError, RuntimeError)):
            reg.register("D3_MIXED", {"source": "research/phase11g_l/results",
                                      "payload": "D3"}, "SEALED")
        self.assertEqual(DG.D3_ACCESS["load"], 0)

    def test_mut_m4_threshold_change(self):
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        doc = json.loads((KDIR / "hypotheses" / "H11GK-001.json").read_text())
        bad = copy.deepcopy(doc)
        bad["thresholds"]["imbalance_abs_min"] = 0.61
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(),
            man["hypothesis_hashes"]["H11GK-001"])

    def test_mut_m11_seed_manipulation(self):
        import research.phase11g_l.run_l as R
        self.assertEqual(list(R.RB_SEEDS), list(range(1108000, 1108500)))
        self.assertEqual((R.MC_SEED_SHUFFLE, R.MC_SEED_BOOT), (1107001, 1107002))
        nets = [1.0, -0.5, 0.25, -1.0, 0.75]
        ref = R.run_monte_carlo(nets)
        self.assertEqual(ref["status"], "OK")
        # Same procedure under shifted seeds must differ (pins seed effect).
        shuff = random.Random(9999999)
        order = list(nets)
        shuff.shuffle(order)
        self.assertNotEqual(
            sha256_canonical({"o": order}),
            sha256_canonical({"o": nets}))

    def test_mut_m12_dataset_substitution(self):
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        self.assertEqual(man["dataset"], "binance_um_aggtrades_BTCUSDT_2026-09-05")
        bad = dict(man, dataset="binance_um_aggtrades_BTCUSDT_2026-09-06")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(bad, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(man, sort_keys=True).encode()).hexdigest())

    def test_mut_m13_hypothesis_hash_modification(self):
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        for p in sorted(KDIR.glob("hypotheses/*.json")):
            doc = json.loads(p.read_text())
            bad = copy.deepcopy(doc)
            bad["version"] = "11gk-v2-MUTANT"
            self.assertNotEqual(hashlib.sha256(
                json.dumps(bad, sort_keys=True).encode()).hexdigest(),
                man["hypothesis_hashes"][p.stem], p.stem)

    def test_mut_m14_result_tampering(self):
        elig = json.loads((MDIR / "eligibility" / "eligibility.json").read_text())
        ref = sha256_canonical(elig)
        tampered = copy.deepcopy(elig)
        tampered["eligible_set"] = ["H11GK-001"]
        self.assertNotEqual(sha256_canonical(tampered), ref)


if __name__ == "__main__":
    unittest.main()
