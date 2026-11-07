"""
====================================================================

QuantEngine

Phase 9O -- Research UX: Recommendation Readback tests

Proves the deterministic, research-only UX layer over the frozen 9N
RecommendationReport. For every recommendation it states WHY it exists,
what evidence supports it, what failed, what remains uncertain, and
exactly why it is still research-only -- consuming ONLY the frozen 9N
report (never re-running OOS / conditional ML / regime).

The central boundary under test:

   VALIDATED_RESEARCH_FINDING  (allowed -- a research verdict)
   TRADABLE_STRATEGY           (impossible -- never produced here)

   * RESEARCH_VERDICTS has NO tradable member;
   * ReadbackEntry / ReadbackReport refuse a tradable verdict;
   * is_tradable is a property permanently False;
   * production_status is always RESEARCH_ONLY;
   * emission_check() verifies NEVER_EMITTED tokens are absent from the
     ACTUAL serialized body.

Also proves: total 9N status -> 9O verdict mapping, 1:1 recommendation ->
ReadbackEntry mapping, deterministic ids / serialization, input-order
independence, immutability, closed uncertainty + negative-evidence
vocabularies, and full production isolation.

Uses ONLY the real 9A-9N machinery (frozen 9N report produced by the
real 9M engine + 9N engine). Stdlib only; offline; deterministic.
====================================================================
"""

import json
import os
import unittest
from dataclasses import FrozenInstanceError

from core.research.recommendation import (
    RECOMMENDATION_STATUSES as R9N,
    RecommendationEngine,
)
from core.research.readback import (
    NEVER_EMITTED,
    EXPLANATION_ASPECTS,
    NEGATIVE_EVIDENCE_ROSTER,
    PRODUCTION_STATUS,
    RESEARCH_VERDICTS,
    UNCERTAINTY_ROSTER,
    ReadbackEntry,
    ReadbackReport,
    build_readback,
    explain_entry,
    explain_report,
    verdict_for_9n_status,
)
from tests.test_researcher_9n import run_oos, synthetic_report


def n_report(variant_kwargs=None, oos_mix=None):
    """Produce a real frozen 9N report (robust by default)."""
    return RecommendationEngine().run(run_oos(variant_kwargs))


def n_synthetic(status, **kw):
    from core.research.oos import OOS_STATUSES
    return RecommendationEngine().run(
        synthetic_report(status, **{**kw}))


# ------------------------------------------------------------------
# protocol surface
# ------------------------------------------------------------------

class TestProtocolSurface(unittest.TestCase):
    def test_closed_verdict_vocabulary(self):
        self.assertEqual(RESEARCH_VERDICTS,
                         ("SEVEN_E_BLOCKED", "NO_EVIDENCE", "INCONCLUSIVE",
                          "REJECTED", "REQUIRES_MORE_OOS", "CONDITIONAL",
                          "PROMISING", "VALIDATED_RESEARCH_FINDING"))

    def test_no_tradable_in_vocabulary(self):
        for v in RESEARCH_VERDICTS:
            self.assertNotIn("TRADABLE", v)
        self.assertNotIn("TRADABLE_STRATEGY", RESEARCH_VERDICTS)

    def test_production_status_research_only(self):
        self.assertEqual(PRODUCTION_STATUS, "RESEARCH_ONLY")

    def test_never_emitted_tokens_include_tradable(self):
        self.assertIn("TRADABLE_STRATEGY", NEVER_EMITTED)

    def test_aspects_closed(self):
        for a in ("status", "oos_evidence", "regime_evidence",
                  "negative_evidence", "limitations", "uncertainty",
                  "production_status", "supporting_metrics"):
            self.assertIn(a, EXPLANATION_ASPECTS)

    def test_uncertainty_roster_closed_unique(self):
        self.assertEqual(len(set(UNCERTAINTY_ROSTER)),
                         len(UNCERTAINTY_ROSTER))

    def test_entry_rejects_tradable_verdict(self):
        with self.assertRaises(ValueError):
            ReadbackEntry(research_verdict="TRADABLE_STRATEGY")

    def test_entry_rejects_bad_production_status(self):
        with self.assertRaises(ValueError):
            ReadbackEntry(production_status="TRADABLE")

    def test_entry_unknown_uncertainty_rejected(self):
        with self.assertRaises(ValueError):
            ReadbackEntry(uncertainty=("BOGUS_TAG",))

    def test_report_rejects_other_production_status(self):
        with self.assertRaises(ValueError):
            ReadbackReport(production_status="TRADABLE")


# ------------------------------------------------------------------
# total 9N -> 9O verdict mapping
# ------------------------------------------------------------------

class TestVerdictMapping(unittest.TestCase):
    def test_total_over_full_9n_vocabulary(self):
        self.assertEqual(len(set(R9N)), 8)
        for status in R9N:
            v = verdict_for_9n_status(status)
            self.assertIn(v, RESEARCH_VERDICTS)

    def test_top_tier_is_validated_not_tradable(self):
        self.assertEqual(
            verdict_for_9n_status("ROBUST_RESEARCH_FINDING"),
            "VALIDATED_RESEARCH_FINDING")
        # the strongest possible statement is research-only, not a trade
        self.assertNotEqual(
            verdict_for_9n_status("ROBUST_RESEARCH_FINDING"),
            "TRADABLE_STRATEGY")

    def test_seven_e_maps_to_seven_e_blocked(self):
        self.assertEqual(verdict_for_9n_status("7E_BLOCKED"),
                         "SEVEN_E_BLOCKED")

    def test_low_tiers_map_faithfully(self):
        self.assertEqual(verdict_for_9n_status("NO_EVIDENCE"),
                         "NO_EVIDENCE")
        self.assertEqual(verdict_for_9n_status("INCONCLUSIVE"),
                         "INCONCLUSIVE")
        self.assertEqual(verdict_for_9n_status("REJECTED"), "REJECTED")
        self.assertEqual(verdict_for_9n_status("REQUIRES_MORE_OOS"),
                         "REQUIRES_MORE_OOS")
        self.assertEqual(verdict_for_9n_status("CONDITIONAL"),
                         "CONDITIONAL")
        self.assertEqual(verdict_for_9n_status("PROMISING"), "PROMISING")

    def test_unknown_status_raises(self):
        with self.assertRaises(ValueError):
            verdict_for_9n_status("NOT_A_STATUS")

    def test_mapping_is_injective_1to1(self):
        out = [verdict_for_9n_status(s) for s in R9N]
        self.assertEqual(len(set(out)), len(out))


# ------------------------------------------------------------------
# explanation engine
# ------------------------------------------------------------------

class TestExplanationEngine(unittest.TestCase):
    def test_robust_explains_validated_research_finding(self):
        rep = n_report()
        o = explain_report(rep)
        e = o.entries[0]
        self.assertEqual(e.research_verdict,
                         "VALIDATED_RESEARCH_FINDING")
        self.assertEqual(e.evidence_status, "ROBUST_RESEARCH_FINDING")

    def test_one_to_one_entries(self):
        rep = n_report()
        o = explain_report(rep)
        self.assertEqual(len(o.entries), len(rep.recommendations))

    def test_entry_has_all_core_aspects(self):
        rep = n_report()
        e = explain_report(rep).entries[0]
        for aspect in ("status", "candidate", "oos_evidence",
                       "supporting_metrics"):
            self.assertIn(aspect, e.aspects)
        self.assertEqual(e.production_status, "RESEARCH_ONLY")
        self.assertIs(e.is_tradable, False)

    def test_oos_evidence_present_for_robust(self):
        rep = n_report()
        e = explain_report(rep).entries[0]
        oos = {x["key"]: x["label"] for x in
               e.aspects.get("oos_evidence", ())}
        self.assertEqual(oos.get("survived"), "6 OF 6")
        self.assertEqual(oos.get("familywise_passed"), "True")
        self.assertEqual(oos.get("walk_forward_passed"), "True")
        self.assertEqual(oos.get("robustness"), "HIGH")

    def test_supporting_metrics_from_frozen_report(self):
        rep = n_report()
        e = explain_report(rep).entries[0]
        keys = {x["key"] for x in
                e.aspects.get("supporting_metrics", ())}
        self.assertIn("survival_ratio", keys)
        self.assertIn("periods_survived", keys)

    def test_claim_clean_no_status_prefix(self):
        rep = n_report()
        e = explain_report(rep).entries[0]
        self.assertTrue(e.claim)
        self.assertNotIn("ROBUST_RESEARCH_FINDING: ", e.claim)
        self.assertNotIn("VALIDATED_RESEARCH_FINDING: ", e.claim)

    def test_rationale_deterministic(self):
        a = explain_report(n_report()).entries[0].rationale
        b = explain_report(n_report()).entries[0].rationale
        self.assertEqual(a, b)

    def test_seven_e_blocked_negative(self):
        rep = n_synthetic("7E_BLOCKED", seven_e=True)
        e = explain_report(rep).entries[0]
        self.assertEqual(e.research_verdict, "SEVEN_E_BLOCKED")
        self.assertIn("REPEATED_REJECTION", e.uncertainty)
        keys = {x["key"] for x in e.aspects.get("negative_evidence", ())}
        self.assertIn("verdict", keys)

    def test_rejected_keeps_adverse_evidence(self):
        from core.research.oos import OOS_STATUSES
        rep = RecommendationEngine().run(
            synthetic_report(OOS_STATUSES[3], periods_rejected=4))
        e = explain_report(rep).entries[0]
        self.assertEqual(e.research_verdict, "REJECTED")
        keys = {x["key"] for x in e.aspects.get("negative_evidence", ())}
        self.assertIn("rejected_periods", keys)

    def test_conditional_scopes_and_uncertainty(self):
        from core.research.oos import OOS_STATUSES
        rep = RecommendationEngine().run(
            synthetic_report(OOS_STATUSES[7], conditional=True))
        e = explain_report(rep).entries[0]
        self.assertEqual(e.research_verdict, "CONDITIONAL")
        self.assertIn("CONDITIONAL_SCOPE", e.uncertainty)
        regime = {x["key"]: x["label"] for x in
                  e.aspects.get("regime_evidence", ())}
        self.assertEqual(regime.get("scoped"), "trend_vs_range=TREND")
        self.assertEqual(regime.get("conditional"), "true")

    def test_uncertainty_tags_are_closed(self):
        rep = n_report()
        o = explain_report(rep)
        for e in o.entries:
            for u in e.uncertainty:
                self.assertIn(u, UNCERTAINTY_ROSTER)

    def test_negative_tags_are_closed(self):
        rep = n_synthetic("7E_BLOCKED", seven_e=True)
        report = explain_report(rep)
        for e in report.entries:
            for row in e.aspects.get("negative_evidence", ()):
                # key must be from the closed roster or a known meta key
                self.assertIn(row["key"],
                              NEGATIVE_EVIDENCE_ROSTER +
                              ("rejected_periods", "verdict",
                               "limitation", "familywise", "seven_e"))

    def test_consumes_only_frozen_report_no_resim(self):
        # explain_report takes a report object and never touches data
        rep = n_report()
        before_render = rep.to_json()
        _ = explain_report(rep)
        self.assertEqual(rep.to_json(), before_render)


# ------------------------------------------------------------------
# report contract: determinism + immutability
# ------------------------------------------------------------------

class TestReportContract(unittest.TestCase):
    def test_report_id_deterministic(self):
        a = explain_report(n_report())
        b = explain_report(n_report())
        self.assertEqual(a.report_id, b.report_id)
        self.assertTrue(a.report_id.startswith("O"))

    def test_full_equality_on_repeat(self):
        a = explain_report(n_report())
        b = explain_report(n_report())
        self.assertEqual(a, b)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_deterministic_serialization(self):
        o = explain_report(n_report())
        self.assertEqual(json.loads(o.to_json()), json.loads(o.to_json()))

    def test_input_order_independent(self):
        e1 = ReadbackEntry(research_verdict="PROMISING", title="a")
        e2 = ReadbackEntry(research_verdict="INCONCLUSIVE", title="b")
        a = build_readback(entries=[e1, e2])
        b = build_readback(entries=[e2, e1])
        self.assertEqual(a.report_id, b.report_id)
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_report_frozen(self):
        o = explain_report(n_report())
        with self.assertRaises(FrozenInstanceError):
            o.report_id = "tampered"

    def test_entry_frozen(self):
        o = explain_report(n_report())
        with self.assertRaises(FrozenInstanceError):
            o.entries[0].research_verdict = "REJECTED"

    def test_production_status_permanently_research_only(self):
        o = explain_report(n_report())
        self.assertEqual(o.production_status, "RESEARCH_ONLY")
        with self.assertRaises(FrozenInstanceError):
            o.production_status = "TRADABLE"

    def test_is_tradable_property_false(self):
        o = explain_report(n_report())
        self.assertIs(o.is_tradable, False)
        self.assertIs(o.entries[0].is_tradable, False)

    def test_no_uuid_random_datetime(self):
        pkg = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "core", "research",
            "readback"))
        for root, _, files in os.walk(pkg):
            for fn in files:
                if fn.endswith(".py"):
                    txt = open(os.path.join(root, fn),
                               encoding="utf-8").read()
                    for fword in ("random", "uuid", "datetime",
                                  "scipy", "sklearn"):
                        self.assertNotIn(fword, txt,
                                         "%s contains %s" % (fn, fword))

    def test_empty_report_honest(self):
        o = build_readback(entries=[])
        self.assertEqual(o.entries, ())
        self.assertEqual(o.research_verdicts, ())
        self.assertTrue(o.emission_check()["clean"])

    def test_invalid_verdict_rejected_by_build(self):
        with self.assertRaises(ValueError):
            ReadbackEntry(research_verdict="BOGUS")
        with self.assertRaises(ValueError):
            build_readback(entries=[ReadbackEntry(
                research_verdict="TRADABLE_STRATEGY")])


# ------------------------------------------------------------------
# boundary hardening (the core of 9O)
# ------------------------------------------------------------------

class TestBoundary(unittest.TestCase):
    def test_strongest_verdict_is_not_tradable(self):
        o = explain_report(n_report())
        e = o.entries[0]
        self.assertEqual(e.research_verdict,
                         "VALIDATED_RESEARCH_FINDING")
        # even the strongest statement never yields a tradable flag
        self.assertIs(e.is_tradable, False)
        self.assertIs(o.is_tradable, False)

    def test_emission_check_clean(self):
        o = explain_report(n_report())
        ec = o.emission_check()
        self.assertTrue(ec["clean"])
        self.assertIs(ec["tradable_requested"], False)
        self.assertIs(ec["is_tradable"], False)
        self.assertEqual(ec["production_status"], "RESEARCH_ONLY")
        self.assertTrue(ec["tokens_absent"])

    def test_tradable_tokens_absent_from_serialized_body(self):
        o = explain_report(n_report())
        body = json.dumps(o.to_dict(), sort_keys=True, default=str)
        for tok in NEVER_EMITTED:
            self.assertNotIn(tok, body)

    def test_no_production_imports(self):
        pkg = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "core", "research",
            "readback"))
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
                                             % (fn, bad))


# ------------------------------------------------------------------
# canonical e2e locks
# ------------------------------------------------------------------

class TestE2E(unittest.TestCase):
    def test_canonical_report_id_stable(self):
        o = explain_report(n_report())
        self.assertEqual(o.report_id, "O881c3a9a39")

    def test_source_is_the_frozen_9n_report(self):
        nine_n = n_report()
        o = explain_report(nine_n)
        self.assertEqual(o.source_report_id, nine_n.report_id)

    def test_validated_boundary_render(self):
        o = explain_report(n_report())
        text = o.render()
        self.assertIn("VALIDATED_RESEARCH_FINDING", text)
        self.assertIn("RESEARCH_ONLY", text)
        self.assertIn("tradable: NO", text)

    def test_seven_e_render(self):
        from core.research.oos import OOS_STATUSES
        rep = RecommendationEngine().run(
            synthetic_report(OOS_STATUSES[0], seven_e=True))
        o = explain_report(rep)
        self.assertIn("SEVEN_E_BLOCKED", o.render())


if __name__ == "__main__":
    unittest.main()
