"""
====================================================

QuantEngine

Phase 16 -- evidence-readiness regression suite.

Research/data-readiness only. Nothing here tunes the
strategy, changes thresholds, enables live trading, or
promotes anything. Frozen gates are pinned (any change
must update these tests deliberately).

Covers the 25 mandated areas: baseline reproduction,
dataset hashing/classification, instrument semantics, fee
semantics, funding/microstructure unavailability, venue
classification, temporal splitting, OOS isolation,
sample-size gates, actual-fill RR, adverse/favorable gaps,
regime/symbol/directional conditioning, multiple-testing
preservation, lookahead causality, deterministic rerun,
worker-invariance scope, production isolation,
never-promotion, 11G immutability, Phase-14/15
immutability, sample-math unit pins.

Stdlib only. No network. Deterministic.
====================================================
"""

import hashlib
import io
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTIFACT = (ROOT / "research" / "results" /
            "phase15_evidence_readiness.json")
P14_ARTIFACT = (ROOT / "research" / "results" /
                "phase14_executable_edge_forensics.json")
GATE_A_RAW = (ROOT / "docs" / "audit" /
              "baseline_9s_delta_5000_raw.json")
# Phase 22 registered versioned identity (Phase-165 architecture;
# see reports/PHASE22_STRATEGY_IDENTITY_BASELINE.json). The Phase-14
# pooled pin in the artifacts stays the historical record; live
# registration covers the LF-canonical alpha core and runtime
# infrastructure composites. Re-registration is deliberate and
# documented.
PHASE22_CORE_SHA256 = (
    "26c2bead8c4599b78c64281a3d2860e194f16603c950840df199c953fcfc9666"
)
PHASE22_INFRA_SHA256 = (
    "997a21f21045551ed25e29d2289157d257b16b5f3b99bbf04e95c7f257b96294"
)


def load_artifact():
    # Phase-15 evidence-readiness artifact (baseline_reference,
    # readiness classifications, gate matrix).
    with io.open(str(ARTIFACT), encoding="utf-8") as fh:
        return json.load(fh)


def load_p14():
    # Frozen Phase-14 forensics artifact (baseline_reproduction,
    # funnel accounting, per-order execution records).
    with io.open(str(P14_ARTIFACT), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------
# 1. Phase-14/15 baseline reproduction
# --------------------------------------------------

class TestBaselineReproduction(unittest.TestCase):

    def test_gate_a_numbers_reproduced(self):
        art = load_p14()
        base = art["baseline_reproduction"]
        self.assertEqual(base["orders"], 25)
        self.assertEqual(base["fills"], 2)
        self.assertEqual(base["wins"], 0)
        self.assertEqual(base["losses"], 2)
        self.assertAlmostEqual(base["net"], -0.206452, places=6)
        self.assertTrue(base["match"])

    def test_lifecycle_identity_reproduced(self):
        art = load_p14()
        funnel = art["funnel_accounting"]
        terminal = funnel["terminal"]
        self.assertEqual(
            sum(terminal.values()), funnel["orders_minted"])
        self.assertEqual(
            terminal, {"EXPIRED": 15, "INVALIDATED": 8,
                       "FILLED": 2})

    def test_parent_lineage(self):
        art = load_artifact()
        self.assertEqual(len(art["commit"]), 40)
        self.assertEqual(len(art["parent_commit"]), 40)
        self.assertNotEqual(art["commit"], art["parent_commit"])
        self.assertEqual(len(art["dataset_hash"]), 64)


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
        flat = sum(1 for r in rows
                   if r["open"] == r["high"] == r["low"] ==
                   r["close"])
        self.assertGreater(flat, 4000)


# --------------------------------------------------
# 4. Instrument semantics
# --------------------------------------------------

class TestInstrumentSemantics(unittest.TestCase):

    def test_contract_schema_exists(self):
        from core.registry.instrument import Instrument
        inst = Instrument(
            instrument_id="DELTA:BTCUSDT", symbol="BTCUSDT",
            exchange="DELTA", tick_size=0.5, quantity_step=0.001,
            minimum_quantity=0.001, trading_enabled=True)
        self.assertTrue(inst.valid_precision)

    def test_no_minimum_notional_field(self):
        # Minimum notional is UNAVAILABLE everywhere: the
        # schema has tick/quantity-step/minimum-quantity but
        # no notional floor.
        from core.registry.instrument import Instrument
        import dataclasses
        names = {f.name for f in dataclasses.fields(Instrument)}
        self.assertNotIn("minimum_notional", names)
        self.assertNotIn("min_notional", names)


# --------------------------------------------------
# 5-7. Fee / funding / microstructure semantics
# --------------------------------------------------

class TestEconomicSemantics(unittest.TestCase):

    def test_fees_explicit_zero(self):
        from config import risk_settings
        self.assertEqual(risk_settings.COMMISSION_PER_TRADE, 0.0)
        self.assertEqual(risk_settings.COMMISSION_RATE, 0.0)
        self.assertEqual(risk_settings.SLIPPAGE_BPS, 0.0)

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


class TestCostScenarios(unittest.TestCase):

    def test_structural_is_identity(self):
        from core.research.readiness.scenarios import (
            scenario_structural)
        out = scenario_structural(10.0)
        self.assertEqual(out["net"], 10.0)
        self.assertEqual(out["fees"], 0.0)
        self.assertEqual(out["slippage"], 0.0)
        self.assertEqual(out["funding"], 0.0)
        self.assertEqual(out["label"], "VERIFIED-zero-cost")

    def test_conservative_fees_labeled_assumed(self):
        from core.research.readiness.scenarios import (
            scenario_conservative_fees)
        out = scenario_conservative_fees(10.0, 10000.0)
        self.assertAlmostEqual(out["fees"], 5.0)
        self.assertAlmostEqual(out["net"], 5.0)
        self.assertTrue(out["label"].startswith("ASSUMED"))

    def test_conservative_slippage_labeled_assumed(self):
        from core.research.readiness.scenarios import (
            scenario_conservative_slippage)
        out = scenario_conservative_slippage(10.0, 10000.0)
        self.assertAlmostEqual(out["slippage"], 2.0)
        self.assertAlmostEqual(out["net"], 8.0)
        self.assertTrue(out["label"].startswith("ASSUMED"))

    def test_combined_sums_both_legs(self):
        from core.research.readiness.scenarios import (
            scenario_combined)
        out = scenario_combined(10.0, 10000.0)
        self.assertAlmostEqual(out["net"], 3.0)
        self.assertTrue(out["label"].startswith("ASSUMED"))

    def test_funding_never_substitutes_zero(self):
        from core.research.readiness.scenarios import (
            scenario_funding)
        out = scenario_funding()
        self.assertIsNone(out["net"])
        self.assertEqual(out["label"], "UNAVAILABLE")


# --------------------------------------------------
# 8. Venue classification
# --------------------------------------------------

class TestVenueClassification(unittest.TestCase):

    def test_documented_target_venue_with_caveat(self):
        doc = (ROOT / "docs" / "audit" /
               "baseline_9s_delta_5000.md").read_text(
                   encoding="utf-8")
        self.assertIn("Delta /v2/history/candles", doc)
        with io.open(str(GATE_A_RAW), encoding="utf-8") as fh:
            rows = json.load(fh)["raw"]
        for key in ("venue", "exchange", "market"):
            self.assertNotIn(key, rows[0])
        art = load_artifact()
        self.assertIn("DIRECT_TARGET_VENUE",
                      art["venue_classification"])


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

    def test_oos_gate_threshold_intact(self):
        from research.phase11g_q import gate
        self.assertEqual(gate.WF_REQUIRED_BARS, 6175)
        doc = (ROOT / "docs" / "audit" /
               "phase11g_Q_full_oos_execution.md").read_text(
                   encoding="utf-8")
        self.assertIn("FULL_WF_DATA_INSUFFICIENT", doc)

    def test_oos_protocol_frozen(self):
        from core.research.oos import constants as C
        self.assertEqual(C.OOS_PERIODS, 6)
        self.assertEqual(C.MIN_OOS_TRADES_PER_PERIOD, 10)
        self.assertEqual(C.MIN_TOTAL_OOS_TRADES, 60)
        self.assertEqual(C.MIN_SURVIVING_PERIODS, 5)
        self.assertTrue(C.SPLIT_PROTOCOL_FROZEN)
        art = load_artifact()
        self.assertEqual(art["periods"], [])
        self.assertEqual(art["hypotheses"], [])


# --------------------------------------------------
# 11. Sample-size gates (frozen 9M semantics + math)
# --------------------------------------------------

class TestSampleSizeGates(unittest.TestCase):

    def test_two_fills_insufficient(self):
        from core.research.oos import constants as C
        from core.research.readiness.sample_math import (
            sample_ladder,
        )
        self.assertEqual(
            sample_ladder(2, C.MIN_OOS_TRADES_PER_PERIOD,
                          C.MIN_TOTAL_OOS_TRADES),
            "INSUFFICIENT_SAMPLE")
        art = load_artifact()
        self.assertTrue(
            art["sample_adequacy"].startswith("INSUFFICIENT_SAMPLE"),
            art["sample_adequacy"][:60])

    def test_required_bars_math(self):
        from core.research.readiness.sample_math import (
            expected_fills, oos_span_bars, required_bars,
        )
        # 10 fills at the observed Gate-A rates.
        self.assertAlmostEqual(
            required_bars(10, 0.005, 0.08), 25000.0)
        self.assertAlmostEqual(
            expected_fills(25000.0, 0.005, 0.08), 10.0)
        # Strict 9M: 6 periods + 50% discovery headroom.
        self.assertAlmostEqual(
            oos_span_bars(25000.0, 6), 300000.0)
        with self.assertRaises(ValueError):
            required_bars(10, 0.0, 0.08)
        with self.assertRaises(ValueError):
            required_bars(10, 0.005, 0.0)
        with self.assertRaises(ValueError):
            oos_span_bars(0.0, 6)


# --------------------------------------------------
# 12-14. Actual-fill RR + gaps (from artifact records)
# --------------------------------------------------

class TestActualFillEvidence(unittest.TestCase):

    def test_fills_all_above_six(self):
        art = load_p14()
        fills = [r for r in art["order_forensics"]
                 if r["final_state"] == "FILLED"]
        self.assertEqual(len(fills), 2)
        for row in fills:
            self.assertGreaterEqual(row["actual_fill_rr"], 6.0)

    def test_no_favorable_gap_refusals(self):
        art = load_p14()
        erosion = art["rr_erosion_analysis"]
        self.assertEqual(
            erosion["adverse_gap_points"]["favorable_gap_refusals"],
            0)


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

    def test_single_symbol(self):
        art = load_p14()
        self.assertEqual(
            set(art["symbol_analysis"].keys()) - {"note"},
            {"BTCUSDT"})

    def test_directional_split_descriptive(self):
        art = load_p14()
        directional = art["directional_analysis"]
        self.assertEqual(directional["BULLISH"]["orders"], 12)
        self.assertEqual(directional["BEARISH"]["orders"], 13)
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

    def test_artifact_states_no_new_family(self):
        art = load_artifact()
        self.assertTrue(
            art["multiple_testing"].startswith(
                "NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY"),
            art["multiple_testing"][:80])


# --------------------------------------------------
# 19. Lookahead causality (exec-bar identity)
# --------------------------------------------------

class TestLookaheadCausality(unittest.TestCase):

    def test_entry_bar_strictly_after_trigger(self):
        art = load_p14()
        for row in art["order_forensics"]:
            if row["trigger_bar"] is not None:
                self.assertGreaterEqual(row["exec_bar"],
                                        row["trigger_bar"] + 1)


# --------------------------------------------------
# 20. Deterministic rerun (serialization)
# --------------------------------------------------

class TestDeterministicSerialization(unittest.TestCase):

    def test_artifact_stable_bytes(self):
        import hashlib
        for path in (ARTIFACT,
                     ROOT / "research" / "results" /
                     "phase14_executable_edge_forensics.json"):
            raw = path.read_bytes()
            first = hashlib.sha256(raw).hexdigest()
            art = json.loads(raw.decode("utf-8"))
            text = json.dumps(art, indent=2, sort_keys=True,
                              separators=(",", ": ")) + "\n"
            second = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            self.assertEqual(first, second)


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

    def test_safe_defaults_deny_live(self):
        from config.settings import Settings
        fresh = Settings()
        self.assertTrue(fresh.PAPER_MODE)
        self.assertFalse(fresh.LIVE_MODE)
        self.assertFalse(fresh.ALLOW_LIVE)
        self.assertFalse(fresh.LIVE_EXECUTE)


# --------------------------------------------------
# 24-25. 11G + Phase-14 immutability + strategy hash
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

    def test_strategy_hash_pinned(self):
        from core.research.strategy_identity import (
            HISTORICAL_PHASE14_STRATEGY_HASH,
            get_versioned_identities,
        )
        from tests.strategy_identity_evidence import assert_unregistered_identity
        files = [
            "core/execution/entry_model.py",
            "core/setup/trade_setup_builder.py",
            "core/setup/decision_engine.py",
            "core/execution/execution_engine.py",
            "core/risk/risk_engine.py",
            "core/backtesting/accounting.py",
            "backtesting/backtester.py",
            "core/paper_trading/paper_trading_engine.py",
            "config/risk_settings.py",
        ]
        art = load_p14()
        self.assertEqual(art["strategy_hash"], HISTORICAL_PHASE14_STRATEGY_HASH)
        self.assertEqual(art["strategy_files"], files)
        assert_unregistered_identity(self, get_versioned_identities(ROOT), ROOT)


if __name__ == "__main__":
    unittest.main()
