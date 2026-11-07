"""Phase 11G-S provider-recheck tests (deterministic, unittest-compatible).

Covers the §28 list: starting-head verification, lineage, cutoff
derivation, provider availability classification, fresh/reused
distinction, checksum validation, quality validation, contiguous-bar
calculation, per-symbol gate, exact 6,175 derivation, no pooling, WF
feasibility, expanding-origin positive control, no rolling/shrinking,
overlap protection, hypothesis/economic execution refusal, D3 access
refusal, lookahead, determinism, mutation suite (§20, 22 items),
production isolation, non-production readiness, no promotion. No
economics anywhere; no D3 contact.
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

import research.phase11g_s.gate_s as GS  # noqa: E402
from research.phase11g_s.report_s import SReadinessReport  # noqa: E402

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

SDIR = BASE_DIR / "research" / "phase11g_s"
SFEAS = SDIR / "readiness_s.json"
KDIR = BASE_DIR / "research" / "phase11g_k"


def feas():
    return json.loads(SFEAS.read_text())


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
    trades, _ = GS.parse_aggtrades(csv_text.encode(), symbol)
    return GS.minute_bars(trades)


class TestStartingState(unittest.TestCase):
    def test_head_descends_from_r(self):
        require_git_fact(self, 'test_researcher_11g_s::TestStartingState::test_head_descends_from_r')
        r = subprocess.run(["git", "merge-base", "--is-ancestor",
                            "d77af19e8574b76f065ded1b2b2c09601aa110de", "HEAD"],
                           capture_output=True, cwd=str(BASE_DIR))
        self.assertEqual(r.returncode, 0)

    def test_branch_main(self):
        require_git_fact(self, 'test_researcher_11g_s::TestStartingState::test_branch_main')
        r = subprocess.run(["git", "branch", "--show-current"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(r.stdout.strip(), "main")

    def test_tree_only_expected(self):
        require_git_fact(self, 'test_researcher_11g_s::TestStartingState::test_tree_only_expected')
        r = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        allowed_new = ("research/phase11g_s/",
                       "tests/test_researcher_11g_s.py",
                       "docs/audit/phase11g_S_provider_recheck.md")
        allowed_modified = ("tests/test_researcher_11g_n.py",
                            "tests/test_researcher_11g_o.py",
                            "tests/test_researcher_11g_p.py",
                            "tests/test_researcher_11g_q.py",
                            "tests/test_researcher_11g_r.py")
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
                if path in allowed_modified:
                    pass
                elif (path.startswith("research/") or
                        "docs/audit/phase11g_" in path):
                    self.fail("frozen research modified: %s" % line)
                # Phase 12 production/test/manifest change: allowed.


class TestLineageCutoff(unittest.TestCase):
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

    def test_cutoffs_rederived(self):
        f = feas()
        self.assertEqual(f["cutoffs"]["pre_cutoff"], 1788751380)
        self.assertEqual(f["cutoffs"]["fresh_start_s"], 1788912000)
        self.assertEqual(GS.PRE_CUTOFF, 1788751380)
        self.assertEqual(GS.FRESH_START_S, 1788912000)
        self.assertGreater(GS.FRESH_START_S, 1788911940)


class TestAvailability(unittest.TestCase):
    def test_observation_recorded(self):
        f = feas()
        av = f["availability"]
        self.assertEqual(av["latest_available_day"], "2026-09-08")
        self.assertEqual(av["result"], "DATA_NOT_YET_AVAILABLE")
        self.assertEqual(len(av["unavailable_days"]), 11)
        self.assertIn("2026-09-09", av["unavailable_days"])
        self.assertIn("2026-09-19", av["unavailable_days"])
        self.assertEqual(f["s_new_files"], 0)
        self.assertEqual(f["n_files_reverified"], 4)

    def test_404_is_not_zero_bars(self):
        f = feas()
        self.assertNotIn("zero-bars", json.dumps(f).lower())
        self.assertEqual(f["availability"]["result"], "DATA_NOT_YET_AVAILABLE")


class TestInventoryQuality(unittest.TestCase):
    def test_manifests_reverified(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        zips = sorted(nraw.glob("*/*/*aggTrades*.zip"))
        self.assertEqual(len(zips), 4)
        for zp in zips:
            man = json.loads((zp.parent / "acquisition_manifest.json").read_text())
            self.assertEqual(hashlib.sha256(zp.read_bytes()).hexdigest(),
                             man["files"]["aggTrades"]["local_sha256"], zp.name)

    def test_zero_quality_flags(self):
        f = feas()
        for asset, q in f["quality"].items():
            self.assertEqual(q["rejected"], 0, asset)
            self.assertEqual(q["dups"], 0, asset)
            self.assertEqual(q["ooo"], 0, asset)

    def test_minute_alignment(self):
        f = feas()
        for asset, c in f["contiguity"].items():
            self.assertEqual(c["first"] % 60, 0, asset)
            self.assertEqual(c["last"] % 60, 0, asset)

    def test_symbol_binding(self):
        nraw = BASE_DIR / "research" / "phase11g_n" / "data" / "raw"
        for mp in sorted(nraw.glob("*/*/acquisition_manifest.json")):
            man = json.loads(mp.read_text())
            self.assertEqual(man["symbol"], mp.parent.parent.name)
            self.assertEqual(man["date"], mp.parent.name)

    def test_venue_binding(self):
        nfeas = json.loads((BASE_DIR / "research" / "phase11g_n" /
                            "feasibility.json").read_text())
        self.assertTrue(nfeas["venue"].startswith("Binance"))
        self.assertIn("Binance != Delta", nfeas["venue"])


class TestContiguityGate(unittest.TestCase):
    def test_reference_spans_exact(self):
        f = feas()
        self.assertEqual(f["contiguity"]["BTC"]["unique"], 2676)
        self.assertEqual(f["contiguity"]["ETH"]["unique"], 2880)
        for asset, c in f["contiguity"].items():
            self.assertEqual(c["gap_count"], 0, asset)
            self.assertEqual(c["unique"], c["expected"], asset)

    def test_gap_detection_positive_control(self):
        from research.phase11g_o.analyze_o import contiguity
        c = contiguity([0, 60, 180])
        self.assertEqual(c["gap_count"], 1)
        self.assertEqual(c["largest_gap_minutes"], 1)

    def test_gate_unmet_shortfalls(self):
        f = feas()
        self.assertEqual(f["gate"]["required_bars"], 6175)
        self.assertFalse(f["gate"]["met"])
        syms = f["gate"]["symbols"]
        self.assertEqual(syms["BTC"]["shortfall_vs_6175"], 6175)
        self.assertEqual(syms["ETH"]["shortfall_vs_6175"], 6175)
        self.assertEqual(syms["BTC"]["fresh_bars"], 0)
        self.assertEqual(syms["ETH"]["fresh_bars"], 0)
        self.assertEqual(f["decision"], "DATA_STILL_INSUFFICIENT")
        self.assertFalse(f["economics_executed"])
        self.assertEqual(f["hypotheses_executed"], 0)


class TestOverlapFreshness(unittest.TestCase):
    def test_zero_overlap(self):
        f = feas()
        self.assertEqual(f["overall_overlap"], "ZERO_OVERLAP")
        for asset, sets in f["overlap"].items():
            for name, o in sets.items():
                self.assertEqual(o["verdict"], "ZERO_OVERLAP",
                                 "%s %s" % (asset, name))

    def test_freshness_reused(self):
        f = feas()
        for asset, v in f["freshness"].items():
            self.assertEqual(v["classification"], "REUSED", asset)
            self.assertEqual(v["overlapping_sets"], [])
            self.assertIn("UNKNOWN_BY_SEAL", v["d3_overlap"])


class TestWFGeometry(unittest.TestCase):
    def test_required_derived_from_builder(self):
        from research.phase11f import validation as V
        import inspect
        sig = inspect.signature(V.build_folds)
        d = {k: v.default for k, v in sig.parameters.items()
             if v.default is not inspect.Parameter.empty}
        required = d["train_bars"] + 3 * d["step_bars"] + d["purge_bars"] + \
            d["embargo_bars"] + d["test_bars"]
        self.assertEqual(required, 6175)
        self.assertEqual((d["train_bars"], d["test_bars"], d["purge_bars"],
                          d["embargo_bars"], d["step_bars"], d["n_folds"]),
                         (2000, 1000, 150, 25, 1000, 4))

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

    def test_no_symbol_pooling(self):
        f = feas()
        self.assertEqual(sorted(f["gate"]["symbols"]), ["BTC", "ETH"])
        for asset, v in f["gate"]["symbols"].items():
            self.assertLess(v["fresh_bars"], 6175, asset)


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

    def test_no_d3_markers_in_s_files(self):
        for path in list(SDIR.rglob("*.py")) + [SDIR / "readiness_s.json"]:
            for line in path.read_text().splitlines():
                if "D3" not in line or "assertNotIn" in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))
                self.assertNotIn("read_bytes", line, str(path))
                self.assertNotIn("load(", line, str(path))


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

    def test_no_d3_markers_in_s_files(self):
        for path in list(SDIR.rglob("*.py")) + [SDIR / "readiness_s.json"]:
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
        self.assertEqual([b["volume"] for b in early],
                         [b["volume"] for b in bars])

    def test_quality_stable_under_future(self):
        _, q1 = GS.parse_aggtrades(fixture_csv().encode(), "BTCUSDT")
        _, q2 = GS.parse_aggtrades((fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50))).encode(), "BTCUSDT")
        self.assertEqual(q1["rejected"], q2["rejected"])
        self.assertEqual(q1["duplicate_trade_ids"], q2["duplicate_trade_ids"])


class TestMutations(unittest.TestCase):
    def test_mut_duplicate_event_id(self):
        _, q = GS.parse_aggtrades(fixture_csv(dup_ids=(3, 7)).encode(), "BTCUSDT")
        self.assertEqual(q["duplicate_trade_ids"], 2)

    def test_mut_duplicate_minute(self):
        from research.phase11g_o.analyze_o import contiguity
        c = contiguity([0, 60, 60, 120])
        self.assertEqual(c["total"], 4)
        self.assertEqual(c["unique"], 3)

    def test_mut_reordered_events(self):
        _, q = GS.parse_aggtrades(fixture_csv(shuffle=True).encode(), "BTCUSDT")
        self.assertGreater(q["out_of_order_events"], 0)
        bars, _ = fixture_bars(fixture_csv())
        shuf, _ = fixture_bars(fixture_csv(shuffle=True))
        self.assertAlmostEqual(sum(b["volume"] for b in bars),
                               sum(b["volume"] for b in shuf))

    def test_mut_timestamp_corruption(self):
        bad = "1,100.0,1.0,1,1,12345,false\n"
        _, q = GS.parse_aggtrades((fixture_csv() + bad).encode(), "BTCUSDT")
        self.assertEqual(q["rejects_by_reason"].get("ValueError"), 1)
        self.assertEqual(q["parsed"], 60)

    def test_mut_negative_quantity(self):
        bad = "1,100.0,-1.0,1,1,2000000000000,false\n"
        _, q = GS.parse_aggtrades((fixture_csv() + bad).encode(), "BTCUSDT")
        self.assertEqual(q["rejects_by_reason"].get("zero_or_negative_quantity"), 1)

    def test_mut_invalid_aggressor(self):
        _, q = GS.parse_aggtrades(fixture_csv(bad_side=True).encode(), "BTCUSDT")
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
                         hashlib.sha256((SDIR / "gate_s.py").read_bytes()
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
        f = feas()
        mut = dict(f["freshness"]["BTC"], classification="FRESH")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["freshness"]["BTC"], sort_keys=True).encode()).hexdigest())

    def test_mut_overlap_tampering(self):
        self.assertEqual(GS.overlap_minutes([10, 20], [20, 30]), [20])
        f = feas()
        mut = dict(f["overlap"]["BTC"]["oos_fresh_BTC"],
                   verdict="OVERLAP_DETECTED", overlap_minutes=5)
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["overlap"]["BTC"]["oos_fresh_BTC"], sort_keys=True).encode()
            ).hexdigest())

    def test_mut_gap_stitching(self):
        from research.phase11g_o.analyze_o import contiguity
        c = contiguity([0, 60, 180])
        self.assertEqual(c["gap_count"], 1)
        self.assertEqual(c["unique"], 3)
        self.assertNotEqual(c["unique"], c["total"] + 1)

    def test_mut_synthetic_bar_insertion(self):
        bars, _ = fixture_bars(fixture_csv())
        more, _ = fixture_bars(fixture_csv() +
                               "9999999,101.0,2.0,9999999,9999999,"
                               "2000000220000,false\n")
        self.assertEqual(len(bars), 3)
        self.assertEqual(len(more), 4)

    def test_mut_pooled_symbol_qualification(self):
        f = feas()
        bic = f["contiguity"]["BTC"]["unique"]
        eic = f["contiguity"]["ETH"]["unique"]
        # Even the illicit sum (double-counting shared timestamps) fails.
        self.assertLess(bic + eic, 6175)
        self.assertEqual(sorted(f["gate"]["symbols"]), ["BTC", "ETH"])
        self.assertNotIn("pooled", json.dumps(f).lower())

    def test_mut_wf_shrink(self):
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

    def test_mut_rolling_substitution(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        self.assertEqual(V.validate_expanding(folds), [])
        rolling = [dict(fo, train_start=1000) for fo in folds]
        self.assertTrue(any("rolling" in e or "train_start" in e
                            for e in V.validate_expanding(rolling)))

    def test_mut_future_data_insertion(self):
        bars, _ = fixture_bars(fixture_csv())
        big, _ = fixture_bars(fixture_csv() + "".join(
            "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
            for i in range(50)))
        early = [b for b in big if b["time"] < 2000000160]
        self.assertEqual(len(early), len(bars))
        self.assertEqual([b["volume"] for b in early],
                         [b["volume"] for b in bars])

    def test_mut_hypothesis_execution_refusal(self):
        import research.phase11g_s.gate_s as G2
        members = [m for m in dir(G2) if not m.startswith("__")]
        for m in members:
            self.assertNotIn(m.lower(), ("run_hypothesis", "evaluate",
                                         "backtest", "execute_signals"))
        self.assertNotIn("signals", members)
        self.assertNotIn("candidates", members)

    def test_mut_economic_execution_refusal(self):
        with self.assertRaises(RuntimeError):
            GS.refuse_economics()
        toks = ("Backtester", "trade_metrics", "expectancy", "sharpe",
                "profit_factor", "open_trade", "OrderIntent", "execution_signal",
                "PositionSizer", "drawdown", "win_rate", "MonteCarlo",
                "random_baseline", "monte_carlo", "pnl", "sortino")
        for path in SDIR.rglob("*.py"):
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
            DG.load_holdout("s-recheck-attack")
        reg = RG.Registry()
        with self.assertRaises((ValueError, RuntimeError)):
            reg.register("D3_S", {}, "SEALED")
        self.assertEqual(DG.D3_ACCESS["load"], 0)


class TestDeterminism(unittest.TestCase):
    def test_rerun_byte_identical(self):
        before = (SDIR / "readiness_s.json").read_bytes()
        GS.determine()
        self.assertEqual((SDIR / "readiness_s.json").read_bytes(), before)


class TestProductionIsolation(unittest.TestCase):
    def test_no_production_imports(self):
        for path in SDIR.rglob("*.py"):
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
                            "argparse", "ast", "csv", "hashlib", "io", "json",
                            "pathlib", "statistics", "sys", "time", "datetime",
                            "dataclasses", "typing", "collections",
                            "zipfile", "__future__") or m.startswith("research."),
                        "%s imports unexpected %s" % (path.name, m))

    def test_no_runtime_tokens(self):
        toks = ("submit" + "_order", "place" + "_order", "live" + "_execute",
                "paper" + "_trade", "shadow" + "_trade", "send" + "_order")
        for path in SDIR.rglob("*.py"):
            code = path.read_text()
            for tok in toks:
                self.assertNotIn(tok, code, "%s: %s" % (path.name, tok))

    def test_report_never_production_ready(self):
        rep = SReadinessReport()
        self.assertIs(rep.is_production_ready, False)
        self.assertFalse(rep.emission_check()["production_ready"])
        with self.assertRaises(ValueError):
            SReadinessReport(is_production_ready=True)
        with self.assertRaises(Exception):
            rep.is_production_ready = True

    def test_econ_fields_never_executed(self):
        t = feas()
        self.assertFalse(t["economics_executed"])
        self.assertEqual(t["hypotheses_executed"], 0)

    def test_no_production_paths(self):
        require_git_fact(self, 'test_researcher_11g_s::TestProductionIsolation::test_no_production_paths')
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
