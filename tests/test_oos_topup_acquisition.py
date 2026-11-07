"""OOS top-up acquisition path: provenance, integrity, isolation.

Research-only, deterministic, offline (network never touched here;
the operator-run fetch script is audited by source scan, not
executed), stdlib-only. Covers the newly implemented
data-readiness path:

* fresh-bar acceptance / pre-boundary rejection / duplicates /
  gaps (§20 A-D);
* future-mutation isolation, reorder stability, duplicate
  accounting (§17 A-D);
* fill integrity -- no signals/setups channel exists (§20 F);
* economics integrity -- explicit-zero defaults cannot
  masquerade as venue schedules (§20 G);
* provenance + byte-identical dataset identity (§20 H);
* production isolation of the fetch script and readiness
  modules (§18).

The real top-up cache assertions use structural properties
(strict growth, post-boundary, identity recompute), never
hard-pinned counts, so operator re-runs stay valid.
"""

from __future__ import annotations

import ast
import io
import json
import pathlib
import unittest

from core.research.readiness import oos_execution_readiness as R

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE_A_END = 1788601440
TOPUP = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
TOPUP_PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.provenance.json"
PHASE19_ROWS = 11899


def mk_rows(start, count, step=60):
    return [{"time": start + i * step, "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 2.5}
            for i in range(count)]


def load_topup():
    with io.open(str(TOPUP), encoding="utf-8") as fh:
        return json.load(fh)


class TestAcquisitionFixtures(unittest.TestCase):
    def test_a_fresh_bar_acceptance(self):
        rows = mk_rows(GATE_A_END + 60, 500)
        obs = R.observe_dataset(rows, GATE_A_END)
        self.assertEqual(obs["fresh_bar_count"], 500)
        self.assertTrue(obs["strictly_after_boundary"])

    def test_b_pre_boundary_rejection(self):
        rows = ([{"time": GATE_A_END, "open": 1.0, "high": 1.0,
                  "low": 1.0, "close": 1.0, "volume": 1.0},
                 {"time": GATE_A_END - 60, "open": 1.0, "high": 1.0,
                  "low": 1.0, "close": 1.0, "volume": 1.0}]
                + mk_rows(GATE_A_END + 60, 500))
        obs = R.observe_dataset(rows, GATE_A_END)
        self.assertEqual(obs["fresh_bar_count"], 500)

    def test_c_duplicate_detection(self):
        rows = mk_rows(GATE_A_END + 60, 500)
        rows = rows + [dict(rows[0])]
        obs = R.observe_dataset(rows, GATE_A_END,
                                discovery_timestamps=frozenset())
        self.assertEqual(obs["duplicate_timestamps"], 1)
        self.assertEqual(obs["fresh_bar_count"], 500)

    def test_d_gap_detection_visible(self):
        rows = mk_rows(GATE_A_END + 60, 300) + mk_rows(
            GATE_A_END + 60 + 600 * 60, 300)
        obs = R.observe_dataset(rows, GATE_A_END)
        self.assertEqual(obs["fresh_bar_count"], 600)
        self.assertEqual(obs["max_contiguous_clean_bars"], 300)
        self.assertLess(obs["max_contiguous_clean_bars"],
                        R.REQUIRED_CONTIGUOUS_CLEAN_BARS)


class TestLookaheadAcquisition(unittest.TestCase):
    def test_a_post_boundary_mutation_preserves_pre_evidence(self):
        base = mk_rows(GATE_A_END + 60, 600)
        mutated = [dict(r) for r in base]
        for row in mutated[300:]:
            row["close"] = float(row["close"]) * 2.0
            row["volume"] = 999.0
        before = R.observe_dataset(base[:300], GATE_A_END)
        after = R.observe_dataset(mutated[:300], GATE_A_END)
        self.assertEqual(json.dumps(before, sort_keys=True),
                         json.dumps(after, sort_keys=True))

    def test_b_future_metadata_ignored(self):
        plain = mk_rows(GATE_A_END + 60, 200)
        tagged = [dict(r, regime_label="FUTURE", funding_rate=1.0)
                  for r in plain]
        self.assertEqual(R.observe_dataset(plain, GATE_A_END),
                         R.observe_dataset(tagged, GATE_A_END))

    def test_c_reorder_stable_identity(self):
        rows = mk_rows(GATE_A_END + 60, 1000)
        rev = list(reversed(rows))
        self.assertEqual(R.observe_dataset(rows, GATE_A_END),
                         R.observe_dataset(rev, GATE_A_END))

    def test_d_duplicates_accounted_not_silently_lost(self):
        from core.research.extension.extension import dedupe_merge
        existing = mk_rows(GATE_A_END + 60, 300)
        incoming = mk_rows(GATE_A_END + 60, 300)
        merged = dedupe_merge(existing, incoming, GATE_A_END)
        self.assertEqual(len(merged), 300)
        obs = R.observe_dataset(existing + incoming, GATE_A_END)
        # 300 duplicates detected pre-merge; merge keeps one copy
        # with first-wins provenance -- the count reconciles.
        self.assertEqual(obs["duplicate_timestamps"], 300)
        self.assertEqual(
            len(merged) + obs["duplicate_timestamps"], 600)


class TestFillAndEconomicsIntegrity(unittest.TestCase):
    def test_f_no_signal_setup_channel(self):
        import inspect
        params = set(inspect.signature(R.evaluate).parameters)
        self.assertEqual(
            params, {"preregistration", "dataset", "fills_observed",
                     "economics", "microstructure"})
        for name in ("signals", "setups", "opportunities", "touches",
                     "candidates"):
            self.assertNotIn(name, params)

    def test_f_zero_fills_never_satisfied(self):
        rep = R.evaluate(
            None, dataset=R.observe_dataset(
                mk_rows(GATE_A_END + 60, 300000), GATE_A_END,
                discovery_timestamps=frozenset()),
            fills_observed=0,
            economics={f: ("VERIFIED", "fixture") for f in
                       R.ECONOMICS_FIELDS},
            microstructure=("VERIFIED", "fixture"))
        self.assertEqual(
            rep.gate("minimum_fill_requirement").status, "BLOCKED")

    def test_g_explicit_zero_not_a_schedule(self):
        from core.risk import costs as costs
        unknown = costs.unknown_costs()
        with self.assertRaises(Exception):
            costs.require_known(unknown)
        profile = costs.paper_cost_profile()
        self.assertEqual(profile.venue_source, "")
        rep = R.evaluate(
            None, dataset=None, fills_observed=None, economics={},
            microstructure=("UNAVAILABLE", "fixture"))
        for field in R.ECONOMICS_FIELDS:
            self.assertEqual(
                rep.gate("economics_" + field).status, "BLOCKED")


class TestTopupCacheProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TOPUP.exists():
            raise unittest.SkipTest("top-up cache absent")

    def test_h_cache_structure_and_growth(self):
        env = load_topup()
        rows = env["raw"]
        self.assertGreater(len(rows), PHASE19_ROWS)
        self.assertTrue(all(r["time"] > GATE_A_END for r in rows))
        self.assertEqual(
            sorted(rows[0].keys()),
            ["close", "high", "low", "open", "time", "volume"])

    def test_h_dataset_identity_recomputes(self):
        env = load_topup()
        blob = json.dumps(
            sorted(env["raw"], key=lambda r: r["time"]),
            sort_keys=True, separators=(",", ":")).encode()
        import hashlib
        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                         env["dataset_identity"])

    def test_h_provenance_fields(self):
        prov = json.loads(TOPUP_PROV.read_text(encoding="utf-8"))
        for key in ("venue", "acquisition_source",
                    "acquisition_method", "merge_authority",
                    "identity_authority", "symbol", "timeframe",
                    "fresh_after", "dataset_identity", "tier"):
            self.assertIn(key, prov)
        self.assertEqual(prov["venue"], "DELTA")
        self.assertEqual(prov["tier"], "A-DIRECT")
        self.assertEqual(prov["fresh_after"], GATE_A_END)
        env = load_topup()
        self.assertEqual(prov["dataset_identity"],
                         env["dataset_identity"])

    def test_h_phase19_cache_untouched(self):
        prior = json.load(io.open(
            str(ROOT / "data" / "history"
                / "BTCUSDT_1m_phase19_extension.json"),
            encoding="utf-8"))
        self.assertEqual(len(prior["raw"]), PHASE19_ROWS)


class TestRealTopupReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TOPUP.exists():
            raise unittest.SkipTest("top-up cache absent")

    def test_topup_readiness_still_blocked(self):
        from core.research.readiness.preregistration import (
            FrozenPreregistration)
        env = load_topup()
        gate_path = (ROOT / "data" / "history" / "BTCUSDT_1m_oos.json")
        discovery = None
        if gate_path.exists():
            with io.open(str(gate_path), encoding="utf-8") as fh:
                discovery = frozenset(
                    r["time"] for r in json.load(fh).get("raw", [])
                    if isinstance(r, dict)
                    and isinstance(r.get("time"), int))
        dataset = R.observe_dataset(env["raw"], GATE_A_END, discovery)
        venue = json.loads((ROOT / "data" / "fixtures" / "delta"
                            / "delta_venue_economics_observation_"
                            "20260925.json").read_text(encoding="utf-8"))
        economics = {}
        for field in R.ECONOMICS_FIELDS:
            status = venue.get(field, {}).get("status", "UNAVAILABLE")
            note = venue.get(field, {}).get("note", "")
            economics[field] = (status, "venue observation: " + note)
        pre = FrozenPreregistration.create(
            hypotheses=(), dataset_identity=env["dataset_identity"],
            discovery_boundary=GATE_A_END,
            oos_boundary=env["raw"][-1]["time"]
            if env["raw"] else GATE_A_END + 60,
            minimum_contiguous_bars=R.REQUIRED_CONTIGUOUS_CLEAN_BARS,
            minimum_fresh_bars=int(R.required_fresh_bars()),
            economics_requirements=tuple(R.ECONOMICS_FIELDS),
            multiple_testing_family="Sidak-9L",
            frozen_execution_semantics="run_frozen_oos/9M",
            limitations=("top-up evaluation; 0 eligible hypotheses",))
        rep = R.evaluate(
            pre, dataset=dataset, fills_observed=0,
            economics=economics,
            microstructure=("UNAVAILABLE", "OHLCV-only adapters"))
        self.assertEqual(rep.final_status, "BLOCKED")
        self.assertEqual(rep.gate("dataset_contiguity").status,
                         "VERIFIED")
        self.assertEqual(rep.gate("zero_overlap").status,
                         "VERIFIED" if discovery is not None else
                         "UNAVAILABLE")
        self.assertEqual(rep.gate("minimum_bar_count").status,
                         "BLOCKED")
        self.assertEqual(
            rep.gate("minimum_fill_requirement").status, "BLOCKED")
        self.assertGreater(rep.available_bars, PHASE19_ROWS)


class TestAcquisitionIsolation(unittest.TestCase):
    FORBIDDEN_IMPORTS = ("core.live", "core.execution",
                         "core.paper_trading", "core.strategies",
                         "core.broker")
    FORBIDDEN_TOKENS = ("place_order", "submit_order", "BrokerEngine",
                        "DeltaOrderExecutor", "LIVE_EXECUTE",
                        "DELTA_API_KEY", "DELTA_API_SECRET")

    def check_file(self, path):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        bad_imports = [m for m in imported
                       if m.startswith(self.FORBIDDEN_IMPORTS)]
        bad_tokens = [t for t in self.FORBIDDEN_TOKENS if t in text]
        return bad_imports, bad_tokens

    def test_fetch_script_isolated(self):
        imports, tokens = self.check_file(
            ROOT / "scripts" / "fetch_oos_topup.py")
        self.assertEqual(imports, [])
        self.assertEqual(tokens, [])

    def test_readiness_modules_isolated(self):
        for name in ("preregistration.py",
                     "oos_execution_readiness.py"):
            imports, tokens = self.check_file(
                ROOT / "core" / "research" / "readiness" / name)
            self.assertEqual(imports, [], name)
            self.assertEqual(tokens, [], name)


if __name__ == "__main__":
    unittest.main()
