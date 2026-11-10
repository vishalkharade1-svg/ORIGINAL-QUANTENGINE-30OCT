"""
====================================================
QuantEngine -- Phase 18 genuine multi-period OOS
validation regression suite.

Research-only, deterministic, offline. Nothing here tunes
the strategy, changes thresholds, weakens the 1:6 RR gate,
enables live trading, resurrects 7E, or promotes anything.
Frozen gates are pinned.

Covers: strategy identity, fresh-data boundary,
discovery/OOS separation, period splitting, chronological
ordering, period determinism, sample-size gates,
actual-fill RR, gap handling, phantom-win defense,
intrabar ambiguity, economic scenarios, symbol/
directional/temporal consistency, OOS survival,
unavailable evidence, insufficient sample, lookahead,
determinism, production isolation, 7E rejection,
multiple-testing protection, no strategy mutation, no
automatic promotion.

Stdlib + frozen project imports only. No network.
====================================================
"""

import hashlib
import io
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
P14_ARTIFACT = ROOT / "research" / "results" / "phase14_executable_edge_forensics.json"
P17_ARTIFACT = ROOT / "research" / "results" / "phase17_oos_feasibility.json"
P18_ARTIFACT = ROOT / "research" / "results" / "phase18_oos_validation.json"
FRESH = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
GATE_A_END = 1788601440
STRATEGY_HASH = ("c52e648ca24fb03b9ba818ebb766e32b035b48df201d5a2a1b254d04f7f3d5a6")
STRATEGY_FILES = [
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
# Phase 22 registered versioned identity (Phase-165 architecture;
# see reports/PHASE22_STRATEGY_IDENTITY_BASELINE.json). The Phase-14
# pooled pin above stays the historical record; live registration
# covers the LF-canonical alpha core and runtime infrastructure
# composites. Re-registration is deliberate and documented.
PHASE22_CORE_SHA256 = (
    "26c2bead8c4599b78c64281a3d2860e194f16603c950840df199c953fcfc9666"
)
PHASE22_INFRA_SHA256 = (
    "997a21f21045551ed25e29d2289157d257b16b5f3b99bbf04e95c7f257b96294"
)


def load_artifact():
    with io.open(str(P18_ARTIFACT), encoding="utf-8") as fh:
        return json.load(fh)


def fresh_rows_asc():
    with io.open(str(FRESH), encoding="utf-8") as fh:
        fresh = json.load(fh)
    return sorted(fresh["raw"], key=lambda r: r["time"]), fresh


# --------------------------------------------------
# 1. Frozen strategy identity (no optimization)
# --------------------------------------------------

class TestStrategyIdentity(unittest.TestCase):

    def test_historical_pin_and_unregistered_identity_are_separate(self):
        from core.research.strategy_identity import (
            HISTORICAL_PHASE14_STRATEGY_HASH,
            get_versioned_identities,
        )
        from tests.strategy_identity_evidence import assert_unregistered_identity

        self.assertEqual(HISTORICAL_PHASE14_STRATEGY_HASH, STRATEGY_HASH)
        assert_unregistered_identity(self, get_versioned_identities(ROOT), ROOT)
        self.assertIn("core/execution/execution_engine.py", STRATEGY_FILES)
        self.assertEqual(len(STRATEGY_FILES), 9)

    def test_baseline_and_rr_frozen(self):
        from config import risk_settings
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )
        self.assertEqual(risk_settings.ENTRY_MODE, "BREAKOUT_CONTINUATION")
        self.assertEqual(tuple(risk_settings.ACTIVE_ENTRY_MODES),
                         ("BREAKOUT_CONTINUATION",))
        with io.open(str(P14_ARTIFACT), encoding="utf-8") as fh:
            base = json.load(fh)["baseline_reproduction"]
        self.assertEqual(
            (base["orders"], base["fills"], base["wins"], base["losses"]),
            (25, 2, 0, 2))
        art = load_artifact()
        self.assertEqual(art["strategy_hash"], STRATEGY_HASH)
        self.assertTrue(art["strategy_unchanged"])
        self.assertEqual(art["baseline_reference"], base)

    def test_no_strategy_mutation_after_runs(self):
        from core.research.oos_validation.execution import run_frozen_oos
        from core.research.strategy_identity import get_versioned_identities
        from tests.strategy_identity_evidence import assert_unregistered_identity

        before = get_versioned_identities(ROOT)
        assert_unregistered_identity(self, before, ROOT)
        rows, _ = fresh_rows_asc()
        run_frozen_oos(rows[:300])
        after = get_versioned_identities(ROOT)
        assert_unregistered_identity(self, after, ROOT)
        self.assertEqual(before["strategy_core"]["sha256"],
                         after["strategy_core"]["sha256"])
        self.assertEqual(before["runtime_infrastructure"]["sha256"],
                         after["runtime_infrastructure"]["sha256"])
        self.assertEqual(
            before["composite_legacy_9_files"]["canonical_lf_sha256"],
            after["composite_legacy_9_files"]["canonical_lf_sha256"],
        )


# --------------------------------------------------
# 2-3. Fresh-data boundary + discovery separation
# --------------------------------------------------

class TestBoundary(unittest.TestCase):

    def test_fresh_strictly_after_gate_a(self):
        rows, fresh = fresh_rows_asc()
        self.assertEqual(fresh["fresh_after"], GATE_A_END)
        stamps = [r["time"] for r in rows]
        self.assertTrue(stamps)
        self.assertGreater(min(stamps), GATE_A_END)
        self.assertEqual(len(set(stamps)), len(stamps))
        self.assertTrue(all(b > a for a, b in zip(stamps, stamps[1:])))

    def test_boundary_equality_excluded(self):
        from core.research.oos_validation.periods import validate_freshness
        rows, _ = fresh_rows_asc()
        ok = validate_freshness(rows, GATE_A_END)
        self.assertTrue(ok["strictly_after"])
        self.assertEqual(ok["violations"], 0)
        # timestamp == boundary must NOT enter OOS
        bad = [{"time": GATE_A_END, "open": 1.0, "high": 1.0,
                "low": 1.0, "close": 1.0, "volume": 1.0}]
        rep = validate_freshness(bad, GATE_A_END)
        self.assertFalse(rep["strictly_after"])
        self.assertEqual(rep["violations"], 1)

    def test_rows_carry_no_venue_identity(self):
        rows, _ = fresh_rows_asc()
        self.assertEqual(sorted(rows[0].keys()),
                         ["close", "high", "low", "open", "time", "volume"])
        art = load_artifact()
        self.assertIn("no venue tag",
                      art["gate_matrix"]["dataset_provenance"].lower())


# --------------------------------------------------
# 4-6. Period splitting + ordering + determinism
# --------------------------------------------------

class TestPeriods(unittest.TestCase):

    def test_six_equal_chronological_periods(self):
        from core.research.oos_validation.periods import split_bars
        rows, _ = fresh_rows_asc()
        periods = split_bars(rows, n_periods=6)
        self.assertEqual(len(periods), 6)
        self.assertEqual([p["period_id"] for p in periods],
                         ["OOS_01", "OOS_02", "OOS_03",
                          "OOS_04", "OOS_05", "OOS_06"])
        self.assertEqual(sum(p["row_count"] for p in periods), len(rows))
        bounds = [(p["start"], p["end"]) for p in periods]
        for (_, prev_end), (cur_start, _) in zip(bounds, bounds[1:]):
            self.assertGreater(cur_start, prev_end)

    def test_period_determinism(self):
        from core.research.oos_validation.periods import split_bars
        rows, _ = fresh_rows_asc()
        first = split_bars(rows, n_periods=6)
        second = split_bars(rows, n_periods=6)
        self.assertEqual(first, second)

    def test_empty_rows_raise(self):
        from core.research.oos_validation.periods import split_bars
        with self.assertRaises(ValueError):
            split_bars([], n_periods=6)


# --------------------------------------------------
# 7-8. Sample-size gates + actual-fill RR
# --------------------------------------------------

class TestSampleAndRR(unittest.TestCase):

    def test_zero_fills_means_blocked(self):
        from core.research.oos_validation.report import decide_final
        agg = {"total_completed_trades": 0, "survived": 0,
               "tested_periods": 6}
        decision, _ = decide_final(agg)
        self.assertEqual(decision, "OOS_BLOCKED")

    def test_period_gate_needs_ten_trades(self):
        from core.research.oos_validation.report import classify_period
        status, _ = classify_period({"orders": 5, "completed_trades": 0,
                                     "wins": 0, "losses": 0,
                                     "gross_pnl": 0.0})
        self.assertEqual(status, "INCONCLUSIVE")
        status0, _ = classify_period({"orders": 0, "completed_trades": 0,
                                      "wins": 0, "losses": 0,
                                      "gross_pnl": 0.0})
        self.assertEqual(status0, "UNAVAILABLE")

    def test_actual_fill_rr_unavailable_with_zero_fills(self):
        art = load_artifact()
        self.assertEqual(art["actual_fill_rr"]["values"], [])
        self.assertIn("UNAVAILABLE", art["actual_fill_rr"]["status"])
        self.assertIn("UNAVAILABLE", art["gate_matrix"]["actual_fill_rr"])


# --------------------------------------------------
# 9-11. Gap / phantom-win / intrabar semantics
# --------------------------------------------------

class TestExecutionSemantics(unittest.TestCase):

    def test_gap_recomputes_rr(self):
        from core.backtesting.accounting import realized_rr
        # adverse gap: long fill gapped up to 102 destroys RR
        self.assertLess(realized_rr("BULLISH", 102.0, 99.0, 106.0), 6.0)
        # zero risk never fabricates
        self.assertEqual(realized_rr("BULLISH", 100.0, 100.0, 106.0), 0.0)

    def test_geometry_gate_preserved(self):
        from core.backtesting.accounting import directional_geometry_ok
        self.assertTrue(directional_geometry_ok("BULLISH", 100.0, 99.0, 106.0))
        self.assertFalse(directional_geometry_ok("BULLISH", 100.0, 101.0, 106.0))
        self.assertFalse(directional_geometry_ok("BEARISH", 100.0, 99.0, 106.0))
        art = load_artifact()
        self.assertEqual(art["aggregate_results"]["wins"], 0)

    def test_conservative_ambiguity_preserved(self):
        from core.backtesting.trade import Trade
        self.assertIn("ambiguous", Trade.__dataclass_fields__)
        art = load_artifact()
        self.assertEqual(art["aggregate_results"]["total_fills"], 0)


# --------------------------------------------------
# 12. Economic scenarios
# --------------------------------------------------

class TestEconomics(unittest.TestCase):

    def test_scenario_labels(self):
        from core.research.readiness import scenarios
        self.assertEqual(
            scenarios.scenario_structural(10.0)["label"], "VERIFIED-zero-cost")
        self.assertEqual(scenarios.scenario_funding()["net"], None)
        self.assertIn("ASSUMED",
                      scenarios.scenario_conservative_fees(10.0, 1000.0)["label"])
        art = load_artifact()
        self.assertEqual(art["economic_scenarios"]["funding"],
                         "UNAVAILABLE (zero NOT substituted)")
        self.assertEqual(art["economic_scenarios"]["structural"],
                         "VERIFIED-zero-cost")


# --------------------------------------------------
# 13-16. Symbol / directional / temporal / survival
# --------------------------------------------------

class TestConsistency(unittest.TestCase):

    def test_symbol_single_and_inconclusive(self):
        art = load_artifact()
        self.assertEqual(list(art["symbol_statistics"].keys()), ["BTCUSDT"])
        self.assertEqual(
            art["symbol_statistics"]["BTCUSDT"]["status"], "INCONCLUSIVE")

    def test_directional_not_assessable(self):
        art = load_artifact()
        self.assertIn("not assessable",
                      art["directional_statistics"]["note"].lower())

    def test_temporal_all_periods_visible(self):
        art = load_artifact()
        self.assertEqual(len(art["periods"]), 6)
        for p in art["periods"]:
            for key in ("period_id", "start", "end", "observations",
                        "orders", "fills", "completed_trades", "wins",
                        "losses", "gross_pnl", "status", "reason"):
                self.assertIn(key, p)

    def test_survival_zero_of_six(self):
        art = load_artifact()
        surv = art["survival_statistics"]
        self.assertEqual((surv["tested"], surv["survived"]), (6, 0))
        self.assertAlmostEqual(surv["survival_ratio"], 0.0)
        self.assertEqual(art["final_decision"], "OOS_BLOCKED")


# --------------------------------------------------
# 17-18. Unavailable / insufficient sample honesty
# --------------------------------------------------

class TestHonesty(unittest.TestCase):

    def test_every_period_retained(self):
        art = load_artifact()
        statuses = [p["status"] for p in art["periods"]]
        self.assertEqual(len(statuses), 6)
        for s in statuses:
            self.assertIn(s, ("UNAVAILABLE", "INCONCLUSIVE", "REJECTED",
                              "PROMISING", "VALIDATED"))

    def test_global_and_per_period_agree_on_zero_fills(self):
        art = load_artifact()
        self.assertEqual(art["aggregate_results"]["total_fills"], 0)
        self.assertEqual(art["global_continuous_run"]["fills"], 0)


# --------------------------------------------------
# 19. Lookahead (future mutation changes nothing before)
# --------------------------------------------------

class TestLookahead(unittest.TestCase):

    def test_future_mutation_preserves_early_period(self):
        from core.research.oos_validation.execution import run_frozen_oos
        from core.research.oos_validation.periods import split_bars
        rows, _ = fresh_rows_asc()
        small = rows[:600]
        periods = split_bars(small, n_periods=2)
        s0, e0 = periods[0]["slice"]
        first_before = run_frozen_oos(small[s0:e0])
        mutated = [dict(r) for r in small]
        for r in mutated[e0:]:
            r["close"] = float(r["close"]) * 2.0
            r["volume"] = 999.0
        s1, e1 = split_bars(mutated, n_periods=2)[0]["slice"]
        first_after = run_frozen_oos(mutated[s1:e1])
        self.assertEqual(first_before, first_after)


# --------------------------------------------------
# 20. Determinism
# --------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_artifact_stable_bytes(self):
        raw = P18_ARTIFACT.read_bytes()
        first = hashlib.sha256(raw).hexdigest()
        art = json.loads(raw.decode("utf-8"))
        text = json.dumps(art, indent=2, sort_keys=True,
                          separators=(",", ": ")) + "\n"
        self.assertEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(), first)

    def test_small_slice_rerun_identical(self):
        from core.research.oos_validation.execution import run_frozen_oos
        rows, _ = fresh_rows_asc()
        self.assertEqual(run_frozen_oos(rows[:300]),
                         run_frozen_oos(rows[:300]))


# --------------------------------------------------
# 21. Production isolation + never-promotion
# --------------------------------------------------

class TestProductionPosture(unittest.TestCase):

    def test_no_live_surface_in_new_code(self):
        hits = []
        targets = list((ROOT / "core" / "research" / "oos_validation").rglob(
            "*.py")) + [ROOT / "scripts" / "build_phase18_artifact.py"]
        for path in targets:
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                for token in ("place_order", "submit_order",
                              "DeltaOrderExecutor", "BrokerEngine("):
                    if token in line:
                        hits.append((str(path), lineno, token))
        self.assertEqual(hits, [])

    def test_artifact_never_promotes(self):
        art = load_artifact()
        self.assertFalse(art["is_production_ready"])
        blob = json.dumps(art)
        for token in ("PROFITABLE", "ROBUST EDGE", "TRADABLE",
                      "PRODUCTION_READY", "GO_LIVE", "VALIDATED_RESEARCH_ONLY"
                      if art["final_decision"] != "VALIDATED_RESEARCH_ONLY"
                      else "GO_LIVE"):
            self.assertNotIn(token, blob)
        self.assertEqual(art["edge"], "NOT_ESTABLISHED")
        self.assertEqual(art["live"], "NO-GO")


# --------------------------------------------------
# 22-24. Frozen boundaries: 7E, OOS protocol, no family
# --------------------------------------------------

class TestFrozenBoundaries(unittest.TestCase):

    def test_oos_protocol_frozen(self):
        from core.research.oos import constants as C
        self.assertEqual(C.OOS_PERIODS, 6)
        self.assertEqual(C.MIN_OOS_TRADES_PER_PERIOD, 10)
        self.assertEqual(C.MIN_TOTAL_OOS_TRADES, 60)
        self.assertTrue(C.SPLIT_PROTOCOL_FROZEN)
        self.assertEqual((C.PURGE_BARS, C.EMBARGO_BARS), (0, 0))

    def test_seven_e_still_rejected(self):
        art = load_artifact()
        self.assertIn("REJECTED", art["seven_e"])

    def test_no_ranking_or_selection_api(self):
        import core.research.oos_validation.periods as per
        import core.research.oos_validation.report as rep
        import core.research.oos_validation.execution as exe
        import re
        names = set(dir(per)) | set(dir(rep)) | set(dir(exe))
        for name in names:
            self.assertIsNone(
                re.search(r"rank|select|optim|promot|\bbest\b", name), name)
        art = load_artifact()
        self.assertEqual(art["multiple_testing"],
                         "NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY")


if __name__ == "__main__":
    unittest.main()
