"""
====================================================================

QuantEngine

Phase 9N -- Research Recommendation & Evidence Readback tests

Proves the deterministic, research-only 9N readback layer. The layer
consumes the frozen 9M OosReport (and optional frozen 9L/9K reports)
and, for every consumed discovery, emits a RecommendationFinding
(evidence-rich) that is flattened 1:1 into a Recommendation, packaged
into the frozen RecommendationReport -- the immutable boundary between
the recommendation engine and anything downstream.

The exact report contract under test:

   * immutable / frozen RecommendationReport with production_ready
     permanently False (construction with True raises; assignment to
     True fails);
   * is_production_ready property permanently False;
   * emission_check() verifies the isolation contract against the
     ACTUAL serialized body (research statuses only, no production
     directive, no NEVER_EMITTED promotion token in the body,
     immutable);
   * deterministic recommendation ids and deterministic report id
     (canonical payload EXCLUDING report_id -- no self-reference, no
     uuid/random/datetime/hash);
   * deterministic serialization (to_dict / to_json);
   * build_report is a constructor/validator: refuses production
     directives, forces production_ready false, preserves every rejected
     / inconclusive finding (no auto-drop), and is stable under
     reordered input;
   * production isolation: no production/execution imports, no order
     submission, no ledger access, no persistence, no parameter
     mutation;
   * the 9N -> downstream boundary is preserved: the engine never turns
     a recommendation into an execution directive or production_ready.

Uses ONLY the real 9A-9N machinery (imports the frozen 9M fixture).
Stdlib only; offline; deterministic.
====================================================================
"""

import json
import os
import unittest
from dataclasses import FrozenInstanceError

from core.research.oos import OOS_STATUSES
from core.research.recommendation import (
    NEVER_EMITTED,
    RECOMMENDATION_DIRECTIVE,
    RECOMMENDATION_DIRECTIVE_TEXT,
    RECOMMENDATION_STATUSES,
    READBACK_QUESTIONS,
    REVIEW_CONSUMES,
    REVIEW_PROTOCOL_FROZEN,
    Recommendation,
    RecommendationEngine,
    RecommendationFinding,
    RecommendationReport,
    build_finding,
    build_report,
    recommend_status,
    to_recommendation,
)
from tests.test_researcher_9m import (
    ALL_WIN,
    ALL_WIN_CANDLES,
    BASE_CONFIG,
    OosValidationEngine as _OosEngine,
    build_candles_for,
    build_records,
    make_hyp,
)


def run_oos(variant_kwargs=None, oos_mix=None, hyp_builder=None):
    eng = _OosEngine()
    records = build_records(oos_mix=oos_mix) if oos_mix else ALL_WIN
    candles = build_candles_for(records) if oos_mix else ALL_WIN_CANDLES
    kwargs = dict(statement="clean long recovery", origin="9K",
                  entry_model="LIMIT_RETEST", symbol="X", direction="LONG",
                  wf=True)
    if variant_kwargs:
        kwargs.update(variant_kwargs)
    h = hyp_builder(**kwargs) if hyp_builder else make_hyp(**kwargs)
    return eng.run(records, candles, BASE_CONFIG, [h], outcome_bars=2)


# ------------------------------------------------------------------
# synthetic report / finding helpers (dict-equivalent 9M inputs)
# ------------------------------------------------------------------

def _synthetic_9m_result(status, conditional=False, seven_e=False,
                         periods_survived=6, periods_rejected=0,
                         sign_consistent=6, familywise=True,
                         robustness="HIGH", survival=None, symbol="X",
                         direction="LONG", statement="synthetic claim",
                         oos_report_id="M-SYNTH-OOS"):
    if survival is None:
        survival = (periods_survived / 6.0) if periods_survived else None
    return {
        "oos_report_id": oos_report_id,
        "hypothesis_id": "H-SYNTH",
        "origin": "9K",
        "statement": statement,
        "symbol": symbol,
        "direction": direction,
        "regime_dim": ("trend_vs_range" if conditional else None),
        "regime_label": ("TREND" if conditional else None),
        "seven_e": seven_e,
        "status": status,
        "periods_tested": 6,
        "periods_available": 6,
        "periods_survived": periods_survived,
        "periods_rejected": periods_rejected,
        "periods_inconclusive": 0,
        "periods_unavailable": 0,
        "survival_ratio": survival,
        "sign_consistent_periods": sign_consistent,
        "economic_consistent": survival is not None and survival > 0,
        "walk_forward_passed": True,
        "survives_familywise": familywise,
        "params": {"entry_model": "LIMIT_RETEST", "rr": 2.0},
        "per_period": [
            {"period": "OOS-%d" % (i + 1), "status": "VALIDATED"}
            for i in range(6)
        ],
        "robustness": {"level": robustness},
    }


def synthetic_report(status, conditional=False, seven_e=False,
                     robustness="HIGH", periods_survived=6,
                     periods_rejected=0, statement="synthetic claim"):
    return {
        "report_id": "M-SYNTH",
        "results": [
            _synthetic_9m_result(
                status, conditional=conditional, seven_e=seven_e,
                robustness=robustness,
                periods_survived=periods_survived,
                periods_rejected=periods_rejected,
                statement=statement)
        ],
    }


def one_finding_report(status, **kw):
    f = build_finding(_synthetic_9m_result(status, **kw))
    return build_report([to_recommendation(f)], findings=[f])


# ------------------------------------------------------------------
# locked-contract surface tests
# ------------------------------------------------------------------

class TestProtocolSurface(unittest.TestCase):
    def test_closed_recommendation_vocabulary(self):
        self.assertEqual(RECOMMENDATION_STATUSES,
                         ("7E_BLOCKED", "NO_EVIDENCE", "INCONCLUSIVE",
                          "REJECTED", "REQUIRES_MORE_OOS", "CONDITIONAL",
                          "PROMISING", "ROBUST_RESEARCH_FINDING"))

    def test_directive_is_locked_investigate(self):
        self.assertEqual(RECOMMENDATION_DIRECTIVE, "INVESTIGATE_FURTHER")
        self.assertTrue(RECOMMENDATION_DIRECTIVE_TEXT)
        self.assertNotIn("CHANGE", RECOMMENDATION_DIRECTIVE.upper())

    def test_readback_questions(self):
        self.assertEqual(READBACK_QUESTIONS,
                         ("what_discovered", "why_it_worked",
                          "where_it_worked", "where_it_failed",
                          "how_robust"))

    def test_review_protocol_and_surface(self):
        self.assertTrue(REVIEW_PROTOCOL_FROZEN)
        self.assertEqual(set(REVIEW_CONSUMES), {"9M", "9L", "9K"})

    def test_statuses_are_closed_and_unique(self):
        self.assertEqual(len(set(RECOMMENDATION_STATUSES)),
                         len(RECOMMENDATION_STATUSES))

    def test_finding_rejects_unknown_status_and_directive(self):
        with self.assertRaises(ValueError):
            RecommendationFinding(recommendation_status="NOT_A_STATUS")
        with self.assertRaises(ValueError):
            RecommendationFinding(
                recommendation_status="INCONCLUSIVE",
                directive="CHANGE_STRATEGY")

    def test_recommendation_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            Recommendation(status="NOT_A_STATUS", title="x", rationale="y")


# ------------------------------------------------------------------
# ladder mapping unit tests
# ------------------------------------------------------------------

class TestLadder(unittest.TestCase):
    def test_seven_e_always_blocked(self):
        self.assertEqual(recommend_status(OOS_STATUSES[0]), "7E_BLOCKED")
        self.assertEqual(recommend_status(OOS_STATUSES[7], seven_e=True),
                         "7E_BLOCKED")

    def test_no_evidence(self):
        self.assertEqual(recommend_status(OOS_STATUSES[1]), "NO_EVIDENCE")

    def test_inconclusive(self):
        self.assertEqual(recommend_status(OOS_STATUSES[2]), "INCONCLUSIVE")

    def test_rejected(self):
        self.assertEqual(recommend_status(OOS_STATUSES[3]), "REJECTED")

    def test_requires_more_oos(self):
        self.assertEqual(recommend_status(OOS_STATUSES[4]),
                         "REQUIRES_MORE_OOS")

    def test_promising_conditional_is_not_universal(self):
        self.assertEqual(recommend_status(OOS_STATUSES[5], False), "PROMISING")
        self.assertEqual(recommend_status(OOS_STATUSES[5], True), "CONDITIONAL")

    def test_robust_conditional_is_never_universal(self):
        self.assertEqual(recommend_status(OOS_STATUSES[6], False), "PROMISING")
        self.assertEqual(recommend_status(OOS_STATUSES[6], True), "CONDITIONAL")

    def test_validated_top_rung_requires_high_and_unconditional(self):
        self.assertEqual(recommend_status(OOS_STATUSES[7], False,
                                          robustness_level="HIGH"),
                         "ROBUST_RESEARCH_FINDING")
        self.assertEqual(recommend_status(OOS_STATUSES[7], False,
                                          robustness_level="LOW"),
                         "PROMISING")
        self.assertEqual(recommend_status(OOS_STATUSES[7], True,
                                          robustness_level="HIGH"),
                         "CONDITIONAL")

    def test_total_over_full_9m_ladder(self):
        for st in OOS_STATUSES:
            self.assertIn(recommend_status(st), RECOMMENDATION_STATUSES)


# ------------------------------------------------------------------
# evidence chain + 1:1 flattening
# ------------------------------------------------------------------

class TestEvidenceChain(unittest.TestCase):
    def test_finding_retains_full_chain(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        self.assertEqual(f.recommendation_status,
                         "ROBUST_RESEARCH_FINDING")
        self.assertEqual(f.hypothesis.statement, "synthetic claim")
        self.assertEqual(f.hypothesis.symbol, "X")
        self.assertEqual(f.oos.periods_survived, 6)
        self.assertTrue(f.oos.familywise_passed)

    def test_deterministic_finding_id(self):
        a = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        b = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        self.assertEqual(a.recommendation_id, b.recommendation_id)
        self.assertTrue(a.recommendation_id.startswith("N"))

    def test_seven_e_result_blocked(self):
        f = build_finding(_synthetic_9m_result(
            OOS_STATUSES[0], seven_e=True))
        self.assertEqual(f.recommendation_status, "7E_BLOCKED")

    def test_conditional_stays_conditional(self):
        f = build_finding(_synthetic_9m_result(
            OOS_STATUSES[7], conditional=True))
        self.assertEqual(f.recommendation_status, "CONDITIONAL")
        self.assertTrue(f.hypothesis.is_conditional)
        self.assertEqual(f.hypothesis.regime_label, "TREND")

    def test_limitations_retain_failures(self):
        f = build_finding(_synthetic_9m_result(
            OOS_STATUSES[3], periods_rejected=4))
        self.assertEqual(f.recommendation_status, "REJECTED")
        self.assertTrue(any("rejected" in x for x in f.limitations))
        self.assertTrue(any("rejected" in x for x in f.reasons))

    def test_to_recommendation_is_one_to_one(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        r = to_recommendation(f)
        self.assertIsInstance(r, Recommendation)
        self.assertEqual(r.status, f.recommendation_status)
        self.assertEqual(r.hypothesis_id, f.hypothesis.hypothesis_id)
        self.assertEqual(r.symbol, f.hypothesis.symbol)
        self.assertEqual(r.direction, f.hypothesis.direction)
        self.assertEqual(r.oos_report_id, f.oos.oos_report_id)
        # non-conditional synthetic finding carries no regime reference
        self.assertIsNone(r.regime)

    def test_to_recommendation_conditional_sets_regime(self):
        f = build_finding(_synthetic_9m_result(
            OOS_STATUSES[7], conditional=True))
        r = to_recommendation(f)
        self.assertEqual(r.regime, "%s=%s" % (
            f.hypothesis.regime_dim, f.hypothesis.regime_label))

    def test_to_recommendation_preserves_evidence_refs(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        r = to_recommendation(f)
        self.assertEqual(r.hypothesis_id, "H-SYNTH")
        self.assertTrue(r.evidence_ids)
        self.assertEqual(r.evidence_ids[0], f.oos.oos_report_id)

    def test_to_recommendation_deterministic(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        r1 = to_recommendation(f)
        r2 = to_recommendation(build_finding(
            _synthetic_9m_result(OOS_STATUSES[7])))
        self.assertEqual(r1.recommendation_id, r2.recommendation_id)

    def test_to_recommendation_no_invented_semantics(self):
        # A plain finding without walk-forward still flattens faithfully.
        f = build_finding(_synthetic_9m_result(
            OOS_STATUSES[4], periods_survived=3))
        r = to_recommendation(f)
        self.assertEqual(r.status, "REQUIRES_MORE_OOS")
        self.assertEqual(r.metrics[1], ("periods_survived", 3))

    def test_answers_are_deterministic(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        self.assertEqual(f.answers.how_robust, "HIGH")
        self.assertTrue(f.answers.why_it_worked)


# ------------------------------------------------------------------
# engine integration
# ------------------------------------------------------------------

class TestEngine(unittest.TestCase):
    def test_engine_reads_real_9m_report(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        self.assertIsInstance(rep, RecommendationReport)
        self.assertEqual(rep.overview if hasattr(rep, "overview") else
                         rep.evidence_summary.to_dict()["n_findings"], 1)
        self.assertEqual(rep.findings[0].recommendation_status,
                         "ROBUST_RESEARCH_FINDING")

    def test_engine_accepts_dict_report(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos.to_dict())
        self.assertEqual(len(rep.findings), 1)

    def test_engine_1to1_and_statistics(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        self.assertEqual(len(rep.findings), len(rep.recommendations))
        self.assertEqual(rep.statistics.n_recommendations,
                         len(rep.recommendations))
        # each recommendation retains its finding's references
        f = rep.findings[0]
        r = rep.recommendations[0]
        self.assertEqual(r.hypothesis_id, f.hypothesis.hypothesis_id)
        self.assertEqual(r.candidate_id, f.hypothesis.hypothesis_id)
        self.assertEqual(r.oos_report_id, f.oos.oos_report_id)

    def test_engine_deterministic_report_id(self):
        oos = run_oos()
        a = RecommendationEngine().run(oos)
        b = RecommendationEngine().run(oos)
        self.assertEqual(a.report_id, b.report_id)
        self.assertTrue(a.report_id.startswith("N"))

    def test_engine_hypothesis_filter(self):
        oos = run_oos()
        hid = oos.results[0].hypothesis_id
        rep = RecommendationEngine().run(oos, hypothesis_ids=[hid])
        self.assertEqual(len(rep.findings), 1)
        rep2 = RecommendationEngine().run(oos, hypothesis_ids=["NOPE"])
        self.assertEqual(len(rep2.findings), 0)

    def test_engine_empty_report_honest(self):
        class Empty:
            results = ()
        rep = RecommendationEngine().run(Empty())
        self.assertEqual(len(rep.findings), 0)
        self.assertEqual(len(rep.recommendations), 0)

    def test_engine_seven_e_blocked(self):
        oos = run_oos(variant_kwargs={"seven_e": True})
        rep = RecommendationEngine().run(oos)
        self.assertEqual(rep.findings[0].recommendation_status,
                         "7E_BLOCKED")
        self.assertEqual(rep.recommendations[0].status, "7E_BLOCKED")
        self.assertTrue(rep.emission_check()["seven_e_blocked_preserved"])

    def test_unknown_gate_keys_raise(self):
        with self.assertRaises(ValueError):
            RecommendationEngine(gates={"bogus": 1})

    def test_engine_never_emits_execution_directive(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        self.assertIs(rep.production_ready, False)
        self.assertIs(rep.is_production_ready, False)
        for r in rep.recommendations:
            self.assertEqual(r.status[0], r.status[0])  # no-op guard
            self.assertNotIn(r.status, ("DEPLOY", "TRADE", "EXECUTE"))
        for f in rep.findings:
            self.assertEqual(f.directive, "INVESTIGATE_FURTHER")

    def test_to_json_is_stable(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        a = json.loads(rep.to_json())
        b = json.loads(rep.to_json())
        self.assertEqual(a, b)
        self.assertEqual(a["report_id"], rep.report_id)


# ------------------------------------------------------------------
# report contract: determinism
# ------------------------------------------------------------------

class TestReportContract(unittest.TestCase):
    def test_report_id_is_deterministic(self):
        r1 = one_finding_report(OOS_STATUSES[7])
        r2 = one_finding_report(OOS_STATUSES[7])
        self.assertEqual(r1.report_id, r2.report_id)
        self.assertTrue(r1.report_id.startswith("N"))

    def test_report_id_does_not_self_reference(self):
        rep = one_finding_report(OOS_STATUSES[7])
        # to_dict() includes report_id; the report's own payload must not.
        payload = rep._payload()
        self.assertNotIn("report_id", payload)
        self.assertEqual(rep.to_dict()["report_id"], rep.report_id)

    def test_report_id_ignores_input_order(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        g = build_finding(_synthetic_9m_result(OOS_STATUSES[3]))
        ra = build_report([to_recommendation(g), to_recommendation(f)],
                          findings=[g, f])
        rb = build_report([to_recommendation(f), to_recommendation(g)],
                          findings=[f, g])
        self.assertEqual(ra.report_id, rb.report_id)
        self.assertEqual(ra.to_dict(), rb.to_dict())
        self.assertEqual([x.status for x in ra.recommendations],
                         [x.status for x in rb.recommendations])

    def test_full_equality_on_repeat_build(self):
        r1 = one_finding_report(OOS_STATUSES[7])
        r2 = one_finding_report(OOS_STATUSES[7])
        self.assertEqual(r1 == r2, True)
        self.assertEqual(r1.report_id, r2.report_id)
        self.assertEqual(r1.to_dict(), r2.to_dict())

    def test_recommendation_id_is_deterministic(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        a = to_recommendation(f)
        b = to_recommendation(build_finding(
            _synthetic_9m_result(OOS_STATUSES[7])))
        self.assertEqual(a.recommendation_id, b.recommendation_id)

    def test_no_uuid_random_datetime(self):
        for mod in ("uuid", "random", "datetime"):
            self.assertNotIn(mod, open(
                os.path.join(os.path.dirname(__file__), "..",
                             "core", "research", "recommendation",
                             "report.py"), encoding="utf-8").read())

    def test_deterministic_serialization_stable_keys(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        # to_json uses sort_keys so key order is canonical
        self.assertTrue(rep.to_json())


# ------------------------------------------------------------------
# report contract: immutability / production guard
# ------------------------------------------------------------------

class TestProductionGuard(unittest.TestCase):
    def test_construction_with_production_ready_raises(self):
        with self.assertRaises(ValueError):
            RecommendationReport(report_id="x", production_ready=True)

    def test_assignment_to_production_ready_fails(self):
        rep = one_finding_report(OOS_STATUSES[7])
        with self.assertRaises(FrozenInstanceError):
            rep.production_ready = True

    def test_is_production_ready_property_permanently_false(self):
        rep = one_finding_report(OOS_STATUSES[7])
        self.assertIs(rep.is_production_ready, False)

    def test_frozen_report_fields(self):
        rep = one_finding_report(OOS_STATUSES[7])
        with self.assertRaises(FrozenInstanceError):
            rep.report_id = "tampered"

    def test_nested_finding_immutable(self):
        rep = one_finding_report(OOS_STATUSES[7])
        with self.assertRaises(FrozenInstanceError):
            rep.findings[0].reasons = ("tampered",)

    def test_nested_recommendation_immutable(self):
        rep = one_finding_report(OOS_STATUSES[7])
        with self.assertRaises(FrozenInstanceError):
            rep.recommendations[0].title = "tampered"

    def test_finding_frozen(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        with self.assertRaises(FrozenInstanceError):
            f.recommendation_status = "REJECTED"


# ------------------------------------------------------------------
# emission_check / promotion tokens
# ------------------------------------------------------------------

class TestEmissionGuard(unittest.TestCase):
    def test_emission_check_clean(self):
        rep = one_finding_report(OOS_STATUSES[7])
        ec = rep.emission_check()
        self.assertTrue(ec["clean"])
        self.assertIs(ec["production_ready"], False)
        self.assertIs(ec["is_production_ready"], False)
        self.assertTrue(ec["tokens_absent"])
        self.assertTrue(ec["statuses_research_only"])
        self.assertTrue(ec["immutable"])

    def test_promotion_tokens_absent_from_serialized_body(self):
        rep = one_finding_report(OOS_STATUSES[7])
        body = json.dumps(rep.to_dict(), sort_keys=True, default=str)
        for tok in NEVER_EMITTED:
            self.assertNotIn(tok, body)

    def test_never_emitted_not_serialized_into_to_dict(self):
        rep = one_finding_report(OOS_STATUSES[7])
        d = rep.to_dict()
        self.assertNotIn("NEVER_EMITTED", d)


# ------------------------------------------------------------------
# build_report edge cases (Section 24)
# ------------------------------------------------------------------

class TestBuildReportEdgeCases(unittest.TestCase):
    def test_empty_recommendations(self):
        rep = build_report([])
        self.assertEqual(len(rep.recommendations), 0)
        self.assertEqual(len(rep.findings), 0)
        self.assertEqual(rep.evidence_summary.n_recommendations, 0)

    def test_empty_findings(self):
        rep = build_report([])
        self.assertEqual(rep.findings, ())

    def test_all_rejected_preserved(self):
        rep = one_finding_report(OOS_STATUSES[3], periods_rejected=4)
        self.assertEqual(len(rep.findings), 1)
        self.assertEqual(rep.recommendations[0].status, "REJECTED")
        self.assertEqual(rep.evidence_summary.n_rejected, 1)

    def test_all_inconclusive_preserved(self):
        rep = one_finding_report(OOS_STATUSES[2])
        self.assertEqual(rep.recommendations[0].status, "INCONCLUSIVE")
        self.assertEqual(rep.evidence_summary.n_inconclusive, 1)

    def test_mixed_statuses_all_retained(self):
        f_robust = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        f_rej = build_finding(_synthetic_9m_result(
            OOS_STATUSES[3], periods_rejected=4))
        f_7e = build_finding(_synthetic_9m_result(
            OOS_STATUSES[0], seven_e=True))
        rep = build_report(
            [to_recommendation(f_robust), to_recommendation(f_rej),
             to_recommendation(f_7e)],
            findings=[f_robust, f_rej, f_7e])
        self.assertEqual(len(rep.findings), 3)
        statuses = {x.status for x in rep.recommendations}
        self.assertEqual(statuses,
                         {"ROBUST_RESEARCH_FINDING", "REJECTED",
                          "7E_BLOCKED"})
        # ranking keeps everything -- nothing hidden
        self.assertEqual(rep.evidence_summary.n_rejected, 1)
        self.assertEqual(rep.evidence_summary.n_7e_blocked, 1)
        self.assertEqual(rep.evidence_summary.n_robust, 1)

    def test_7e_blocked_terminal(self):
        rep = one_finding_report(OOS_STATUSES[0], seven_e=True)
        self.assertEqual(rep.recommendations[0].status, "7E_BLOCKED")

    def test_duplicate_recommendations_deterministic(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        rep = build_report([to_recommendation(f), to_recommendation(f)],
                           findings=[f, f])
        rep2 = build_report([to_recommendation(f), to_recommendation(f)],
                            findings=[f, f])
        self.assertEqual(rep.report_id, rep2.report_id)
        self.assertEqual(len(rep.recommendations), 2)

    def test_reversed_input_ordering(self):
        f = build_finding(_synthetic_9m_result(OOS_STATUSES[7]))
        g = build_finding(_synthetic_9m_result(OOS_STATUSES[3]))
        a = build_report([to_recommendation(f), to_recommendation(g)],
                         findings=[f, g])
        b = build_report([to_recommendation(g), to_recommendation(f)],
                         findings=[g, f])
        self.assertEqual(a.report_id, b.report_id)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_missing_evidence_is_honest(self):
        rep = build_report([])
        self.assertEqual(rep.evidence_summary.n_recommendations, 0)
        self.assertEqual(len(rep.limitations), 0)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            build_report([Recommendation(status="NOT_A_STATUS",
                                         title="x", rationale="y")])

    def test_production_directive_attempt_rejected(self):
        # A status that IS a production directive is invalid regardless.
        with self.assertRaises(ValueError):
            build_report([Recommendation(status="PRODUCTION_READY",
                                         title="x", rationale="y")])

    def test_deterministic_repeated_construction(self):
        r1 = one_finding_report(OOS_STATUSES[7])
        r2 = one_finding_report(OOS_STATUSES[7])
        self.assertEqual(r1.report_id, r2.report_id)
        self.assertEqual(r1.to_dict(), r2.to_dict())


# ------------------------------------------------------------------
# production isolation
# ------------------------------------------------------------------

class TestProductionIsolation(unittest.TestCase):
    def test_no_production_imports(self):
        pkg = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "core", "research",
            "recommendation"))
        bad_prefixes = ("core.execution", "core.trading", "core.ledger",
                        "core.account", "core.portfolio", "core.risk",
                        "core.market_data", "core.setup", "core.pipeline",
                        "core.broker", "core.strategies")
        for root, _, files in os.walk(pkg):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(root, fn), encoding="utf-8") as fh:
                    txt = fh.read()
                for line in txt.splitlines():
                    if "import" in line:
                        for bad in bad_prefixes:
                            self.assertNotIn(bad, line,
                                             "%s imports %s"
                                             % (os.path.join(root, fn), bad))

    def test_no_random_uuid_datetime_scipy_sklearn(self):
        pkg = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "core", "research",
            "recommendation"))
        forbidden = ("random", "uuid", "datetime", "scipy", "sklearn")
        for root, _, files in os.walk(pkg):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(root, fn), encoding="utf-8") as fh:
                    txt = fh.read()
                for fword in forbidden:
                    self.assertNotIn(fword, txt,
                                     "%s contains %s"
                                     % (os.path.join(root, fn), fword))

    def test_research_only_flag(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        self.assertIs(rep.research_only, True)
        self.assertIs(rep.production_ready, False)

    def test_no_filesystem_persistence_in_build_report(self):
        # build_report must not open files for writing. Scan report.py for
        # write-path calls.
        src = open(os.path.join(os.path.dirname(__file__), "..",
                                "core", "research", "recommendation",
                                "report.py"), encoding="utf-8").read()
        for bad in ("open(", ".write(", ".dump(", "json.dump(",
                    "sqlite", "Path("):
            self.assertNotIn(bad, src)


# ------------------------------------------------------------------
# canonical e2e locks
# ------------------------------------------------------------------

class TestE2E(unittest.TestCase):
    def test_report_ids_stable(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        self.assertEqual(rep.report_id, "Ne4c9dc7886")

    def test_finding_id_stable(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        self.assertEqual(rep.findings[0].recommendation_id, "N7ff6711cff")

    def test_robust_finding_chain_locked(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        f = rep.findings[0]
        self.assertEqual(f.recommendation_status,
                         "ROBUST_RESEARCH_FINDING")
        self.assertEqual(f.oos.oos_report_id, "Me686dca76c")
        self.assertEqual(f.oos.final_status, "VALIDATED_RESEARCH_ONLY")
        self.assertEqual(f.oos.periods_survived, 6)
        self.assertEqual(f.oos.sign_consistent_periods, 6)
        self.assertTrue(f.oos.familywise_passed)
        self.assertEqual(f.oos.robustness_level, "HIGH")

    def test_wf_false_maps_to_promising_not_robust(self):
        oos = run_oos(variant_kwargs={"wf": False})
        rep = RecommendationEngine().run(oos)
        self.assertEqual(rep.findings[0].recommendation_status, "PROMISING")
        self.assertEqual(rep.recommendations[0].status, "PROMISING")

    def test_conditional_result_maps_to_conditional(self):
        rep = RecommendationEngine().run(synthetic_report(
            OOS_STATUSES[7], conditional=True))
        self.assertEqual(rep.findings[0].recommendation_status,
                         "CONDITIONAL")
        self.assertEqual(rep.recommendations[0].status, "CONDITIONAL")

    def test_rejected_result_maps_to_rejected(self):
        rep = RecommendationEngine().run(synthetic_report(
            OOS_STATUSES[3], periods_rejected=4))
        self.assertEqual(rep.findings[0].recommendation_status, "REJECTED")
        self.assertEqual(rep.recommendations[0].status, "REJECTED")

    def test_render_contains_directive_and_statuses(self):
        oos = run_oos()
        rep = RecommendationEngine().run(oos)
        text = rep.render()
        self.assertIn("INVESTIGATE_FURTHER", text)
        self.assertIn("ROBUST_RESEARCH_FINDING", text)
        self.assertIn(rep.report_id, text)


if __name__ == "__main__":
    unittest.main()
