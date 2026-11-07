"""11G-F hypothesis contract tests (schema, family, prohibitions)."""

import json
import unittest
from pathlib import Path

HYPS = json.loads((Path("research/phase11g_f/hypotheses/hypotheses.json")).read_text())

REQUIRED_FIELDS = {"id", "name", "research_question", "scientific_claim",
                   "data_requirements", "required_features", "feature_sequence",
                   "direction_rule", "entry_condition", "entry_model",
                   "stop_rule", "target_rule", "risk_rule", "expiry_rule",
                   "deduplication_rule", "cost_scenarios", "allowed_ablations",
                   "forbidden_dimensions", "minimum_evidence", "status",
                   "parameters", "frozen_parameters"}

KNOWN_FEATURES = {"liquidity_pool", "sweep", "session_sweep", "displacement",
                  "fvg", "mitigation", "swing", "bos", "order_block",
                  "breaker", "range_state", "wyckoff_spring",
                  "wyckoff_upthrust", "volume_stats", "mtf_context"}


class TestFamilyContracts(unittest.TestCase):
    def test_exactly_eight_unique(self):
        self.assertEqual(len(HYPS["hypotheses"]), 8)
        ids = [h["id"] for h in HYPS["hypotheses"]]
        self.assertEqual(ids, ["H11GF-%03d" % i for i in range(1, 9)])
        self.assertEqual(len(set(ids)), 8)

    def test_required_fields_and_registered(self):
        for h in HYPS["hypotheses"]:
            self.assertTrue(REQUIRED_FIELDS <= set(h), h["id"])
            self.assertEqual(h["status"], "REGISTERED")

    def test_feature_references_valid(self):
        for h in HYPS["hypotheses"]:
            for feat in h["required_features"]:
                self.assertIn(feat, KNOWN_FEATURES, (h["id"], feat))

    def test_single_nbo_family(self):
        for h in HYPS["hypotheses"]:
            self.assertEqual(h["entry_model"][:13], "NEXT_BAR_OPEN", h["id"])

    def test_costs_evidence_frozen(self):
        for h in HYPS["hypotheses"]:
            self.assertEqual(h["cost_scenarios"], ["A", "B", "C", "D"])
            ev = h["minimum_evidence"]
            self.assertEqual((ev["pooled_trades"], ev["folds"],
                              ev["active_folds"], ev["regime_cell_trades"]),
                             (30, 3, 2, 3))

    def test_no_real_orderflow(self):
        blob = json.dumps(HYPS).lower()
        for token in ("real_delta", "real_cvd", "real_footprint",
                      "real_absorption", "real_imbalance", "real delta",
                      "real footprint"):
            self.assertNotIn(token, blob)

    def test_no_d3_no_live_no_production(self):
        blob = json.dumps(HYPS)
        for token in ("D3", "LIVE_EXECUTE", "ALLOW_LIVE", "core.",
                      "place_order", "DeltaOrderExecutor", "BrokerEngine"):
            self.assertNotIn(token, blob, token)

    def test_no_scores_ml_custom_fib(self):
        blob = json.dumps(HYPS).lower()
        for token in ('"score"', '"weight"', "classifier", "neural",
                      "machine learning", "random forest"):
            self.assertNotIn(token, blob)
        stripped = json.dumps(HYPS).replace("custom_fibonacci", "")
        self.assertNotIn("custom", stripped.lower())
        for h in HYPS["hypotheses"]:
            for dim in ("scores", "ml", "custom_fibonacci", "real_order_flow"):
                self.assertIn(dim, h["forbidden_dimensions"])

    def test_no_performance_results(self):
        blob = json.dumps(HYPS).lower()
        for token in ("win rate", "profit factor", "sharpe", "sortino",
                      "drawdown", "monte carlo", "winner", "net +"):
            self.assertNotIn(token, blob)

    def test_falsifiable_distinct(self):
        seen = set()
        for h in HYPS["hypotheses"]:
            self.assertIn("cost c", h["scientific_claim"].lower(), h["id"])
            key = (h["entry_condition"], h["stop_rule"], h["target_rule"])
            self.assertNotIn(key, seen, h["id"])
            seen.add(key)

    def test_multiple_testing(self):
        mt = HYPS["multiple_testing"]
        self.assertEqual(mt["family_size"], 8)
        self.assertAlmostEqual(mt["bonferroni_reference"], 0.00625)

    def test_candidate_classes_match_registry(self):
        from research.phase11g_f import candidates as F
        by_id = {c.id: c for c in F.ALL}
        self.assertEqual(sorted(by_id), ["H11GF-%03d" % i for i in range(1, 9)])
        doc = {h["id"]: h for h in HYPS["hypotheses"]}
        for hid, cls in by_id.items():
            code = sorted(n for n, _ in cls().ablations() if n != "full")
            reg = sorted(a["name"] for a in doc[hid]["allowed_ablations"])
            self.assertEqual(code, reg, hid)


if __name__ == "__main__":
    unittest.main()
