"""Phase 11F-1 contract tests (architecture only, no research execution).

Verifies hypothesis schema, candidate signal contract, ablation
registry, and research-only execution channel. Uses synthetic bars
only — never D2/D3 data, never profitability evaluation.
"""

import json
import unittest
from pathlib import Path

from research.phase11f import candidates as C
from research.phase11f import contracts as K

RESEARCH = Path("research/phase11f")


def _bars(n=80, start=1787000000, step=60, base=100.0):
    bars = []
    for i in range(n):
        bars.append({
            "time": start + step * i,
            "open": base + 0.1 * i,
            "high": base + 0.1 * i + 0.6,
            "low": base + 0.1 * i - 0.6,
            "close": base + 0.1 * i + 0.2,
            "volume": 10.0,
        })
    return bars


class TestHypothesisSchema(unittest.TestCase):
    def test_eight_hypotheses_pass_schema(self):
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        self.assertEqual(K.validate_hypotheses(doc), [])

    def test_ids_unique_and_ordered(self):
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        ids = [h["hypothesis_id"] for h in doc["hypotheses"]]
        self.assertEqual(ids, ["H11F-%03d" % i for i in range(1, 9)])

    def test_frozen_allowed_forbidden_present(self):
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        for h in doc["hypotheses"]:
            self.assertIsInstance(h["frozen_parameters"], dict)
            self.assertIsInstance(h["allowed_research_parameters"], dict)
            self.assertIsInstance(h["forbidden_optimization_dimensions"], list)
            for dim in ("symbol", "timeframe", "costs", "holdout"):
                self.assertIn(dim, h["forbidden_optimization_dimensions"])
            self.assertEqual(h["status"], "RESEARCH_ONLY")

    def test_required_features_known(self):
        known = set(K.FEATURE_CONTRACTS) | {
            "equal_level", "sweep", "reclaim_close", "displacement", "fvg",
            "trading_range", "spring", "upthrust", "order_block", "swing",
            "bos", "breaker_level", "ema_trend", "rsi_extreme",
        }
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        for h in doc["hypotheses"]:
            for feat in h["required_features"]:
                self.assertIn(feat, known, "%s unknown feature %s" % (h["hypothesis_id"], feat))

    def test_mutation_missing_field_fails(self):
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        bad = json.loads(json.dumps(doc))
        del bad["hypotheses"][0]["stop_definition"]
        errors = K.validate_hypotheses(bad)
        self.assertTrue(any("stop_definition" in e for e in errors))
        # restoration passes again
        self.assertEqual(K.validate_hypotheses(doc), [])


class TestCandidateContract(unittest.TestCase):
    def test_all_eight_candidates_present(self):
        self.assertEqual(len(C.ALL), 8)
        ids = sorted(cls.id for cls in C.ALL)
        self.assertEqual(ids, K.CANDIDATE_IDS)

    def test_candidate_params_match_hypotheses(self):
        doc = json.loads((RESEARCH / "hypotheses.json").read_text())
        frozen_by_id = {h["hypothesis_id"]: h["frozen_parameters"] for h in doc["hypotheses"]}
        for cls in C.ALL:
            inst = cls()
            frozen = frozen_by_id[cls.id]
            for key in inst.params:
                # candidate config keys must be a subset of the frozen
                # spec keys plus research-only switches (wait/use_*).
                # Q7: H11F-008 buffer_atr is stop-text-implied
                # ("beyond range extreme + 0.25x ATR14 buffer"), frozen
                # at 0.25, no optimization.
                allowed = set(frozen) | {"wait", "use_sweep", "use_fvg",
                                         "use_trend", "long_only"}
                if cls.id == "H11F-008" and key == "buffer_atr":
                    self.assertAlmostEqual(inst.params[key], 0.25)
                    continue
                self.assertIn(key, allowed, "%s unexpected param %s" % (cls.id, key))

    def test_signals_satisfy_contract_and_are_causal(self):
        bars = _bars(80)
        for cls in C.ALL:
            inst = cls()
            for idx in (20, 40, 60, 79):
                sigs = inst.signals(idx, bars, None) or []
                for sig in sigs:
                    self.assertEqual(K.validate_signal(sig), [])
            # causal invariance: truncating future bars must not
            # change the signal at idx.
            for idx in (30, 60):
                inst_a = cls()
                full = inst_a.signals(idx, bars, None) or []
                inst_b = cls()
                trunc = inst_b.signals(idx, bars[:idx + 1], None) or []
                self.assertEqual(full, trunc, "%s uses future bars at %d" % (cls.id, idx))

    def test_mutation_future_bar_access_detected(self):
        bars = _bars(40)

        class Peeking:
            def signals(self, idx, all_bars, ctx):
                # deliberately reads one future bar
                _ = all_bars[idx + 1]
                return []

        inst = C.SweepReversal()
        ok_full = inst.signals(20, bars, None)
        ok_trunc = C.SweepReversal().signals(20, bars[:21], None)
        self.assertEqual(ok_full, ok_trunc)
        with self.assertRaises(IndexError):
            Peeking().signals(20, bars[:21], None)

    def test_no_forbidden_execution_imports(self):
        for name in ("candidates.py", "features.py", "fibonacci.py",
                     "harness.py", "contracts.py", "metrics.py", "datasets.py"):
            src = (RESEARCH / name).read_text()
            # Exclude the denylist declaration itself (it names the
            # objects as strings without importing/calling them).
            lines = src.splitlines()
            code, skip = [], False
            for ln in lines:
                if "FORBIDDEN_RESEARCH_IMPORTS = [" in ln:
                    skip = True
                    continue
                if skip:
                    if ln.strip() == "]":
                        skip = False
                    continue
                code.append(ln)
            body = "\n".join(code)
            for forbidden in K.FORBIDDEN_RESEARCH_IMPORTS:
                # harness legitimately mentions cost keys; the ban is
                # on execution/credential imports, not on the word
                # "commission". Check the execution-specific list.
                if forbidden in ("place_order", "submit_order", "DeltaOrderExecutor",
                                 "BrokerEngine", "DeltaExchange", "_require_auth",
                                 "DELTA_API_KEY", "DELTA_API_SECRET", "ccxt", "delta_rest"):
                    self.assertNotIn(forbidden, body, "%s leaks %s" % (name, forbidden))


class TestAblationContract(unittest.TestCase):
    def test_registry_valid(self):
        self.assertEqual(K.validate_ablations(), [])
        self.assertEqual(set(K.ABLATIONS), {"H11F-002", "H11F-005", "H11F-007"})

    def test_candidates_match_registry(self):
        by_id = {cls.id: cls for cls in C.ALL}
        for hid, variants in K.ABLATIONS.items():
            inst = by_id[hid]()
            names = sorted(n for n, _ in inst.ablations())
            self.assertEqual(names, sorted(v["name"] for v in variants))
        # non-ablated candidates expose full only
        for hid in ("H11F-001", "H11F-003", "H11F-004", "H11F-006", "H11F-008"):
            self.assertEqual(by_id[hid]().ablations(), [("full", {})])

    def test_single_removal_only(self):
        for hid, variants in K.ABLATIONS.items():
            for v in variants:
                if v["name"] == "full":
                    self.assertEqual(v["overrides"], {})
                else:
                    self.assertEqual(len(v["overrides"]), 1)
        self.assertEqual(K.ABLATION_INVARIANTS,
                         ["identical data", "identical execution", "identical costs",
                          "identical risk", "single component removed"])

    def test_mutation_double_removal_fails(self):
        bad = {"H11F-002": [{"name": "full", "removed": None, "overrides": {}},
                            {"name": "bad", "removed": None, "overrides": {}}]}
        real = K.ABLATIONS["H11F-002"]
        K.ABLATIONS["H11F-002"] = bad["H11F-002"]
        try:
            self.assertNotEqual(K.validate_ablations(), [])
        finally:
            K.ABLATIONS["H11F-002"] = real
        self.assertEqual(K.validate_ablations(), [])


if __name__ == "__main__":
    unittest.main()
