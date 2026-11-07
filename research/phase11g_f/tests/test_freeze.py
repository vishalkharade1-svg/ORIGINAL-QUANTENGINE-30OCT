"""11G-F freeze tests (any post-freeze edit is detected)."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

P = Path("research/phase11g_f/hypotheses/hypotheses.json")
MAN = Path("research/phase11g_f/freeze_manifest.json")

MUTABLE_FIELDS = ["entry_condition", "stop_rule", "target_rule",
                  "entry_model", "cost_scenarios", "required_features",
                  "frozen_parameters", "allowed_ablations", "minimum_evidence",
                  "direction_rule", "expiry_rule", "risk_rule"]


def file_hash():
    return hashlib.sha256(P.read_bytes()).hexdigest()


class TestFreeze(unittest.TestCase):
    def test_manifest_matches_disk(self):
        man = json.loads(MAN.read_text())
        self.assertEqual(man["hypothesis_sha256"], file_hash())
        self.assertEqual(man["hypothesis_count"], 8)

    def test_mutation_detected_per_field(self):
        doc = json.loads(P.read_text())
        ref = file_hash()
        for field in MUTABLE_FIELDS:
            mutant = copy.deepcopy(doc)
            h = mutant["hypotheses"][0]
            if isinstance(h[field], list):
                h[field] = h[field] + ["MUTANT"]
            elif isinstance(h[field], dict):
                h[field] = dict(h[field], MUTANT=True)
            else:
                h[field] = str(h[field]) + " MUTANT"
            blob = json.dumps(mutant, sort_keys=True).encode()
            self.assertNotEqual(hashlib.sha256(blob).hexdigest(), ref, field)
        self.assertEqual(file_hash(), ref)

    def test_add_remove_detected(self):
        doc = json.loads(P.read_text())
        ref = file_hash()
        add = copy.deepcopy(doc)
        add["hypotheses"].append(dict(add["hypotheses"][0], id="H11GF-009"))
        self.assertNotEqual(hashlib.sha256(
            json.dumps(add, sort_keys=True).encode()).hexdigest(), ref)
        drop = copy.deepcopy(doc)
        drop["hypotheses"] = drop["hypotheses"][:7]
        self.assertNotEqual(hashlib.sha256(
            json.dumps(drop, sort_keys=True).encode()).hexdigest(), ref)
        self.assertEqual(len(doc["hypotheses"]), 8)

    def test_cost_risk_wf_frozen(self):
        doc = json.loads(P.read_text())
        self.assertEqual(doc["risk_frozen"],
                         {"allocation_cap": 500, "leverage": 10,
                          "risk_per_trade": 0.01, "starting_balance": 2000})
        wf = doc["walk_forward_frozen"]
        self.assertTrue(wf["expanding_origin"])
        self.assertEqual((wf["train_min_bars"], wf["test_bars"],
                          wf["purge_bars"], wf["embargo_bars"],
                          wf["step_bars"], wf["n_folds"]),
                         (2000, 1000, 150, 25, 1000, 4))


if __name__ == "__main__":
    unittest.main()
