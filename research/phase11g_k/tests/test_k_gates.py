"""11G-K determinism, lineage, D3 seal, outcome-blind, mutation tests."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

K = Path("research/phase11g_k")
MAN = json.loads((K / "freeze" / "freeze_manifest.json").read_text())


class TestDeterminism(unittest.TestCase):
    def test_generate_twice_identical(self):
        # Manifest stores CANONICAL hashes (sort_keys); compare like
        # with like. Raw-byte equality is not required (whitespace).
        first = {p.stem: hashlib.sha256(
            json.dumps(json.loads(p.read_bytes()),
                       sort_keys=True).encode()).hexdigest()
                 for p in sorted((K / "hypotheses").glob("*.json"))}
        second = {p.stem: hashlib.sha256(
            json.dumps(json.loads(p.read_bytes()),
                       sort_keys=True).encode()).hexdigest()
                  for p in sorted((K / "hypotheses").glob("*.json"))}
        self.assertEqual(first, second)
        self.assertEqual(first, MAN["hypothesis_hashes"])

    def test_serialization_canonical(self):
        for p in sorted((K / "hypotheses").glob("*.json")):
            doc = json.loads(p.read_text())
            a = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
            b = hashlib.sha256(
                json.dumps(json.loads(json.dumps(doc)), sort_keys=True).encode()
            ).hexdigest()
            self.assertEqual(a, b, p.stem)


class TestLineage(unittest.TestCase):
    def test_dataset_policy_points_to_certified(self):
        for p in sorted((K / "hypotheses").glob("*.json")):
            doc = json.loads(p.read_text())
            pol = doc["dataset_policy"]
            self.assertNotIn("D3", json.dumps(pol))
            self.assertIn("NOT used for 11G-K economics", pol["contamination"])

    def test_registered_dataset_exists(self):
        from research.phase11g.registry import registry as RG
        reg = RG.bootstrap_11g_registry()
        self.assertIn("oos_fresh", reg.summary()["datasets"])


class TestD3Seal(unittest.TestCase):
    def test_counters_zero(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})

    def test_no_d3_references(self):
        for path in list(K.rglob("*.py")) + list(K.rglob("*.json")) + list(K.rglob("*.md")):
            for line in path.read_text().splitlines():
                if "D3" not in line or "assertNotIn" in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))
                self.assertNotIn("read_bytes", line, str(path))
                self.assertNotIn("load(", line, str(path))

    def test_registry_refuses_d3(self):
        from research.phase11g.registry import registry as RG
        reg = RG.Registry()
        with self.assertRaises(ValueError):
            reg.register("D3_X", {}, "SEALED")
        with self.assertRaises(RuntimeError):
            reg.d3_block("read")


class TestOutcomeBlind(unittest.TestCase):
    def test_no_economic_imports(self):
        # Strip string literals and comments via tokenize, then match
        # real code use. Vocabulary defined inside string literals can
        # never match, so the scanner cannot trip on itself.
        import io
        import re
        import tokenize
        pats = [r"(import|from)\s+\S*(backtester|Backtester|MonteCarlo)\b",
                r"trade_metrics\s*\(", "PerformanceAnalytics",
                r"fold_results", r"primary_results", r"expectancy\s*="]

        def code_only(src):
            out = []
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type in (tokenize.STRING, tokenize.COMMENT):
                    out.append(" " * (tok.end[1] - tok.start[1]))
                else:
                    out.append(tok.string)
            return "".join(out)

        for path in list(K.rglob("*.py")):
            code = code_only(path.read_text())
            for pat in pats:
                self.assertIsNone(re.search(pat, code),
                                  "%s: %s" % (path.name, pat))

    def test_no_results_artifacts(self):
        for name in ("results", "primary_results.json", "fold_results.json",
                     "cost_results.json", "backtest"):
            self.assertFalse((K / name).exists(), name)


class TestMutations(unittest.TestCase):
    def _doc(self):
        return json.loads((K / "hypotheses" / "H11GK-001.json").read_text())

    def test_mut_threshold(self):
        ref = MAN["hypothesis_hashes"]["H11GK-001"]
        bad = copy.deepcopy(self._doc())
        bad["thresholds"]["imbalance_abs_min"] = 0.99
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(), ref)

    def test_mut_stop_target(self):
        ref = MAN["hypothesis_hashes"]["H11GK-002"]
        doc = json.loads((K / "hypotheses" / "H11GK-002.json").read_text())
        for field in ("stop", "target"):
            bad = copy.deepcopy(doc)
            bad[field] = {"definition": "MUTANT"}
            self.assertNotEqual(hashlib.sha256(
                json.dumps(bad, sort_keys=True).encode()).hexdigest(), ref, field)

    def test_mut_cost(self):
        from research.phase11f.harness import COST_SCENARIOS_11F
        self.assertAlmostEqual(COST_SCENARIOS_11F["C"]["COMMISSION_RATE"], 0.00059)
        bad = dict(COST_SCENARIOS_11F["C"], COMMISSION_RATE=0.0)
        self.assertNotEqual(bad["COMMISSION_RATE"],
                            COST_SCENARIOS_11F["C"]["COMMISSION_RATE"])

    def test_mut_risk(self):
        from config import risk_settings
        self.assertAlmostEqual(risk_settings.RISK_PER_TRADE, 0.01)
        self.assertEqual(risk_settings.MAX_ALLOCATION_PER_TRADE, 500)

    def test_mut_dataset(self):
        from research.phase11g import datasets as DG
        self.assertEqual(DG.DATASETS["D1_BTC"]["bar_count"], 4001)
        with self.assertRaises(KeyError):
            DG.describe("D3_BTC")

    def test_mut_execution(self):
        doc = self._doc()
        self.assertEqual(doc["execution_model"][:13], "NEXT_BAR_OPEN")
        bad = copy.deepcopy(doc)
        bad["execution_model"] = "LIMIT_RETEST (MUTANT)"
        ref = MAN["hypothesis_hashes"]["H11GK-001"]
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(), ref)

    def test_mut_wf_rolling(self):
        from research.phase11f import validation as V
        folds = V.build_folds(8000)
        self.assertEqual(V.validate_expanding(folds), [])
        mutant = [dict(f, train_start=f["fold"] * 1000,
                       train_end=f["fold"] * 1000 + 2000) for f in folds]
        self.assertTrue(any("rolling" in e for e in V.validate_expanding(mutant)))

    def test_mut_feature_version(self):
        from research.phase11g_j.replay import events as REV
        self.assertEqual(REV.FEATURE_VERSION, "real-trade-features-v1")
        self.assertNotEqual(REV.FEATURE_VERSION, "real-trade-features-v2")

    def test_mut_id_and_future(self):
        doc = self._doc()
        self.assertEqual(doc["hypothesis_id"], "H11GK-001")
        bad = copy.deepcopy(doc)
        bad["hypothesis_id"] = "H11GK-001-MUTANT"
        ref = MAN["hypothesis_hashes"]["H11GK-001"]
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(), ref)
        self.assertIn("future trades", json.dumps(doc["forbidden_information"]))


class TestProductionScope(unittest.TestCase):
    def test_no_production_paths(self):
        import subprocess
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "core/", "config/", "data/",
             "execution/", "risk/", "backtesting/", "main.py"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
