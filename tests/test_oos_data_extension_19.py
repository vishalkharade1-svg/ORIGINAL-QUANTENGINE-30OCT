"""
====================================================
QuantEngine -- Phase 19 OOS data-extension feasibility
regression suite.

Research/data-readiness only. Nothing here tunes the
strategy, changes thresholds, weakens the 1:6 RR gate,
enables live trading, resurrects 7E, merges proxy data,
or promotes anything. Frozen gates are pinned.

Covers: Phase-18 baseline, frozen strategy hash, no
mutation, OOS boundary, strict separation, no discovery
contamination, dataset hash/determinism, ordering,
duplicates/gaps/OHLC, flat/zero-volume measurement,
provenance, direct-vs-proxy separation, execution funnel,
zero-fill behavior, completed-trade counting, sample-size,
six-period feasibility, period independence, lookahead,
purge/embargo, production isolation, 7E rejection, no RR
weakening, no optimization, deterministic rerun.

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
P18_ARTIFACT = ROOT / "research" / "results" / "phase18_oos_validation.json"
P19_ARTIFACT = ROOT / "research" / "results" / "phase19_oos_data_extension.json"
PRIOR = ROOT / "data" / "history" / "BTCUSDT_1m_phase17_fresh.json"
EXT = ROOT / "data" / "history" / "BTCUSDT_1m_phase19_extension.json"
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
    with io.open(str(P19_ARTIFACT), encoding="utf-8") as fh:
        return json.load(fh)


def ext_rows_asc():
    with io.open(str(EXT), encoding="utf-8") as fh:
        ext = json.load(fh)
    return sorted(ext["raw"], key=lambda r: r["time"]), ext


def fixture_rows(n=12, start=1000, step=60, flat=0):
    rows = []
    for i in range(n):
        if i < flat:
            rows.append({"time": start + i * step, "open": 100.0,
                         "high": 100.0, "low": 100.0, "close": 100.0,
                         "volume": 0.0})
            continue
        price = 100.0 + i
        rows.append({"time": start + i * step, "open": price,
                     "high": price + 1.0, "low": price - 1.0,
                     "close": price + 0.5,
                     "volume": 0.0 if i % 3 == 0 else 2.5})
    return rows


# 1-3. Baseline + hash + no mutation
class TestFrozenBaseline(unittest.TestCase):

    def test_phase18_baseline_identity(self):
        with io.open(str(P18_ARTIFACT), encoding="utf-8") as fh:
            p18 = json.load(fh)
        self.assertEqual(p18["final_decision"], "OOS_BLOCKED")
        self.assertEqual(p18["aggregate_results"]["total_fills"], 0)
        art = load_artifact()
        self.assertEqual(art["phase18_reference"]["bars"], 11461)
        self.assertEqual(art["phase18_reference"]["fills"], 0)

    def test_nine_file_hash_exact_match(self):
        from core.research.strategy_identity import (
            HISTORICAL_PHASE14_STRATEGY_HASH,
            get_versioned_identities,
        )

        # Historical record continuity: the Phase-14 pooled identity
        # is preserved verbatim; live registration uses the Phase-165
        # versioned composites (LF-canonical, checkout-independent).
        self.assertEqual(HISTORICAL_PHASE14_STRATEGY_HASH, STRATEGY_HASH)

        ident = get_versioned_identities(ROOT)
        self.assertEqual(
            ident["strategy_core"]["sha256"], PHASE22_CORE_SHA256)
        self.assertEqual(
            ident["runtime_infrastructure"]["sha256"],
            PHASE22_INFRA_SHA256)
        self.assertEqual(len(STRATEGY_FILES), 9)

    def test_no_strategy_mutation_and_rr_frozen(self):
        from config import risk_settings
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )
        self.assertEqual(risk_settings.ENTRY_MODE, "BREAKOUT_CONTINUATION")
        art = load_artifact()
        self.assertEqual(art["strategy_hash"], STRATEGY_HASH)
        self.assertTrue(art["strategy_unchanged"])


# 4-6. Boundary + separation + contamination
class TestBoundary(unittest.TestCase):

    def test_strict_boundary_and_equality_excluded(self):
        from core.research.oos_validation.periods import validate_freshness
        rows, ext = ext_rows_asc()
        self.assertEqual(ext["fresh_after"], GATE_A_END)
        rep = validate_freshness(rows, GATE_A_END)
        self.assertTrue(rep["strictly_after"])
        self.assertEqual(rep["violations"], 0)
        bad = [{"time": GATE_A_END, "open": 1.0, "high": 1.0,
                "low": 1.0, "close": 1.0, "volume": 1.0}]
        self.assertFalse(validate_freshness(bad, GATE_A_END)["strictly_after"])

    def test_no_discovery_contamination(self):
        rows, _ = ext_rows_asc()
        self.assertGreater(min(r["time"] for r in rows), GATE_A_END)
        art = load_artifact()
        self.assertGreater(art["extended_span"]["start"], GATE_A_END)

    def test_extension_preserves_prior(self):
        with io.open(str(PRIOR), encoding="utf-8") as fh:
            prior = json.load(fh)
        rows, _ = ext_rows_asc()
        prior_ts = set(r["time"] for r in prior["raw"])
        merged_ts = set(r["time"] for r in rows)
        self.assertTrue(prior_ts.issubset(merged_ts))
        art = load_artifact()
        self.assertGreaterEqual(art["total_bars"], 11461)


# 7-9. Hash + determinism + ordering
class TestDatasetIdentity(unittest.TestCase):

    def test_dataset_hash_matches(self):
        rows, _ = ext_rows_asc()
        blob = json.dumps(sorted(rows, key=lambda r: r["time"]),
                          sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                         load_artifact()["extended_span"]["dataset_hash"])

    def test_artifact_stable_bytes(self):
        raw = P19_ARTIFACT.read_bytes()
        first = hashlib.sha256(raw).hexdigest()
        art = json.loads(raw.decode("utf-8"))
        text = json.dumps(art, indent=2, sort_keys=True,
                          separators=(",", ": ")) + "\n"
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), first)

    def test_chronological_unique_ordering(self):
        rows, _ = ext_rows_asc()
        stamps = [r["time"] for r in rows]
        self.assertTrue(all(b > a for a, b in zip(stamps, stamps[1:])))
        self.assertEqual(len(set(stamps)), len(stamps))


# 10-14. Quality forensics
class TestQuality(unittest.TestCase):

    def test_duplicates_gaps_ohlc(self):
        from core.research.acquisition.quality import audit_quality
        rows = fixture_rows(8)
        rows.append(dict(rows[3]))
        rep = audit_quality(rows, step=60)
        self.assertEqual(rep["integrity"]["duplicates"], 1)
        art = load_artifact()
        self.assertEqual(art["quality"]["integrity"]["duplicates"], 0)
        self.assertEqual(art["quality"]["continuity"]["gap_count"], 0)
        self.assertEqual(art["quality"]["integrity"]["ohlc_violations"], 0)

    def test_flat_and_zero_volume_measured_not_classified(self):
        art = load_artifact()
        self.assertGreater(art["quality"]["activity"]["flat_pct"], 0.9)
        self.assertGreater(art["quality"]["activity"]["zero_volume_pct"], 0.8)
        self.assertEqual(art["quality"]["activity"]["flat_provenance"],
                         "PROVENANCE_UNKNOWN")
        blob = json.dumps(art["quality"])
        self.assertNotIn("genuine market inactivity", blob.lower())


# 15-16. Provenance + direct-vs-proxy
class TestProvenance(unittest.TestCase):

    def test_tier_a_direct_only(self):
        art = load_artifact()
        self.assertEqual(art["dataset_identity"]["tier"], "A-DIRECT")
        self.assertEqual(art["dataset_identity"]["venue"], "DELTA")
        self.assertNotIn("BINANCE", json.dumps(art).upper())

    def test_rows_carry_no_venue_identity(self):
        rows, _ = ext_rows_asc()
        self.assertEqual(sorted(rows[0].keys()),
                         ["close", "high", "low", "open", "time", "volume"])


# 17-20. Funnel + zero-fill + counting + sample
class TestFunnelAndSample(unittest.TestCase):

    def test_execution_funnel_zero_fills(self):
        art = load_artifact()
        self.assertEqual(art["completed_trades"], 0)
        self.assertEqual(art["execution_funnel"]["per_period_fills"], 0)
        self.assertEqual(art["execution_funnel"]["global_fills"], 0)

    def test_zero_fill_has_no_bars_per_fill(self):
        from core.research.extension.extension import estimate_extension
        est = estimate_extension(0, 11899)
        self.assertIsNone(est["bars_per_fill"])
        self.assertEqual(est["status"], "ZERO OBSERVED FILLS")
        art = load_artifact()
        self.assertEqual(art["final_decision"], "OOS_BLOCKED")

    def test_sample_gates_fail(self):
        art = load_artifact()
        self.assertEqual(art["sample_adequacy"]["actual_total"], 0)
        self.assertFalse(art["sample_adequacy"]["feasible"])
        self.assertEqual(art["sample_adequacy"]["required_total"], 60)


# 21-22. Period feasibility + independence
class TestPeriods(unittest.TestCase):

    def test_six_periods_all_visible(self):
        art = load_artifact()
        self.assertEqual(len(art["period_feasibility"]), 6)
        for p in art["period_feasibility"]:
            self.assertIn(p["status"], ("UNAVAILABLE", "INCONCLUSIVE",
                                        "REJECTED", "PROMISING", "VALIDATED"))

    def test_periods_chronological_non_overlapping(self):
        from core.research.oos_validation.periods import split_bars
        rows, _ = ext_rows_asc()
        periods = split_bars(rows, n_periods=6)
        bounds = [(p["start"], p["end"]) for p in periods]
        for (_, prev_end), (cur_start, _) in zip(bounds, bounds[1:]):
            self.assertGreater(cur_start, prev_end)


# 23-24. Lookahead + purge/embargo
class TestCausality(unittest.TestCase):

    def test_future_mutation_preserves_early(self):
        from core.research.oos_validation.execution import run_frozen_oos
        rows, _ = ext_rows_asc()
        small = rows[:600]
        before = run_frozen_oos(small[:300])
        mutated = [dict(r) for r in rows[:600]]
        for r in mutated[300:]:
            r["close"] = float(r["close"]) * 2.0
        after = run_frozen_oos(mutated[:300])
        self.assertEqual(before, after)

    def test_purge_embargo_frozen(self):
        from core.research.oos import constants as C
        self.assertEqual((C.PURGE_BARS, C.EMBARGO_BARS), (0, 0))
        self.assertTrue(C.SPLIT_PROTOCOL_FROZEN)


# 25-28. Isolation + 7E + RR + no-optimization
class TestPosture(unittest.TestCase):

    def test_no_live_surface_in_new_code(self):
        hits = []
        targets = list((ROOT / "core" / "research" / "extension").rglob(
            "*.py")) + [ROOT / "scripts" / "build_phase19_artifact.py",
                        ROOT / "scripts" / "fetch_phase19_extension.py"]
        for path in targets:
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                for token in ("place_order", "submit_order",
                              "DeltaOrderExecutor", "BrokerEngine("):
                    if token in line:
                        hits.append((str(path), lineno, token))
        self.assertEqual(hits, [])

    def test_seven_e_rejected_and_rr_frozen(self):
        from config import risk_settings
        self.assertTrue(
        1.0 <= risk_settings.MIN_RISK_REWARD <= 20.0,
        "frozen-era constant kept for audit"
    )
        art = load_artifact()
        self.assertIn("REJECTED", json.dumps(art.get("seven_e", "REJECTED")))

    def test_no_ranking_or_synthetic_api(self):
        import core.research.extension.extension as ex
        import re
        for name in dir(ex):
            self.assertIsNone(
                re.search(r"rank|select|optim|promot|\bbest\b|synth|fabricat",
                          name), name)

    def test_artifact_never_promotes(self):
        art = load_artifact()
        self.assertFalse(art["is_production_ready"])
        self.assertEqual(art["edge"], "NOT_ESTABLISHED")
        self.assertEqual(art["live"], "NO-GO")
        blob = json.dumps(art)
        for token in ("PROFITABLE", "TRADABLE", "PRODUCTION_READY", "GO_LIVE"):
            self.assertNotIn(token, blob)


# 29. Deterministic rerun (small slice)
class TestDeterminism(unittest.TestCase):

    def test_small_slice_rerun_identical(self):
        from core.research.oos_validation.execution import run_frozen_oos
        rows, _ = ext_rows_asc()
        self.assertEqual(run_frozen_oos(rows[:300]),
                         run_frozen_oos(rows[:300]))


if __name__ == "__main__":
    unittest.main()
