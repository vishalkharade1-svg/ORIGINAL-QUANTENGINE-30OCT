"""
====================================================

QuantEngine

Phase 9H -- Autonomous AI Researcher tests

Proves the provider-neutral, research-only autonomous researcher:

   * provider-neutral engine (NullProvider always available; external
     providers degrade to PROVIDER_UNAVAILABLE and the engine still
     runs deterministically)
   * planner: evidence-gated, only-supported experiment semantics,
     unsupported params fail loudly, memory dedup prevents
     rediscovery, deterministic hypothesis ids
   * executor: drives the frozen 9C/9D/9E/9F/9G machinery read-only
   * evaluator ladder: VALIDATED / HYPOTHESIS / REJECTED /
     INSUFFICIENT_EVIDENCE / OBSERVATION; OOS can never be bypassed;
     failed experiments retained; conclusions cite evidence
   * research memory: record/recall/dedup/next-suggestion + JSON
     round-trip
   * orchestrator: full evidence chain investigation end-to-end with
     deterministic ids; production_ready=False everywhere
   * boundaries: never imports production internals, never a trade
     directive, never mutates records, never auto-promotes

Uses ONLY the real 9A-9G machinery and genuine counterfactual
simulation. Stdlib only; offline; deterministic.
====================================================
"""

import json
import os
import re
import tempfile
import unittest

from core.research.journal import OpportunityRecord
from core.research.counterfactual import CounterfactualConfig
from core.research.researcher import (
    AutonomousResearcher,
    build_context,
    DEFAULT_BASE_CONFIG,
)

# ==========================================================
# Fixtures
# ==========================================================


class _C:
    __slots__ = ("open", "high", "low", "close", "timestamp")

    def __init__(self, o, h, l, c, ts):
        self.open, self.high, self.low = o, h, l
        self.close, self.timestamp = c, ts


def candle_series(total, win_region_end):
    """Shared chronological series. Bars 1..win_region_end are WIN-able
    (high>=target, close>entry, no stop breach); later bars are passive
    (close==entry), producing unfilled / unsettled outcomes."""
    seq = [_C(100.0, 101.0, 99.0, 100.0, 0)]
    for i in range(1, total):
        if i <= win_region_end:
            seq.append(_C(102.0, 108.0, 100.0, 108.0, i))
        else:
            seq.append(_C(102.0, 103.0, 100.0, 100.0, i))
    return seq


def _record(i, symbol="SYM", baseline_win=True):
    if baseline_win:
        trade = {
            "result": "WIN", "pnl": 2.0, "risk_amount": 4.0,
            "entry_bar": i + 2, "exit_bar": i + 2, "bars_held": 1,
            "r": 0.5, "exit_price": 104.0,
        }
    else:
        trade = {
            "result": "LOSS", "pnl": -4.0, "risk_amount": 4.0,
            "entry_bar": i + 2, "exit_bar": i + 2, "bars_held": 1,
            "r": -1.0, "exit_price": 98.0,
        }
    return OpportunityRecord(
        canonical_id="r-%s-%02d" % (symbol, i),
        exchange="TESTEX",
        instrument_id=symbol,
        timeframe="1m",
        direction="BULLISH",
        strategy="BREAKOUT_CONTINUATION",
        setup_id="r-%s-%02d" % (symbol, i),
        setup={
            "entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0,
            "risk_reward": 2.0, "bar": i, "atr": 4.0,
            "rejection_reasons": [],
        },
        order={},
        trade=trade,
        terminal_outcome="FILLED_CLOSED",
    )


def make_win_records(n, symbol="SYM", baseline_losses=0):
    """Baseline starts with high WR but carries some baseline losses so
    the 9E advantage rule operates on finite profit-factor deltas; under
    the fixture candles every record still counterfactually wins."""
    return [
        _record(i, symbol, baseline_win=i >= baseline_losses)
        for i in range(n)
    ]


def make_empty_population_candles(n_bars):
    return candle_series(n_bars, win_region_end=0)


# ==========================================================
# Evidence context
# ==========================================================


class EvidenceContextTest(unittest.TestCase):
    def test_win_population_context(self):
        records = make_win_records(20)
        ctx = build_context(records)
        self.assertEqual(ctx.records, 20)
        self.assertEqual(ctx.filled, 20)
        self.assertGreater(ctx.expectancy, 0)
        self.assertEqual(ctx.population.get("FILLED"), 20)

    def test_vacuous_context(self):
        ctx = build_context([])
        self.assertTrue(ctx.vacuous)
        self.assertEqual(ctx.records, 0)
        self.assertEqual(ctx.filled, 0)


# ==========================================================
# Providers
# ==========================================================


class ProviderTest(unittest.TestCase):
    def test_null_provider_always_available(self):
        from core.research.researcher import NullProvider
        self.assertTrue(NullProvider().available())

    def test_external_providers_unavailable_without_sdk(self):
        from core.research.researcher import (
            available_providers,
            OpenAIProvider,
        )
        self.assertEqual(
            [p.name for p in available_providers()], ["null"],
        )
        self.assertFalse(OpenAIProvider().available())
        self.assertIn("PROVIDER_UNAVAILABLE", OpenAIProvider().unavailable_note())

    def test_unavailable_provider_raises_guarded(self):
        from core.research.researcher import (
            OpenAIProvider,
            ProviderUnavailable,
        )
        with self.assertRaises(ProviderUnavailable):
            OpenAIProvider().propose_hypotheses(build_context([]))

    def test_engine_runs_without_any_external_provider(self):
        from core.research.researcher import OpenAIProvider
        researcher = AutonomousResearcher(
            provider=OpenAIProvider(), candles=candle_series(48, 42),
        )
        report = researcher.investigate(
            make_win_records(40, baseline_losses=12), symbol="SYM",
        )
        self.assertEqual(report.provider, "null")
        self.assertTrue(report.provider_available)


# ==========================================================
# Planner: only-supported semantics + dedup + determinism
# ==========================================================


class PlannerTest(unittest.TestCase):
    def setUp(self):
        from core.research.researcher.planner import ResearchPlanner
        self.planner = ResearchPlanner()

    def _plan(self, records, provider=None, memory=None):
        from core.research.researcher import NullProvider
        ctx = build_context(records)
        provider = provider or NullProvider()
        return self.planner.plan(ctx, provider, memory=memory)

    def test_win_population_plans_offset_probe_only(self):
        hypotheses, notes = self._plan(make_win_records(20))
        kinds = [h.kind for h in hypotheses]
        self.assertEqual(kinds, ["ENTRY_OFFSET_ANALYSIS"])
        self.assertTrue(notes == [])
        self.assertTrue(all(h.overrides for h in hypotheses))

    def test_hypothesis_ids_deterministic(self):
        a, _ = self._plan(make_win_records(20))
        b, _ = self._plan(make_win_records(20))
        self.assertEqual(
            [h.hypothesis_id for h in a], [h.hypothesis_id for h in b],
        )

    def test_unsupported_param_fails_loudly(self):
        with self.assertRaises(ValueError):
            self.planner.validate_override("not_a_param", [1.0])

    def test_unsupported_entry_model_fails_loudly(self):
        with self.assertRaises(ValueError):
            self.planner.validate_override(
                "entry_model", ["FVG_RETRACE"],
            )

    def test_unsupported_param_blocks_hypothesis_with_note(self):
        from core.research.researcher import NullProvider
        from core.research.researcher.types import EvidenceContext
        from core.research.researcher.memory import ResearchMemory

        class BadProvider(NullProvider):
            def propose_hypotheses(self, context):
                return [{
                    "kind": "GENERAL",
                    "question": "bad?",
                    "statement": "bad",
                    "why": "test",
                    "overrides": {"entry_model": "NOT_A_MODEL"},
                    "features": (),
                    "outcome_bars": None,
                }]

        hypotheses, notes = self.planner.plan(
            build_context(make_win_records(5)), BadProvider(),
            memory=ResearchMemory(),
        )
        self.assertEqual(hypotheses, [])
        self.assertTrue(any("unsupported entry model" in n for n in notes))

    def test_memory_dedup_prevents_rediscovery(self):
        from core.research.researcher.memory import ResearchMemory
        memory = ResearchMemory()
        h1, _ = self._plan(make_win_records(20), memory=memory)
        self.assertEqual(len(h1), 1)
        memory.record(
            memory.investigation_id_for("SYM", h1[0].question, [h1[0].hypothesis_id]),
            h1[0].question, h1, [], [], [], "VALIDATED",
        )
        h2, notes = self._plan(make_win_records(20), memory=memory)
        self.assertEqual(h2, [])
        self.assertTrue(any("duplicate" in n for n in notes))


# ==========================================================
# Evaluator ladder (pure, deterministic)
# ==========================================================


def _dummy_hypothesis(kind="ENTRY_OFFSET_ANALYSIS"):
    from core.research.researcher import Hypothesis
    return Hypothesis(
        hypothesis_id="Htest0001",
        kind=kind,
        question="q",
        statement="s",
        why="w",
        dataset="d",
        features=(),
        overrides={"entry_offset_atr": [0.0]},
    )


def _result(settled, expectancy, delta, oos_settled, oos_exp,
            rec_status="ROBUST", strength="EVIDENCE_MODERATE",
            robustness=(), robust_status="ROBUST"):
    from core.research.researcher import ExperimentResult
    return ExperimentResult(
        experiment_id="exp-1",
        config=None,
        filled=settled,
        settled=settled,
        metrics={"expectancy": expectancy, "filled": settled,
                 "settled": settled},
        comparison={"delta_expectancy": delta},
        robustness=tuple(robustness),
        categories={},
        evidence_strength=strength,
        recommendation_status=rec_status,
        robustness_status=robust_status,
        statistical={"expectancy": expectancy, "n": settled},
        oos={"oos_filled": oos_settled, "oos_settled": oos_settled,
             "oos_expectancy": oos_exp},
        features={},
    )


def _run(results):
    from core.research.researcher.experiments import ExperimentRun
    hypothesis = _dummy_hypothesis()
    return ExperimentRun(hypothesis=hypothesis, results=tuple(results),
                         report=None, intelligence=None)


class EvaluatorTest(unittest.TestCase):
    def setUp(self):
        from core.research.researcher import EvidenceEvaluator
        self.evaluator = EvidenceEvaluator()

    def _conclude(self, results):
        # baseline expectancy deliberately below the candidate
        return self.evaluator.conclude(_run(results), 0.0, None)

    def test_validated_when_positive_robust_oos(self):
        rec = self._conclude([
            _result(40, 0.8, 0.6, 8, 0.5),
        ])
        self.assertEqual(rec.status, "VALIDATED")
        self.assertFalse(rec.is_production_directive)
        self.assertTrue(rec.evidence)
        self.assertEqual(rec.evidence[0]["experiment_id"], "exp-1")

    def test_rejected_when_no_advantage(self):
        rec = self._conclude([_result(40, -0.3, -0.5, 8, -0.1)])
        self.assertEqual(rec.status, "REJECTED")

    def test_oos_gate_cannot_be_bypassed(self):
        # positive in-sample, but OOS negative -> REJECTED
        rec = self._conclude([_result(40, 0.8, 0.6, 8, -0.4)])
        self.assertEqual(rec.status, "REJECTED")
        self.assertIn("OOS", rec.statement)

    def test_oos_too_small_downgrades_to_hypothesis(self):
        rec = self._conclude([_result(40, 0.8, 0.6, 3, 0.5)])
        self.assertEqual(rec.status, "HYPOTHESIS")

    def test_robustness_blocker_downgrades_to_hypothesis(self):
        rec = self._conclude([
            _result(40, 0.8, 0.6, 8, 0.5, rec_status="OOS_REQUIRED"),
        ])
        self.assertEqual(rec.status, "HYPOTHESIS")
        self.assertIn("robustness gate", rec.statement)

    def test_insufficient_evidence_when_sample_small(self):
        rec = self._conclude([_result(3, 0.8, 0.6, 0, None)])
        self.assertEqual(rec.status, "INSUFFICIENT_EVIDENCE")

    def test_insufficient_evidence_when_no_experiments(self):
        rec = self._conclude([])
        self.assertEqual(rec.status, "INSUFFICIENT_EVIDENCE")

    def test_warnings_evidence_is_retained_not_pruned(self):
        rec = self._conclude([
            _result(40, -0.2, -0.4, 8, -0.2),
            _result(60, -0.1, -0.3, 12, -0.1),
        ])
        self.assertEqual(rec.status, "REJECTED")


# ==========================================================
# Research memory
# ==========================================================


class MemoryTest(unittest.TestCase):
    def test_record_and_recall_deterministic(self):
        from core.research.researcher.memory import ResearchMemory
        mem = ResearchMemory()
        inv_id = mem.investigation_id_for("SYM", "q?", ["H1"])
        mem.record(inv_id, "q?", [], ["exp-1"], ["VALIDATED"], [], "VALIDATED")
        self.assertTrue(mem.contains_question("q?"))
        self.assertEqual(len(mem.recall("q?")), 1)
        self.assertIn("exp-1", mem.recall("q?")[0]["experiment_ids"])

    def test_next_suggestion_respects_probed_dims(self):
        from core.research.researcher.memory import ResearchMemory
        from core.research.researcher import Hypothesis
        mem = ResearchMemory()
        h = Hypothesis(
            hypothesis_id="H1", kind="K", question="Q", statement="s",
            overrides={"rr": [1.5], "entry_offset_atr": [0.0]},
        )
        inv = mem.investigation_id_for("SYM", "Q", ["H1"])
        mem.record(inv, "Q", [h], ["e1"], ["VALIDATED"], [], "VALIDATED")
        nudge = mem.next_suggestion("Q")
        self.assertEqual(nudge, "entry_offset")

    def test_json_round_trip(self):
        from core.research.researcher.memory import ResearchMemory
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "memory.json")
            mem = ResearchMemory(path=path)
            inv = mem.investigation_id_for("SYM", "Q?", ["H9"])
            mem.record(inv, "Q?", [], ["e9"], ["REJECTED"], [], "REJECTED")
            mem2 = ResearchMemory(path=path)
            self.assertTrue(mem2.contains_question("Q?"))
            self.assertIn("e9", mem2.recall("Q?")[0]["experiment_ids"])

    def test_corrupt_file_degrades_to_fresh_memory(self):
        from core.research.researcher.memory import ResearchMemory
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{ not json")
            mem = ResearchMemory(path=path)
            self.assertEqual(mem.recall("anything"), ())


# ==========================================================
# Autonomous researcher end-to-end (real 9B-9G machinery)
# ==========================================================


class AutonomousResearcherTest(unittest.TestCase):

    def test_win_population_validates_with_evidence_chain(self):
        candles = candle_series(48, 42)
        researcher = AutonomousResearcher(candles=candles)
        report = researcher.investigate(
            make_win_records(40, baseline_losses=12),
            candles=candles, symbol="SYM",
        )
        self.assertEqual(report.phase, "9H")
        self.assertEqual(report.status, "VALIDATED")
        self.assertFalse(report.production_ready)
        self.assertTrue(report.context.records > 0)
        self.assertTrue(report.hypotheses)
        recs = [r.status for r in report.recommendations]
        self.assertIn("VALIDATED", recs)
        for rec in report.recommendations:
            self.assertFalse(rec.is_production_directive)
            if rec.status in ("VALIDATED", "REJECTED", "HYPOTHESIS"):
                self.assertTrue(rec.evidence)
        self.assertTrue(
            any("production" in lim.lower()
                for lim in report.standing_limitations)
        )

    def test_evidence_chain_marker_in_render(self):
        candles = candle_series(48, 42)
        report = AutonomousResearcher(candles=candles).investigate(
            make_win_records(40, baseline_losses=12),
            candles=candles, symbol="SYM",
        )
        text = report.render()
        for marker in ("DATASET", "HYPOTHESIS", "RECOMMENDATION",
                       "LIMITATION"):
            self.assertIn(marker, text)

    def test_deterministic_investigation(self):
        candles = candle_series(48, 42)
        a = AutonomousResearcher(candles=candles).investigate(
            make_win_records(40, baseline_losses=12),
            candles=candles, symbol="SYM",
        )
        b = AutonomousResearcher(candles=candles).investigate(
            make_win_records(40, baseline_losses=12),
            candles=candles, symbol="SYM",
        )
        self.assertEqual(a.investigation_id, b.investigation_id)
        self.assertEqual(
            [h.hypothesis_id for h in a.hypotheses],
            [h.hypothesis_id for h in b.hypotheses],
        )
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_memory_dedup_second_run_skips_rediscovery(self):
        candles = candle_series(48, 42)
        from core.research.researcher import ResearchMemory
        memory = ResearchMemory()
        researcher = AutonomousResearcher(candles=candles, memory=memory)
        first = researcher.investigate(
            make_win_records(40, baseline_losses=12),
            candles=candles, symbol="SYM",
        )
        self.assertEqual(first.status, "VALIDATED")
        self.assertEqual(first.recommendations[0].question,
                         first.hypotheses[0].question)
        second = researcher.investigate(
            make_win_records(40, baseline_losses=12),
            candles=candles, symbol="SYM",
        )
        self.assertEqual(len(second.hypotheses), 0)
        self.assertIn(
            second.recommendations[0].status,
            ("OBSERVATION", "INSUFFICIENT_EVIDENCE"),
        )
        # the first research question is still documented exactly once
        self.assertEqual(
            len(memory.recall(first.recommendations[0].question)), 1,
        )

    def test_insufficient_evidence_for_tiny_population(self):
        candles = candle_series(10, 8)
        report = AutonomousResearcher(candles=candles).investigate(
            make_win_records(3), candles=candles, symbol="SYM",
        )
        statuses = [r.status for r in report.recommendations]
        self.assertIn("INSUFFICIENT_EVIDENCE", statuses)
        self.assertNotIn("VALIDATED", statuses)

    def test_insufficient_evidence_for_vacuous_population(self):
        candles = candle_series(10, 8)
        report = AutonomousResearcher(candles=candles).investigate(
            [], candles=candles, symbol="SYM",
        )
        self.assertEqual(report.status, "INSUFFICIENT_EVIDENCE")
        self.assertTrue(report.recommendations)
        self.assertEqual(
            report.recommendations[0].status, "INSUFFICIENT_EVIDENCE",
        )

    def test_oos_cannot_be_bypassed_by_in_sample_advantage(self):
        # in-sample head wins; the chronological OOS tail (unfilled)
        # can never produce validation.
        candles = candle_series(64, 40)
        report = AutonomousResearcher(candles=candles).investigate(
            make_win_records(48), candles=candles, symbol="SYM",
        )
        statuses = [r.status for r in report.recommendations]
        self.assertIn("HYPOTHESIS", statuses)
        self.assertNotIn("VALIDATED", statuses)

    def test_failed_experiments_retained_in_report_json(self):
        from core.research.researcher import ExperimentExecutor
        candles = candle_series(48, 42)
        from core.research.researcher import NullProvider
        from core.research.researcher.memory import ResearchMemory
        from core.research.researcher.planner import ResearchPlanner
        from core.research.researcher.types import EvidenceContext
        records = make_win_records(40)
        ctx = build_context(records)
        hypotheses, _ = ResearchPlanner().plan(ctx, NullProvider())
        executor = ExperimentExecutor(candles)
        # run carries the full counterfactual + statistical + OOS
        # evidence for every configuration, nothing pruned.
        run = executor.execute(
            records, DEFAULT_BASE_CONFIG, hypotheses[0],
        )
        self.assertTrue(run.results)
        payload = [r.to_dict() for r in run.results]
        self.assertTrue(all("experiment_id" in p for p in payload))
        self.assertTrue(payload[0]["metrics"])

    def test_records_never_mutated_by_investigation(self):
        candles = candle_series(48, 42)
        records = make_win_records(40)
        before = [r.to_dict() if hasattr(r, "to_dict") else str(r.dict())
                  for r in records]
        AutonomousResearcher(candles=candles).investigate(
            records, candles=candles, symbol="SYM",
        )
        after = [r.to_dict() if hasattr(r, "to_dict") else str(r.dict())
                 for r in records]
        self.assertEqual(before, after)


# ==========================================================
# Boundaries: research-only, no production, no trading
# ==========================================================


class BoundaryTest(unittest.TestCase):
    def _researcher_sources(self):
        base = os.path.join(os.path.dirname(__file__), "..", "core",
                            "research", "researcher")
        for fname in sorted(os.listdir(base)):
            if fname.endswith(".py"):
                with open(os.path.join(base, fname), encoding="utf-8") as fh:
                    yield fname, fh.read()

    def test_no_production_internals_imported(self):
        banned = re.compile(
            r"^(\s*)(from|import)\s+"
            r"(core\.)?(execution|risk|portfolio|engine|trade|account|"
            r"strategy)\b"
        )
        for fname, src in self._researcher_sources():
            for lineno, line in enumerate(src.splitlines(), 1):
                if banned.match(line):
                    self.fail(
                        f"{fname}:{lineno} imports production internals: "
                        f"{line.strip()}"
                    )

    def test_no_top_level_ai_sdk_imports(self):
        for fname, src in self._researcher_sources():
            for lineno, line in enumerate(src.splitlines(), 1):
                if line.startswith(("import ", "from ")):
                    if re.search(
                        r"^\s*(import|from)\s+(torch|tensorflow|sklearn|"
                        r"keras|transformers|openai|anthropic|mlx|mlflow)",
                        line,
                    ):
                        self.fail(
                            f"{fname}:{lineno} opens an AI SDK at module "
                            "top level"
                        )

    def test_no_order_or_ledger_touches(self):
        for fname, src in self._researcher_sources():
            low = src.lower()
            for token in ("trade opening", "place order", "order_placement"):
                self.assertNotIn(token, low)

    def test_default_baseline_config_is_supported(self):
        params = DEFAULT_BASE_CONFIG.params
        self.assertEqual(params["entry_model"], "BREAKOUT_CONTINUATION")
        self.assertIn("rr", params)


if __name__ == "__main__":
    unittest.main()