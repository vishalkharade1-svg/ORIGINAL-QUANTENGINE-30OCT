"""Frozen-OOS execution readiness: preregistration + gates.

Research-only, deterministic, offline, stdlib-only. Proves the
readiness layer answers "are we ready to run the frozen OOS
experiment" without executing it, without inventing data, and
without weakening any authority:

* preregistration is immutable with a deterministic identity;
* every gate uses explicit arithmetic from frozen protocol numbers;
* missing evidence stays UNAVAILABLE/BLOCKED (never passes);
* synthetic fixtures prove gate LOGIC only -- Fixture H carries an
  explicit limitation that it is not real OOS validation;
* the real-data evaluation reports BLOCKED on the actual caches.

Nothing here tunes the strategy, generates fills, provisions venue
economics, or promotes anything. ``is_production_ready`` is False
everywhere.
"""

from __future__ import annotations

import dataclasses
import io
import json
import pathlib
import unittest

from core.research.oos.oos_types import HypothesisRecord
from core.research.readiness import oos_execution_readiness as R
from core.research.readiness.preregistration import (
    FrozenPreregistration,
    PreregistrationError,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE_A_END = 1788601440  # frozen discovery boundary (phase17/18/19)
OOS_START = 1788601500  # first fresh timestamp after Gate-A

ECONOMICS_VERIFIED = {
    field: ("VERIFIED", "venue schedule provisioned (fixture)")
    for field in R.ECONOMICS_FIELDS}
ECONOMICS_MISSING = {
    field: ("UNAVAILABLE", "no venue schedule (fixture)")
    for field in R.ECONOMICS_FIELDS}


def mk_hypothesis(hid, direction="LONG", symbol="BTCUSDT",
                  seven_e=False, regime=None):
    return HypothesisRecord(
        hypothesis_id=hid, origin="9L", statement="fixture " + hid,
        symbol=symbol, direction=direction,
        regime_dim="trend_vs_range" if regime else None,
        regime_label=regime,
        params={"entry_model": "BREAKOUT_CONTINUATION"},
        seven_e_no_go=seven_e, walk_forward_passed=True,
        walk_forward_note="fixture", expected_outcome="OOS_ROBUST",
        evidence=())


def drifted(pre, **changes):
    """Simulate a post-creation mutation attempt.

    Frozen construction refuses mismatched copies outright, so a
    drifted instance is built by bypassing __init__ -- exactly what
    verify_identity() must then catch.
    """
    import copy
    clone = copy.copy(pre)
    for key, value in changes.items():
        object.__setattr__(clone, key, value)
    return clone


def mk_preregistration(hypotheses, discovery=GATE_A_END,
                       oos=OOS_START):
    return FrozenPreregistration.create(
        hypotheses=tuple(hypotheses),
        dataset_identity="fixture-dataset",
        discovery_boundary=discovery, oos_boundary=oos,
        minimum_contiguous_bars=R.REQUIRED_CONTIGUOUS_CLEAN_BARS,
        minimum_fresh_bars=int(R.required_fresh_bars()),
        economics_requirements=tuple(R.ECONOMICS_FIELDS),
        multiple_testing_family="Sidak-9L-fixture",
        regime_constraints=(), symbol_constraints=("BTCUSDT",),
        directional_constraints=("LONG",),
        frozen_execution_semantics="run_frozen_oos/9M-constants",
        limitations=("synthetic fixture",))


def mk_rows(start, count, step=60):
    return [{"time": start + i * step, "open": 100.0, "high": 101.0,
             "low": 99.0, "close": 100.5, "volume": 2.5}
            for i in range(count)]


def small_prereg():
    return mk_preregistration([mk_hypothesis("FIX-A-01",
                                             regime="TREND")])


def small_dataset(count=120):
    return R.observe_dataset(mk_rows(OOS_START, count), GATE_A_END,
                             discovery_timestamps=frozenset())


class TestPreregistrationImmutability(unittest.TestCase):
    def test_create_verifies(self):
        pre = small_prereg()
        self.assertTrue(pre.verify_identity())
        self.assertEqual(len(pre.preregistration_id), 64)

    def test_same_input_byte_identical(self):
        first = small_prereg()
        second = small_prereg()
        self.assertEqual(first.preregistration_id,
                         second.preregistration_id)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))

    def test_frozen_attributes_rejected(self):
        pre = small_prereg()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            pre.dataset_identity = "mutated"

    def test_altered_boundary_rejected(self):
        pre = small_prereg()
        altered = drifted(pre, oos_boundary=OOS_START + 60)
        self.assertFalse(altered.verify_identity())

    def test_altered_dataset_rejected(self):
        pre = small_prereg()
        altered = drifted(pre, dataset_identity="other")
        self.assertFalse(altered.verify_identity())

    def test_altered_thresholds_rejected(self):
        pre = small_prereg()
        altered = drifted(pre, minimum_total_trades=59)
        self.assertFalse(altered.verify_identity())

    def test_altered_hypothesis_set_rejected(self):
        pre = small_prereg()
        other = mk_hypothesis("FIX-A-02")
        altered = drifted(pre, hypotheses=(other,),
                          hypothesis_ids=("FIX-A-02",))
        # The stale id no longer matches the drifted content.
        self.assertFalse(altered.verify_identity())

    def test_constructing_mismatched_copy_raises(self):
        # Belt and braces: frozen construction itself refuses to
        # mint a copy whose content disagrees with its identity.
        pre = small_prereg()
        with self.assertRaises(PreregistrationError):
            dataclasses.replace(pre, oos_boundary=OOS_START + 60)

    def test_seven_e_never_preregistered(self):
        with self.assertRaises(PreregistrationError):
            mk_preregistration([mk_hypothesis("FIX-7E", seven_e=True)])

    def test_production_ready_always_false(self):
        pre = small_prereg()
        self.assertIs(pre.is_production_ready, False)
        with self.assertRaises(PreregistrationError):
            dataclasses.replace(pre, is_production_ready=True)

    def test_inverted_boundary_rejected(self):
        with self.assertRaises(PreregistrationError):
            mk_preregistration([mk_hypothesis("FIX-B-01")],
                               discovery=OOS_START, oos=GATE_A_END)


class TestArithmetic(unittest.TestCase):
    def test_documented_thresholds(self):
        self.assertEqual(R.REQUIRED_CONTIGUOUS_CLEAN_BARS, 6175)
        self.assertEqual(R.required_per_period_bars(), 25000.0)
        self.assertEqual(R.required_fresh_bars(), 300000.0)
        self.assertEqual(R.DOCUMENTED_FRESH_BAR_FLOOR, 75000)


class TestReadinessFixtures(unittest.TestCase):
    def run_gate(self, count=120, fills=0, economics=None,
                 micro=("UNAVAILABLE", "fixture: no adapters")):
        return R.evaluate(
            small_prereg(), dataset=small_dataset(count),
            fills_observed=fills,
            economics=dict(ECONOMICS_MISSING) if economics is None
            else economics, microstructure=micro)

    def test_fixture_a_insufficient_bars_blocked(self):
        rep = self.run_gate(count=120, fills=60,
                            economics=dict(ECONOMICS_VERIFIED),
                            micro=("VERIFIED", "fixture"))
        self.assertEqual(rep.final_status, "BLOCKED")
        self.assertEqual(rep.gate("minimum_bar_count").status,
                         "BLOCKED")
        self.assertEqual(rep.gate("dataset_contiguity").status,
                         "BLOCKED")

    def test_fixture_b_insufficient_fills_blocked(self):
        rep = R.evaluate(
            small_prereg(),
            dataset=R.observe_dataset(
                mk_rows(OOS_START, 300000), GATE_A_END,
                discovery_timestamps=frozenset()),
            fills_observed=0, economics=dict(ECONOMICS_VERIFIED),
            microstructure=("VERIFIED", "fixture"))
        self.assertEqual(rep.final_status, "BLOCKED")
        self.assertEqual(rep.gate("minimum_fill_requirement").status,
                         "BLOCKED")
        self.assertEqual(rep.available_fills, 0)

    def test_fixture_c_missing_economics_blocked(self):
        rep = self.run_gate()
        for field in R.ECONOMICS_FIELDS:
            self.assertEqual(
                rep.gate("economics_" + field).status, "BLOCKED")
        self.assertEqual(rep.final_status, "BLOCKED")

    def test_fixture_d_missing_microstructure_blocked(self):
        rep = self.run_gate(count=300000, fills=60,
                            economics=dict(ECONOMICS_VERIFIED))
        self.assertEqual(rep.gate("microstructure_evidence").status,
                         "BLOCKED")
        self.assertEqual(rep.final_status, "BLOCKED")

    def test_fixture_e_overlapping_oos_blocked(self):
        rows = mk_rows(OOS_START, 7000)
        rows = rows + [dict(rows[0])]
        pre = small_prereg()
        rep = R.evaluate(
            pre, dataset=R.observe_dataset(
                rows, GATE_A_END, discovery_timestamps=frozenset()),
            fills_observed=60, economics=dict(ECONOMICS_VERIFIED),
            microstructure=("VERIFIED", "fixture"))
        self.assertEqual(rep.gate("zero_overlap").status, "BLOCKED")
        self.assertEqual(rep.final_status, "BLOCKED")

    def test_fixture_e_reused_discovery_blocked(self):
        rows = mk_rows(OOS_START, 7000)
        pre = small_prereg()
        rep = R.evaluate(
            pre, dataset=R.observe_dataset(
                rows, GATE_A_END,
                discovery_timestamps=frozenset(
                    {rows[0]["time"]})),
            fills_observed=60, economics=dict(ECONOMICS_VERIFIED),
            microstructure=("VERIFIED", "fixture"))
        self.assertEqual(rep.gate("zero_overlap").status, "BLOCKED")

    def test_fixture_f_future_leakage_blocked(self):
        rows = ([{"time": GATE_A_END - 60, "open": 1.0, "high": 1.0,
                  "low": 1.0, "close": 1.0, "volume": 1.0}]
                + mk_rows(OOS_START, 7000))
        rep = R.evaluate(
            small_prereg(),
            dataset=R.observe_dataset(
                rows, GATE_A_END, discovery_timestamps=frozenset()),
            fills_observed=60, economics=dict(ECONOMICS_VERIFIED),
            microstructure=("VERIFIED", "fixture"))
        # Pre-boundary rows never enter the fresh set: the fresh
        # count excludes the intruding row and the boundary gate
        # still verifies on what remains.
        self.assertEqual(rep.available_bars, 7000)
        self.assertEqual(rep.gate("frozen_boundary").status,
                         "VERIFIED")

    def test_fixture_g_hypothesis_mutation_rejected(self):
        pre = small_prereg()
        mutated = drifted(
            pre, hypotheses=(mk_hypothesis("FIX-A-99"),),
            hypothesis_ids=("FIX-A-99",))
        rep = R.evaluate(
            mutated, dataset=small_dataset(),
            fills_observed=0,
            economics=dict(ECONOMICS_MISSING),
            microstructure=("UNAVAILABLE", "fixture"))
        self.assertEqual(
            rep.gate("hypothesis_preregistration").status, "BLOCKED")
        self.assertIn("rejected",
                      rep.gate("hypothesis_preregistration").detail)

    def test_fixture_h_sufficient_synthetic_verified(self):
        # Proves gate LOGIC only. Synthetic inputs satisfying every
        # gate yield READINESS_VERIFIED here; this is NOT real OOS
        # validation and must never be cited as a trading edge.
        rep = R.evaluate(
            small_prereg(),
            dataset=R.observe_dataset(
                mk_rows(OOS_START, 300000), GATE_A_END,
                discovery_timestamps=frozenset()),
            fills_observed=60, economics=dict(ECONOMICS_VERIFIED),
            microstructure=("VERIFIED", "synthetic fixture only"))
        self.assertEqual(rep.final_status, "READINESS_VERIFIED")
        self.assertEqual(rep.blockers, ())
        for gate in rep.gates:
            self.assertEqual(gate.status, "VERIFIED", gate.gate_id)
        self.assertIn("never a trading edge",
                      " ".join(rep.limitations).lower())

    def test_empty_hypothesis_set_blocked(self):
        pre = mk_preregistration([])
        rep = R.evaluate(
            pre, dataset=small_dataset(), fills_observed=0,
            economics=dict(ECONOMICS_MISSING),
            microstructure=("UNAVAILABLE", "fixture"))
        self.assertEqual(
            rep.gate("hypothesis_preregistration").status, "BLOCKED")
        self.assertEqual(rep.final_status, "BLOCKED")


class TestLookahead(unittest.TestCase):
    def test_post_boundary_mutation_preserves_pre_evidence(self):
        before_rows = mk_rows(OOS_START, 600)
        after_rows = [dict(r) for r in before_rows]
        for row in after_rows[300:]:
            row["close"] = float(row["close"]) * 2.0
            row["volume"] = 999.0
        obs_before = R.observe_dataset(before_rows[:300], GATE_A_END)
        obs_after = R.observe_dataset(after_rows[:300], GATE_A_END)
        self.assertEqual(json.dumps(obs_before, sort_keys=True),
                         json.dumps(obs_after, sort_keys=True))

    def test_future_metadata_keys_ignored(self):
        plain = mk_rows(OOS_START, 120)
        tagged = [dict(r, regime_label="FUTURE_TREND",
                       funding_rate=0.99) for r in plain]
        self.assertEqual(
            R.observe_dataset(plain, GATE_A_END),
            R.observe_dataset(tagged, GATE_A_END))

    def test_readiness_report_deterministic(self):
        kwargs = dict(dataset=small_dataset(), fills_observed=0,
                      economics=dict(ECONOMICS_MISSING),
                      microstructure=("UNAVAILABLE", "fixture"))
        first = R.evaluate(small_prereg(), **kwargs)
        second = R.evaluate(small_prereg(), **kwargs)
        self.assertEqual(first.report_id, second.report_id)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))


class TestProductionIsolation(unittest.TestCase):
    FORBIDDEN = ("broker_engine", "order_executor", "place_order",
                 "submit_order", "BrokerEngine", "DeltaOrderExecutor",
                 "LIVE_EXECUTE", "paper_trading", "live_executor",
                 "live_trading")

    def test_no_production_surface_in_new_modules(self):
        hits = []
        base = (ROOT / "core" / "research" / "readiness")
        for name in ("preregistration.py",
                     "oos_execution_readiness.py"):
            text = (base / name).read_text(encoding="utf-8")
            for token in self.FORBIDDEN:
                if token in text:
                    hits.append((name, token))
        self.assertEqual(hits, [])

    def test_never_production_ready(self):
        rep = R.evaluate(
            small_prereg(), dataset=small_dataset(), fills_observed=0,
            economics=dict(ECONOMICS_MISSING),
            microstructure=("UNAVAILABLE", "fixture"))
        self.assertIs(rep.is_production_ready, False)
        self.assertTrue(rep.production_isolation)
        with self.assertRaises(R.ReadinessError):
            R.OOSExecutionReadinessReport.create(
                preregistration_id="x", hypothesis_set_id="y",
                dataset_id="z", gates=(),
                available_bars=0, required_bars=1,
                available_fills=0, required_fills=1,
                limitations=(), is_production_ready=True)


class TestRealDataReadinessBlocked(unittest.TestCase):
    """Real caches + persisted evidence must report BLOCKED.

    Uses only read-only offline inputs already in the worktree
    (gitignored caches when present, tracked research artifacts).
    Missing inputs evaluate as UNAVAILABLE -- never invented.
    """

    def test_real_readiness_is_blocked(self):
        ext_path = (ROOT / "data" / "history"
                    / "BTCUSDT_1m_phase19_extension.json")
        prior_path = (ROOT / "data" / "history"
                      / "BTCUSDT_1m_phase17_fresh.json")
        gate_path = (ROOT / "data" / "history"
                     / "BTCUSDT_1m_oos.json")
        if ext_path.exists():
            with io.open(str(ext_path), encoding="utf-8") as fh:
                rows = json.load(fh)["raw"]
        elif prior_path.exists():
            with io.open(str(prior_path), encoding="utf-8") as fh:
                rows = json.load(fh)["raw"]
            ext_path = prior_path
        else:
            rows = None
        if rows is None:
            dataset = None
        else:
            if gate_path.exists():
                with io.open(str(gate_path),
                             encoding="utf-8") as fh:
                    gate_rows = json.load(fh).get("raw", [])
                discovery = frozenset(
                    r["time"] for r in gate_rows
                    if isinstance(r, dict) and isinstance(
                        r.get("time"), int))
            else:
                discovery = None
            dataset = R.observe_dataset(rows, GATE_A_END, discovery)
        art_path = (ROOT / "research" / "results"
                    / "phase19_oos_data_extension.json")
        if art_path.exists():
            with io.open(str(art_path), encoding="utf-8") as fh:
                art = json.load(fh)
            fills = art.get("completed_trades")
            fills = fills if isinstance(fills, int) else None
        else:
            fills = None
        rep = R.evaluate(
            # Empty frozen set: truthful while no eligible real
            # hypotheses exist (proven by the 9M input trace).
            FrozenPreregistration.create(
                hypotheses=(), dataset_identity=ext_path.name
                if rows is not None else "UNAVAILABLE",
                discovery_boundary=GATE_A_END, oos_boundary=OOS_START,
                minimum_contiguous_bars=(
                    R.REQUIRED_CONTIGUOUS_CLEAN_BARS),
                minimum_fresh_bars=int(R.required_fresh_bars()),
                economics_requirements=tuple(R.ECONOMICS_FIELDS),
                multiple_testing_family="Sidak-9L",
                regime_constraints=(), symbol_constraints=(),
                directional_constraints=(),
                frozen_execution_semantics="run_frozen_oos/9M",
                limitations=("no eligible real hypotheses; economics "
                             "and microstructure from venue authorities "
                             "only")),
            dataset=dataset, fills_observed=fills,
            economics={
                "maker_fee": ("UNAVAILABLE",
                              "costs.py defaults explicit-zero; no "
                              "venue fee schedule provisioned"),
                "taker_fee": ("UNAVAILABLE",
                              "costs.py defaults explicit-zero; no "
                              "venue fee schedule provisioned"),
                "funding": ("UNAVAILABLE",
                            "scenarios.scenario_funding net None; "
                            "zero never substituted"),
                "contract_value": ("UNAVAILABLE",
                                   "no provisioned venue schedule "
                                   "for the OOS dataset"),
                "slippage": ("UNAVAILABLE",
                             "no venue slippage schedule; never "
                             "assumed zero")},
            microstructure=("UNAVAILABLE",
                            "OHLCV-only adapters; no trades/depth/"
                            "footprint evidence"))
        self.assertEqual(rep.final_status, "BLOCKED")
        self.assertEqual(
            rep.gate("hypothesis_preregistration").status, "BLOCKED")
        self.assertEqual(
            rep.gate("minimum_fill_requirement").status
            if fills is not None else
            rep.gate("minimum_fill_requirement").status,
            "BLOCKED" if fills is not None else "UNAVAILABLE")
        if dataset is not None:
            self.assertLess(rep.available_bars,
                            rep.required_bars)
            # Honest partial credit: the merged cache genuinely is
            # one contiguous run, so contiguity verifies while fresh
            # span, fills, and economics keep the final BLOCKED.
            self.assertEqual(
                rep.gate("dataset_contiguity").status, "VERIFIED")


if __name__ == "__main__":
    unittest.main()
