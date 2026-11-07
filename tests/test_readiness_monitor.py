"""Readiness monitor: snapshots, blockers, handoff, isolation.

Research-only, deterministic, offline, stdlib-only. Proves the
monitor layer reuses the existing readiness evaluator (no second
calculation engine), records byte-identical snapshots, classifies
blockers without collapsing them, derives terminal handoff
states without executing OOS, and stays production-isolated.

Coverage: determinism (§17 preamble), lookahead A-F (§18),
isolation (§19), real-data snapshot (§§15, 22-23).
"""

from __future__ import annotations

import ast
import io
import json
import pathlib
import unittest

from core.research.oos.oos_types import HypothesisRecord
from core.research.readiness import monitor as M
from core.research.readiness import oos_execution_readiness as R
from core.research.readiness.preregistration import FrozenPreregistration

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE_A_END = 1788601440
OOS_START = 1788601500
TOPUP = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.json"
TOPUP_PROV = ROOT / "data" / "history" / "BTCUSDT_1m_oos_topup.provenance.json"
GATE_CACHE = ROOT / "data" / "history" / "BTCUSDT_1m_oos.json"

ECONOMICS_MISSING = {
    field: ("UNAVAILABLE", "no venue schedule (fixture)")
    for field in R.ECONOMICS_FIELDS}
ECONOMICS_VERIFIED = {
    field: ("VERIFIED", "provisioned (fixture)")
    for field in R.ECONOMICS_FIELDS}
PROV_DIRECT = {"tier": "A-DIRECT", "venue": "DELTA"}


def mk_hypothesis(hid, regime="TREND"):
    return HypothesisRecord(
        hypothesis_id=hid, origin="9L", statement="fixture " + hid,
        symbol="BTCUSDT", direction="LONG",
        regime_dim="trend_vs_range" if regime else None,
        regime_label=regime,
        params={"entry_model": "BREAKOUT_CONTINUATION"},
        seven_e_no_go=False, walk_forward_passed=True,
        walk_forward_note="fixture", expected_outcome="OOS_ROBUST",
        evidence=())


def mk_prereg(hypotheses):
    return FrozenPreregistration.create(
        hypotheses=tuple(hypotheses), dataset_identity="fixture",
        discovery_boundary=GATE_A_END, oos_boundary=OOS_START,
        minimum_contiguous_bars=R.REQUIRED_CONTIGUOUS_CLEAN_BARS,
        minimum_fresh_bars=int(R.required_fresh_bars()),
        economics_requirements=tuple(R.ECONOMICS_FIELDS),
        multiple_testing_family="Sidak-9L-fixture",
        symbol_constraints=("BTCUSDT",),
        directional_constraints=("LONG",),
        frozen_execution_semantics="run_frozen_oos/9M",
        limitations=("synthetic fixture",))


def mk_rows(start, count, step=60):
    return [{"time": start + i * step, "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 2.5}
            for i in range(count)]


def run_snapshot(rows, hypotheses=(), fills=0, economics=None,
                 micro=("UNAVAILABLE", "fixture"), discovery=None,
                 provenance=None, stored=None, repo="BLOCKED"):
    pre = mk_prereg(hypotheses) if hypotheses else mk_prereg([])
    if discovery is None:
        discovery_set = frozenset()
    else:
        discovery_set = discovery
    dataset = R.observe_dataset(rows, GATE_A_END, discovery_set)
    return M.run_monitor(
        pre, dataset=dataset, dataset_identity="fixture",
        fills_observed=fills,
        economics=dict(ECONOMICS_MISSING) if economics is None
        else economics, microstructure=micro,
        provenance=PROV_DIRECT if provenance is None else provenance,
        latest_stored_timestamp=stored, source_rows=[],
        repository_forensic_status=repo)


class TestSnapshotDeterminism(unittest.TestCase):
    def test_double_run_byte_identical(self):
        kwargs = dict(rows=mk_rows(OOS_START, 7000), fills=0,
                      stored=OOS_START + 7000 * 60)
        first = run_snapshot(**kwargs)
        second = run_snapshot(**kwargs)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))

    def test_ordering_stable(self):
        # Blocker order follows gate evaluation order and is stable
        # across identical runs.
        first = [b.gate_id for b in run_snapshot(
            rows=mk_rows(OOS_START, 7000), fills=0).blockers]
        second = [b.gate_id for b in run_snapshot(
            rows=mk_rows(OOS_START, 7000), fills=0).blockers]
        self.assertEqual(first, second)
        self.assertTrue(first)


class TestBlockerClasses(unittest.TestCase):
    def test_real_world_classes_present(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 7000), fills=0)
        classes = set(b.blocker_class for b in snap.blockers)
        for expected in ("DATA_TIME_BOUND", "NO_ELIGIBLE_HYPOTHESES",
                         "NO_FILLS", "ECONOMICS_UNAVAILABLE",
                         "MICROSTRUCTURE_UNAVAILABLE",
                         "REPOSITORY_FORENSIC_BLOCK"):
            self.assertIn(expected, classes)

    def test_no_collapse_to_bare_blocked(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 7000), fills=0)
        for blocker in snap.blockers:
            self.assertIn(blocker.blocker_class, M.BLOCKER_CLASSES)
            self.assertTrue(blocker.detail)
            self.assertTrue(blocker.gate_id)

    def test_repo_verified_drops_forensic_blocker(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 7000), fills=0,
                            repo="VERIFIED")
        self.assertNotIn(
            "REPOSITORY_FORENSIC_BLOCK",
            set(b.blocker_class for b in snap.blockers))


class TestHandoff(unittest.TestCase):
    def test_real_state_waits_for_data(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 7000), fills=0)
        self.assertEqual(snap.overall_readiness, "BLOCKED")
        self.assertEqual(snap.handoff_state, "WAITING_FOR_DATA")

    def test_hypotheses_wait_when_data_sufficient(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 300000), fills=0)
        self.assertEqual(snap.handoff_state, "WAITING_FOR_HYPOTHESES")

    def test_ready_for_preregistration_when_unbound(self):
        import copy
        pre = mk_prereg([mk_hypothesis("FIX-H-01")])
        drifted = copy.copy(pre)
        object.__setattr__(drifted, "oos_boundary", OOS_START + 60)
        dataset = R.observe_dataset(mk_rows(OOS_START, 300000),
                                    GATE_A_END, frozenset())
        snap = M.run_monitor(
            drifted, dataset=dataset, dataset_identity="fixture",
            fills_observed=60, economics=dict(ECONOMICS_VERIFIED),
            microstructure=("VERIFIED", "fixture"),
            provenance=dict(PROV_DIRECT), latest_stored_timestamp=1,
            source_rows=[], repository_forensic_status="VERIFIED")
        self.assertEqual(snap.handoff_state, "READY_FOR_PREREGISTRATION")

    def test_ready_terminal_never_executes(self):
        # The module exposes no execution entry point at all.
        for name in ("run_oos", "execute", "execute_oos",
                     "run_frozen_oos", "start_execution"):
            self.assertFalse(hasattr(M, name), name)
        self.assertFalse(hasattr(R, "run_oos"))
        snap = run_snapshot(rows=mk_rows(OOS_START, 300000), fills=60,
                            hypotheses=[mk_hypothesis("FIX-H-01")],
                            economics=dict(ECONOMICS_VERIFIED),
                            micro=("VERIFIED", "fixture"), repo="VERIFIED")
        self.assertEqual(snap.handoff_state, "READY_FOR_OOS_EXECUTION")
        self.assertEqual(snap.overall_readiness, "READINESS_VERIFIED")
        self.assertEqual(snap.blockers, ())


class TestSourceCondition(unittest.TestCase):
    def test_no_new_source_data(self):
        state, newest = M.source_status(10000, mk_rows(100, 50))
        self.assertEqual(state, "NO_NEW_SOURCE_DATA")
        self.assertEqual(newest, 100 + 49 * 60)

    def test_current_when_source_advances(self):
        state, newest = M.source_status(
            100, mk_rows(100, 50))
        self.assertEqual(state, "CURRENT")
        self.assertEqual(newest, 100 + 49 * 60)

    def test_snapshot_carries_source_status(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 100), fills=0,
                            stored=OOS_START + 100 * 60)
        self.assertEqual(snap.source_status, "NO_NEW_SOURCE_DATA")
        self.assertEqual(snap.latest_observed_timestamp,
                         OOS_START + 100 * 60)


class TestLookaheadMonitor(unittest.TestCase):
    def test_a_future_mutation_preserves_earlier_snapshot(self):
        base = mk_rows(OOS_START, 600)
        mutated = [dict(r) for r in base]
        for row in mutated[300:]:
            row["close"] = float(row["close"]) * 2.0
        snap_before = run_snapshot(rows=base[:300], fills=0)
        snap_after = run_snapshot(rows=mutated[:300], fills=0)
        self.assertEqual(snap_before.snapshot_id,
                         snap_after.snapshot_id)

    def test_b_future_metadata_ignored(self):
        plain = mk_rows(OOS_START, 200)
        tagged = [dict(r, regime_label="FUTURE", funding_rate=2.0)
                  for r in plain]
        self.assertEqual(
            run_snapshot(rows=plain, fills=0).snapshot_id,
            run_snapshot(rows=tagged, fills=0).snapshot_id)

    def test_c_reorder_identical_snapshot(self):
        rows = mk_rows(OOS_START, 1000)
        self.assertEqual(
            run_snapshot(rows=rows, fills=0).snapshot_id,
            run_snapshot(rows=list(reversed(rows)),
                         fills=0).snapshot_id)

    def test_d_duplicates_explicit(self):
        rows = mk_rows(OOS_START, 500) + [
            dict(mk_rows(OOS_START, 1)[0])]
        snap = run_snapshot(rows=rows, fills=0)
        zero = [b for b in snap.blockers
                if b.gate_id == "zero_overlap"]
        self.assertTrue(zero)
        self.assertIn("duplicates=1", zero[0].detail)

    def test_e_synthetic_without_provenance_blocked(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 300000), fills=60,
                            hypotheses=[mk_hypothesis("FIX-H-01")],
                            economics=dict(ECONOMICS_VERIFIED),
                            micro=("VERIFIED", "fixture"),
                            provenance={"tier": "SYNTHETIC"},
                            repo="VERIFIED")
        prov = [b for b in snap.blockers
                if b.gate_id == "dataset_provenance"]
        self.assertEqual(len(prov), 1)
        self.assertEqual(prov[0].blocker_class,
                         "OPERATOR_PREREQUISITE")

    def test_f_boundary_equality_not_fresh(self):
        rows = ([{"time": GATE_A_END, "open": 1.0, "high": 1.0,
                  "low": 1.0, "close": 1.0, "volume": 1.0}]
                + mk_rows(OOS_START, 500))
        snap = run_snapshot(rows=rows, fills=0)
        self.assertEqual(snap.available_fresh_bars, 500)
        self.assertEqual(snap.oos_window_start, OOS_START)


class TestMonitorIsolation(unittest.TestCase):
    def test_no_production_surface(self):
        # AST-level check (not substring matching, which trips on
        # documentation prose): no wall-clock/random/UUID imports
        # or calls, no production modules, no order tokens.
        path = (ROOT / "core" / "research" / "readiness"
                / "monitor.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0]
                                for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    called.add(func.attr)
                elif isinstance(func, ast.Name):
                    called.add(func.id)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(
            imported & {"datetime", "time", "random", "uuid",
                        "live", "execution", "broker", "monitoring"},
            set())
        self.assertEqual(
            called & {"now", "time", "uuid4", "random", "seed",
                      "place_order", "submit_order"}, set())
        for token in ("BrokerEngine", "DeltaOrderExecutor",
                      "LIVE_EXECUTE", "DELTA_API_KEY",
                      "DELTA_API_SECRET", "run_frozen_oos"):
            self.assertNotIn(token, text)
        self.assertNotIn("run_frozen_oos", text)

    def test_never_production_ready(self):
        snap = run_snapshot(rows=mk_rows(OOS_START, 100), fills=0)
        self.assertIs(snap.is_production_ready, False)
        self.assertTrue(snap.production_isolation)


class TestRealSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (TOPUP, TOPUP_PROV):
            if not path.exists():
                raise unittest.SkipTest("top-up cache absent")

    def test_real_snapshot_blocked_with_gap(self):
        env = json.loads(TOPUP.read_text(encoding="utf-8"))
        prov = json.loads(TOPUP_PROV.read_text(encoding="utf-8"))
        discovery = None
        if GATE_CACHE.exists():
            with io.open(str(GATE_CACHE), encoding="utf-8") as fh:
                discovery = frozenset(
                    r["time"] for r in json.load(fh).get("raw", [])
                    if isinstance(r, dict)
                    and isinstance(r.get("time"), int))
        from core.research.readiness.preregistration import (
            FrozenPreregistration)
        pre = FrozenPreregistration.create(
            hypotheses=(), dataset_identity=env["dataset_identity"],
            discovery_boundary=GATE_A_END, oos_boundary=OOS_START,
            minimum_contiguous_bars=R.REQUIRED_CONTIGUOUS_CLEAN_BARS,
            minimum_fresh_bars=int(R.required_fresh_bars()),
            economics_requirements=tuple(R.ECONOMICS_FIELDS),
            multiple_testing_family="Sidak-9L",
            frozen_execution_semantics="run_frozen_oos/9M",
            limitations=("no eligible real hypotheses",))
        dataset = R.observe_dataset(env["raw"], GATE_A_END, discovery)
        venue = json.loads((ROOT / "data" / "fixtures" / "delta"
                            / "delta_venue_economics_observation_"
                            "20260925.json").read_text(encoding="utf-8"))
        economics = {}
        for field in R.ECONOMICS_FIELDS:
            entry = venue.get(field, {})
            economics[field] = (
                entry.get("status", "UNAVAILABLE"),
                "venue observation")
        snap = M.run_monitor(
            pre, dataset=dataset,
            dataset_identity=env["dataset_identity"],
            fills_observed=0, economics=economics,
            microstructure=("UNAVAILABLE", "OHLCV-only adapters"),
            provenance=prov,
            latest_stored_timestamp=max(
                r["time"] for r in env["raw"]),
            source_rows=[],
            repository_forensic_status="BLOCKED")
        self.assertEqual(snap.overall_readiness, "BLOCKED")
        self.assertEqual(snap.handoff_state, "WAITING_FOR_DATA")
        self.assertEqual(snap.required_fresh_bars, 300000)
        # Structural properties of the current cache (no hard-pinned
        # counts: operator re-runs extend the cache lawfully).
        self.assertEqual(snap.available_fresh_bars, len(env["raw"]))
        self.assertEqual(snap.fresh_bar_gap,
                         300000 - len(env["raw"]))
        self.assertGreater(len(env["raw"]), 11899)
        self.assertEqual(snap.required_fills, 60)
        self.assertEqual(snap.available_fills, 0)
        self.assertEqual(snap.fill_gap, 60)
        self.assertEqual(snap.hypothesis_count, 0)
        self.assertEqual(snap.source_status, "NO_NEW_SOURCE_DATA")
        self.assertEqual(snap.dataset_id, env["dataset_identity"])
        import hashlib
        blob = json.dumps(
            sorted(env["raw"], key=lambda r: r["time"]),
            sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                         env["dataset_identity"])
        classes = set(b.blocker_class for b in snap.blockers)
        for expected in ("DATA_TIME_BOUND", "NO_ELIGIBLE_HYPOTHESES",
                         "NO_FILLS", "ECONOMICS_UNAVAILABLE",
                         "MICROSTRUCTURE_UNAVAILABLE",
                         "REPOSITORY_FORENSIC_BLOCK"):
            self.assertIn(expected, classes)


if __name__ == "__main__":
    unittest.main()
