"""11G-K schema + freeze tests (no economics, no network)."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

K = Path("research/phase11g_k")
HYPS = sorted((K / "hypotheses").glob("H11GK-*.json"))
SCHEMA = json.loads((K / "schema" / "hypothesis_schema.json").read_text())

REQUIRED = set(SCHEMA["required"])


class TestSchema(unittest.TestCase):
    def test_eight_ids(self):
        self.assertEqual(len(HYPS), 8)
        self.assertEqual([p.stem for p in HYPS],
                         ["H11GK-%03d" % i for i in range(1, 9)])

    def test_required_fields_and_frozen(self):
        for p in HYPS:
            doc = json.loads(p.read_text())
            self.assertTrue(REQUIRED <= set(doc), p.stem)
            self.assertEqual(doc["status"], "FROZEN")
            self.assertEqual(doc["version"], "11gk-v1")
            self.assertFalse(doc["production_modification"])
            self.assertEqual(doc["d3_policy"], "SEALED")
            self.assertEqual(doc["promotion_policy"], "NONE")

    def test_no_orderflow_overreach(self):
        # Forbidden order-flow language may appear ONLY inside the
        # forbidden_information / feature_classification declarations
        # (where it is banned, not claimed) — never as a claimed input.
        for p in HYPS:
            doc = json.loads(p.read_text())
            scrubbed = copy.deepcopy(doc)
            scrubbed.pop("forbidden_information", None)
            scrubbed.pop("feature_classification", None)
            if isinstance(scrubbed.get("causality_contract"), dict):
                scrubbed["causality_contract"] = {
                    k: v for k, v in scrubbed["causality_contract"].items()
                    if k != "forbidden"}
            blob = json.dumps(scrubbed).lower()
            for token in ("order-book imbalance", "order book absorption",
                          "resting liquidity", "queue position", "l2 depletion",
                          "historical spread", "real footprint",
                          "real absorption", "real imbalance",
                          "real order flow", "bid/ask imbalance"):
                # "real delta"/"real CVD" are legitimate: certified REAL
                # aggressor trades exist, so those phrases are allowed.
                self.assertNotIn(token, blob, p.stem)

    def test_no_scores_ml(self):
        for p in HYPS:
            blob = json.dumps(json.loads(p.read_text())).lower()
            for token in ('"score"', "random forest", "neural", "classifier",
                          "gradient", '"weight"'):
                self.assertNotIn(token, blob, p.stem)

    def test_no_economics_in_specs(self):
        # "expectancy" legitimately appears inside falsification criteria
        # ("expectancy <= 0 falsifies"); what must be absent are measured
        # result figures. Check result-like patterns instead.
        for p in HYPS:
            blob = json.dumps(json.loads(p.read_text())).lower()
            for token in ("win rate", "profit factor", "sharpe", "sortino",
                          "drawdown", "monte carlo", "winner", "net +",
                          "trades:", "pnl:"):
                self.assertNotIn(token, blob, p.stem)

    def test_thresholds_present_with_provenance(self):
        for p in HYPS:
            doc = json.loads(p.read_text())
            self.assertTrue(doc["thresholds"])
            self.assertTrue(len(doc["threshold_provenance"]) > 40, p.stem)

    def test_ablations_bounded(self):
        expected = {"H11GK-001": ["A0", "A1", "A2", "A3"],
                    "H11GK-002": ["A0", "A1", "A2", "A3"],
                    "H11GK-003": ["A0", "A1", "A2", "A3"],
                    "H11GK-004": ["A0", "A1", "A2"],
                    "H11GK-005": ["A0", "A1", "A2"],
                    "H11GK-006": ["A0", "A1", "A2"],
                    "H11GK-007": ["A0", "A1", "A2"],
                    "H11GK-008": ["A0", "A1", "A2"]}
        for p in HYPS:
            doc = json.loads(p.read_text())
            names = [a["id"] for a in doc["ablations"]]
            self.assertEqual(names[0], "A0", p.stem)
            self.assertEqual(names, expected[p.stem], p.stem)
            for a in doc["ablations"]:
                self.assertIn("removed", a)


class TestFreeze(unittest.TestCase):
    def test_manifest_hashes_match(self):
        man = json.loads((K / "freeze" / "freeze_manifest.json").read_text())
        self.assertEqual(man["family_count"], 8)
        for stem, recorded in man["hypothesis_hashes"].items():
            doc = json.loads((K / "hypotheses" / (stem + ".json")).read_text())
            actual = hashlib.sha256(
                json.dumps(doc, sort_keys=True).encode()).hexdigest()
            self.assertEqual(actual, recorded, stem)
        fam = hashlib.sha256(
            json.dumps(man["hypothesis_hashes"], sort_keys=True).encode()).hexdigest()
        self.assertEqual(
            (K / "freeze" / "freeze_hash.txt").read_text().strip(), fam)

    def test_mutation_detected(self):
        man = json.loads((K / "freeze" / "freeze_manifest.json").read_text())
        ref = man["hypothesis_hashes"]["H11GK-001"]
        doc = json.loads((K / "hypotheses" / "H11GK-001.json").read_text())
        for field in ("thresholds", "stop", "target", "entry", "execution_model",
                      "event_definition", "ablations"):
            bad = copy.deepcopy(doc)
            if isinstance(bad[field], dict):
                bad[field] = dict(bad[field], MUTANT=True)
            elif isinstance(bad[field], list):
                bad[field] = bad[field] + ["MUTANT"]
            else:
                bad[field] = str(bad[field]) + " MUTANT"
            self.assertNotEqual(hashlib.sha256(
                json.dumps(bad, sort_keys=True).encode()).hexdigest(), ref, field)

    def test_add_remove_detected(self):
        man = json.loads((K / "freeze" / "freeze_manifest.json").read_text())
        self.assertEqual(len(man["hypothesis_hashes"]), 8)
        self.assertNotIn("H11GK-009", man["hypothesis_hashes"])


if __name__ == "__main__":
    unittest.main()
