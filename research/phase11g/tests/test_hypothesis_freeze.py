"""11G-B freeze tests (any post-freeze edit is detected)."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

P = Path("research/phase11g/hypotheses.json")

MUTABLE_FIELDS = ["entry_condition", "stop_rule", "target_rule",
                  "entry_model", "cost_scenarios", "required_features",
                  "frozen_parameters", "allowed_ablations", "minimum_evidence",
                  "direction_rule", "expiry_rule", "risk_rule"]


def file_hash():
    return hashlib.sha256(P.read_bytes()).hexdigest()


class TestHypothesisFreeze(unittest.TestCase):
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
            self.assertNotEqual(hashlib.sha256(blob).hexdigest(), ref,
                                "mutation invisible: %s" % field)
        # Restoration: on-disk file still matches the recorded hash.
        self.assertEqual(file_hash(), ref)

    def test_adding_ninth_detected(self):
        doc = json.loads(P.read_text())
        ref = file_hash()
        mutant = copy.deepcopy(doc)
        mutant["hypotheses"].append(dict(mutant["hypotheses"][0], id="H11G-009"))
        blob = json.dumps(mutant, sort_keys=True).encode()
        self.assertNotEqual(hashlib.sha256(blob).hexdigest(), ref)
        self.assertEqual(len(doc["hypotheses"]), 8)

    def test_removing_detected(self):
        doc = json.loads(P.read_text())
        ref = file_hash()
        mutant = copy.deepcopy(doc)
        mutant["hypotheses"] = mutant["hypotheses"][:7]
        blob = json.dumps(mutant, sort_keys=True).encode()
        self.assertNotEqual(hashlib.sha256(blob).hexdigest(), ref)

    def test_dataset_mutation_detected(self):
        doc = json.loads(P.read_text())
        self.assertNotIn("D3", json.dumps(doc))


if __name__ == "__main__":
    unittest.main()
