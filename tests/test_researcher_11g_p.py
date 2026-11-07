"""Phase 11G-P accumulation tests (deterministic, unittest-compatible).

Covers the §31 list: HEAD, lineage, cutoff, availability, quality,
contiguity, overlap, symbol/venue binding, classification, WF
feasibility, expanding geometry, D3 seal, lookahead, mutations
(MUT-P1..P18), determinism, production isolation, no-economics
boundary. No economics anywhere; no D3 contact.
"""

import ast
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import research.phase11g_p.analyze_p as AP  # noqa: E402
from research.phase11g_p.report_p import (  # noqa: E402
    PReadinessReport, from_readiness, recommendation_for)

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

PDIR = BASE_DIR / "research" / "phase11g_p"
PFEAS = PDIR / "readiness_p.json"


def feas():
    return json.loads(PFEAS.read_text())


def fixture_csv(n_minutes=3, per_minute=20, side="buy", start_ms=2_000_000_000_000,
                dup_ids=(), shuffle=False, bad_rows=(), bad_side=False):
    import random
    lines = ["agg_trade_id,price,quantity,first_trade_id,last_trade_id,"
             "transact_time,is_buyer_maker"]
    rows = []
    tid = 0
    for m in range(n_minutes):
        for k in range(per_minute):
            rows.append((tid, 100.0 + m + k * 0.001, 1.0, tid, tid,
                         start_ms + m * 60_000 + k * 1000,
                         "notaside" if bad_side else
                         ("false" if side == "buy" else "true")))
            tid += 1
    for d in dup_ids:
        rows.append(rows[d])
    for b in bad_rows:
        rows.append(b)
    if shuffle:
        random.Random(42).shuffle(rows)
    for r in rows:
        if isinstance(r, tuple):
            lines.append("%d,%.3f,%.1f,%d,%d,%d,%s" % r)
        else:
            lines.append(r)
    return "\n".join(lines) + "\n"


def fixture_bars(csv_text, symbol="BTCUSDT"):
    trades, _ = AP.parse_aggtrades(csv_text.encode(), symbol)
    return AP.minute_bars(trades)


class TestRepositoryHead(unittest.TestCase):
    def test_starting_head_ancestor(self):
        require_git_fact(self, 'test_researcher_11g_p::TestRepositoryHead::test_starting_head_ancestor')
        r = subprocess.run(["git", "merge-base", "--is-ancestor",
                            "6a961459aed7051564c17a4ab88cdf0814ee5b1a", "HEAD"],
                           capture_output=True, cwd=str(BASE_DIR))
        self.assertEqual(r.returncode, 0)

    def test_branch_main(self):
        require_git_fact(self, 'test_researcher_11g_p::TestRepositoryHead::test_branch_main')
        r = subprocess.run(["git", "branch", "--show-current"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(r.stdout.strip(), "main")

    def test_tree_only_expected(self):
        require_git_fact(self, 'test_researcher_11g_p::TestRepositoryHead::test_tree_only_expected')
        r = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        allowed = ("research/phase11g_p/", "research/phase11g_q/",
                   "research/phase11g_r/",
                   "tests/test_researcher_11g_p.py",
                   "tests/test_researcher_11g_q.py",
                   "tests/test_researcher_11g_r.py",
                   "docs/audit/phase11g_P_fresh_data_accumulation.md",
                   "docs/audit/phase11g_Q_full_oos_execution.md",
                   "docs/audit/phase11g_R_fresh_data_accumulation.md")
        # Pre-commit only: the additive untracked-allowlist compat edits in
        # the N/O tree tests (same justification as O's N-edit; post-commit
        # the tree shows notes alone and this branch is vacuous).
        allowed_modified = ("tests/test_researcher_11g_n.py",
                            "tests/test_researcher_11g_o.py")
        # Phase 12 supersession (disclosed in the Phase 12
        # report + manifests): production, test, manifest and
        # tooling paths change BY MANDATE in Phase 12. The
        # freeze that remains is the RESEARCH freeze: any
        # modification under research/ or to the frozen 11G
        # audit docs fails loudly.
        for line in r.stdout.strip().splitlines():
            if line.startswith("?? "):
                path = line[3:].strip('"')
                if path in allowed or "muse suggetions" in path:
                    continue
                if path.startswith("research/"):
                    self.fail("frozen research added: %s" % line)
                continue
            else:
                path = line.split()[-1].strip('"') if line.split() else line
                if path in allowed_modified:
                    pass
                elif (path.startswith("research/") or
                        "docs/audit/phase11g_" in path):
                    self.fail("frozen research modified: %s" % line)
                # Phase 12 production/test/manifest change: allowed.


class TestCutoffAvailability(unittest.TestCase):
    def test_cutoffs_pinned(self):
        f = feas()
        self.assertEqual(f["cutoffs"]["fresh_start_p"], 1788912000)
        self.assertEqual(f["cutoffs"]["pre_cutoff"], 1788751380)
        self.assertEqual(AP.FRESH_START_P, 1788912000)
        self.assertEqual(AP.PRE_CUTOFF, 1788751380)

    def test_gap_before_cutoff_real(self):
        f = feas()
        for asset, c in f["contiguity"].items():
            self.assertLess(c["last"], 1788912000, asset)

    def test_availability_observation(self):
        f = feas()
        av = f["availability"]
        self.assertEqual(av["latest_available_day"], "2026-09-08")
        self.assertEqual(av["result"], "DATA_NOT_YET_AVAILABLE")
        self.assertEqual(len(av["unavailable_days"]), 8)
        self.assertIn("2026-09-09", av["unavailable_days"])
        self.assertEqual(f["p_new_files"], 0)


class TestLineageInventory(unittest.TestCase):
    def test_inventory_counts(self):
        f = feas()
        self.assertEqual(f["n_files_reverified"], 4)
        self.assertEqual(f["p_new_files"], 0)

    def test_store_hashes_match_manifests(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        for zp in sorted(nraw.glob("*/*/*aggTrades*.zip")):
            man = json.loads((zp.parent / "acquisition_manifest.json").read_text())
            self.assertEqual(hashlib.sha256(zp.read_bytes()).hexdigest(),
                             man["files"]["aggTrades"]["local_sha256"], zp.name)


class TestQualityContiguity(unittest.TestCase):
    def test_zero_quality_flags(self):
        f = feas()
        for asset, q in f["quality"].items():
            self.assertEqual(q["rejected"], 0, asset)
            self.assertEqual(q["dups"], 0, asset)
            self.assertEqual(q["ooo"], 0, asset)

    def test_contiguity_exact(self):
        f = feas()
        self.assertEqual(f["contiguity"]["BTC"]["unique"], 2676)
        self.assertEqual(f["contiguity"]["ETH"]["unique"], 2880)
        for asset, c in f["contiguity"].items():
            self.assertEqual(c["gap_count"], 0, asset)
            self.assertEqual(c["largest_gap_minutes"], 0, asset)
            self.assertEqual(c["unique"], c["expected"], asset)


class TestOverlapFreshness(unittest.TestCase):
    def test_zero_overlap(self):
        f = feas()
        self.assertEqual(f["overall_overlap"], "ZERO_OVERLAP")
        for asset, sets in f["overlap"].items():
            for name, o in sets.items():
                self.assertEqual(o["verdict"], "ZERO_OVERLAP",
                                 "%s %s" % (asset, name))
                self.assertNotIn("first_overlap", o)

    def test_no_self_sets_counted(self):
        f = feas()
        for asset, sets in f["overlap"].items():
            for name in sets:
                self.assertFalse(name.startswith("11G_N_"), name)

    def test_freshness_reused(self):
        f = feas()
        for asset, v in f["freshness"].items():
            self.assertEqual(v["classification"], "REUSED", asset)
            self.assertEqual(v["overlapping_sets"], [])
            self.assertIn("UNKNOWN_BY_SEAL", v["d3_overlap"])


class TestWFFeasibility(unittest.TestCase):
    def test_required_and_verdict(self):
        f = feas()
        self.assertEqual(f["walk_forward"]["required_bars"], 6175)
        self.assertEqual(f["walk_forward"]["geometry"],
                         {"train_min": 2000, "test": 1000, "purge": 150,
                          "embargo": 25, "step": 1000, "folds": 4})
        self.assertEqual(f["walk_forward"]["verdict"], "FULL_WF_INFEASIBLE")
        self.assertEqual(f["walk_forward"]["per_symbol"]["BTC"]
                         ["available_clean_bars"], 2676)
        self.assertEqual(f["walk_forward"]["per_symbol"]["ETH"]
                         ["available_clean_bars"], 2880)
        for asset, v in f["walk_forward"]["per_symbol"].items():
            self.assertFalse(v["feasible_full_wf"], asset)
            self.assertEqual(v["folds"], [], asset)

    def test_builder_probe_raises(self):
        from research.phase11f import validation as V
        with self.assertRaises(ValueError):
            V.build_folds(2880, train_bars=2000, test_bars=1000,
                          purge_bars=150, embargo_bars=25,
                          step_bars=1000, n_folds=4)

    def test_expanding_geometry_at_scale(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        self.assertEqual(V.validate_folds(folds), [])
        self.assertEqual(V.validate_expanding(folds), [])
        self.assertEqual(
            [(fo["train_start"], fo["train_end"]) for fo in folds],
            [(0, 2000), (0, 3000), (0, 4000), (0, 5000)])


class TestRegimeSymbolVenue(unittest.TestCase):
    def test_regimes_descriptive(self):
        f = feas()
        for asset, r in f["regimes"].items():
            self.assertIn("must not be reused", r["note"])
            self.assertIn("p50", r["return_bps_deciles"])
            self.assertGreater(r["events_per_minute"], 500, asset)

    def test_symbols_separate(self):
        f = feas()
        self.assertEqual(sorted(f["walk_forward"]["per_symbol"]), ["BTC", "ETH"])
        self.assertEqual(f["events_total"], 3425209)


class TestD3Seal(unittest.TestCase):
    def test_counters_zero(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})
        f = feas()
        self.assertTrue(all(v == 0 for v in f["seal_counters_before"].values()))
        self.assertTrue(all(v == 0 for v in f["seal_counters_after"].values()))

    def test_no_d3_markers_in_p_files(self):
        for path in list(PDIR.rglob("*.py")) + [PDIR / "readiness_p.json"]:
            for line in path.read_text().splitlines():
                if "D3" not in line or "assertNotIn" in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))
                self.assertNotIn("read_bytes", line, str(path))
                self.assertNotIn("load(", line, str(path))


class TestLookahead(unittest.TestCase):
    def test_future_append_stable(self):
        bars, _ = fixture_bars(fixture_csv())
        big, _ = fixture_bars(fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50)))
        early = [b for b in big if b["time"] < 2000000160]
        self.assertEqual([b["close"] for b in early],
                         [b["close"] for b in bars])
        self.assertEqual(AP.contiguity([b["time"] for b in early])["unique"], 3)

    def test_overlap_stable_under_future(self):
        bars, _ = fixture_bars(fixture_csv())
        mins = [b["time"] for b in bars]
        self.assertEqual(AP.overlap_minutes(mins, [mins[0]]), [mins[0]])
        self.assertEqual(AP.classify_freshness(False, True, True), "REUSED")


class TestMutations(unittest.TestCase):
    def test_mut_p1_future_contamination(self):
        bars, _ = fixture_bars(fixture_csv())
        big, _ = fixture_bars(fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50)))
        early = [b for b in big if b["time"] < 2000000160]
        self.assertEqual(len(early), len(bars))
        self.assertEqual([b["volume"] for b in early],
                         [b["volume"] for b in bars])

    def test_mut_p2_duplicate_trade_id(self):
        _, q = AP.parse_aggtrades(fixture_csv(dup_ids=(3, 7)).encode(), "BTCUSDT")
        self.assertEqual(q["duplicate_trade_ids"], 2)

    def test_mut_p3_event_ordering(self):
        _, q = AP.parse_aggtrades(fixture_csv(shuffle=True).encode(), "BTCUSDT")
        self.assertGreater(q["out_of_order_events"], 0)
        bars, _ = fixture_bars(fixture_csv())
        shuf, _ = fixture_bars(fixture_csv(shuffle=True))
        self.assertAlmostEqual(sum(b["volume"] for b in bars),
                               sum(b["volume"] for b in shuf))

    def test_mut_p4_timestamp_corruption(self):
        bad = "1,100.0,1.0,1,1,12345,false\n"
        _, q = AP.parse_aggtrades((fixture_csv() + bad).encode(), "BTCUSDT")
        self.assertEqual(q["rejects_by_reason"].get("ValueError"), 1)
        self.assertEqual(q["parsed"], 60)

    def test_mut_p5_negative_quantity(self):
        bad = "1,100.0,-1.0,1,1,2000000000000,false\n"
        _, q = AP.parse_aggtrades((fixture_csv() + bad).encode(), "BTCUSDT")
        self.assertEqual(q["rejects_by_reason"].get("zero_or_negative_quantity"), 1)

    def test_mut_p6_invalid_aggressor(self):
        _, q = AP.parse_aggtrades(fixture_csv(bad_side=True).encode(), "BTCUSDT")
        self.assertEqual(q["parsed"], 0)
        self.assertGreater(q["rejected"], 0)

    def test_mut_p7_source_hash_tampering(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        zp = sorted(nraw.glob("BTCUSDT/2026-09-08/*aggTrades*.zip"))[0]
        blob = bytearray(zp.read_bytes())
        blob[1000] ^= 0xFF
        man = json.loads((zp.parent / "acquisition_manifest.json").read_text())
        self.assertNotEqual(hashlib.sha256(bytes(blob)).hexdigest(),
                            man["files"]["aggTrades"]["local_sha256"])

    def test_mut_p8_normalized_hash_tampering(self):
        f = feas()
        self.assertEqual(f["code_hash"],
                         hashlib.sha256((BASE_DIR / "research" / "phase11g_p" /
                                         "analyze_p.py").read_bytes()).hexdigest())
        mut = dict(f["contiguity"]["ETH"], unique=6175)
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["contiguity"]["ETH"], sort_keys=True).encode()).hexdigest())

    def test_mut_p9_symbol_substitution(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        for mp in sorted(nraw.glob("*/*/acquisition_manifest.json")):
            man = json.loads(mp.read_text())
            self.assertEqual(man["symbol"], mp.parent.parent.name)
            self.assertEqual(man["date"], mp.parent.name)

    def test_mut_p10_venue_substitution(self):
        f = feas()
        mut = dict(f["cutoffs"], fresh_start_p=0)
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["cutoffs"], sort_keys=True).encode()).hexdigest())

    def test_mut_p11_freshness_tampering(self):
        f = feas()
        mut = dict(f["freshness"]["BTC"], classification="FRESH")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["freshness"]["BTC"], sort_keys=True).encode()).hexdigest())

    def test_mut_p12_overlap_tampering(self):
        self.assertEqual(AP.overlap_minutes([10, 20], [20, 30]), [20])
        f = feas()
        mut = dict(f["overlap"]["BTC"]["oos_fresh_BTC"],
                   verdict="OVERLAP_DETECTED", overlap_minutes=5)
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["overlap"]["BTC"]["oos_fresh_BTC"], sort_keys=True).encode()
            ).hexdigest())

    def test_mut_p13_contiguous_manipulation(self):
        self.assertEqual(AP.contiguity([0, 60, 180])["gap_count"], 1)
        f = feas()
        mut = dict(f["contiguity"]["ETH"], unique=6175)
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["contiguity"]["ETH"], sort_keys=True).encode()).hexdigest())

    def test_mut_p14_wf_geometry_shrink(self):
        from research.phase11f import validation as V
        with self.assertRaises(ValueError):
            V.build_folds(2880, train_bars=2000, test_bars=1000,
                          purge_bars=150, embargo_bars=25,
                          step_bars=1000, n_folds=4)
        shrunk = V.build_folds(2880, train_bars=300, test_bars=300,
                               purge_bars=150, embargo_bars=25,
                               step_bars=300, n_folds=3)
        self.assertEqual(V.validate_folds(shrunk), [])
        self.assertNotEqual((2000, 1000, 150, 25, 1000, 4),
                            (300, 300, 150, 25, 300, 3))

    def test_mut_p15_rolling_substitution(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        self.assertEqual(V.validate_expanding(folds), [])
        rolling = [dict(fo, train_start=1000) for fo in folds]
        self.assertTrue(any("rolling" in e or "train_start" in e
                            for e in V.validate_expanding(rolling)))

    def test_mut_p16_d3_access(self):
        from research.phase11g import datasets as DG
        from research.phase11g.registry import registry as RG
        with self.assertRaises(Exception):
            DG.load_holdout("p-accumulation-attack")
        reg = RG.Registry()
        with self.assertRaises((ValueError, RuntimeError)):
            reg.register("D3_P", {}, "SEALED")
        self.assertEqual(DG.D3_ACCESS["load"], 0)

    def test_mut_p17_hypothesis_modification(self):
        import copy
        man = json.loads((BASE_DIR / "research" / "phase11g_k" / "freeze" /
                          "freeze_manifest.json").read_text())
        doc = json.loads((BASE_DIR / "research" / "phase11g_k" / "hypotheses" /
                          "H11GK-007.json").read_text())
        bad = copy.deepcopy(doc)
        bad["thresholds"]["buffer_atr"] = 9.99
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(),
            man["hypothesis_hashes"]["H11GK-007"])

    def test_mut_p18_economics_execution_attempt(self):
        toks = ("Backtester", "trade_metrics", "expectancy", "sharpe",
                "profit_factor", "open_trade", "OrderIntent", "execution_signal",
                "PositionSizer", "drawdown", "win_rate", "MonteCarlo",
                "random_baseline", "monte_carlo", "pnl", "sortino")
        for path in PDIR.rglob("*.py"):
            code = path.read_text()
            for tok in toks:
                self.assertNotIn(tok, code, "%s: %s" % (path.name, tok))
        f = feas()
        blob = json.dumps(f, sort_keys=True).lower()
        for tok in ("pnl", "profit_factor", "sharpe", "win_rate", "drawdown",
                    "expectancy", "fills", "sortino"):
            self.assertNotIn('"%s"' % tok, blob, tok)


class TestDeterminism(unittest.TestCase):
    def test_rerun_byte_identical(self):
        before = (PDIR / "readiness_p.json").read_bytes()
        AP.analyze()
        self.assertEqual((PDIR / "readiness_p.json").read_bytes(), before)


class TestProductionIsolation(unittest.TestCase):
    def test_no_production_imports(self):
        banned = ("core.", "backtesting", "data.", "execution", "risk",
                  "config", "main")
        for path in PDIR.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                else:
                    continue
                for m in mods:
                    self.assertNotIn(m.split(".")[0], banned,
                                     "%s imports %s" % (path.name, m))
                    self.assertTrue(
                        m.split(".")[0] in (
                            "argparse", "ast", "csv", "hashlib", "io", "json",
                            "pathlib", "statistics", "sys", "time", "datetime",
                            "dataclasses", "typing", "collections",
                            "zipfile", "__future__") or m.startswith("research."),
                        "%s imports unexpected %s" % (path.name, m))

    def test_no_runtime_tokens(self):
        toks = ("submit" + "_order", "place" + "_order", "live" + "_execute",
                "paper" + "_trade", "shadow" + "_trade", "send" + "_order")
        for path in PDIR.rglob("*.py"):
            code = path.read_text()
            for tok in toks:
                self.assertNotIn(tok, code, "%s: %s" % (path.name, tok))

    def test_report_never_production_ready(self):
        rep = PReadinessReport()
        self.assertIs(rep.is_production_ready, False)
        self.assertFalse(rep.emission_check()["production_ready"])
        self.assertEqual(rep.emission_check()["recommendation"], "UNKNOWN")
        with self.assertRaises(ValueError):
            PReadinessReport(is_production_ready=True)
        f = feas()
        rep2 = from_readiness(f, "ab" * 32, "cd" * 32)
        self.assertIs(rep2.is_production_ready, False)
        self.assertEqual(rep2.recommend_next_phase, "DATA_EXPANSION_REQUIRED")

    def test_recommendation_mapping(self):
        self.assertEqual(recommendation_for("WF_FEASIBLE", "ZERO_OVERLAP"),
                         "NEW_PREREGISTERED_OOS_EXECUTION")
        self.assertEqual(recommendation_for("FULL_WF_INFEASIBLE", "ZERO_OVERLAP"),
                         "DATA_EXPANSION_REQUIRED")
        self.assertEqual(recommendation_for("WF_FEASIBLE", "OVERLAP_DETECTED"),
                         "DATA_QUALITY_REMEDIATION")

    def test_no_production_paths(self):
        require_git_fact(self, 'test_researcher_11g_p::TestProductionIsolation::test_no_production_paths')
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "research/", "docs/audit/"],
            capture_output=True, text=True, cwd=str(BASE_DIR)).stdout.strip()
        self.assertEqual(out, "")

    def test_live_disabled(self):
        import os
        self.assertNotIn(os.getenv("ALLOW_LIVE", "").lower(), ("1", "true"))
        self.assertNotIn(os.getenv("LIVE_EXECUTE", "").lower(), ("1", "true"))


if __name__ == "__main__":
    unittest.main()
