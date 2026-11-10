"""
====================================================

QuantEngine

Phase 17 -- independent data acquisition & genuine OOS
feasibility regression suite.

Research/data-readiness only. Nothing here tunes the
strategy, changes thresholds, weakens the 1:6 RR gate,
enables live trading, resurrects 7E, or promotes
anything. Frozen gates are pinned (any change must
update these tests deliberately).

Covers: strategy identity (9-file hash), baseline
reproduction, provenance manifest determinism +
wall-clock exclusion, quality-audit math, sample-size
recalculation, period budgeting, OOS contamination
isolation, determinism, production isolation,
never-promotion, 7E rejection, no-new-hypothesis-family,
frozen OOS protocol + purge/embargo, fresh-data
discipline (strictly-after, readiness-checks-only).

Stdlib only. No network. Deterministic.
====================================================
"""

import hashlib
import io
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
P14_ARTIFACT = (ROOT / "research" / "results" /
                "phase14_executable_edge_forensics.json")
P17_ARTIFACT = (ROOT / "research" / "results" /
                "phase17_oos_feasibility.json")
FRESH = (ROOT / "data" / "history" /
         "BTCUSDT_1m_phase17_fresh.json")
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
    with io.open(str(P17_ARTIFACT), encoding="utf-8") as fh:
        return json.load(fh)


def manifest_kwargs(**over):
    base = {
        "venue": "DELTA",
        "market": "perpetual_futures",
        "instrument": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "acquisition_source": "Delta /v2/history/candles",
        "acquisition_method": "HistoricalLoader.candles_paginated",
        "requested_start": GATE_A_END,
        "requested_end": GATE_A_END + 600,
        "actual_start": GATE_A_END + 60,
        "actual_end": GATE_A_END + 600,
        "row_count": 10,
        "schema_version": "gate-a-raw-v1",
        "normalization_version": "none (venue rows verbatim)",
        "dataset_hash": "0" * 64,
        "acquisition_status": "COMPLETE",
    }
    base.update(over)
    return base


def fixture_rows(n=12, start=1000, step=60, flat=0):
    rows = []
    for i in range(n):
        if i < flat:
            price = 100.0
            rows.append({"time": start + i * step, "open": price,
                         "high": price, "low": price,
                         "close": price, "volume": 0.0})
            continue
        price = 100.0 + i
        rows.append({"time": start + i * step, "open": price,
                     "high": price + 1.0, "low": price - 1.0,
                     "close": price + 0.5, "volume": 0.0 if i % 3 == 0
                     else 2.5})
    return rows


# --------------------------------------------------
# 1. Strategy identity + baseline (frozen)
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

    def test_baseline_reproduced(self):
        with io.open(str(P14_ARTIFACT), encoding="utf-8") as fh:
            base = json.load(fh)["baseline_reproduction"]
        self.assertEqual(
            (base["orders"], base["fills"], base["wins"],
             base["losses"]), (25, 2, 0, 2))
        self.assertAlmostEqual(base["net"], -0.206452, places=6)
        art = load_artifact()
        self.assertEqual(art["strategy_hash"], STRATEGY_HASH)
        self.assertTrue(art["strategy_unchanged"])
        self.assertEqual(art["baseline_reference"], base)

    def test_rr_gate_still_frozen(self):
        from config import risk_settings
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )
        self.assertEqual(risk_settings.ENTRY_MODE,
                         "BREAKOUT_CONTINUATION")
        self.assertEqual(tuple(risk_settings.ACTIVE_ENTRY_MODES),
                         ("BREAKOUT_CONTINUATION",))


# --------------------------------------------------
# 2. Provenance manifest (§13)
# --------------------------------------------------

class TestProvenance(unittest.TestCase):

    def test_manifest_id_deterministic(self):
        from core.research.acquisition.provenance import (
            ProvenanceManifest)
        first = ProvenanceManifest(**manifest_kwargs()).manifest_id()
        second = ProvenanceManifest(**manifest_kwargs()).manifest_id()
        self.assertEqual(len(first), 64)
        self.assertEqual(first, second)

    def test_wall_clock_excluded_from_id(self):
        from core.research.acquisition.provenance import (
            ProvenanceManifest)
        early = ProvenanceManifest(
            **manifest_kwargs(fetched_at="2026-09-13T00:00:00Z"))
        late = ProvenanceManifest(
            **manifest_kwargs(fetched_at="2027-01-01T00:00:00Z"))
        self.assertEqual(early.manifest_id(), late.manifest_id())
        self.assertNotIn("fetched_at", early.canonical_dict())

    def test_closed_status_vocabulary(self):
        from core.research.acquisition.provenance import (
            ProvenanceManifest)
        for status in ("COMPLETE", "PARTIAL", "EMPTY", "BLOCKED"):
            m = ProvenanceManifest(**manifest_kwargs(
                acquisition_status=status))
            self.assertEqual(m.acquisition_status, status)
        with self.assertRaises(ValueError):
            ProvenanceManifest(**manifest_kwargs(
                acquisition_status="SUCCESS"))

    def test_manifest_rejects_bad_rows(self):
        from core.research.acquisition.provenance import (
            ProvenanceManifest, manifest_id)
        with self.assertRaises(ValueError):
            ProvenanceManifest(**manifest_kwargs(row_count=-1))
        with self.assertRaises(ValueError):
            manifest_id({"venue": "DELTA"})
        with self.assertRaises(ValueError):
            manifest_id(dict(
                ProvenanceManifest(
                    **manifest_kwargs()).canonical_dict(),
                fetched_at="sneaky"))


# --------------------------------------------------
# 3. Quality audit math
# --------------------------------------------------

class TestQualityAudit(unittest.TestCase):

    def test_clean_series_scores_full(self):
        from core.research.acquisition.quality import audit_quality
        rep = audit_quality(fixture_rows(12), step=60, requested=12)
        self.assertEqual(rep["coverage"]["coverage_pct"], 1.0)
        self.assertTrue(rep["coverage"]["actual_intervals"], 12)
        self.assertEqual(rep["integrity"]["duplicates"], 0)
        self.assertTrue(rep["integrity"]["monotonic"])
        self.assertEqual(rep["integrity"]["ohlc_violations"], 0)
        self.assertEqual(rep["integrity"]["malformed_rows"], 0)
        self.assertEqual(rep["continuity"]["gap_count"], 0)

    def test_duplicates_gaps_violations_counted(self):
        from core.research.acquisition.quality import audit_quality
        rows = fixture_rows(8)
        rows.append(dict(rows[3]))
        top = max(r["time"] for r in rows)
        rows.append({"time": top + 180,
                     "open": 1.0, "high": 0.5, "low": 2.0,
                     "close": 1.0, "volume": 1.0})
        rows.append({"time": rows[-1]["time"] + 60, "open": 1.0})
        rep = audit_quality(rows, step=60)
        self.assertEqual(rep["integrity"]["duplicates"], 1)
        self.assertEqual(rep["continuity"]["gap_count"], 1)
        self.assertEqual(rep["continuity"]["max_gap_bars"], 2)
        self.assertEqual(rep["integrity"]["ohlc_violations"], 1)
        self.assertEqual(rep["integrity"]["malformed_rows"], 1)

    def test_flat_bars_counted_never_classified(self):
        from core.research.acquisition.quality import audit_quality
        rep = audit_quality(fixture_rows(10, flat=10), step=60)
        self.assertEqual(rep["activity"]["flat_bars"], 10)
        self.assertEqual(rep["activity"]["flat_provenance"],
                         "PROVENANCE_UNKNOWN")
        blob = json.dumps(rep)
        self.assertNotIn("bad data", blob.lower())
        self.assertNotIn("genuine market inactivity", blob.lower())


# --------------------------------------------------
# 4. Sample-size recalculation (§23)
# --------------------------------------------------

class TestSampleRequirements(unittest.TestCase):

    def test_measured_rates_give_25k_per_period(self):
        from core.research.acquisition.feasibility import (
            recalculate_requirements)
        req = recalculate_requirements(0.005, 0.08)
        self.assertAlmostEqual(req["per_period_bars"], 25000.0)
        self.assertAlmostEqual(req["oos_span_bars"], 150000.0)
        self.assertAlmostEqual(req["total_span_bars"], 300000.0)
        self.assertAlmostEqual(req["expected_fills_per_period"], 10.0)
        self.assertIn("lower bound", req["realistic_requirement"])

    def test_zero_rates_raise(self):
        from core.research.acquisition.feasibility import (
            recalculate_requirements)
        with self.assertRaises(ValueError):
            recalculate_requirements(0.0, 0.08)
        with self.assertRaises(ValueError):
            recalculate_requirements(0.005, 0.0)

    def test_period_budget_gates(self):
        from core.research.acquisition.feasibility import budget_periods
        short = budget_periods(11461.0, 25000.0)
        self.assertEqual(short["adequate_periods"], 0)
        self.assertEqual(short["verdict"], "OOS_BLOCKED")
        full = budget_periods(150000.0, 25000.0)
        self.assertEqual(full["adequate_periods"], 6)
        self.assertEqual(full["verdict"], "OOS_FEASIBLE")
        with self.assertRaises(ValueError):
            budget_periods(100.0, 0.0)


# --------------------------------------------------
# 5. Fresh-data discipline (§10/§14/§21)
# --------------------------------------------------

class TestFreshDataDiscipline(unittest.TestCase):

    def test_fresh_cache_strictly_after_gate_a(self):
        with io.open(str(FRESH), encoding="utf-8") as fh:
            fresh = json.load(fh)
        self.assertEqual(fresh["fresh_after"], GATE_A_END)
        stamps = [r["time"] for r in fresh["raw"]]
        self.assertTrue(stamps)
        self.assertGreater(min(stamps), GATE_A_END)
        self.assertEqual(len(set(stamps)), len(stamps))

    def test_rows_carry_no_venue_identity(self):
        with io.open(str(FRESH), encoding="utf-8") as fh:
            row = json.load(fh)["raw"][0]
        self.assertEqual(sorted(row.keys()),
                         ["close", "high", "low", "open", "time",
                          "volume"])
        art = load_artifact()
        self.assertIn("no venue tag",
                      art["gate_matrix"]["venue_provenance"])

    def test_readiness_checks_only_no_trade_evidence(self):
        with io.open(str(FRESH), encoding="utf-8") as fh:
            blob = fh.read()
        for token in ("\"fills\"", "\"trades\"", "\"pnl\"",
                      "\"fill_rate\""):
            self.assertNotIn(token, blob)
        art = load_artifact()
        self.assertEqual(art["final_decision"], "OOS_BLOCKED")


# --------------------------------------------------
# 6. OOS contamination isolation (§32)
# --------------------------------------------------

class TestContaminationIsolation(unittest.TestCase):

    def test_post_boundary_mutation_changes_nothing_before(self):
        from core.research.acquisition.quality import audit_quality
        rows = fixture_rows(20, start=2000)
        boundary = rows[12]["time"]
        before = [r for r in rows if r["time"] < boundary]

        def snapshot(series):
            rep = audit_quality(
                [r for r in series if r["time"] < boundary])
            return json.dumps(rep, sort_keys=True)

        first = snapshot(rows)
        mutated = [dict(r) for r in rows]
        for r in mutated:
            if r["time"] >= boundary:
                r["close"] = r["close"] * 2.0
                r["volume"] = 999.0
        self.assertEqual(snapshot(mutated), first)
        self.assertEqual(
            len([r for r in mutated if r["time"] < boundary]),
            len(before))


# --------------------------------------------------
# 7. Determinism (§34)
# --------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_artifact_stable_bytes(self):
        raw = P17_ARTIFACT.read_bytes()
        first = hashlib.sha256(raw).hexdigest()
        art = json.loads(raw.decode("utf-8"))
        text = json.dumps(art, indent=2, sort_keys=True,
                          separators=(",", ": ")) + "\n"
        self.assertEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(), first)

    def test_manifest_and_budget_stable(self):
        from core.research.acquisition.feasibility import (
            budget_periods)
        from core.research.acquisition.provenance import (
            ProvenanceManifest)
        art = load_artifact()
        self.assertEqual(
            ProvenanceManifest(
                **manifest_kwargs()).manifest_id(),
            ProvenanceManifest(
                **manifest_kwargs()).manifest_id())
        self.assertEqual(
            budget_periods(11461.0, 25000.0),
            budget_periods(11461.0, 25000.0))
        self.assertEqual(art["manifest_id"],
                         art["provenance"] and
                         __import__(
                             "core.research.acquisition.provenance",
                             fromlist=["manifest_id"]).manifest_id(
                                 art["provenance"]))


# --------------------------------------------------
# 8. Production isolation (§35) + never-promotion
# --------------------------------------------------

class TestProductionPosture(unittest.TestCase):

    def test_no_live_surface_in_new_code(self):
        hits = []
        targets = list((ROOT / "core" / "research" / "acquisition").rglob(
            "*.py")) + [ROOT / "scripts" / "fetch_phase17_fresh.py",
                        ROOT / "scripts" / "build_phase17_artifact.py"]
        for path in targets:
            lines = path.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, start=1):
                window = "\n".join(
                    lines[max(0, lineno - 21):lineno + 20])
                if "FORBIDDEN" in window:
                    continue
                for token in ("place_order", "submit_order",
                              "DeltaOrderExecutor", "BrokerEngine("):
                    if token in line:
                        hits.append((str(path), lineno, token))
        self.assertEqual(hits, [])

    def test_new_code_imports_no_strategy_or_execution(self):
        import re
        for path in (ROOT / "core" / "research" / "acquisition").rglob(
                "*.py"):
            text = path.read_text(encoding="utf-8")
            for token in ("trade_setup_builder", "decision_engine",
                          "risk_engine", "execution_engine",
                          "backtester", "paper_trading"):
                self.assertNotIn(token, text, path.name)

    def test_artifact_never_promotes(self):
        art = load_artifact()
        self.assertFalse(art["is_production_ready"])
        self.assertFalse(art["production_isolation"] != "PASS")
        blob = json.dumps(art)
        for token in ("PROFITABLE", "ROBUST EDGE", "TRADABLE",
                      "PRODUCTION_READY", "GO_LIVE", "VALIDATED"):
            self.assertNotIn(token, blob)
        self.assertEqual(art["edge"], "NOT_ESTABLISHED")
        self.assertEqual(art["live"], "NO-GO")

    def test_safe_defaults_still_deny_live(self):
        from config.settings import Settings
        fresh = Settings()
        self.assertTrue(fresh.PAPER_MODE)
        self.assertFalse(fresh.LIVE_MODE)
        self.assertFalse(fresh.ALLOW_LIVE)
        self.assertFalse(fresh.LIVE_EXECUTE)


# --------------------------------------------------
# 9. Frozen OOS protocol + 7E + no-new-family (§21/§28/§29)
# --------------------------------------------------

class TestFrozenBoundaries(unittest.TestCase):

    def test_oos_protocol_frozen(self):
        from core.research.oos import constants as C
        self.assertEqual(C.OOS_PERIODS, 6)
        self.assertEqual(C.MIN_OOS_TRADES_PER_PERIOD, 10)
        self.assertEqual(C.MIN_TOTAL_OOS_TRADES, 60)
        self.assertEqual(C.MIN_SURVIVING_PERIODS, 5)
        self.assertTrue(C.SPLIT_PROTOCOL_FROZEN)
        self.assertEqual((C.PURGE_BARS, C.EMBARGO_BARS), (0, 0))
        art = load_artifact()
        self.assertIn("6-period protocol", art["gate_matrix"][
            "oos_infrastructure"])

    def test_seven_e_still_rejected(self):
        art = load_artifact()
        self.assertIn("REJECTED", art["seven_e"])
        self.assertNotIn("directional branch", json.dumps(
            art["gate_matrix"]).lower().replace(
                "no directional branch", ""))

    def test_no_ranking_or_selection_api(self):
        import core.research.acquisition.feasibility as feas
        import core.research.acquisition.provenance as prov
        import core.research.acquisition.quality as qual
        import re
        names = set(dir(feas)) | set(dir(prov)) | set(dir(qual))
        for name in names:
            self.assertIsNone(
                re.search(r"rank|select|optim|promot|\bbest\b",
                          name),
                name)

    def test_familywise_guards_preserved(self):
        from core.research.conditional_ml import (
            familywise_alpha, holm_survives)
        self.assertLess(familywise_alpha(0.05, 10), 0.05)
        self.assertTrue(callable(holm_survives))
        art = load_artifact()
        self.assertEqual(
            art["multiple_testing"],
            "NO_NEW_CONFIRMATORY_HYPOTHESIS_FAMILY")


if __name__ == "__main__":
    unittest.main()
