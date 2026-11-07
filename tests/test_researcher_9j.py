"""
====================================================================

QuantEngine

Phase 9J -- Strategy Discovery / Experiment Engine tests

Proves the deterministic, research-only autonomous discovery engine:

   * candidate space: every parameter axis is drawn from the frozen
     9B ExperimentConfig schema; unsupported axes and entry models
     fail LOUDLY and are never silently invented;
   * gap detection + hypothesis generation: deterministic,
     evidence-gated, recovery-first candidates (entry offset / entry
     model / expiry / confirmation / RR / stop) that are always
     executable and carry their evidence;
   * scheduler: deterministic order, an explicit budget for GENERATED
     hypotheses (injected experiments are NEVER suppressed),
     research-memory dedup reported explicitly as skipped;
   * gates: the closed discovery ladder (BLOCKED / INCONCLUSIVE /
     REJECTED / PROMISING / REQUIRES_OOS / VALIDATED) with OOS never
     bypassed, 7E NO-GO preserved, and small populations never
     validated;
   * end-to-end runs through StrategyDiscoveryEngine over the genuine
     9C/9D/9E/9G machinery: VALIDATED only with a clean chronological
     OOS fold, OOS-fail -> REJECTED, directional contradiction ->
     REJECTED, rejected/blocked/inconclusive experiments retained,
     byte-identical repeated reports, recovery of previously-rejected
     opportunities (count + per-category + added R), observed-only
     9F confluence, and empty-dataset honesty;
   * boundaries: no production imports, no randomness/uuid sources,
     no external SDK, closed status vocabulary, and never a
     promotion token (AUTOMATICALLY_DEPLOY / PRODUCTION_READY absent).

Uses ONLY the real 9A-9I machinery and genuine counterfactual
simulation. Stdlib only; offline; deterministic.
====================================================================
"""

import os
import re
import unittest
from dataclasses import FrozenInstanceError

from core.research.journal import OpportunityRecord
from core.research.researcher import DEFAULT_BASE_CONFIG
from core.research.researcher.memory import ResearchMemory
from core.research.dataset import (
    ResearchDataset,
    ResearchRow,
    collect_journal,
    collect_features,
)
from core.research.discovery import (
    REJECTED,
    INCONCLUSIVE,
    PROMISING,
    REQUIRES_OOS,
    VALIDATED,
    BLOCKED,
    DISCOVERY_STATUSES,
    NEVER_EMITTED,
    DiscoveryHypothesis,
    validate_overrides,
    vocabulary,
    detect_gaps,
    generate_hypotheses,
    dedup_hypotheses,
    schedule,
    DiscoveryGates,
    StrategyDiscoveryEngine,
)
from core.research.discovery.discovery_types import stable_json

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DISCOVERY_DIR = os.path.join(_REPO, "core", "research", "discovery")


def _param(e, key):
    """Experiment params are the CounterfactualConfig to_dict() (nested
    'params'), except for blocked experiments which carry the raw
    hypothesis overrides."""
    p = e.params or {}
    nested = p.get("params")
    if isinstance(nested, dict):
        return nested.get(key)
    return p.get(key)


# ==================================================================
# Fixtures
# ==================================================================

class _C:
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open, self.high, self.low = o, h, l
        self.close, self.timestamp = c, ts


def candle_series(total, win_region_end):
    """Bars 1..win_region_end WIN-able; later bars passive."""
    seq = [_C(100.0, 101.0, 99.0, 100.0, 0)]
    for i in range(1, total):
        if i <= win_region_end:
            seq.append(_C(102.0, 108.0, 100.0, 108.0, i))
        else:
            seq.append(_C(102.0, 103.0, 100.0, 100.0, i))
    return seq


def _record(i, symbol="X", baseline_win=True, terminal="FILLED_CLOSED",
            rejection=()):
    if terminal == "REJECTED":
        return OpportunityRecord(
            canonical_id="r-%s-%02d" % (symbol, i), exchange="TESTEX",
            instrument_id=symbol, timeframe="1m", direction="BULLISH",
            strategy="BREAKOUT_CONTINUATION",
            setup_id="r-%s-%02d" % (symbol, i),
            setup={"entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
                   "risk_reward": 2.0, "bar": i, "atr": 4.0,
                   "rejection_reasons": list(rejection)},
            order={}, trade={}, terminal_outcome="REJECTED",
        )
    trade = {
        "result": "WIN" if baseline_win else "LOSS",
        "pnl": 2.0 if baseline_win else -4.0, "risk_amount": 4.0,
        "entry_bar": i + 2, "exit_bar": i + 2, "bars_held": 1,
        "r": 0.5 if baseline_win else -1.0,
        "exit_price": 104.0 if baseline_win else 98.0,
    }
    return OpportunityRecord(
        canonical_id="r-%s-%02d" % (symbol, i), exchange="TESTEX",
        instrument_id=symbol, timeframe="1m", direction="BULLISH",
        strategy="BREAKOUT_CONTINUATION",
        setup_id="r-%s-%02d" % (symbol, i),
        setup={"entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
               "risk_reward": 2.0, "bar": i, "atr": 4.0,
               "rejection_reasons": []},
        order={}, trade=trade, terminal_outcome=terminal,
    )


def make_win_records(n, symbol="X", baseline_losses=0):
    return [
        _record(i, symbol, baseline_win=i >= baseline_losses)
        for i in range(n)
    ]


def pair_series(total, win_region_end):
    """Trigger candles (fill) then stop-breach candles (loss)."""
    seq = [_C(100.0, 101.0, 99.0, 100.0, 0)]
    for i in range(1, total):
        if i <= win_region_end:
            seq.append(_C(102.0, 108.0, 100.0, 108.0, i))
        elif i % 2 == 1:
            seq.append(_C(102.0, 104.0, 101.0, 103.0, i))
        else:
            seq.append(_C(102.0, 103.0, 95.0, 99.0, i))
    return seq


def make_tail_loss_records(n, tail_loss):
    """Wins everywhere except the last tail_loss records (LOSS)."""
    return [_record(i, baseline_win=i < n - tail_loss) for i in range(n)]


def _hypothesis(kind="RECOVERY_RR", overrides=None, direction="",
                injected=False, seven_e=False, question=None):
    return DiscoveryHypothesis(
        kind=kind,
        question=question or "Q-%s" % kind,
        statement="test statement",
        why="test why",
        expected_outcome="test outcome",
        overrides=overrides if overrides is not None else {"rr": [3.0, 4.0]},
        direction=direction,
        symbol="X",
        evidence=(),
        seven_e_no_go=seven_e,
        injected=injected,
    )


class _Snap:
    def __init__(self, oid, features):
        self.opportunity_id = oid
        self.features = features
        self.instrument_id = "X"
        self.direction = "BULLISH"
        self.timeframe = "1m"
        self.decision_bar = 3
        self.window_size = 1
        self.entry = 100.0
        self.stop = 98.0
        self.target = 104.0
        self.atr = 4.0


class FixtureTest(unittest.TestCase):
    def test_candle_series_monotonic(self):
        candles = candle_series(48, 42)
        self.assertEqual(len(candles), 48)
        stamps = [c.timestamp for c in candles]
        self.assertEqual(stamps, sorted(stamps))

    def test_record_fixture(self):
        records = make_win_records(48, baseline_losses=4)
        self.assertEqual(len(records), 48)
        self.assertEqual(records[0].trade["result"], "LOSS")
        self.assertEqual(records[4].trade["result"], "WIN")
        self.assertTrue(records[0].terminal_outcome == "FILLED_CLOSED")

    def test_tail_loss_fixture(self):
        records = make_tail_loss_records(140, 21)
        self.assertEqual(records[130].trade["result"], "LOSS")
        self.assertEqual(records[100].trade["result"], "WIN")


class CandidateSpaceTest(unittest.TestCase):
    def test_supported_axes_return_sorted(self):
        out = validate_overrides({"rr": [3.0, 4.0], "entry_offset_atr": [0.5]})
        self.assertEqual(list(out.keys()), ["entry_offset_atr", "rr"])

    def test_unsupported_axis_fails_loudly(self):
        with self.assertRaises(ValueError) as cm:
            validate_overrides({"alpha": [0.5]})
        self.assertIn("unsupported experiment parameter axis", str(cm.exception))
        self.assertIn("rr", str(cm.exception))

    def test_known_unsupported_entry_model_fails(self):
        with self.assertRaises(ValueError) as cm:
            validate_overrides({"entry_model": ["FVG_RETRACE"]})
        self.assertIn("known unsupported", str(cm.exception))

    def test_expiry_must_be_positive_int(self):
        with self.assertRaises(ValueError):
            validate_overrides({"expiry": [0]})
        with self.assertRaises(ValueError):
            validate_overrides({"expiry": ["5"]})

    def test_vocabulary_never_invents_axes(self):
        v = vocabulary()
        self.assertTrue(v["never_invented_axes"])
        self.assertIn("rr", v["supported_axes"])
        self.assertIn("expiry", v["supported_axes"])


class GapAndHypothesisTest(unittest.TestCase):
    def test_empty_dataset_no_gaps(self):
        ds = ResearchDataset()
        self.assertEqual(detect_gaps(ds), ())
        self.assertEqual(generate_hypotheses(ds, DEFAULT_BASE_CONFIG), ())

    def test_filled_population_generates_rr_and_stop(self):
        ds = ResearchDataset()
        ds.add_rows(collect_journal(make_win_records(48)))
        gaps = detect_gaps(ds)
        categories = {g.category for g in gaps}
        self.assertIn("FILLED", categories)
        kinds = {h.kind for h in generate_hypotheses(
            ds, DEFAULT_BASE_CONFIG, symbol="X")}
        self.assertEqual(kinds, {"RECOVERY_RR", "RECOVERY_STOP"})

    def test_entry_not_reached_gap(self):
        ds = ResearchDataset()
        ds.add_rows([
            ResearchRow(
                source="JOURNAL", observation_id="obs-1", instrument_id="X",
                direction="BULLISH", timeframe="1m",
                strategy="BREAKOUT_CONTINUATION", decision_bar=5,
                category="ENTRY_NOT_REACHED", result="REJECTED",
                source_id="obs-1",
                kv={"rejection_reasons": ["ENTRY_NOT_REACHED"]},
            )
        ])
        gaps = detect_gaps(ds)
        gap = next(g for g in gaps if g.category == "ENTRY_NOT_REACHED")
        self.assertEqual(gap.count, 1)
        self.assertEqual(gap.directions, ("BULLISH",))
        gen = generate_hypotheses(ds, DEFAULT_BASE_CONFIG, symbol="X")
        kinds = {h.kind for h in gen}
        self.assertEqual(
            kinds, {"RECOVERY_ENTRY_OFFSET", "RECOVERY_ENTRY_MODEL"})
        for h in gen:
            self.assertEqual(h.direction, "BULLISH")
            self.assertTrue(h.overrides)
            self.assertTrue(h.evidence)

    def test_hypotheses_executable(self):
        ds = ResearchDataset()
        ds.add_rows(collect_journal(make_win_records(30)))
        for h in generate_hypotheses(ds, DEFAULT_BASE_CONFIG, symbol="X"):
            self.assertTrue(h.overrides, "every hypothesis is executable")

    def test_generation_is_deterministic(self):
        ds = ResearchDataset()
        ds.add_rows(collect_journal(make_win_records(30)))
        a = generate_hypotheses(ds, DEFAULT_BASE_CONFIG, symbol="X")
        b = generate_hypotheses(ds, DEFAULT_BASE_CONFIG, symbol="X")
        self.assertEqual(a, b)

    def test_dedup_keeps_unique(self):
        h = _hypothesis()
        merged = dedup_hypotheses((h, h))
        self.assertEqual(len(merged), 1)
        self.assertIs(merged[0], h)


class SchedulerTest(unittest.TestCase):
    def test_schedule_deterministic_order(self):
        hs = (dedup_hypotheses(
            generate_hypotheses_from_records()
        ))
        scheduled, skipped = schedule(hs)
        self.assertEqual(skipped, ())
        keys = [(h.kind, h.question, h.hypothesis_id) for h in scheduled]
        self.assertEqual(keys, sorted(keys))

    def test_budget_counts_generated_not_injected(self):
        hs = dedup_hypotheses(
            generate_hypotheses_from_records() +
            (_hypothesis(kind="RECOVERY_EXPIRY", overrides={"expiry": [5]},
                         injected=True),)
        )
        scheduled, skipped = schedule(hs, budget=1)
        kinds = {h.kind for h in scheduled}
        self.assertIn("RECOVERY_EXPIRY", kinds)  # injected never suppressed
        self.assertEqual(len([h for h in scheduled if not h.injected]), 1)
        self.assertTrue(
            any(reason == "experiment budget reached"
                for _, reason in skipped))

    def test_memory_dedup_marks_skipped(self):
        mem = ResearchMemory()
        prior = _hypothesis(question="same-q")
        mem.record(
            investigation_id="I-test", question="same-q",
            hypotheses=[prior], experiment_ids=(),
            recommendation_statuses=(), oos_statuses=(),
            report_status="9H_TEST",
        )
        again = _hypothesis(question="same-q")
        scheduled, skipped = schedule((again,), memory=mem)
        self.assertEqual(scheduled, ())
        self.assertEqual(len(skipped), 1)
        self.assertIn("previously studied", skipped[0][1])

    def test_invalid_candidate_skipped_with_reason(self):
        bad = _hypothesis(kind="RECOVERY_RR", overrides={"rr": [0]})
        scheduled, skipped = schedule((bad,))
        self.assertEqual(scheduled, ())
        self.assertIn("invalid candidate", skipped[0][1])


def generate_hypotheses_from_records():
    ds = ResearchDataset()
    ds.add_rows(collect_journal(make_win_records(30)))
    return generate_hypotheses(ds, DEFAULT_BASE_CONFIG, symbol="X")


class GateTest(unittest.TestCase):
    def _run_gate(self, hypothesis=None, **kwargs):
        h = hypothesis or _hypothesis()
        metrics = kwargs.pop("metrics", {"settled": 40, "expectancy": 2.0})
        comparison = kwargs.pop(
            "comparison", {"delta_expectancy": 1.0})
        economic = kwargs.pop("economic", {
            "capture_gain": 5, "expectancy_delta": 1.0,
            "risk_delta": 1.0, "loss_rate_delta": -0.1,
            "max_drawdown_delta": -0.5, "loss_expansion": False,
            "acceptable": True, "verdict": "RECOVERY_CAPTURES_...",
        })
        oos = kwargs.pop(
            "oos", {"oos_settled": 6, "oos_expectancy": 0.5})
        return DiscoveryGates().evaluate(
            h, metrics=metrics, comparison=comparison,
            robustness=(), economic=economic, oos=oos, **kwargs)

    def test_blocked_seven_e(self):
        status, reasons = self._run_gate(
            hypothesis=_hypothesis(seven_e=True))
        self.assertEqual(status, BLOCKED)
        self.assertTrue(any("7E NO-GO" in r for r in reasons))

    def test_inconclusive_small_population(self):
        status, reasons = self._run_gate(
            metrics={"settled": 9, "expectancy": 2.0})
        self.assertEqual(status, INCONCLUSIVE)
        self.assertTrue(any("retained" in r for r in reasons))

    def test_rejected_no_advantage(self):
        status, reasons = self._run_gate(
            comparison={"delta_expectancy": 0.0})
        self.assertEqual(status, REJECTED)
        self.assertTrue(any("no advantage" in r for r in reasons))

    def test_rejected_loss_expansion(self):
        status, reasons = self._run_gate(economic={
            "acceptable": False, "loss_expansion": True,
            "verdict": "LOSS_EXPANSION: ..."})
        self.assertEqual(status, REJECTED)
        self.assertTrue(any("LOSS_EXPANSION" in r for r in reasons))

    def test_rejected_directional_contradiction(self):
        status, reasons = self._run_gate(
            hypothesis=_hypothesis(direction="LONG"),
            dir_evidence={
                "expected": "LONG", "dominant_direction": "SHORT",
                "sign_agreement": False, "agreed_settled": 9,
                "settled_by_direction": {"SHORT": 9},
            })
        self.assertEqual(status, REJECTED)
        self.assertTrue(any("directional contradiction" in r for r in reasons))

    def test_promising_when_economic_not_acceptable(self):
        status, reasons = self._run_gate(economic={
            "acceptable": False, "loss_expansion": False,
            "verdict": "CAPTURE_TRADE_OFF: no net capture gain"})
        self.assertEqual(status, PROMISING)
        self.assertTrue(any("economic trade-off" in r for r in reasons))

    def test_requires_oos_never_bypassed(self):
        status, reasons = self._run_gate(
            oos={"oos_settled": 0, "oos_expectancy": 0.0})
        self.assertEqual(status, REQUIRES_OOS)
        self.assertTrue(any("never validated without OOS" in r for r in reasons))

    def test_rejected_oos_not_confirm(self):
        status, reasons = self._run_gate(
            oos={"oos_settled": 6, "oos_expectancy": -0.2})
        self.assertEqual(status, REJECTED)
        self.assertTrue(any("OOS evidence did not confirm" in r for r in reasons))

    def test_validated_research_only(self):
        status, reasons = self._run_gate()
        self.assertEqual(status, VALIDATED)
        self.assertTrue(any("never production-ready" in r for r in reasons))

    def test_small_spread_never_validated(self):
        status, _ = self._run_gate(metrics={"settled": 25, "expectancy": 2.0})
        self.assertEqual(status, PROMISING)


class EngineEndToEndTest(unittest.TestCase):
    def _run(self, records, candles, symbol="X", extra=(), memory=None,
             dataset=None):
        return StrategyDiscoveryEngine(
            candles=candles, memory=memory, budget=None
        ).run(records, DEFAULT_BASE_CONFIG, symbol=symbol,
              extra_hypotheses=extra, dataset=dataset)

    def test_e2e_all_win_validates(self):
        rep = self._run(
            make_win_records(48, baseline_losses=3),
            candle_series(48, 45),
            extra=(_hypothesis(
                kind="RECOVERY_EXPIRY", overrides={"expiry": [5]},
                injected=True),),
        )
        statuses = {e.status for e in rep.experiments}
        self.assertIn(VALIDATED, statuses)
        expiry = [e for e in rep.experiments if _param(e, "expiry") == 5]
        self.assertTrue(expiry)
        self.assertEqual(expiry[0].status, VALIDATED)
        stop = [e for e in rep.experiments
                if _param(e, "stop_mode") == "ATR"]
        self.assertEqual(stop[0].status, INCONCLUSIVE)

    def test_e2e_small_population_inconclusive(self):
        rep = self._run(make_win_records(6), candle_series(10, 9))
        self.assertTrue(rep.experiments)
        for e in rep.experiments:
            self.assertEqual(e.status, INCONCLUSIVE)

    def test_e2e_requires_oos_on_14(self):
        rep = self._run(make_win_records(14), candle_series(20, 18))
        statuses = {e.status for e in rep.experiments}
        self.assertIn(REQUIRES_OOS, statuses)
        self.assertNotIn(VALIDATED, statuses)

    def test_e2e_recovery_rejected_positions(self):
        records = [_record(i) for i in range(24)] + [
            _record(i, terminal="REJECTED",
                    rejection=["ENTRY_NOT_REACHED"])
            for i in range(24, 40)
        ]
        rep = self._run(records, candle_series(42, 42))
        self.assertEqual(rep.recovery.get("recovery_count"), 16)
        self.assertGreater(rep.recovery.get("added_R", 0), 0)
        rejected_ids = {("r-X-%02d") % i for i in range(24, 40)}
        for oid in rep.recovery.get("recovered_observations", ()):
            self.assertIn(oid, rejected_ids)
        for e in rep.experiments:
            if e.status == VALIDATED:
                self.assertEqual(e.recovery.get("recovery_count"), 16)

    def test_e2e_directional_contradiction(self):
        records = make_win_records(48, baseline_losses=3)
        rep = self._run(
            records, candle_series(48, 45),
            extra=(_hypothesis(
                kind="RECOVERY_EXPIRY", overrides={"expiry": [5]},
                direction="SHORT", injected=True),),
        )
        shorted = [e for e in rep.experiments if _param(e, "expiry") == 5]
        self.assertEqual(shorted[0].status, REJECTED)
        self.assertTrue(any("directional contradiction" in r
                            for r in shorted[0].reasons))

    def test_e2e_oos_fail_rejected(self):
        rep = self._run(
            make_tail_loss_records(140, 21),
            pair_series(140, 118),
        )
        statuses = {e.status for e in rep.experiments}
        self.assertIn(REJECTED, statuses)
        self.assertNotIn(VALIDATED, statuses)
        rejected = [e for e in rep.experiments if e.status == REJECTED]
        self.assertTrue(all(
            any("OOS evidence did not confirm" in r for r in e.reasons)
            for e in rejected))

    def test_e2e_closed_vocabulary(self):
        rep = self._run(make_win_records(48, baseline_losses=3),
                        candle_series(48, 45))
        for e in rep.experiments:
            self.assertIn(e.status, DISCOVERY_STATUSES)
        for f in rep.findings:
            self.assertIn(f.status, DISCOVERY_STATUSES)

    def test_e2e_report_byte_identical(self):
        r1 = self._run(make_win_records(48, baseline_losses=3),
                       candle_series(48, 45))
        r2 = self._run(make_win_records(48, baseline_losses=3),
                       candle_series(48, 45))
        self.assertEqual(r1.to_dict(), r2.to_dict())
        self.assertEqual(r1.report_id, r2.report_id)

    def test_e2e_never_emitted(self):
        rep = self._run(make_win_records(48, baseline_losses=3),
                        candle_series(48, 45))
        self.assertTrue(rep.emission_check)
        blob = stable_json(rep.to_dict())
        for token in NEVER_EMITTED:
            self.assertNotIn(token, blob)

    def test_e2e_is_production_ready_false(self):
        rep = self._run(make_win_records(48, baseline_losses=3),
                        candle_series(48, 45))
        self.assertFalse(rep.is_production_ready)
        with self.assertRaises(FrozenInstanceError):
            rep.is_production_ready = True
        with self.assertRaises(FrozenInstanceError):
            rep.is_production_directive = True
        for f in rep.findings:
            self.assertFalse(f.is_production_directive)

    def test_e2e_seven_e_blocked_retained(self):
        rep = self._run(
            make_win_records(48, baseline_losses=3),
            candle_series(48, 45),
            extra=(_hypothesis(
                kind="RECOVERY_ENTRY_MODEL",
                overrides={"entry_model": ["LIMIT_RETEST"]},
                seven_e=True),),
        )
        blocked = [e for e in rep.experiments if e.status == BLOCKED]
        self.assertTrue(blocked)
        self.assertTrue(any("7E NO-GO" in r
                            for e in blocked for r in e.reasons))

    def test_e2e_empty_dataset(self):
        rep = self._run([], candle_series(24, 20))
        self.assertEqual(rep.gaps, ())
        self.assertEqual(rep.experiments, ())
        self.assertIn(
            "no opportunity gaps were identifiable",
            " ".join(rep.limitations),
        )
        self.assertFalse(rep.is_production_ready)

    def test_e2e_memory_dedup_reported(self):
        mem = ResearchMemory()
        records = make_win_records(48, baseline_losses=3)
        candles = candle_series(48, 45)
        extra = (_hypothesis(kind="RECOVERY_EXPIRY",
                             overrides={"expiry": [5]}, injected=True),)
        first = self._run(records, candles, memory=mem, extra=extra)
        self.assertEqual(first.skipped, ())
        second = self._run(records, candles, memory=mem, extra=extra)
        reasons = [reason for _, reason in second.skipped]
        self.assertTrue(any("previously studied" in r for r in reasons))
        self.assertTrue(second.experiments)
        executed_ids = {e.hypothesis_id for e in second.experiments}
        self.assertIn(extra[0].hypothesis_id, executed_ids)

    def test_e2e_confluence_observed_only(self):
        records = [_record(i) for i in range(24)] + [
            _record(i, terminal="REJECTED", rejection=["ENTRY_NOT_REACHED"])
            for i in range(24, 40)
        ]
        ds = ResearchDataset()
        ds.add_rows(collect_journal(records))
        ds.add_rows(collect_features([
            _Snap("r-X-%02d" % i, {"distance_to_entry_atr": 0.3})
            for i in range(24, 40)
        ]))
        rep = self._run(records, candle_series(42, 42), dataset=ds)
        self.assertIn("distance_to_entry_atr",
                      rep.confluence.get("feature_availability", []))
        assocs = rep.confluence.get("associations", ())
        self.assertTrue(any(
            a["feature"] == "distance_to_entry_atr"
            and a["recovered"] == 16 for a in assocs))
        self.assertEqual(rep.confluence.get("status"),
                         "OBSERVED_ASSOCIATIONS_ONLY")

    def test_e2e_confluence_never_fabricated(self):
        rep = self._run(make_win_records(48, baseline_losses=3),
                        candle_series(48, 45))
        self.assertEqual(rep.confluence.get("associations"), ())
        self.assertFalse(rep.confluence.get("feature_availability"))
        self.assertTrue(any(
            "NOT fabricated" in n
            for n in rep.confluence.get("notes", ())))

    def test_e2e_ranking_complete_no_hiding(self):
        rep = self._run(make_win_records(48, baseline_losses=3),
                        candle_series(48, 45))
        self.assertEqual(len(rep.ranking), len(rep.experiments))
        ranked_ids = [r["experiment_id"] for r in rep.ranking]
        self.assertEqual(set(ranked_ids),
                         {e.experiment_id for e in rep.experiments})
        scores = [r["score"] for r in rep.ranking]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_e2e_invalid_hypothesis_skipped_loudly(self):
        bad = _hypothesis(kind="RECOVERY_RR", overrides={"rr": [0]})
        rep = self._run(
            make_win_records(48, baseline_losses=3),
            candle_series(48, 45),
            extra=(bad,),
        )
        skipped_ids = [h.hypothesis_id for h, _ in rep.skipped]
        self.assertIn(bad.hypothesis_id, skipped_ids)
        reasons = [reason for _, reason in rep.skipped]
        self.assertTrue(any("invalid candidate" in r for r in reasons))
        executed_ids = {e.hypothesis_id for e in rep.experiments}
        self.assertNotIn(bad.hypothesis_id, executed_ids)


class RecoveryEconomicTest(unittest.TestCase):
    def test_recovery_rejected_with_added_R(self):
        records = [_record(i) for i in range(24)] + [
            _record(i, terminal="REJECTED", rejection=["ENTRY_NOT_REACHED"])
            for i in range(24, 36)
        ]
        candles = candle_series(38, 36)
        rep = StrategyDiscoveryEngine(candles=candles).run(
            records, DEFAULT_BASE_CONFIG, symbol="X")
        self.assertGreater(rep.recovery.get("added_R", 0.0), 0.0)
        self.assertGreater(rep.recovery.get("recovery_count", 0), 0)
        per = rep.recovery.get("per_category", {})
        self.assertIn("REJECTED", per)

    def test_economic_not_acceptable_promising(self):
        rep = StrategyDiscoveryEngine(candles=candle_series(48, 45)).run(
            make_win_records(48, baseline_losses=3),
            DEFAULT_BASE_CONFIG, symbol="X")
        atr = [e for e in rep.experiments
               if _param(e, "stop_mode") == "ATR"][0]
        self.assertFalse(atr.economic["acceptable"])
        self.assertIn("CAPTURE_TRADE_OFF", atr.economic["verdict"])
        self.assertEqual(atr.status, INCONCLUSIVE)


class BoundaryTest(unittest.TestCase):
    def test_no_production_imports(self):
        forbidden = re.compile(
            r"^\s*(from|import)\s+core\.(execution|trading|ledger|"
            r"account|portfolio|risk|market_data|setup|pipeline)\b")
        hits = []
        for name in os.listdir(_DISCOVERY_DIR):
            if not name.endswith(".py"):
                continue
            path = os.path.join(_DISCOVERY_DIR, name)
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if forbidden.match(line):
                        hits.append("%s: %s" % (name, line.strip()))
        self.assertEqual(hits, [])

    def test_no_randomness_sources(self):
        pat = re.compile(r"\b(uuid|random|datetime)\b")
        hits = []
        for name in os.listdir(_DISCOVERY_DIR):
            if not name.endswith(".py"):
                continue
            path = os.path.join(_DISCOVERY_DIR, name)
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if pat.search(line):
                        hits.append("%s: %s" % (name, line.strip()))
        self.assertEqual(hits, [])

    def test_no_ai_sdk_required(self):
        av = StrategyDiscoveryEngine.availability()
        self.assertFalse(av["requires_external_sdk"])
        self.assertEqual(
            set(av["never_emits"]), set(NEVER_EMITTED))

    def test_closed_status_vocabulary(self):
        self.assertEqual(set(DISCOVERY_STATUSES),
                         {REJECTED, INCONCLUSIVE, PROMISING,
                          REQUIRES_OOS, VALIDATED, BLOCKED})
        self.assertNotIn("AUTOMATICALLY_DEPLOY", DISCOVERY_STATUSES)


if __name__ == "__main__":
    unittest.main(verbosity=2)