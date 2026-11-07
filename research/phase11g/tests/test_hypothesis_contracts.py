"""11G-B hypothesis contract tests (schema, family, prohibitions)."""

import json
import unittest
from pathlib import Path

HYPS = json.loads((Path("research/phase11g/hypotheses.json")).read_text())

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


class TestHypothesisContracts(unittest.TestCase):
    def test_exactly_eight_unique(self):
        self.assertEqual(len(HYPS["hypotheses"]), 8)
        ids = [h["id"] for h in HYPS["hypotheses"]]
        self.assertEqual(ids, ["H11G-%03d" % i for i in range(1, 9)])
        self.assertEqual(len(set(ids)), 8)

    def test_required_fields(self):
        for h in HYPS["hypotheses"]:
            self.assertTrue(REQUIRED_FIELDS <= set(h), h["id"])
            self.assertEqual(h["status"], "REGISTERED")

    def test_feature_references_valid(self):
        for h in HYPS["hypotheses"]:
            for feat in h["required_features"]:
                self.assertIn(feat, KNOWN_FEATURES, (h["id"], feat))

    def test_execution_model_single_family(self):
        for h in HYPS["hypotheses"]:
            self.assertEqual(h["entry_model"][:13], "NEXT_BAR_OPEN", h["id"])

    def test_costs_frozen_ladder(self):
        for h in HYPS["hypotheses"]:
            self.assertEqual(h["cost_scenarios"], ["A", "B", "C", "D"])

    def test_evidence_thresholds(self):
        for h in HYPS["hypotheses"]:
            ev = h["minimum_evidence"]
            self.assertEqual((ev["pooled_trades"], ev["folds"],
                              ev["active_folds"], ev["regime_cell_trades"]),
                             (30, 3, 2, 3))

    def test_no_forbidden_orderflow(self):
        blob = json.dumps(HYPS).lower()
        for token in ("real_delta", "real_cvd", "real_footprint",
                      "real_absorption", "real_imbalance", "real delta",
                      "real footprint", "bid/ask imbalance"):
            self.assertNotIn(token, blob)
        for h in HYPS["hypotheses"]:
            for dim in ("real_order_flow",):
                self.assertIn(dim, h["forbidden_dimensions"])

    def test_no_d3_no_live(self):
        blob = json.dumps(HYPS)
        self.assertNotIn("D3", blob)
        self.assertNotIn("LIVE_EXECUTE", blob)
        self.assertNotIn("ALLOW_LIVE", blob)

    def test_no_production_paths(self):
        blob = json.dumps(HYPS)
        for token in ("core.", "place_order", "DeltaOrderExecutor", "BrokerEngine"):
            self.assertNotIn(token, blob)

    def test_no_custom_fibonacci(self):
        blob = json.dumps(HYPS)
        # "custom" may appear ONLY inside the custom_fibonacci forbidden
        # dimension (which bans custom ratios). Strip those, then require
        # zero remaining occurrences: no custom ratio is defined anywhere.
        stripped = blob.replace("custom_fibonacci", "")
        self.assertNotIn("custom", stripped.lower())
        # Frozen ratios are referenced by rule, never redefined per
        # hypothesis: no ratio literal is attached to a fib definition.
        self.assertNotIn("0.382", blob)
        for h in HYPS["hypotheses"]:
            self.assertIn("custom_fibonacci", h["forbidden_dimensions"])

    def test_no_scoring_no_ml(self):
        blob = json.dumps(HYPS).lower()
        # "ml"/"scores" appear ONLY as forbidden dimensions (required),
        # never as methods/weights. Method tokens must be absent.
        for token in ("classifier", "random forest", "neural", "gradient",
                      "machine learning", "svm", '"weight"'):
            self.assertNotIn(token, blob)
        self.assertNotIn('"score"', blob)
        for h in HYPS["hypotheses"]:
            self.assertIn("scores", h["forbidden_dimensions"])
            self.assertIn("ml", h["forbidden_dimensions"])

    def test_no_performance_results(self):
        # "expectancy" appears legitimately inside falsifiable claims
        # ("positive OOS expectancy"); what must be absent are measured
        # results. Check result-like tokens instead.
        blob = json.dumps(HYPS).lower()
        for token in ("win rate", "profit factor", "sharpe", "sortino",
                      "drawdown", "monte carlo", "winner", "net +",
                      "trades:"):
            self.assertNotIn(token, blob)

    def test_no_duplicates(self):
        seen = set()
        for h in HYPS["hypotheses"]:
            key = (h["entry_condition"], h["stop_rule"], h["target_rule"])
            self.assertNotIn(key, seen, h["id"])
            seen.add(key)

    def test_falsifiable_claims(self):
        for h in HYPS["hypotheses"]:
            c = h["scientific_claim"].lower()
            self.assertIn("cost c", c, h["id"])
            self.assertIn("expectancy", c, h["id"])

    def test_multiple_testing_frozen(self):
        mt = HYPS["multiple_testing"]
        self.assertEqual(mt["family_size"], 8)
        self.assertAlmostEqual(mt["bonferroni_reference"], 0.00625)


if __name__ == "__main__":
    unittest.main()
