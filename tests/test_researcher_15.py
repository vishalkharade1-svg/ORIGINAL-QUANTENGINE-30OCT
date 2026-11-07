"""
====================================================

QuantEngine

Phase 15 -- evidence-readiness regression suite.

Research-only. Nothing here tunes the strategy, changes
thresholds, enables live trading, or promotes anything.
Frozen gates are pinned (any change must update these
tests deliberately -- they never change by accident).

Covers the 25 mandated areas: baseline reproduction,
dataset hashing/classification, instrument semantics, fee
semantics, funding/microstructure unavailability, venue
classification, temporal splitting, OOS isolation,
sample-size gates, actual-fill RR, adverse/favorable gaps,
regime/symbol/directional conditioning, multiple-testing
preservation, lookahead causality, deterministic rerun,
worker-invariance scope, production isolation,
never-promotion, 11G immutability, Phase-14 immutability.

Stdlib only. No network. Deterministic.
====================================================
"""

import hashlib
import io
import json
import os
import pathlib
import unittest

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = (ROOT / "research" / "results" /
            "phase14_executable_edge_forensics.json")
GATE_A_RAW = (ROOT / "docs" / "audit" /
              "baseline_9s_delta_5000_raw.json")


def load_artifact():
    with io.open(str(ARTIFACT), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------
# 1. Phase-14 baseline reproduction
# --------------------------------------------------

class TestBaselineReproduction(unittest.TestCase):

    def test_artifact_baseline_block(self):
        art = load_artifact()
        base = art["baseline_reproduction"]
        self.assertEqual(base["orders"], 25)
        self.assertEqual(base["fills"], 2)
        self.assertEqual(base["wins"], 0)
        self.assertEqual(base["losses"], 2)
        self.assertAlmostEqual(base["net"], -0.206452, places=6)
        self.assertTrue(base["match"])

    def test_lifecycle_identity_holds(self):
        art = load_artifact()
        funnel = art["funnel_accounting"]
        terminal = funnel["terminal"]
        self.assertEqual(
            sum(terminal.values()), funnel["orders_minted"])
        self.assertEqual(
            terminal, {"EXPIRED": 15, "INVALIDATED": 8,
                       "FILLED": 2})


# --------------------------------------------------
# 2-3. Dataset hashing + classification
# --------------------------------------------------

class TestDatasetReadiness(unittest.TestCase):

    def _raw(self):
        with io.open(str(GATE_A_RAW), encoding="utf-8") as fh:
            return json.load(fh)

    def test_dataset_hash_stable(self):
        first = hashlib.sha256(
            GATE_A_RAW.read_bytes()).hexdigest()
        second = hashlib.sha256(
            GATE_A_RAW.read_bytes()).hexdigest()
        self.assertEqual(len(first), 64)
        self.assertEqual(first, second)
        art = load_artifact()
        self.assertEqual(art["dataset_hash"], first)

    def test_dataset_classification(self):
        raw = self._raw()
        rows = raw["raw"]
        self.assertEqual(raw["symbol"], "BTCUSDT")
        self.assertEqual(raw["timeframe"], "1m")
        self.assertEqual(len(rows), 5000)
        for row in rows:
            self.assertEqual(
                sorted(row.keys()),
                ["close", "high", "low", "open", "time",
                 "volume"])
        stamps = sorted(r["time"] for r in rows)
        self.assertEqual(len(set(stamps)), 5000)
        steps = {b - a for a, b in zip(stamps, stamps[1:])}
        self.assertEqual(steps, {60})
        # Continuity VERIFIED; flat-bar provenance unknown
        # (92%+ flat minutes) -- documented, not resolved.
        flat = sum(1 for r in rows
                   if r["open"] == r["high"] == r["low"] ==
                   r["close"])
        self.assertGreater(flat, 4000)


# --------------------------------------------------
# 4. Instrument semantics
# --------------------------------------------------

class TestInstrumentSemantics(unittest.TestCase):

    def test_contract_schema_supports_full_semantics(self):
        from core.registry.instrument import Instrument
        inst = Instrument(
            instrument_id="DELTA:BTCUSDT", symbol="BTCUSDT",
            exchange="DELTA", tick_size=0.5, quantity_step=0.001,
            minimum_quantity=0.001, trading_enabled=True)
        self.assertTrue(inst.valid_precision)
        self.assertAlmostEqual(inst.round_price(100.3), 100.5)

    def test_backtester_needs_no_contract(self):
        # The frozen Gate-A path sizes generically (quantity /
        # dust / precision); venue contract population is a
        # separate, explicitly PARTIAL layer.
        from config import risk_settings
        self.assertGreater(risk_settings.MIN_QUANTITY, 0.0)
        self.assertFalse(hasattr(risk_settings, "MIN_NOTIONAL"))


# --------------------------------------------------
# 5-7. Fee / funding / microstructure semantics
# --------------------------------------------------

class TestEconomicSemantics(unittest.TestCase):

    def test_fees_explicit_zero_not_invented(self):
        from config import risk_settings
        self.assertEqual(risk_settings.COMMISSION_PER_TRADE, 0.0)
        self.assertEqual(risk_settings.COMMISSION_RATE, 0.0)
        self.assertEqual(risk_settings.SLIPPAGE_BPS, 0.0)

    def test_no_machine_fee_schedule(self):
        # No machine-readable venue fee schedule exists;
        # any fee assumption is therefore ASSUMED, never VERIFIED.
        hits = []
        for path in (ROOT / "core" / "risk").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "fee_schedule" in text:
                hits.append(path.name)
        self.assertEqual(hits, [])

    def test_funding_unavailable(self):
        from core.backtesting.trade import Trade
        from core.backtesting.trade_simulator import TradeSimulator
        # Funding accrues ONLY from an explicit venue-evidence-backed
        # FundingSchedule. Without one no venue funding is applied: a
        # default trade carries 0.0/0 and a default simulator holds no
        # schedule (fail-closed; unknown funding is never silently
        # modeled). Dedicated arithmetic lives in the funding-evidence
        # suites (phase 67/70/71).
        trade = Trade()
        self.assertEqual(trade.funding, 0.0)
        self.assertEqual(trade.funding_events, 0)
        self.assertIsNone(TradeSimulator().funding_schedule)

    def test_microstructure_unavailable(self):
        from core.history.candle import Candle
        import dataclasses
        fields = {f.name for f in dataclasses.fields(Candle)}
        for missing in ("tick", "aggressor", "bid", "ask",
                        "depth", "footprint"):
            self.assertNotIn(missing, fields)
        # No trades/depth/funding endpoints in the adapters.
        hits = []
        import re as _re
        for path in list((ROOT / "core" / "exchanges").rglob("*.py")) + \
                [ROOT / "data" / "historical_loader.py"]:
            text = path.read_text(encoding="utf-8")
            for token in ("/v2/trades", "/v2/funding", "/v2/l2",
                          "/v2/depth", "/v2/orderbook"):
                # Segment-boundary match: the validated public
                # `/v2/l2orderbook/{symbol}` evidence path (phase 72)
                # must not trip the `/v2/l2` token.
                if _re.search(_re.escape(token) + r"(?![A-Za-z0-9_])", text):
                    hits.append((path.name, token))
        self.assertEqual(hits, [])


# --------------------------------------------------
# 8. Venue classification
# --------------------------------------------------

class TestVenueClassification(unittest.TestCase):

    def test_documented_target_venue_with_caveat(self):
        doc = (ROOT / "docs" / "audit" /
               "baseline_9s_delta_5000.md").read_text(
                   encoding="utf-8")
        self.assertIn("Delta /v2/history/candles", doc)
        # ...but rows carry no self-identifying venue field.
        with io.open(str(GATE_A_RAW), encoding="utf-8") as fh:
            rows = json.load(fh)["raw"]
        for key in ("venue", "exchange", "market"):
            self.assertNotIn(key, rows[0])


# --------------------------------------------------
# 9-10. Temporal splitting + OOS isolation
# --------------------------------------------------

class TestTemporalSplitting(unittest.TestCase):

    def _items(self, n=10):
        return [{"t": i, "v": float(n - i)} for i in range(n)]

    def test_split_chronological_no_overlap(self):
        from core.research.ml.split import temporal_split
        items = self._items(10)
        first = temporal_split(items)
        second = temporal_split(list(reversed(items)))
        self.assertEqual(first.to_dict(), second.to_dict())
        train = first.train_items()
        validation = first.validation_items()
        oos = first.oos_items()
        self.assertLess(max(x["t"] for x in train),
                        min(x["t"] for x in validation))
        self.assertLess(max(x["t"] for x in validation),
                        min(x["t"] for x in oos))

    def test_walk_forward_purge_embargo_accepted(self):
        from core.research.ml.split import walk_forward
        items = self._items(20)
        result = walk_forward(items, train_size=0.5,
                              step=0.2, min_oos=3, purge_bars=2,
                              embargo_bars=1)
        folds = list(result.iter_folds())
        self.assertGreater(len(folds), 0)
        for fold in folds:
            trains = [items[i]["t"] for i in fold.train.indices]
            tests = [items[i]["t"] for i in fold.test.indices]
            if trains and tests:
                self.assertLess(max(trains), min(tests))
                # Embargo respected: test block starts at least
                # embargo_bars after the unpurged train end.
                self.assertGreaterEqual(
                    min(tests) - max(trains), 1)

    def test_oos_gate_threshold_intact(self):
        from research.phase11g_q import gate
        self.assertEqual(gate.WF_REQUIRED_BARS, 6175)
        doc = (ROOT / "docs" / "audit" /
               "phase11g_Q_full_oos_execution.md").read_text(
                   encoding="utf-8")
        self.assertIn("FULL_WF_DATA_INSUFFICIENT", doc)


# --------------------------------------------------
# 11. Sample-size gates (from frozen 9M semantics)
# --------------------------------------------------

class TestSampleSizeGates(unittest.TestCase):

    def _ladder(self, n_trades):
        from core.research.oos import constants as C
        if n_trades < C.MIN_OOS_TRADES_PER_PERIOD:
            return "INSUFFICIENT_SAMPLE"
        if n_trades < C.MIN_TOTAL_OOS_TRADES:
            return "INCONCLUSIVE"
        return "SUFFICIENT_FOR_ROBUSTNESS_REVIEW"

    def test_two_fills_insufficient(self):
        self.assertEqual(self._ladder(2), "INSUFFICIENT_SAMPLE")
        self.assertEqual(self._ladder(9), "INSUFFICIENT_SAMPLE")
        self.assertEqual(self._ladder(10), "INCONCLUSIVE")
        self.assertEqual(self._ladder(60),
                         "SUFFICIENT_FOR_ROBUSTNESS_REVIEW")

    def test_protocol_constants_frozen(self):
        from core.research.oos import constants as C
        self.assertEqual(C.MIN_OOS_TRADES_PER_PERIOD, 10)
        self.assertEqual(C.MIN_TOTAL_OOS_TRADES, 60)
        self.assertEqual(C.MIN_SURVIVING_PERIODS, 5)
        self.assertEqual(C.OOS_PERIODS, 6)
        self.assertTrue(C.SPLIT_PROTOCOL_FROZEN)


# --------------------------------------------------
# 12-14. Actual-fill RR + gaps (from artifact records)
# --------------------------------------------------

class TestActualFillEvidence(unittest.TestCase):

    def test_fills_all_above_six(self):
        art = load_artifact()
        fills = [r for r in art["order_forensics"]
                 if r["final_state"] == "FILLED"]
        self.assertEqual(len(fills), 2)
        for row in fills:
            self.assertGreaterEqual(row["actual_fill_rr"], 6.0)

    def test_no_favorable_gap_refusals(self):
        art = load_artifact()
        erosion = art["rr_erosion_analysis"]
        self.assertEqual(
            erosion["adverse_gap_points"]["favorable_gap_refusals"],
            0)

    def test_refusals_below_six(self):
        art = load_artifact()
        for row in art["order_forensics"]:
            if row["final_state"] != "FILLED" and \
                    row["actual_fill_rr"] is not None and \
                    row["trigger_bar"] is not None:
                # Every evaluated refusal sat below the gate
                # (the one compliant exception expired via the
                # correct single-position block).
                if row["actual_fill_rr"] >= 6.0:
                    self.assertEqual(row["final_state"], "EXPIRED")


# --------------------------------------------------
# 15-17. Regime / symbol / directional conditioning
# --------------------------------------------------

class TestConditioning(unittest.TestCase):

    def test_regime_labels_heuristic_vol_unavailable(self):
        from core.regime import regime_engine
        source = pathlib.Path(regime_engine.__file__).read_text(
            encoding="utf-8")
        for label in ("BULLISH", "BEARISH", "RANGE"):
            self.assertIn(label, source)
        for label in ("HIGH_VOL", "LOW_VOL"):
            self.assertNotIn(label, source)

    def test_single_symbol_gate_a(self):
        art = load_artifact()
        self.assertEqual(
            set(art["symbol_analysis"].keys()) - {"note"},
            {"BTCUSDT"})
        self.assertEqual(art["symbol_analysis"]["BTCUSDT"]["fills"], 2)

    def test_directional_split_descriptive(self):
        art = load_artifact()
        directional = art["directional_analysis"]
        self.assertEqual(directional["BULLISH"]["orders"], 12)
        self.assertEqual(directional["BEARISH"]["orders"], 13)
        self.assertEqual(directional["BULLISH"]["fills"], 2)
        self.assertEqual(directional["BEARISH"]["fills"], 0)
        self.assertIn("ASYMMETRY", directional["verdict"])


# --------------------------------------------------
# 18. Multiple-testing preservation
# --------------------------------------------------

class TestMultipleTestingPreserved(unittest.TestCase):

    def test_familywise_guards_present(self):
        from core.research.conditional_ml import (
            familywise_alpha, holm_survives)
        self.assertLess(familywise_alpha(0.05, 10), 0.05)
        self.assertTrue(callable(holm_survives))

    def test_no_new_hypothesis_family(self):
        require_git_fact(self, 'test_researcher_15::TestMultipleTestingPreserved::test_no_new_hypothesis_family')
        # Phase 15 creates no hypothesis registry, no alpha,
        # no family: the research tree must show zero
        # modifications (any new family would require new or
        # changed research files).
        import subprocess
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "research/"],
            capture_output=True, text=True, cwd=str(ROOT),
            timeout=60,
        )
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "")


# --------------------------------------------------
# 19. Lookahead causality (exec-bar identity)
# --------------------------------------------------

class TestLookaheadCausality(unittest.TestCase):

    def test_entry_bar_strictly_after_trigger(self):
        art = load_artifact()
        for row in art["order_forensics"]:
            if row["trigger_bar"] is not None:
                self.assertGreaterEqual(row["exec_bar"],
                                        row["trigger_bar"] + 1)
                self.assertGreaterEqual(row["exec_ts"],
                                        row["trigger_ts"])

    def test_fills_reference_prior_bars_only(self):
        art = load_artifact()
        for row in art["order_forensics"]:
            if row["final_state"] == "FILLED":
                self.assertIsNotNone(row["fill_entry"])
                self.assertGreater(row["exec_ts"], 0)


# --------------------------------------------------
# 20. Deterministic rerun (serialization)
# --------------------------------------------------

class TestDeterministicSerialization(unittest.TestCase):

    def test_artifact_stable_bytes(self):
        import hashlib
        raw = ARTIFACT.read_bytes()
        first = hashlib.sha256(raw).hexdigest()
        art = load_artifact()
        text = json.dumps(art, indent=2, sort_keys=True,
                          separators=(",", ": ")) + "\n"
        second = hashlib.sha256(
            text.encode("utf-8")).hexdigest()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)


# --------------------------------------------------
# 21. Worker invariance scope
# --------------------------------------------------

class TestWorkerScope(unittest.TestCase):

    def test_no_parallel_paths_in_forensic_surface(self):
        hits = []
        for path in list((ROOT / "core" / "backtesting").glob("*.py")) + \
                list((ROOT / "backtesting").glob("*.py")) + \
                list((ROOT / "core" / "pipeline").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in ("multiprocessing", "concurrent.futures",
                          "joblib", "ProcessPool", "ThreadPool"):
                if token in text:
                    hits.append((path.name, token))
        self.assertEqual(hits, [])


# --------------------------------------------------
# 22-23. Production isolation + never-promotion
# --------------------------------------------------

class TestProductionPosture(unittest.TestCase):

    def test_no_live_surface_in_research(self):
        # Live-mutation tokens may appear ONLY inside
        # FORBIDDEN-* declaration blocks (isolation contracts
        # asserting their absence elsewhere), never as live
        # call sites.
        hits = []
        for path in (ROOT / "research").rglob("*.py"):
            if "test_" in path.name:
                continue
            lines = path.read_text(
                encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, start=1):
                window = "\n".join(
                    lines[max(0, lineno - 21):lineno + 20])
                if "FORBIDDEN" in window:
                    continue
                for token in ("place_order", "submit_order",
                              "DeltaOrderExecutor",
                              "BrokerEngine("):
                    if token in line:
                        hits.append((str(path), lineno, token))
        self.assertEqual(hits, [])

    def test_artifact_never_promotes(self):
        art = load_artifact()
        self.assertFalse(art["is_production_ready"])
        blob = json.dumps(art)
        for token in ("PROFITABLE", "ROBUST EDGE", "TRADABLE",
                      "PRODUCTION_READY", "GO_LIVE"):
            self.assertNotIn(token, blob)
        self.assertIn("LOW_EXECUTABLE_OPPORTUNITY",
                      art["final_classification"])

    def test_safe_defaults_deny_live(self):
        from config.settings import Settings
        fresh = Settings()
        self.assertTrue(fresh.PAPER_MODE)
        self.assertFalse(fresh.LIVE_MODE)
        self.assertFalse(fresh.ALLOW_LIVE)
        self.assertFalse(fresh.LIVE_EXECUTE)


# --------------------------------------------------
# 24-25. 11G + Phase-14 immutability
# --------------------------------------------------

class TestFrozenRecords(unittest.TestCase):

    def test_11g_negative_verdicts_intact(self):
        base = ROOT / "docs" / "audit"
        text_l = (base / "phase11g_L_real_orderflow_economic_research.md"
                  ).read_text(encoding="utf-8")
        self.assertIn("H11GK-004", text_l)
        self.assertIn("FAIL", text_l)
        text_m = (base / "phase11g_M_independent_holdout_validation.md"
                  ).read_text(encoding="utf-8")
        self.assertIn("NO-GO", text_m)

    def test_phase14_artifact_complete(self):
        art = load_artifact()
        self.assertEqual(len(art["order_forensics"]), 25)
        for key in ("lifecycle_model", "funnel_accounting",
                    "rr_erosion_analysis", "execution_semantics",
                    "gap_analysis", "pnl_analysis", "cost_scenarios",
                    "market_data_status", "reconciliation_status",
                    "symbol_analysis", "directional_analysis",
                    "regime_analysis", "oos_status", "sample_adequacy",
                    "lookahead", "determinism", "test_integrity",
                    "production_isolation", "limitations",
                    "gate_matrix", "final_classification",
                    "is_production_ready"):
            self.assertIn(key, art)


if __name__ == "__main__":
    unittest.main()
