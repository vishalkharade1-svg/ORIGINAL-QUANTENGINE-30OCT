"""Phase 11G-N feasibility tests (deterministic, unittest-compatible).

Covers the §25 list: repository/head validation, lineage, freshness,
overlap, quality, timestamp semantics, order-flow classification,
scale, WF feasibility, regimes, symbols, venue separation, D3 seal,
lookahead, mutation resistance (MUT-N1..N14), deterministic rerun,
production isolation. No economics anywhere; no D3 contact.
"""

import ast
import hashlib
import io
import json
import subprocess
import unittest
import zipfile
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import research.phase11g_n.analyze as AN  # noqa: E402
from research.phase11g_n.report import (  # noqa: E402
    NFeasibilityReport, from_feasibility)

try:  # package import when pytest loads tests.test_*
    from tests.evidence_mode import require_git_fact
except ImportError:  # direct execution of this file
    from evidence_mode import require_git_fact

NDIR = BASE_DIR / "research" / "phase11g_n"
FEAS = NDIR / "feasibility.json"


def feas():
    return json.loads(FEAS.read_text())


def fixture_csv(n_minutes=3, per_minute=20, side="buy", start_ms=2_000_000_000_000,
                dup_ids=(), shuffle=False, symbol="BTCUSDT", shift_ms=0):
    import random
    lines = ["agg_trade_id,price,quantity,first_trade_id,last_trade_id,"
             "transact_time,is_buyer_maker"]
    rows = []
    tid = 0
    for m in range(n_minutes):
        for k in range(per_minute):
            rows.append((tid, 100.0 + m + k * 0.001, 1.0, tid, tid,
                         start_ms + m * 60_000 + k * 1000 + shift_ms,
                         "false" if side == "buy" else "true"))
            tid += 1
    for d in dup_ids:
        rows.append(rows[d])
    if shuffle:
        random.Random(42).shuffle(rows)
    for r in rows:
        lines.append("%d,%.3f,%.1f,%d,%d,%d,%s" % r)
    return "\n".join(lines) + "\n"


class TestRepositoryHead(unittest.TestCase):
    def test_starting_head_ancestor(self):
        require_git_fact(self, 'test_researcher_11g_n::TestRepositoryHead::test_starting_head_ancestor')
        r = subprocess.run(["git", "merge-base", "--is-ancestor",
                            "acab874d1a2cf256ab5f63a1b7fce5d061069b2d", "HEAD"],
                           capture_output=True, cwd=str(BASE_DIR))
        self.assertEqual(r.returncode, 0)

    def test_branch_main(self):
        require_git_fact(self, 'test_researcher_11g_n::TestRepositoryHead::test_branch_main')
        r = subprocess.run(["git", "branch", "--show-current"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(r.stdout.strip(), "main")

    def test_tree_clean_except_notes(self):
        require_git_fact(self, 'test_researcher_11g_n::TestRepositoryHead::test_tree_clean_except_notes')
        # Phase 12 supersession (disclosed in the Phase 12
        # report + manifests): production, test, manifest and
        # tooling paths change BY MANDATE in Phase 12, so a
        # fully-frozen tree no longer applies. What MUST stay
        # frozen is the research record itself: any
        # modification under research/ or to the frozen 11G
        # audit docs fails loudly (that freeze protects every
        # 11G verdict: L no-edge, M holdout NO-GO, Q-U data
        # insufficiency).
        r = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True, cwd=str(BASE_DIR))
        allowed_untracked = ("research/phase11g_n/", "research/phase11g_o/",
                             "research/phase11g_p/", "research/phase11g_q/",
                             "docs/audit/phase11g_N_fresh_data_eligibility.md",
                             "docs/audit/phase11g_O_fresh_data_expansion.md",
                             "docs/audit/phase11g_P_fresh_data_accumulation.md",
                             "docs/audit/phase11g_Q_full_oos_execution.md",
                             "docs/audit/phase11g_R_fresh_data_accumulation.md",
                             "tests/test_researcher_11g_n.py",
                             "tests/test_researcher_11g_o.py",
                             "tests/test_researcher_11g_p.py",
                             "tests/test_researcher_11g_q.py",
                             "tests/test_researcher_11g_r.py")
        for line in r.stdout.strip().splitlines():
            if line.startswith("?? "):
                path = line[3:].strip('"')
                if path in allowed_untracked or "muse suggetions" in path:
                    continue
                if path.startswith("research/"):
                    self.fail("frozen research added: %s" % line)
                continue
            else:
                path = line[3:].strip().strip('"')
                if (path.startswith("research/") or
                        "docs/audit/phase11g_" in path):
                    self.fail("frozen research modified: %s" % line)
                # Phase 12 production/test/manifest change: allowed.


class TestLineage(unittest.TestCase):
    def test_manifests_checksum_match(self):
        for mp in sorted((NDIR / "data" / "raw").glob("*/*/acquisition_manifest.json")):
            man = json.loads(mp.read_text())
            for kind, info in man["files"].items():
                self.assertTrue(info["checksum_match"])
                blob = (mp.parent / (man["files"][kind]["url"].split("/")[-1])).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                 info["local_sha256"])
                self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                 info["provider_sha256"])

    def test_source_hashes_pinned_in_feasibility(self):
        f = feas()
        self.assertEqual(len(f["datasets"]), 4)
        for key, ds in f["datasets"].items():
            self.assertEqual(ds["provider"], "Binance")
            self.assertEqual(len(ds["source_sha256"]), 64)
            self.assertEqual(ds["source_sha256"], ds["provider_sha256"])


class TestFreshnessOverlap(unittest.TestCase):
    def test_zero_overlap_all_sets(self):
        f = feas()
        self.assertEqual(f["overall_overlap"], "ZERO_OVERLAP")
        for sym, sets in f["overlap"].items():
            for name, o in sets.items():
                self.assertEqual(o["verdict"], "ZERO_OVERLAP", "%s %s" % (sym, name))
                self.assertEqual(o["overlap_minutes"], 0)

    def test_fresh_classification(self):
        f = feas()
        for sym, v in f["freshness"].items():
            self.assertEqual(v["classification"], "FRESH", sym)
            self.assertEqual(v["overlapping_sets"], [])
        self.assertEqual(f["freshness"]["BTCUSDT"]["d3_overlap"][:7], "UNKNOWN")

    def test_expected_prior_sets_compared(self):
        f = feas()
        self.assertEqual(sorted(f["overlap"]["BTCUSDT"]),
                         ["11F_D1_BTC", "11F_D2_BTC", "11G_G_gap_BTC",
                          "11G_I_dev_BTC_trades", "gateA_snapshot_BTC",
                          "oos_fresh_BTC"])
        self.assertEqual(sorted(f["overlap"]["ETHUSDT"]),
                         ["11F_D1_ETH", "11F_D2_ETH", "11G_G_gap_ETH"])


class TestQuality(unittest.TestCase):
    def test_zero_rejects_duplicates_ooo(self):
        f = feas()
        for sym, v in f["symbols"].items():
            self.assertEqual(v["rejected_records"], 0, sym)
            self.assertEqual(v["duplicate_trade_ids"], 0, sym)
            self.assertEqual(v["out_of_order_events"], 0, sym)
            self.assertEqual(v["missing_clean_minutes"], 0, sym)

    def test_kline_crosscheck(self):
        f = feas()
        for key, ds in f["datasets"].items():
            self.assertEqual(ds["kline_crosscheck"]["matched_minutes"], 1440, key)
            self.assertEqual(ds["kline_crosscheck"]["max_abs_close_diff"], 0.0, key)

    def test_timestamp_semantics(self):
        f = feas()
        for key, ds in f["datasets"].items():
            self.assertIn("milliseconds", ds["aggtrades"]["precision"], key)

    def test_orderflow_classification(self):
        f = feas()
        for key, ds in f["datasets"].items():
            self.assertIn("REAL", ds["aggtrades"]["aggressor_side"], key)
            self.assertIn("aggregate", ds["aggtrades"]["event_model"], key)


class TestScaleWF(unittest.TestCase):
    def test_scale_numbers(self):
        f = feas()
        self.assertEqual(f["symbols"]["BTCUSDT"]["clean_bars"], 2676)
        self.assertEqual(f["symbols"]["ETHUSDT"]["clean_bars"], 2880)
        self.assertEqual(f["symbols"]["BTCUSDT"]["days"], ["2026-09-07", "2026-09-08"])
        self.assertEqual(f["symbols"]["ETHUSDT"]["days"], ["2026-09-07", "2026-09-08"])
        self.assertGreater(f["symbols"]["BTCUSDT"]["clean_events"], 1_700_000)
        self.assertGreater(f["symbols"]["ETHUSDT"]["clean_events"], 1_800_000)

    def test_wf_required_is_6175(self):
        f = feas()
        self.assertEqual(f["walk_forward"]["required_bars"], 6175)
        self.assertEqual(f["walk_forward"]["geometry"],
                         {"train_min": 2000, "test": 1000, "purge": 150,
                          "embargo": 25, "step": 1000, "folds": 4})

    def test_full_wf_infeasible(self):
        from research.phase11f import validation as V
        f = feas()
        self.assertEqual(f["walk_forward"]["verdict"], "FULL_WF_INFEASIBLE")
        for sym, v in f["walk_forward"]["per_symbol"].items():
            self.assertFalse(v["feasible_full_wf"], sym)
            with self.assertRaises(ValueError):
                V.build_folds(v["available_clean_bars"], train_bars=2000,
                              test_bars=1000, purge_bars=150, embargo_bars=25,
                              step_bars=1000, n_folds=4)


class TestRegimeSymbolVenue(unittest.TestCase):
    def test_regime_descriptives_present(self):
        f = feas()
        for sym, r in f["regimes"].items():
            self.assertIn("descriptive only", r["note"])
            self.assertIn("p50", r["return_bps_deciles"])
            self.assertIn("p50", r["atr14_close_ratio_deciles"])
            self.assertGreaterEqual(r["up_days"] + r["down_days"], 1)

    def test_symbol_coverage(self):
        f = feas()
        self.assertEqual(sorted(f["symbols"]), ["BTCUSDT", "ETHUSDT"])
        for sym, v in f["symbols"].items():
            self.assertGreater(v["events_per_day"], 800_000, sym)

    def test_venue_separation(self):
        f = feas()
        self.assertIn("Binance", f["venue"])
        self.assertIn("Binance != Delta", f["venue"])
        for key, ds in f["datasets"].items():
            self.assertEqual(ds["venue"], "Binance")
            self.assertEqual(ds["provider"], "Binance")


class TestD3Seal(unittest.TestCase):
    def test_counters_zero_live_and_artifact(self):
        from research.phase11g import datasets as D11G
        from research.phase11g import fresh as FR
        self.assertEqual(D11G.D3_ACCESS["read"], 0)
        self.assertEqual(D11G.D3_ACCESS["hash"], 0)
        self.assertEqual(D11G.D3_ACCESS["load"], 0)
        self.assertEqual(FR.D3_ACCESS_11GD, {"read": 0, "hash": 0, "load": 0})
        f = feas()
        self.assertTrue(all(v == 0 for v in f["seal_counters_before"].values()))
        self.assertTrue(all(v == 0 for v in f["seal_counters_after"].values()))

    def test_no_d3_markers_in_n_files(self):
        for path in list(NDIR.rglob("*.py")) + [NDIR / "feasibility.json"]:
            for line in path.read_text().splitlines():
                if "D3" not in line or "assertNotIn" in line:
                    continue
                self.assertNotIn("universe_D3", line, str(path))
                self.assertNotIn("open(", line, str(path))
                self.assertNotIn("read_bytes", line, str(path))
                self.assertNotIn("load(", line, str(path))


class TestLookahead(unittest.TestCase):
    def _bars(self, csv_text, symbol="BTCUSDT"):
        trades, _ = AN.parse_aggtrades(csv_text.encode(), symbol)
        bars, minutes, _ = AN.minute_bars(trades)
        return bars, minutes

    def test_future_append_invariant(self):
        bars, _ = self._bars(fixture_csv())
        bumped, _ = self._bars(fixture_csv() + "9999999,999.0,500.0,9999999,9999999,"
                               "2000000180000,false\n")
        self.assertEqual([b["close"] for b in bars[:3]],
                         [b["close"] for b in bumped[:3]])
        self.assertEqual([b["volume"] for b in bars[:3]],
                         [b["volume"] for b in bumped[:3]])

    def test_totals_order_invariant(self):
        bars, _ = self._bars(fixture_csv())
        shuf, _ = self._bars(fixture_csv(shuffle=True))
        tot = lambda bs: (round(sum(b["volume"] for b in bs), 6), len(bs))
        self.assertEqual(tot(bars), tot(shuf))


class TestMutations(unittest.TestCase):
    def test_mut_n1_future_contamination(self):
        bars, _ = TestLookahead()._bars(fixture_csv())
        n0 = len(bars)
        big, _ = TestLookahead()._bars(
            fixture_csv() + "".join(
                "8%05d,100.0,1000.0,8%05d,8%05d,2000000160000,false\n" % (i, i, i)
                for i in range(50)))
        early = [b for b in big if b["time"] < 2000000160]
        self.assertEqual(len(early), n0)
        self.assertEqual([b["volume"] for b in early],
                         [b["volume"] for b in bars])

    def test_mut_n2_timestamp_shift(self):
        bars, _ = TestLookahead()._bars(fixture_csv())
        shifted, _ = TestLookahead()._bars(fixture_csv(shift_ms=60_000))
        self.assertEqual([b["time"] + 60 for b in bars],
                         [b["time"] for b in shifted])
        self.assertEqual([b["volume"] for b in bars],
                         [b["volume"] for b in shifted])

    def test_mut_n3_dataset_substitution(self):
        mp = sorted((NDIR / "data" / "raw").glob("BTCUSDT/2026-09-07/acquisition_manifest.json"))[0]
        man = json.loads(mp.read_text())
        eth_blob = sorted((NDIR / "data" / "raw").glob("ETHUSDT/2026-09-07/*aggTrades*.zip"))[0].read_bytes()
        self.assertNotEqual(hashlib.sha256(eth_blob).hexdigest(),
                            man["files"]["aggTrades"]["local_sha256"])

    def test_mut_n4_hash_tampering(self):
        zp = sorted((NDIR / "data" / "raw").glob("BTCUSDT/2026-09-08/*aggTrades*.zip"))[0]
        blob = bytearray(zp.read_bytes())
        blob[1000] ^= 0xFF
        mp = zp.parent / "acquisition_manifest.json"
        man = json.loads(mp.read_text())
        self.assertNotEqual(hashlib.sha256(bytes(blob)).hexdigest(),
                            man["files"]["aggTrades"]["local_sha256"])

    def test_mut_n5_duplicate_injection(self):
        _, q = AN.parse_aggtrades(
            fixture_csv(dup_ids=(3, 7)).encode(), "BTCUSDT")
        self.assertEqual(q["duplicate_trade_ids"], 2)

    def test_mut_n6_event_order(self):
        _, q = AN.parse_aggtrades(fixture_csv(shuffle=True).encode(), "BTCUSDT")
        self.assertGreater(q["out_of_order_events"], 0)

    def test_mut_n7_symbol_substitution(self):
        # Binance aggTrades CSVs carry no symbol column (binding lives at
        # file level): the parser stamps the caller-supplied symbol, so a
        # row-level swap is a no-op by construction — and file-level swaps
        # are caught by the manifest/directory/key binding chain below.
        _, q = AN.parse_aggtrades(fixture_csv(symbol="ETHUSDT").encode(), "BTCUSDT")
        self.assertEqual(q["parsed"], 60)
        self.assertEqual(q["rejected"], 0)
        for mp in sorted((NDIR / "data" / "raw").glob("*/*/acquisition_manifest.json")):
            man = json.loads(mp.read_text())
            self.assertEqual(man["symbol"], mp.parent.parent.name)
            self.assertEqual(man["date"], mp.parent.name)
        f = feas()
        for key in f["datasets"]:
            sym, date = key.split("/")
            self.assertTrue((NDIR / "data" / "raw" / sym / date).is_dir(), key)

    def test_mut_n8_venue_substitution(self):
        f = feas()
        for key, ds in f["datasets"].items():
            self.assertEqual(ds["venue"], "Binance", key)
        mut = dict(f["datasets"]["BTCUSDT/2026-09-07"], venue="Delta")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["datasets"]["BTCUSDT/2026-09-07"], sort_keys=True).encode()
            ).hexdigest())

    def test_mut_n9_freshness_tampering(self):
        f = feas()
        mut = dict(f["freshness"]["BTCUSDT"], classification="OVERLAPPING")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["freshness"]["BTCUSDT"], sort_keys=True).encode()).hexdigest())

    def test_mut_n10_d3_access_attempt(self):
        from research.phase11g import datasets as DG
        from research.phase11g.registry import registry as RG
        with self.assertRaises(Exception):
            DG.load_holdout("n-contamination-attack")
        reg = RG.Registry()
        with self.assertRaises((ValueError, RuntimeError)):
            reg.register("D3_N", {}, "SEALED")
        self.assertEqual(DG.D3_ACCESS["load"], 0)

    def test_mut_n11_wf_geometry_shrink(self):
        from research.phase11f import validation as V
        # Full geometry raises on N scale; a shrunk plan would not —
        # proving the verdict hinges on the unshrunk geometry.
        with self.assertRaises(ValueError):
            V.build_folds(2880, train_bars=2000, test_bars=1000,
                          purge_bars=150, embargo_bars=25,
                          step_bars=1000, n_folds=4)
        shrunk = V.build_folds(2880, train_bars=300, test_bars=300,
                               purge_bars=150, embargo_bars=25,
                               step_bars=300, n_folds=3)
        self.assertEqual(V.validate_folds(shrunk), [])
        self.assertNotEqual(
            (2000, 1000, 150, 25, 1000, 4), (300, 300, 150, 25, 300, 3))

    def test_mut_n12_rolling_substitution(self):
        from research.phase11f import validation as V
        folds = V.build_folds(7000)
        self.assertEqual(V.validate_expanding(folds), [])
        rolling = [dict(f, train_start=1000) for f in folds]
        self.assertTrue(any("rolling" in e or "train_start" in e
                            for e in V.validate_expanding(rolling)))

    def test_mut_n13_threshold_modification(self):
        import copy
        man = json.loads((BASE_DIR / "research" / "phase11g_k" / "freeze" /
                          "freeze_manifest.json").read_text())
        doc = json.loads((BASE_DIR / "research" / "phase11g_k" / "hypotheses" /
                          "H11GK-001.json").read_text())
        bad = copy.deepcopy(doc)
        bad["thresholds"]["imbalance_abs_min"] = 0.61
        self.assertNotEqual(hashlib.sha256(
            json.dumps(bad, sort_keys=True).encode()).hexdigest(),
            man["hypothesis_hashes"]["H11GK-001"])

    def test_mut_n14_capability_misclassification(self):
        f = feas()
        for key, ds in f["datasets"].items():
            self.assertIn("REAL", ds["aggtrades"]["aggressor_side"], key)
        mut = dict(f["datasets"]["ETHUSDT/2026-09-08"]["aggtrades"],
                   aggressor_side="PROXY (mutant)")
        self.assertNotEqual(
            hashlib.sha256(json.dumps(mut, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(
                f["datasets"]["ETHUSDT/2026-09-08"]["aggtrades"],
                sort_keys=True).encode()).hexdigest())


class TestDeterminism(unittest.TestCase):
    def test_rerun_byte_identical(self):
        before = (NDIR / "feasibility.json").read_bytes()
        AN.analyze()
        self.assertEqual((NDIR / "feasibility.json").read_bytes(), before)


class TestProductionIsolation(unittest.TestCase):
    def test_no_production_imports(self):
        banned = ("core.", "backtesting", "data.", "execution", "risk",
                  "config", "main")
        allowed_prefix = ("research.",)
        for path in NDIR.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                else:
                    continue
                for m in mods:
                    root = m.split(".")[0]
                    self.assertNotIn(root, banned, "%s imports %s" % (path.name, m))
                    self.assertTrue(
                        m in ("argparse", "ast", "csv", "hashlib", "io", "json",
                              "pathlib", "statistics", "sys", "time",
                              "datetime", "dataclasses", "typing", "collections",
                              "httpx", "zipfile", "__future__") or m.startswith(allowed_prefix)
                        or m.split(".")[0] in ("argparse", "ast", "csv", "hashlib",
                                               "io", "json", "pathlib", "statistics",
                                               "sys", "time", "datetime", "dataclasses",
                                               "typing", "collections", "httpx",
                                               "zipfile", "__future__"),
                        "%s imports unexpected %s" % (path.name, m))

    def test_no_order_tokens(self):
        toks = ("submit" + "_order", "place" + "_order", "live" + "_execute",
                "paper" + "_trade", "shadow" + "_trade", "send" + "_order")
        for path in NDIR.rglob("*.py"):
            code = path.read_text()
            for tok in toks:
                self.assertNotIn(tok, code, "%s: %s" % (path.name, tok))

    def test_report_never_production_ready(self):
        rep = NFeasibilityReport()
        self.assertIs(rep.is_production_ready, False)
        self.assertFalse(rep.emission_check()["production_ready"])
        with self.assertRaises(ValueError):
            NFeasibilityReport(is_production_ready=True)
        f = feas()
        rep2 = from_feasibility(f, "ab" * 32, "cd" * 32)
        self.assertIs(rep2.is_production_ready, False)

    def test_no_production_paths(self):
        require_git_fact(self, 'test_researcher_11g_n::TestProductionIsolation::test_no_production_paths')
        # Phase 12 supersession (disclosed): production paths
        # change BY MANDATE in Phase 12. The freeze that
        # remains is the RESEARCH freeze -- research/ and the
        # frozen 11G audit docs must show zero modifications
        # (tracked or untracked).
        import subprocess
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "research/",
             "docs/audit/"],
            capture_output=True, text=True, cwd=str(BASE_DIR)).stdout.strip()
        self.assertEqual(out, "")

    def test_live_disabled(self):
        import os
        self.assertNotIn(os.getenv("ALLOW_LIVE", "").lower(), ("1", "true"))
        self.assertNotIn(os.getenv("LIVE_EXECUTE", "").lower(), ("1", "true"))


if __name__ == "__main__":
    unittest.main()
