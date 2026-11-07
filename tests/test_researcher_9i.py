"""
====================================================

QuantEngine

Phase 9I -- Unified Research Dataset / Knowledge & Data Intelligence tests

Proves the research-only knowledge/data layer that unifies 9A-9H
evidence into one queryable ResearchDataset:

   * row model: deterministic sha1 ids (never UUID/timestamp), closed
     source vocabulary, kv + measured evidence bags, round-trip
   * collectors: read-only normalization of journal records,
     counterfactual outcomes, 9D analysis, 9E intelligence, 9F feature
     snapshots, 9G ML report, and 9H investigations into unified rows
   * ResearchDataset: append-only, dedup by row_id, deterministic
     JSON persistence, corrupt file -> fresh
   * queries - entry_pipeline_breakdown: answers "N structurally valid
     setups, why only M entered" (by category + rejection reason)
   * queries - recovery_candidates: answers "of the missed/rejected,
     which could have been captured profitably under an alternative
     9B/9C config" with captured-vs-missed economics
   * queries - unify_by_observation / aggregate / answer_context
   * boundaries: never imports production internals, never orders,
     never auto-promotes, deterministic, inputs never mutated

Uses ONLY the real 9A-9H surfaces and stdlib; offline; deterministic.
====================================================
"""

import json
import os
import re
import tempfile
import unittest

from core.research.dataset import (
    ResearchRow,
    ResearchDataset,
    DatasetSource as S,
    collect_journal,
    collect_counterfactual,
    collect_analysis,
    collect_intelligence,
    collect_features,
    collect_ml,
    collect_researcher,
    entry_pipeline_breakdown,
    recovery_candidates,
    unify_by_observation,
    aggregate,
    answer_context,
)
from core.research.journal import OpportunityRecord
from core.research.counterfactual import (
    CounterfactualConfig,
    CounterfactualOutcome,
    FILLED,
    REJECTED,
    ENTRY_NOT_REACHED,
    MISSED_CONTINUATION,
)


# ==========================================================
# Fixtures
# ==========================================================


def _record(canonical_id, terminal, direction="BULLISH",
            instrument="ES", rejection=None, trade_result="",
            pnl=0.0, r=0.0):
    setup = {
        "bar": 2, "entry": 100.0, "stop_loss": 98.0,
        "take_profit": 104.0, "atr": 4.0, "risk_reward": 2.0,
    }
    if rejection:
        setup["rejection_reasons"] = [rejection]
    trade = {}
    if trade_result:
        trade.update({
            "result": trade_result, "pnl": pnl, "risk_amount": 4.0,
            "r": r, "exit_price": 104.0,
        })
    return OpportunityRecord(
        canonical_id=canonical_id,
        instrument_id=instrument,
        direction=direction,
        strategy="BREAKOUT_CONTINUATION",
        setup_id=canonical_id,
        setup=setup,
        trade=trade,
        terminal_outcome=terminal,
    )


def _cf(observation_id, result, rr=2.0, entry_model="BREAKOUT_CONTINUATION",
        r=1.5, pnl=6.0, entry_offset=0.0, expiry=None, experiment_id="exp-r"):
    outcome = CounterfactualOutcome(
        experiment_id=experiment_id,
        opportunity_id=observation_id,
        config=CounterfactualConfig(params={
            "entry_model": entry_model,
            "entry_offset_atr": entry_offset,
            "rr": rr,
        }),
        filled=True,
        result=result,
        pnl=pnl,
        r=r,
        mfe=6.0,
        mae=0.5,
        bars_in_trade=2,
        entry_reached=True,
        direction="BULLISH",
        instrument_id="ES",
    )
    return outcome


# ==========================================================
# Row model
# ==========================================================


class RowTest(unittest.TestCase):
    def test_deterministic_ids_not_uuid(self):
        row = ResearchRow(source=S.JOURNAL, observation_id="o1", kv={"a": 1})
        self.assertTrue(row.row_id.startswith("I-"))
        self.assertRegex(row.row_id, "^I-[0-9a-f]{10}$")
        row2 = ResearchRow(
            source=S.JOURNAL, observation_id="o1", kv={"a": 1},
        )
        self.assertEqual(row.row_id, row2.row_id)

    def test_ids_differ_across_content(self):
        a = ResearchRow(source=S.JOURNAL, observation_id="o1", kv={"a": 1})
        b = ResearchRow(source=S.JOURNAL, observation_id="o1", kv={"a": 2})
        self.assertNotEqual(a.row_id, b.row_id)

    def test_round_trip(self):
        from core.research.dataset import row_from_dict
        row = ResearchRow(
            source=S.COUNTERFACTUAL, observation_id="o1",
            direction="BULLISH", category=FILLED, result="WIN",
            kv={"entry_model": "BREAKOUT_CONTINUATION"},
            measured={"r": 1.5},
        )
        restored = row_from_dict(row.to_dict())
        self.assertEqual(restored, row)


# ==========================================================
# Collectors (read-only normalization)
# ==========================================================


class CollectorTest(unittest.TestCase):
    def test_collect_journal(self):
        rows = collect_journal([
            _record("o1", "FILLED_CLOSED", trade_result="WIN",
                    pnl=2.0, r=0.5),
            _record("o2", "REJECTED", rejection="TOO_FAR_FROM_MARKET"),
        ])
        self.assertEqual(len(rows), 2)
        by_id = {r.observation_id: r for r in rows}
        self.assertEqual(by_id["o1"].category, FILLED)
        self.assertEqual(by_id["o1"].result, "WIN")
        self.assertEqual(by_id["o1"].measured["r"], 0.5)
        self.assertEqual(by_id["o2"].category, REJECTED)
        self.assertIn(
            "TOO_FAR_FROM_MARKET", by_id["o2"].kv["rejection_reasons"],
        )

    def test_collect_counterfactual(self):
        rows = collect_counterfactual([
            _cf("o9", "WIN", entry_offset=0.25),
            _cf("o9", "LOSS", rr=3.0, r=-1.0),
        ])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].source, S.COUNTERFACTUAL)
        self.assertEqual(rows[0].kv["entry_offset_atr"], 0.25)
        self.assertEqual(rows[0].measured["r"], 1.5)
        self.assertEqual(rows[0].result, "WIN")

    def test_collect_analysis(self):
        from core.research.analyzer.research_report import ResearchReport
        from types import SimpleNamespace
        exp = SimpleNamespace(
            experiment_id="exp-1",
            metrics={"filled": 12, "settled": 10, "wins": 8,
                     "losses": 2, "expectancy": 0.6, "avg_R": 1.2},
            recovery=SimpleNamespace(recovered=5),
            comparison=SimpleNamespace(to_dict=lambda: {
                "delta_expectancy": 0.4, "incremental_fills": 3,
                "incremental_R": 2.0, "incremental_pnl": 8.0,
            }),
            config=None,
        )
        report = ResearchReport()
        report.experiments = [exp]
        report.baseline_metrics = {"filled": 9, "settled": 8,
                                   "expectancy": 0.2}
        rows = collect_analysis(report)
        exps = [r for r in rows if r.category == "EXPERIMENT"]
        base = [r for r in rows if r.category == "BASELINE"]
        self.assertEqual(len(exps), 1)
        self.assertEqual(len(base), 1)
        self.assertEqual(exps[0].source_id, "exp-1")
        self.assertEqual(exps[0].measured["delta_expectancy"], 0.4)
        self.assertEqual(base[0].observation_id, "baseline")

    def test_collect_intelligence_and_features_ml_research(self):
        # 9E recommendation row
        from types import SimpleNamespace
        rec = SimpleNamespace(
            recommendation_id="REC-9e-1", category="ENTRY_OFFSET_ANALYSIS",
            status="HYPOTHESIS", evidence_strength="MODERATE",
            affected_opportunity_categories=("ENTRY_NOT_REACHED",),
            affected_directions=("BULLISH",), affected_symbols=("ES",),
            parameters_changed={"entry_offset_atr": 0.25},
            hypothesis="offset recovers", incremental_fills=3,
            recovered_opportunities=2, recovered_wins=2,
            recovery_losses=0, sample_size=35,
            expectancy_delta=0.5, win_rate_delta=10.0,
            robustness_status="ROBUST",
            baseline_metrics={"expectancy": 0.1, "filled": 9},
            candidate_metrics={"expectancy": 0.6, "filled": 12},
        )
        from core.research.intelligence import IntelligenceReport
        report = IntelligenceReport(
            phase="9E", status="HYPOTHESIS", lead=rec,
            recommendations=(rec,),
            evidence=(), confluence=None, insights={}, baseline={},
            hypotheses=(), rejected=frozenset(), horizon="1m",
        )
        irows = collect_intelligence(report)
        self.assertEqual(len(irows), 1)
        self.assertEqual(irows[0].source, S.INTELLIGENCE)
        self.assertEqual(irows[0].measured["incremental_fills"], 3)
        self.assertEqual(irows[0].kv["status"], "HYPOTHESIS")

        # 9F feature snapshot row
        from core.research.features import FeatureSnapshot
        snap = FeatureSnapshot(
            opportunity_id="o1", instrument_id="ES", direction="BULLISH",
            decision_bar=2, features={"wyckoff_phase": "ACCUMULATION",
                                      "fvg_present": True},
        )
        frows = collect_features([snap])
        self.assertEqual(len(frows), 1)
        self.assertEqual(frows[0].source, S.FEATURE)
        self.assertEqual(frows[0].kv["wyckoff_phase"], "ACCUMULATION")
        self.assertIsNone(snap.to_dict()["features"].get("obv_trend"))

        # 9G ML report row
        from core.research.ml import MlResearchReport
        mlr = SimpleNamespace(
            ml_results={
                "WIN": {"backend": "numpy", "status": "TRAINED",
                        "kind": "decision-tree",
                        "auc_validation": 0.61, "auc_oos": 0.58},
                "ENTRY_REACHED": {"backend": "numpy", "status": "TRAINED",
                                  "kind": "logistic",
                                  "auc_validation": 0.7, "auc_oos": 0.66},
            },
            interaction=[],
        )
        mrows = collect_ml(MlResearchReport(
            snapshots=(), split=None, walk_forward=None, baseline=None,
            conditional={}, ml_results=mlr.ml_results, interaction=[],
            recovery=None, backend="numpy", features=(),
        ))
        self.assertTrue(any(
            r.category == "ML_TARGET" and r.result == "WIN" for r in mrows
        ))

        # 9H investigation row
        from core.research.researcher import InvestigationReport
        inv = InvestigationReport(
            phase="9H", investigation_id="INV-1", symbol="ES",
            hypotheses=(), recommendations=(), status="VALIDATED",
            provider="null", provider_available=True,
            production_ready=False,
        )
        rrows = collect_researcher(inv)
        self.assertTrue(any(
            r.category == "INVESTIGATION" and r.result == "VALIDATED"
            for r in rrows
        ))


# ==========================================================
# ResearchDataset container
# ==========================================================


class DatasetTest(unittest.TestCase):
    def test_append_dedup_load(self):
        dataset = ResearchDataset()
        row = ResearchRow(source=S.JOURNAL, observation_id="o1")
        dataset.add_row(row)
        dataset.add_row(row)  # dedup by id
        self.assertEqual(dataset.row_count(), 1)
        dataset.add_rows(collect_journal([
            _record("o2", "REJECTED", rejection="STALE_ZONE"),
        ]))
        self.assertEqual(dataset.row_count(), 2)
        self.assertEqual(len(dataset.rows(S.JOURNAL)), 2)
        with self.assertRaises(ValueError):
            dataset.rows("NOT_A_SOURCE")

    def test_persist_round_trip_and_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "research.json")
            ds = ResearchDataset()
            ds.add_rows(collect_journal([
                _record("o1", "FILLED_CLOSED", trade_result="WIN"),
                _record("o2", "REJECTED", rejection="TOO_FAR_FROM_MARKET"),
            ]))
            ds.add_rows(collect_counterfactual([_cf("o2", "WIN")]))
            ds.persist(path)
            loaded = ResearchDataset.load(path)
            self.assertEqual(loaded.row_count(), ds.row_count())
            self.assertEqual(
                {r.observation_id for r in loaded.rows(S.JOURNAL)},
                {"o1", "o2"},
            )
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write("{ nope")
            fresh = ResearchDataset.load(bad)
            self.assertTrue(fresh.empty())

    def test_inputs_never_mutated(self):
        rec = _record("o1", "FILLED_CLOSED", trade_result="WIN")
        before = rec.to_dict()
        collect_journal([rec])
        self.assertEqual(rec.to_dict(), before)


# ==========================================================
# Queries: why only some entered?
# ==========================================================


class EntryPipelineTest(unittest.TestCase):
    def _dataset(self):
        ds = ResearchDataset()
        ds.add_rows(collect_journal([
            _record("o1", "FILLED_CLOSED", trade_result="WIN"),
            _record("o2", "FILLED_CLOSED", trade_result="LOSS",
                    pnl=-4.0, r=-1.0),
            _record("o3", "FILLED_CLOSED", trade_result="WIN"),
            _record("o4", "REJECTED", rejection="TOO_FAR_FROM_MARKET"),
            _record("o5", "REJECTED", rejection="TOO_FAR_FROM_MARKET"),
            _record("o6", "REJECTED", rejection="STALE_ZONE"),
            _record("o7", "EXPIRED", instrument="NQ"),
            _record("o8", "ORDER_NOT_CREATED"),
        ]))
        return ds

    def test_breakdown_counts(self):
        ds = self._dataset()
        report = entry_pipeline_breakdown(ds)
        self.assertEqual(report["structurally_valid_setups"], 8)
        self.assertEqual(report["entered"], 3)
        self.assertEqual(report["not_entered"], 5)
        self.assertAlmostEqual(report["entry_rate"], 3 / 8)
        self.assertEqual(report["settled"], 3)
        self.assertEqual(report["wins"], 2)
        self.assertEqual(report["losses"], 1)
        self.assertAlmostEqual(report["win_rate"], 2 / 3)
        self.assertEqual(report["by_category"][FILLED], 3)
        self.assertEqual(report["by_category"][REJECTED], 3)
        self.assertEqual(
            report["rejected_by_reason"]["TOO_FAR_FROM_MARKET"], 2,
        )
        self.assertEqual(report["rejected_by_reason"]["STALE_ZONE"], 1)

    def test_deterministic(self):
        a = entry_pipeline_breakdown(self._dataset())
        b = entry_pipeline_breakdown(self._dataset())
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


# ==========================================================
# Queries: which missed could have been captured?
# ==========================================================


class RecoveryCandidateTest(unittest.TestCase):
    def test_missed_opportunities_recoverable(self):
        ds = ResearchDataset()
        # 1 captured WIN baseline
        ds.add_rows(collect_journal([
            _record("o1", "FILLED_CLOSED", trade_result="WIN"),
            # 4 missed/rejected that counterfactually WIN under an
            # alternative config (entry offset / expiry / rr changed)
            _record("o2", "REJECTED", rejection="TOO_FAR_FROM_MARKET"),
            _record("o3", "REJECTED", rejection="STALE_ZONE"),
            _record("o4", "ORDER_NOT_CREATED"),
            _record("o5", "EXPIRED"),
            # one missed that is NOT recovered (stays LOSS)
            _record("o6", "REJECTED", rejection="INSUFFICIENT_RISK_WIDTH"),
        ]))
        # counterfactual experiments: o2-o5 recover to WIN, o6 to LOSS
        cf_rows = [
            _cf("o2", "WIN", entry_offset=0.25, experiment_id="exp-a"),
            _cf("o3", "WIN", entry_offset=0.5, rr=3.0, experiment_id="exp-b"),
            _cf("o4", "WIN", expiry=5, experiment_id="exp-c"),
            _cf("o5", "WIN", entry_model="MARKET_CONFIRMATION",
                experiment_id="exp-d"),
            _cf("o6", "LOSS", r=-1.0, pnl=-4.0, experiment_id="exp-e"),
        ]
        ds.add_rows(collect_counterfactual(cf_rows))

        report = recovery_candidates(ds)
        self.assertEqual(report["captured_wins"], 1)
        self.assertEqual(report["captured_opportunity_count"], 1)
        self.assertEqual(report["potentially_recoverable_count"], 4)
        self.assertEqual(report["missed_wins_before_recovery"], 4)
        self.assertEqual(report["recovery_candidate_count"], 4)
        self.assertEqual(
            {c["observation_id"] for c in report["recovery_candidates"]},
            {"o2", "o3", "o4", "o5"},
        )
        # the recovered per-opportunity R is the best alternative config
        self.assertAlmostEqual(
            report["expected_captured_R_from_recovery"], 4 * 1.5,
        )
        self.assertEqual(
            report["net_captured_opportunities"], 1 + 4,
        )
        # o6 (stays a loss even under the alternative) is NOT a candidate
        self.assertNotIn(
            "o6", {c["observation_id"]
                   for c in report["recovery_candidates"]},
        )
        # the alternative config that recovered each is presented
        for c in report["recovery_candidates"]:
            self.assertIn("alternative_config", c)
            self.assertNotIn("o6", c["observation_id"])


# ==========================================================
# Unify / aggregate / answer context
# ==========================================================


class KnowledgeLayerTest(unittest.TestCase):
    def _unified(self):
        ds = ResearchDataset()
        ds.add_rows(collect_journal([
            _record("o1", "FILLED_CLOSED", trade_result="WIN"),
            _record("o2", "REJECTED", rejection="TOO_FAR_FROM_MARKET"),
        ]))
        ds.add_rows(collect_counterfactual([_cf("o1", "WIN"),
                                            _cf("o2", "WIN")]))
        from core.research.features import FeatureSnapshot
        ds.add_rows(collect_features([
            FeatureSnapshot(
                opportunity_id="o1", features={"wyckoff_phase": "ACCUMULATION"},
            ),
        ]))
        return ds

    def test_unify_by_observation(self):
        ds = self._unified()
        chain = unify_by_observation(ds, "o1")
        sources = {r.source for r in chain}
        self.assertIn(S.JOURNAL, sources)
        self.assertIn(S.COUNTERFACTUAL, sources)
        self.assertIn(S.FEATURE, sources)

    def test_aggregate(self):
        ds = self._unified()
        rows = ds.rows(S.COUNTERFACTUAL)
        out = aggregate(
            rows, group_by=("direction",), measures=(("result", "win_rate"),),
            filters=lambda r: r.result in ("WIN", "LOSS"),
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["direction"], "BULLISH")
        self.assertEqual(out[0]["result_win_rate"], 1.0)

    def test_answer_context(self):
        ds = self._unified()
        ctx = answer_context(ds)
        self.assertEqual(ctx["phase"], "9I")
        self.assertEqual(ctx["structurally_valid_setups"], 2)
        self.assertEqual(ctx["entered"], 1)
        self.assertEqual(ctx["not_entered"], 1)
        self.assertIn("research_only", ctx)
        self.assertTrue(ctx["research_only"])


# ==========================================================
# Boundaries: research-only, no production, no trading
# ==========================================================


class BoundaryTest(unittest.TestCase):
    def _sources(self):
        base = os.path.join(os.path.dirname(__file__), "..", "core",
                            "research", "dataset")
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
        for fname, src in self._sources():
            for lineno, line in enumerate(src.splitlines(), 1):
                if banned.match(line):
                    self.fail(
                        f"{fname}:{lineno} imports production internals: "
                        f"{line.strip()}"
                    )

    def test_no_auto_promotion_or_order_tokens(self):
        for fname, src in self._sources():
            low = src.lower()
            for token in ("place order", "order_placement",
                          "auto_promot", "promote to production"):
                self.assertNotIn(token, low)

    def test_no_random_or_datetime_ids(self):
        for fname, src in self._sources():
            self.assertNotIn("import random", src)
            self.assertNotIn("import uuid", src)
            self.assertNotIn("datetime.now", src)
            self.assertNotIn("time.time", src)


if __name__ == "__main__":
    unittest.main()
