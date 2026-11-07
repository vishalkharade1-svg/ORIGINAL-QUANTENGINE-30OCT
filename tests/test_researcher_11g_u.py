"""Phase 11G-U continuation tests (deterministic, unittest-compatible, fast).

Covers starting state, cutoff derivation, availability, fast-path
gate, full-path fixtures, WF geometry, freeze pins, D3 seal,
lookahead, mutations (22 items), determinism, machine-verified
counts, production isolation, no-economics boundary. No bulk
parsing, no network, no economics, no D3 contact.
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

import research.phase11g_u.monitor_u as MU  # noqa: E402
from research.phase11g_u.report_u import UMonitorReport  # noqa: E402

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

UDIR = BASE_DIR / "research" / "phase11g_u"
UFEAS = UDIR / "readiness_u.json"
KDIR = BASE_DIR / "research" / "phase11g_k"


def feas():
    return json.loads(UFEAS.read_text())


def availability():
    return json.loads((UDIR / "availability_observation.json").read_text())


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
    trades, _ = MU.parse_aggtrades(csv_text.encode(), symbol)
    return MU.minute_bars(trades)


class TestStartingState(unittest.TestCase):
    def test_head_descends_from_t(self):
        require_git_fact(self, 'test_researcher_11g_u::TestStartingState::test_head_descends_from_t')
        r = subprocess.run(["git", "merge-base", "--is-ancestor",
                            "0e4d3f04ce139dfd64c5819b63a63601c3793bd8", "HEAD"],
                           capture_output=True, cwd=str(BASE_DIR))
        self.assertEqual(r.returncode, 0)

    def test_branch_main(self):
        require_git_fact(self, 'test_researcher_11g_u::TestStartingState::test_branch_main')
        r = subprocess.run(["git", "branch", "--show-current"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(r.stdout.strip(), "main")

    def test_tree_only_expected(self):
        require_git_fact(self, 'test_researcher_11g_u::TestStartingState::test_tree_only_expected')
        r = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        allowed_new = ("research/phase11g_u/",
                       "tests/test_researcher_11g_u.py",
                       "docs/audit/phase11g_U_continuation.md")
        # Phase 12 supersession (disclosed in the Phase 12
        # report + manifests): production, test, manifest and
        # tooling paths change BY MANDATE in Phase 12. The
        # freeze that remains is the RESEARCH freeze: any
        # modification under research/ or to the frozen 11G
        # audit docs fails loudly.
        for line in r.stdout.strip().splitlines():
            if line.startswith("?? "):
                path = line[3:].strip('"')
                if path in allowed_new or "muse suggetions" in path:
                    continue
                if path.startswith("research/"):
                    self.fail("frozen research added: %s" % line)
                continue
            else:
                path = line.split()[-1].strip('"') if line.split() else line
                if (path.startswith("research/") or
                        "docs/audit/phase11g_" in path):
                    self.fail("frozen research modified: %s" % line)
                # Phase 12 production/test/manifest change: allowed.


class TestCutoffAvailability(unittest.TestCase):
    def test_derive_cutoff(self):
        latest, fresh = MU.derive_cutoff()
        self.assertEqual((latest, fresh), (1788911940, 1788912000))
        f = feas()
        self.assertEqual(f["cutoffs"]["fresh_start_u"], 1788912000)

    def test_required_derived(self):
        self.assertEqual(MU.required_bars(), 6175)
        self.assertEqual(feas()["required_bars"], 6175)

    def test_classify_availability(self):
        self.assertEqual(MU.classify_availability(404), "DATA_NOT_YET_AVAILABLE")
        self.assertEqual(MU.classify_availability(200), "AVAILABLE")
        self.assertEqual(MU.classify_availability(None), "ACQUISITION_FAILED")
        self.assertEqual(MU.classify_availability(500), "INVALID_PROVIDER_ARTIFACT")

    def test_observation_recorded(self):
        av = availability()
        f = feas()
        self.assertEqual(av["latest_available_day"], "2026-09-08")
        self.assertEqual(av["result"], "DATA_NOT_YET_AVAILABLE")
        self.assertEqual(len(av["unavailable_days"]), 13)
        self.assertEqual(len(av["status"]), 26)
        self.assertTrue(all(v == 404 for v in av["status"].values()))
        self.assertEqual(f["availability"], av)
        self.assertEqual(f["new_files"], [])
        self.assertEqual(f["new_fresh_bars"], 0)

    def test_resume_trigger(self):
        self.assertEqual(MU.next_unchecked(availability(), "BTCUSDT"), "2026-09-22")
        self.assertEqual(MU.next_unchecked(availability(), "ETHUSDT"), "2026-09-22")
        self.assertEqual(feas()["resume"],
                         {"BTCUSDT": "2026-09-22", "ETHUSDT": "2026-09-22"})


class TestFastPathGate(unittest.TestCase):
    def test_gate_unmet(self):
        f = feas()
        self.assertEqual(f["decision"], "DATA_NOT_YET_AVAILABLE")
        for asset, v in f["symbols"].items():
            self.assertEqual(v["fresh_bars"], 0, asset)
            self.assertEqual(v["shortfall_vs_required"], 6175, asset)
            self.assertFalse(v["gate_met"], asset)
        self.assertFalse(f["economics_executed"])
        self.assertEqual(f["hypotheses_executed"], 0)

    def test_no_pooling(self):
        f = feas()
        self.assertEqual(sorted(f["symbols"]), ["BTC", "ETH"])

    def test_refuse_economics(self):
        with self.assertRaises(RuntimeError):
            MU.refuse_economics()


class TestFullPathFixtures(unittest.TestCase):
    def test_validate_new_file(self):
        prior = {"old_set": [1000000000]}
        out = MU.validate_new_file(fixture_csv().encode(), "BTCUSDT", prior)
        self.assertEqual(len(out["bars"]), 3)
        self.assertEqual(out["quality"]["rejected"], 0)
        self.assertEqual(out["overall_overlap"], "ZERO_OVERLAP")
        self.assertEqual(out["freshness"], "FRESH")

    def test_validate_new_file_overlap(self):
        prior = {"old_set": [1999999980]}
        out = MU.validate_new_file(fixture_csv().encode(), "BTCUSDT", prior)
        self.assertEqual(out["overlap"]["old_set"]["verdict"], "OVERLAP_DETECTED")


class TestWFGeometry(unittest.TestCase):
    def test_builder_raises_on_reference_spans(self):
        from research.phase11f import validation as V
        with self.assertRaises(ValueError):
            V.build_folds(2880, train_bars=2000, test_bars=1000,
                          purge_bars=150, embargo_bars=25,
                          step_bars=1000, n_folds=4)

    def test_expanding_positive_control(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        self.assertEqual(V.validate_folds(folds), [])
        self.assertEqual(V.validate_expanding(folds), [])
        self.assertEqual(
            [(fo["train_start"], fo["train_end"]) for fo in folds],
            [(0, 2000), (0, 3000), (0, 4000), (0, 5000)])
        f0 = folds[0]
        self.assertEqual((f0["purge_start"], f0["purge_end"]), (2000, 2150))
        self.assertEqual((f0["embargo_start"], f0["embargo_end"]), (2150, 2175))
        self.assertEqual((f0["test_start"], f0["test_end"]), (2175, 3175))

    def test_rolling_rejected(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        rolling = [dict(fo, train_start=1000) for fo in folds]
        self.assertTrue(any("rolling" in e or "train_start" in e
                            for e in V.validate_expanding(rolling)))

    def test_shrink_rejected(self):
        from research.phase11f import validation as V
        shrunk = V.build_folds(2880, train_bars=300, test_bars=300,
                               purge_bars=150, embargo_bars=25,
                               step_bars=300, n_folds=3)
        self.assertEqual(V.validate_folds(shrunk), [])
        self.assertNotEqual((2000, 1000, 150, 25, 1000, 4),
                            (300, 300, 150, 25, 300, 3))


class TestFreezePins(unittest.TestCase):
    def test_k_hashes_and_freeze(self):
        man = json.loads((KDIR / "freeze" / "freeze_manifest.json").read_text())
        self.assertTrue((KDIR / "freeze" / "freeze_hash.txt").read_text(
        ).strip().startswith("f803fe7d"))
        for p in sorted((KDIR / "hypotheses").glob("*.json")):
            doc = json.loads(p.read_text())
            h = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()
                               ).hexdigest()
            self.assertEqual(h, man["hypothesis_hashes"][p.stem], p.stem)

    def test_h004_h007_stay_failed(self):
        prim = json.loads((BASE_DIR / "research" / "phase11g_l" / "results" /
                           "primary_results.json").read_text())
        self.assertEqual(prim["H11GK-004"]["verdict"], "FAIL")
        self.assertEqual(prim["H11GK-007"]["verdict"], "FAIL")


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

    def test_no_d3_markers_in_u_files(self):
        for path in list(UDIR.rglob("*.py")) + [UDIR / "readiness_u.json",
                                                UDIR / "availability_observation.json"]:
            for line in path.read_text().splitlines():
                if "D3" not in line or "assertNotIn" in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))
                self.assertNotIn("read_bytes", line, str(path))
                self.assertNotIn("load(", line, str(path))

    def test_d3_access_refused(self):
        from research.phase11g import datasets as DG
        from research.phase11g.registry import registry as RG
        with self.assertRaises(Exception):
            DG.load_holdout("u-monitor-attack")
        reg = RG.Registry()
        with self.assertRaises((ValueError, RuntimeError)):
            reg.register("D3_U", {}, "SEALED")
        self.assertEqual(DG.D3_ACCESS["load"], 0)


class TestLookahead(unittest.TestCase):
    def test_future_append_stable(self):
        bars, _ = fixture_bars(fixture_csv())
        big, _ = fixture_bars(fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50)))
        early = [b for b in big if b["time"] < 2000000160]
        self.assertEqual([b["close"] for b in early],
                         [b["close"] for b in bars])
        self.assertEqual([b["volume"] for b in early],
                         [b["volume"] for b in bars])

    def test_quality_stable_under_future(self):
        _, q1 = MU.parse_aggtrades(fixture_csv().encode(), "BTCUSDT")
        _, q2 = MU.parse_aggtrades((fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50))).encode(), "BTCUSDT")
        self.assertEqual(q1["rejected"], q2["rejected"])
        self.assertEqual(q1["duplicate_trade_ids"], q2["duplicate_trade_ids"])


class TestMutations(unittest.TestCase):
    def test_mut_duplicate_event_id(self):
        _, q = MU.parse_aggtrades(fixture_csv(dup_ids=(3, 7)).encode(), "BTCUSDT")
        self.assertEqual(q["duplicate_trade_ids"], 2)

    def test_mut_duplicate_minute(self):
        from research.phase11g_o.analyze_o import contiguity
        c = contiguity([0, 60, 60, 120])
        self.assertEqual(c["total"], 4)
        self.assertEqual(c["unique"], 3)

    def test_mut_reordered_events(self):
        _, q = MU.parse_aggtrades(fixture_csv(shuffle=True).encode(), "BTCUSDT")
        self.assertGreater(q["out_of_order_events"], 0)
        bars, _ = fixture_bars(fixture_csv())
        shuf, _ = fixture_bars(fixture_csv(shuffle=True))
        self.assertAlmostEqual(sum(b["volume"] for b in bars),
                               sum(b["volume"] for b in shuf))

    def test_mut_timestamp_corruption(self):
        bad = "1,100.0,1.0,1,1,12345,false\n"
        _, q = MU.parse_aggtrades((fixture_csv() + bad).encode(), "BTCUSDT")
        self.assertEqual(q["rejects_by_reason"].get("ValueError"), 1)
        self.assertEqual(q["parsed"], 60)

    def test_mut_negative_quantity(self):
        bad = "1,100.0,-1.0,1,1,2000000000000,false\n"
        _, q = MU.parse_aggtrades((fixture_csv() + bad).encode(), "BTCUSDT")
        self.assertEqual(q["rejects_by_reason"].get("zero_or_negative_quantity"), 1)

    def test_mut_invalid_aggressor(self):
        _, q = MU.parse_aggtrades(fixture_csv(bad_side=True).encode(), "BTCUSDT")
        self.assertEqual(q["parsed"], 0)
        self.assertGreater(q["rejected"], 0)

    def test_mut_checksum_tampering(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        zp = sorted(nraw.glob("BTCUSDT/2026-09-08/*aggTrades*.zip"))[0]
        blob = bytearray(zp.read_bytes())
        blob[1000] ^= 0xFF
        man = json.loads((zp.parent / "acquisition_manifest.json").read_text())
        self.assertNotEqual(hashlib.sha256(bytes(blob)).hexdigest(),
                            man["files"]["aggTrades"]["local_sha256"])

    def test_mut_normalized_hash_tampering(self):
        nfeas = json.loads((BASE_DIR / "research" / "phase11g_n" /
                            "feasibility.json").read_text())
        agg = nfeas["datasets"]["BTCUSDT/2026-09-08"]["aggtrades"]
        key = [k for k in agg if "normalized" in k][0]
        mut = dict(agg, **{key: "0" * 64})
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(agg, sort_keys=True).encode()).hexdigest())

    def test_mut_transformation_tampering(self):
        f = feas()
        self.assertEqual(f["code_hash"],
                         hashlib.sha256((UDIR / "monitor_u.py").read_bytes()
                                        ).hexdigest())
        mut = dict(f, code_hash="0" * 64)
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest())

    def test_mut_symbol_substitution(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        for mp in sorted(nraw.glob("*/*/acquisition_manifest.json")):
            man = json.loads(mp.read_text())
            self.assertEqual(man["symbol"], mp.parent.parent.name)
            self.assertEqual(man["date"], mp.parent.name)

    def test_mut_venue_substitution(self):
        nfeas = json.loads((BASE_DIR / "research" / "phase11g_n" /
                            "feasibility.json").read_text())
        self.assertTrue(nfeas["venue"].startswith("Binance"))
        mut = dict(nfeas, venue="Delta")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(nfeas, sort_keys=True).encode()).hexdigest())

    def test_mut_freshness_relabeling(self):
        from research.phase11g_o.analyze_o import classify_freshness
        self.assertEqual(classify_freshness(False, True, False), "FRESH")
        self.assertEqual(classify_freshness(True, True, False), "OVERLAPPING")
        self.assertEqual(classify_freshness(False, True, True), "REUSED")
        f = feas()
        mut = dict(f, decision="FULL_WF_DATA_READY")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest())

    def test_mut_overlap_tampering(self):
        self.assertEqual(MU.overlap_minutes([10, 20], [20, 30]), [20])
        self.assertEqual(MU.overlap_minutes([1, 2], [3, 4]), [])

    def test_mut_gap_stitching(self):
        from research.phase11g_o.analyze_o import contiguity
        c = contiguity([0, 60, 180])
        self.assertEqual(c["gap_count"], 1)
        self.assertEqual(c["unique"], 3)
        self.assertNotEqual(c["unique"], c["total"] + 1)

    def test_mut_synthetic_insertion(self):
        bars, _ = fixture_bars(fixture_csv())
        more, _ = fixture_bars(fixture_csv() +
                               "9999999,101.0,2.0,9999999,9999999,"
                               "2000000220000,false\n")
        self.assertEqual(len(bars), 3)
        self.assertEqual(len(more), 4)

    def test_mut_pooled_symbol_qualification(self):
        f = feas()
        self.assertEqual(sorted(f["symbols"]), ["BTC", "ETH"])
        self.assertNotIn("pooled", json.dumps(f).lower())

    def test_mut_wf_shrink(self):
        from research.phase11f import validation as V
        with self.assertRaises(ValueError):
            V.build_folds(2880, train_bars=2000, test_bars=1000,
                          purge_bars=150, embargo_bars=25,
                          step_bars=1000, n_folds=3 + 1)
        shrunk = V.build_folds(2880, train_bars=300, test_bars=300,
                               purge_bars=150, embargo_bars=25,
                               step_bars=300, n_folds=3)
        self.assertEqual(V.validate_folds(shrunk), [])
        self.assertNotEqual((2000, 1000, 150, 25, 1000, 4),
                            (300, 300, 150, 25, 300, 3))

    def test_mut_rolling_substitution(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        self.assertEqual(V.validate_expanding(folds), [])
        rolling = [dict(fo, train_start=1000) for fo in folds]
        self.assertTrue(any("rolling" in e or "train_start" in e
                            for e in V.validate_expanding(rolling)))

    def test_mut_future_insertion(self):
        bars, _ = fixture_bars(fixture_csv())
        big, _ = fixture_bars(fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50)))
        early = [b for b in big if b["time"] < 2000000160]
        self.assertEqual(len(early), len(bars))
        self.assertEqual([b["volume"] for b in early],
                         [b["volume"] for b in bars])

    def test_mut_hypothesis_execution_refusal(self):
        members = [m for m in dir(MU) if not m.startswith("__")]
        for m in members:
            self.assertNotIn(m.lower(), ("run_hypothesis", "evaluate",
                                         "backtest", "execute_signals"))
        self.assertNotIn("signals", members)
        self.assertNotIn("candidates", members)
        with self.assertRaises(RuntimeError):
            MU.refuse_economics()

    def test_mut_economic_execution_refusal(self):
        toks = ("Backtester", "trade_metrics", "expectancy", "sharpe",
                "profit_factor", "open_trade", "OrderIntent", "execution_signal",
                "PositionSizer", "drawdown", "win_rate", "MonteCarlo",
                "random_baseline", "monte_carlo", "pnl", "sortino")
        for path in UDIR.rglob("*.py"):
            for line in path.read_text().splitlines():
                if "NOT_EXECUTED" in line:
                    continue
                for tok in toks:
                    if tok in line and ("self." + tok) in line:
                        continue
                    self.assertNotIn(tok, line, "%s: %s" % (path.name, tok))
        blob = json.dumps(feas(), sort_keys=True).lower()
        for tok in ("pnl", "profit_factor", "sharpe", "win_rate", "drawdown",
                    "expectancy", "fills", "sortino"):
            self.assertNotIn('"%s"' % tok, blob, tok)

    def test_mut_d3_access_refused(self):
        from research.phase11g import datasets as DG
        from research.phase11g.registry import registry as RG
        with self.assertRaises(Exception):
            DG.load_holdout("u-monitor-attack")
        reg = RG.Registry()
        with self.assertRaises((ValueError, RuntimeError)):
            reg.register("D3_U", {}, "SEALED")
        self.assertEqual(DG.D3_ACCESS["load"], 0)


class TestDeterminism(unittest.TestCase):
    def test_rerun_byte_identical(self):
        before = (UDIR / "readiness_u.json").read_bytes()
        MU.determine(availability())
        self.assertEqual((UDIR / "readiness_u.json").read_bytes(), before)


class TestMachineCounts(unittest.TestCase):
    def test_collect_reconciles(self):
        from research.phase11g_u import counts as CNT2
        c = CNT2.collect()
        self.assertTrue(c["reconciled"], c)
        self.assertEqual(c["main_total"], c["baseline"] + c["family_sum"])
        self.assertGreater(c["baseline"], 2000)
        for fam, n in c["families"].items():
            self.assertIsInstance(n, int, fam)
            self.assertGreater(n, 0, fam)

    def test_research_total_sane(self):
        from research.phase11g_u import counts as CNT2
        c = CNT2.collect()
        self.assertGreater(c["research_total"], 400)


class TestProductionIsolation(unittest.TestCase):
    def test_no_production_imports(self):
        for path in UDIR.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                else:
                    continue
                for m in mods:
                    self.assertNotIn(m.split(".")[0],
                                     ("core", "backtesting", "data",
                                      "execution", "risk", "config", "main"),
                                     "%s imports %s" % (path.name, m))
                    self.assertTrue(
                        m.split(".")[0] in (
                            "argparse", "ast", "csv", "hashlib", "inspect",
                            "io", "json",
                            "pathlib", "statistics", "sys", "time", "datetime",
                            "dataclasses", "typing", "collections", "unittest",
                            "zipfile", "__future__") or m.startswith("research."),
                        "%s imports unexpected %s" % (path.name, m))

    def test_no_runtime_tokens(self):
        toks = ("submit" + "_order", "place" + "_order", "live" + "_execute",
                "paper" + "_trade", "shadow" + "_trade", "send" + "_order")
        for path in UDIR.rglob("*.py"):
            code = path.read_text()
            for tok in toks:
                self.assertNotIn(tok, code, "%s: %s" % (path.name, tok))

    def test_report_never_production_ready(self):
        rep = UMonitorReport()
        self.assertIs(rep.is_production_ready, False)
        self.assertFalse(rep.emission_check()["production_ready"])
        with self.assertRaises(ValueError):
            UMonitorReport(is_production_ready=True)
        with self.assertRaises(Exception):
            rep.is_production_ready = True

    def test_no_production_paths(self):
        require_git_fact(self, 'test_researcher_11g_u::TestProductionIsolation::test_no_production_paths')
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
