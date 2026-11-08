from dataclasses import replace
from core.governance.production_hardening_stages68_71 import (
    AncestryReconciliation, FindingRemediation, VenueEconomicsEvidence,
    TestEvidenceProvenance, evaluate_ancestry_reconciliation,
    evaluate_finding_remediation, evaluate_venue_economics, evaluate_test_evidence,
)
C="a"*40
D="b"*64

def ancestry():
    return AncestryReconciliation(C,"b42e8181406091bf06af18e312508a93924dcc37",
        "ancestry.txt","independent-review.txt","2026-11-09T12:00:00Z",True,True)

def findings():
    return FindingRemediation(C,"findings.csv","remediation.pdf","independent-review.txt",
        "2026-11-09T12:00:00Z",0,0,0,14,True,True,True)

def economics():
    return VenueEconomicsEvidence(C,D,"prereg.json","fees.csv","slippage.md","latency.md",
        "venues.csv","oos.pdf","review.md","2026-11-09T12:00:00Z",3,3,500,0,True,True)

def tests():
    return TestEvidenceProvenance(C,"workflow/123","pytest -q","c"*64,"results.xml",
        "review.md","2026-11-09T12:00:00Z",12,0,0,12,True,True)

def test_complete_assessments_remain_unverified_and_never_arm():
    results=[evaluate_ancestry_reconciliation(ancestry()),evaluate_finding_remediation(findings()),
        evaluate_venue_economics(economics()),evaluate_test_evidence(tests())]
    assert [x.stage for x in results]==[68,69,70,71]
    assert all(x.status.endswith("UNVERIFIED") for x in results)
    assert all(x.live_arming_permitted is False for x in results)

def test_missing_pinned_ancestor_is_a_hard_hold():
    x=evaluate_ancestry_reconciliation(replace(ancestry(),required_ancestor_reachable=False))
    assert x.status=="PINNED_ANCESTRY_HOLD"
    assert any("cannot be bypassed" in reason for reason in x.reasons)

def test_open_or_expired_findings_hold():
    x=evaluate_finding_remediation(replace(findings(),open_p0=1,expired_actions=2))
    assert x.status=="FINDING_REMEDIATION_HOLD"
    assert len(x.reasons)>=2

def test_incomplete_venue_cost_coverage_holds():
    x=evaluate_venue_economics(replace(economics(),venues_tested=2,missing_cost_components=1))
    assert x.status=="VENUE_ECONOMICS_HOLD"
    assert len(x.reasons)>=2

def test_test_provenance_rejects_failed_skipped_and_unreconciled_counts():
    x=evaluate_test_evidence(replace(tests(),tests_failed=1,tests_skipped=1,tests_collected=12))
    assert x.status=="TEST_EVIDENCE_HOLD"
    assert len(x.reasons)>=3
