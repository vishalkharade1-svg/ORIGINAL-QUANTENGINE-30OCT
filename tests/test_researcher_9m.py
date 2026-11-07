"""
====================================================================

QuantEngine

Phase 9M -- Multi-Period Out-of-Sample Validation tests

Proves the deterministic, research-only 9M re-validation layer that
consumes frozen 9J / 9K / 9L discoveries and replays each against 6
trailing, non-overlapping, CHRONOLOGICAL out-of-sample periods through
the frozen 9C counterfactual machinery, always against the frozen
BREAKOUT_CONTINUATION production baseline:

   * the locked protocol: 6 OOS periods over the trailing 50%,
     discovery = leading 50% (SPLIT_PROTOCOL_FROZEN), 30 opportunities
     + 10 trades per settled period, 60 minimum total trades, 5/6
     survival, 5/6 sign-consistent periods; no shuffle / no
     randomization / no split re-optimization;
   * the closed ladder: BLOCKED / UNAVAILABLE / INCONCLUSIVE /
     REJECTED / OOS_PARTIAL / OOS_PROMISING / OOS_ROBUST /
     VALIDATED_RESEARCH_ONLY -- with every failure and limitation kept
     visible;
   * a 7E-NO-GO hypothesis is BLOCKED and can never be resurrected;
   * the familywise (Sidak) correction is applied across the whole
     re-validated family and reported WITH its family size;
   * a recovered/missed baseline / MAE trade-off surface is retained,
     never hidden;
   * outcome = decision-time only, byte-repeatable: identical reruns
     produce identical frozen reports and divergent FUTURE bars beyond
     every decision/fill produce byte-identical reports (no lookahead);
   * production isolation: is_production_ready always raises and
     emission_check is always clean (research-only, never emitted);
   * deterministic e2e fixture locks: 864 opportunities / 432 discovery
     / 432 OOS / 6x72 periods / report ids / Sisak numbers -- a clean
     6/6 all-WIN hypothesis (X/LONG, LIMIT_RETEST) validates
     VALIDATED_RESEARCH_ONLY (HIGH); the same without the 9K
     walk-forward declaration is OOS_ROBUST; seven_e_no_go is BLOCKED;
     an unclaimed SHORT is UNAVAILABLE.

Uses ONLY the real 9A-9M machinery and genuine counterfactual
simulation. Stdlib only; offline; deterministic.
====================================================================
"""

import math
import os
import re
import unittest
from dataclasses import FrozenInstanceError

from core.research.oos import (
    ALPHA,
    CANDIDATE_ALTERNATIVES,
    DISCOVERY_FRACTION,
    MIN_OOS_OPPORTUNITIES_PER_PERIOD,
    MIN_OOS_TRADES_PER_PERIOD,
    MIN_SURVIVING_PERIODS,
    MIN_TOTAL_OOS_TRADES,
    OOS_PERIODS,
    OOS_STATUSES,
    PERIOD_STATUSES,
    REQUIRED_SIGN_CONSISTENT_PERIODS,
    SPLIT_PROTOCOL_FROZEN,
    HypothesisRecord,
    OosValidationEngine,
    OosReport,
    partition,
)
from core.research.oos.aggregator import (
    final_status,
    multiple_testing,
    summarize_periods,
)
from core.research.oos.engine import _DEFAULT_GATES
from core.research.oos.oos_types import OosPeriodEvidence
from core.research.oos.period import outcome_leakage
from core.research.oos.report import NEVER_EMITTED
from core.research.oos.validator import evaluate_pool
from core.research.journal import OpportunityRecord


class _C(object):
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open, self.high, self.low = o, h, l
        self.close, self.timestamp = c, ts


# ------------------------------------------------------------------
# Deterministic e2e fixture
# ------------------------------------------------------------------
# entry 100, stop 98, target 104, FIXED_RR rr=2.0. 4-bar blocks,
# decision bar = block 0 (index i*4).

WIN = [
    (99.5, 100.5, 99.2, 100.0),
    (100.0, 100.5, 99.5, 100.2),   # LIMIT fill@100; BRK trigger, fill open+2=100
    (100.0, 106.0, 99.0, 105.0),
    (101.0, 102.0, 100.5, 101.5),
]
LOSS = [
    (99.5, 100.5, 99.2, 100.0),
    (100.0, 100.5, 99.5, 100.2),
    (99.0, 100.5, 96.5, 97.0),     # both hit stop 98 -> LOSS
    (100.0, 100.5, 99.5, 100.0),
]
RECOVERY = [
    (99.5, 100.5, 99.2, 100.0),
    (100.0, 101.0, 99.5, 99.5),    # LIMIT fill@100; BRK close 99.5 not>100 (missed)
    (100.0, 108.0, 99.0, 107.0),   # LIMIT reaches target 104 -> WIN
    (101.0, 102.0, 100.5, 101.5),
]

BLOCKS = {"W": WIN, "L": LOSS, "R": RECOVERY}


def mk_record(symbol, seq, decision, motif):
    trade = {
        "result": "UNSETTLED", "pnl": 0.0, "risk_amount": 2.0,
        "entry_bar": decision + 1, "exit_bar": decision + 1,
        "bars_held": 1, "r": 0.0, "exit_price": 0.0,
    }
    return OpportunityRecord(
        canonical_id="9m-%s-%s-%04d" % (symbol, motif, seq),
        exchange="TESTEX", instrument_id=symbol, timeframe="1m",
        direction="BULLISH", strategy="BREAKOUT_CONTINUATION",
        setup_id="9m-%s-%s-%04d" % (symbol, motif, seq),
        setup={
            "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
            "risk_reward": 2.0, "bar": decision, "atr": 4.0,
            "rejection_reasons": [],
        },
        order={}, trade=trade, terminal_outcome="ORDER_NOT_CREATED",
    )


def build_records(oos_mix=None):
    """Cost-free discovery half (all-WIN) + provided OOS motif mix."""
    out = []
    seq = 0
    for i in range(432):
        out.append(mk_record("X", seq, i * 4, "W"))
        seq += 1
    if oos_mix is None:
        oos_mix = [["W"] * 72 for _ in range(6)]
    for pi, period in enumerate(oos_mix):
        for mi, motif in enumerate(period):
            out.append(mk_record(
                "X", seq, (432 + pi * 72 + mi) * 4, motif))
            seq += 1
    return out


def build_candles_for(records):
    bars = {}
    for i, rec in enumerate(records):
        b0 = i * 4
        motif = rec.canonical_id.split("-")[2]
        for off, (o, h, l, c) in enumerate(BLOCKS[motif]):
            bars[b0 + off] = _C(o, h, l, c, b0 + off)
    n_slots = (len(records) - 1) * 4 + 4
    series = [bars.get(i, _C(100, 100, 100, 100, i))
              for i in range(n_slots)]
    series.append(_C(100, 100, 100, 100, n_slots))
    series.append(_C(100, 100, 100, 100, n_slots + 1))
    return series


ALL_WIN = build_records()
ALL_WIN_CANDLES = build_candles_for(ALL_WIN)
BASE_CONFIG = {"rr": 2.0, "stop_mode": "EXISTING_STOP",
               "target_mode": "FIXED_RR", "expiry": 1}


def make_hyp(origin="9K", entry_model="LIMIT_RETEST", symbol="X",
             direction="LONG", wf=False, seven_e=False, statement="s",
             reg=None):
    params = {
        "entry_model": entry_model, "rr": 2.0,
        "stop_mode": "EXISTING_STOP", "target_mode": "FIXED_RR",
        "expiry": 1,
    }
    k = dict(origin=origin, statement=statement, symbol=symbol,
             direction=direction, params=params,
             seven_e_no_go=seven_e, walk_forward_passed=wf)
    if reg:
        k["regime_dim"], k["regime_label"] = reg
    return HypothesisRecord(**k)


def run(variant_kwargs=None, oos_mix=None):
    eng = OosValidationEngine()
    records = build_records(oos_mix=oos_mix) if oos_mix else ALL_WIN
    candles = build_candles_for(records) if oos_mix else ALL_WIN_CANDLES
    kwargs = dict(statement="clean long recovery", origin="9K",
                  entry_model="LIMIT_RETEST", symbol="X", direction="LONG",
                  wf=True)
    if variant_kwargs:
        kwargs.update(variant_kwargs)
    return eng.run(records, candles, BASE_CONFIG,
                   [make_hyp(**kwargs)], outcome_bars=2)


def divergent_future(records, candles):
    import copy
    modified = []
    for b in candles:
        modified.append(_C(b.open, b.high, b.low, b.close, b.timestamp))
    for i in range(len(modified) - 12, len(modified)):
        modified[i].close = modified[i].close + 50.0
    return modified


# ------------------------------------------------------------------
# locked-contract surface tests
# ------------------------------------------------------------------

class TestProtocolSurface(unittest.TestCase):
    def test_locked_protocol_defaults(self):
        self.assertTrue(SPLIT_PROTOCOL_FROZEN)
        self.assertEqual(OOS_PERIODS, 6)
        self.assertEqual(DISCOVERY_FRACTION, 0.5)
        self.assertEqual(MIN_OOS_OPPORTUNITIES_PER_PERIOD, 30)
        self.assertEqual(MIN_OOS_TRADES_PER_PERIOD, 10)
        self.assertEqual(MIN_TOTAL_OOS_TRADES, 60)
        self.assertEqual(MIN_SURVIVING_PERIODS, 5)
        self.assertEqual(REQUIRED_SIGN_CONSISTENT_PERIODS, 5)
        self.assertEqual(CANDIDATE_ALTERNATIVES,
                         ("LIMIT_RETEST", "MARKET_CONFIRMATION",
                          "BREAKOUT_CONTINUATION"))
        self.assertEqual(ALPHA, 0.05)

    def test_closed_status_vocabularies(self):
        self.assertEqual(PERIOD_STATUSES,
                         ("VALIDATED", "PROMISING", "INCONCLUSIVE",
                          "REJECTED", "UNAVAILABLE"))
        self.assertEqual(OOS_STATUSES,
                         ("BLOCKED", "UNAVAILABLE", "INCONCLUSIVE",
                          "REJECTED", "OOS_PARTIAL", "OOS_PROMISING",
                          "OOS_ROBUST", "VALIDATED_RESEARCH_ONLY"))

    def test_default_gates_are_real_keys(self):
        for key in ("oos_periods", "discovery_fraction",
                    "min_oos_opportunities_per_period",
                    "min_oos_trades_per_period", "min_total_oos_trades",
                    "min_surviving_periods",
                    "required_sign_consistent_periods", "purge_bars",
                    "embargo_bars", "economic_delta_r",
                    "loss_rate_expansion", "alpha", "conclusive_only"):
            self.assertIn(key, _DEFAULT_GATES)

    def test_unknown_gate_key_fails_loudly(self):
        with self.assertRaises(ValueError):
            OosValidationEngine(gates={"bogus": 1})


class TestFamilywise(unittest.TestCase):
    def test_sidak_single(self):
        mt = multiple_testing(1, alpha=0.05)
        self.assertEqual(mt["family_size"], 1)
        self.assertAlmostEqual(mt["corrected_alpha"], 0.05, places=10)
        self.assertEqual(mt["method"], "Sidak-familywise")

    def test_sidak_multi(self):
        mt = multiple_testing(4, alpha=0.05)
        self.assertAlmostEqual(
            mt["corrected_alpha"], 0.012741455098566168, places=12)
        self.assertEqual(mt["survives_correction"], 4)

    def test_denominator_never_hidden(self):
        mt = multiple_testing(4)
        self.assertIn("family_size", mt)
        self.assertIn("note", mt)


class TestPartitionmath(unittest.TestCase):
    def test_deterministic_chronological_partition(self):
        p = partition(ALL_WIN)
        self.assertEqual(p.n_periods(), 6)
        self.assertEqual(len(p.ordered), 864)
        self.assertEqual(len(p.discovery), 432)
        self.assertEqual(sum(len(x) for x in p.oos_periods), 432)
        self.assertEqual([len(x) for x in p.oos_periods],
                         [72, 72, 72, 72, 72, 72])
        labels = [b.label for b in p.boundaries]
        self.assertEqual(labels[0], "DISCOVERY")
        self.assertEqual(
            labels[1:], ["OOS-1", "OOS-2", "OOS-3", "OOS-4", "OOS-5",
                         "OOS-6"])
        d = p.to_dict()
        self.assertTrue(d["chronological"])
        self.assertTrue(d["no_shuffle"])
        self.assertEqual(d["discovery_fraction"], 0.5)
        self.assertEqual(d["n_oos_periods"], 6)

    def test_partition_requires_at_least_two(self):
        with self.assertRaises(ValueError):
            partition(ALL_WIN[:1])

    def test_leakage_not_required_when_no_horizon(self):
        p = partition(ALL_WIN, outcome_bars=None, expiry=None)
        self.assertEqual(p.leak["status"], "NOT_REQUIRED")

    def test_leakage_protected_honest(self):
        p = partition(ALL_WIN, outcome_bars=2)
        self.assertEqual(p.leak["status"], "PROTECTED")
        self.assertEqual(p.leak["required_horizon_bars"], 2)
        self.assertGreaterEqual(p.leak["gap_bars"], p.leak["required_horizon_bars"])

    def test_time_key_stable_with_tie_break(self):
        p = partition(ALL_WIN)
        # chronological by decision bar
        bars = [r.setup["bar"] for r in p.ordered]
        self.assertEqual(bars, sorted(bars))


class TestAggregatorLadder(unittest.TestCase):
    def _h(self):
        return HypothesisRecord(origin="9K", statement="s", symbol="X",
                                direction="LONG",
                                params={"entry_model": "LIMIT_RETEST"})

    def _ev(self, status, d=0.0):
        return OosPeriodEvidence(
            period="x", n_opportunities=60, n_baseline_settled=60,
            n_baseline_missed=0, n_candidate_filled=60, n_trades=60,
            n_wins=30, n_losses=30, n_recovered=0, expectancy_delta=d,
            status=status, sample_sufficient=True,
            economic_acceptable=status != PERIOD_STATUSES[3])

    def test_blocked_when_seven_e(self):
        h = HypothesisRecord(origin="9K", statement="s", seven_e_no_go=True,
                             params={"entry_model": "LIMIT_RETEST"})
        st, _ = final_status(h, [self._ev(PERIOD_STATUSES[0])] * 6,
                             _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[0])

    def test_unavailable_when_no_evidence(self):
        st, _ = final_status(self._h(), [], _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[1])

    def test_inconclusive_when_nothing_settled(self):
        pe = [self._ev(PERIOD_STATUSES[2])] * 6
        st, _ = final_status(self._h(), pe, _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[2])

    def test_rejected_when_repeated_adverse(self):
        pe = [self._ev(PERIOD_STATUSES[3])] * 2 + \
             [self._ev(PERIOD_STATUSES[0])] * 4
        st, _ = final_status(self._h(), pe, _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[3])

    def test_partial_when_too_few_settled(self):
        pe = [self._ev(PERIOD_STATUSES[0])] * 4 + \
             [self._ev(PERIOD_STATUSES[2])] * 2
        st, _ = final_status(self._h(), pe, _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[4])

    def test_promising_when_strong_but_not_full(self):
        pe = [self._ev(PERIOD_STATUSES[0])] * 4 + \
             [self._ev(PERIOD_STATUSES[3])] + \
             [self._ev(PERIOD_STATUSES[2])]
        st, _ = final_status(self._h(), pe, _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[5])

    def test_robust_when_full_survival(self):
        pe = [self._ev(PERIOD_STATUSES[0])] * 6
        st, _ = final_status(self._h(), pe, _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[-2])

    def test_validated_requires_walk_forward_declared(self):
        pe = [self._ev(PERIOD_STATUSES[0])] * 6
        h = HypothesisRecord(origin="9K", statement="s", symbol="X",
                             direction="LONG",
                             params={"entry_model": "LIMIT_RETEST"},
                             walk_forward_passed=True)
        st, reasons = final_status(h, pe, _DEFAULT_GATES)
        self.assertEqual(st, OOS_STATUSES[-1])
        # LOW robustness blocks the top rung
        st2, _ = final_status(h, pe, dict(_DEFAULT_GATES), robustness_level="LOW")
        self.assertEqual(st2, OOS_STATUSES[-2])

    def test_summarize_counts(self):
        pe = [self._ev(PERIOD_STATUSES[0])] * 5 + \
             [self._ev(PERIOD_STATUSES[-1])]
        s = summarize_periods(pe, _DEFAULT_GATES)
        self.assertEqual(s["periods_available"], 5)
        self.assertEqual(s["periods_survived"], 5)
        self.assertEqual(s["periods_rejected"], 0)
        self.assertEqual(s["periods_unavailable"], 1)
        self.assertEqual(s["survival_ratio"], 1.0)
        self.assertEqual(s["sign_consistent_periods"], 5)
        self.assertTrue(s["economic_consistent"])


class TestRecoveryUnit(unittest.TestCase):
    def test_recovery_capture_surface(self):
        recs = [mk_record("X", i, i * 4, "R") for i in range(40)]
        candles = build_candles_for(recs)
        h = make_hyp(origin="9K", wf=True, statement="recovery")
        m = evaluate_pool(recs, candles, BASE_CONFIG, h, 2, _DEFAULT_GATES)
        self.assertEqual(m["n_opportunities"], 40)
        self.assertEqual(m["n_trades"], 40)
        self.assertEqual(m["win_rate"], 1.0)
        self.assertEqual(m["expectancy"], 2.0)
        self.assertEqual(m["n_recovered"], 40)
        self.assertEqual(m["n_baseline_missed"], 40)
        self.assertEqual(m["capture_gain"], 1.0)
        # no baseline settled -> cannot settle economics -> INCONCLUSIVE
        self.assertEqual(m["status"], PERIOD_STATUSES[2])


class TestE2E(unittest.TestCase):
    def test_clean_6_6_validated_research_only(self):
        rep = run()
        r = rep.results[0]
        self.assertEqual(r.status, OOS_STATUSES[-1])
        self.assertEqual(r.periods_tested, 6)
        self.assertEqual(r.periods_available, 6)
        self.assertEqual(r.periods_survived, 6)
        self.assertEqual(r.periods_rejected, 0)
        self.assertEqual(r.sign_consistent_periods, 6)
        self.assertEqual(r.survival_ratio, 1.0)
        self.assertTrue(r.survives_familywise)
        self.assertEqual(r.robustness["level"], "HIGH")
        self.assertTrue(r.walk_forward_passed)
        self.assertEqual(r.hypothesis_id[:1], "M")
        self.assertTrue(any(
            p.expectancy == 2.0 and p.baseline_expectancy == 2.0
            and p.status == PERIOD_STATUSES[0] for p in r.per_period))

    def test_clean_6_6_without_walkforward_is_robust(self):
        rep = run({"wf": False})
        r = rep.results[0]
        self.assertEqual(r.status, OOS_STATUSES[-2])
        self.assertEqual(r.robustness["level"], "HIGH")

    def test_seven_e_blocked(self):
        rep = run({"seven_e": True})
        r = rep.results[0]
        self.assertEqual(r.status, OOS_STATUSES[0])
        self.assertTrue(r.seven_e)

    def test_unclaimed_short_unavailable(self):
        rep = run({"direction": "SHORT"})
        r = rep.results[0]
        self.assertEqual(r.status, OOS_STATUSES[1])
        self.assertTrue(all(p.status == PERIOD_STATUSES[-1]
                            for p in r.per_period))

    def test_partition_surface_in_report(self):
        rep = run()
        pa = rep.partition
        self.assertEqual(pa["n_total"], 864)
        self.assertEqual(pa["n_discovery"], 432)
        self.assertEqual(pa["n_oos"], 432)
        self.assertEqual(pa["n_oos_periods"], 6)
        self.assertEqual(pa["leak_guard"]["status"], "PROTECTED")

    def test_familywise_multi_hypotheses(self):
        eng = OosValidationEngine()
        hs = [make_hyp(statement="a", wf=True),
              make_hyp(statement="b", wf=True)]
        rep = eng.run(ALL_WIN, ALL_WIN_CANDLES, BASE_CONFIG, hs,
                      outcome_bars=2)
        self.assertEqual(rep.familywise["family_size"], 2)
        self.assertAlmostEqual(
            rep.familywise["corrected_alpha"],
            0.025320565519103666, places=12)

    def test_report_ids_stable(self):
        self.assertEqual(run().report_id, "Me686dca76c")
        self.assertEqual(run({"wf": False}).report_id, "M8be132b4e4")

    def test_byte_repeatable_determinism(self):
        a = run()
        b = run()
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(a.report_id, b.report_id)

    def test_decision_time_only_no_lookahead(self):
        base = run()
        future = run()
        modified = divergent_future(ALL_WIN, ALL_WIN_CANDLES)
        eng = OosValidationEngine()
        rep_f = eng.run(ALL_WIN, modified, BASE_CONFIG,
                        [make_hyp(wf=True, statement="clean long recovery")],
                        outcome_bars=2)
        self.assertEqual(base.to_json(), rep_f.to_json())

    def test_report_is_frozen(self):
        rep = run()
        with self.assertRaises(FrozenInstanceError):
            rep.report_id = "x"

    def test_production_ready_always_raises(self):
        rep = run()
        with self.assertRaises(ValueError):
            rep.is_production_ready()

    def test_emission_check_never_emits(self):
        rep = run()
        ok, reason = rep.emission_check()
        self.assertFalse(ok)
        self.assertTrue(any(tok in reason for tok in NEVER_EMITTED))


class TestBoundaries(unittest.TestCase):
    _FORBIDDEN_MODULES = (
        "scipy", "sklearn", "pandas", "torch", "random", "uuid",
        "datetime", "core.quant", "core.execution", "core.strategies",
        "core.broker",
    )

    def test_no_forbidden_imports_in_oos(self):
        pkg = os.path.join(
            os.path.dirname(__file__), os.pardir,
            "core", "research", "oos")
        pkg = os.path.normpath(pkg)
        sources = []
        for root, _, files in os.walk(pkg):
            for name in files:
                if name.endswith(".py"):
                    sources.append(os.path.join(root, name))
        self.assertTrue(sources)
        for path in sources:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            imports = re.findall(
                r"^\s*(?:import\s+([\w\.,\s]+)|from\s+([\w\.]+)\s+"
                r"import\s+.+)$",
                text, re.MULTILINE)
            for a, b in imports:
                clause = (a or "").strip() + (b or "")
                for module in clause.replace(",", " ") \
                        .replace(" as ", " ") \
                        .split():
                    head = module.split(".")[0]
                    if head == "core":
                        self.assertTrue(
                            module.startswith("core.research."),
                            "%s imports outside core.research.*: %r"
                            % (path, module))
                    else:
                        self.assertNotIn(
                            head, self._FORBIDDEN_MODULES,
                            "%s imports forbidden %r" % (path, head))
                    if module.startswith("core.execution."):
                        self.fail("%s imports production %r"
                                  % (path, module))

    def test_promotion_token_never_emitted_in_body(self):
        import json
        rep = run()
        body = json.dumps(rep.to_dict(), sort_keys=True)
        for tok in NEVER_EMITTED:
            self.assertNotIn(tok, body)

    def test_report_renders_ladder_and_protocol(self):
        text = run().render()
        self.assertIn("chronological", text)
        self.assertIn("familywise", text)
        self.assertIn("Sidak", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)